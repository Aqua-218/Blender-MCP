from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.serialization import json_loads
from mcp_server.tools.advanced_helpers import list_entity_specs, save_metadata_entity
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.utils import new_id

SELECTION_SET_ENTITY_TYPE = "selection_set"


class SelectionSetTargetsRequest(CommonToolRequest):
    project_id: str
    name: str
    description: str | None = None
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    spatial_range: dict[str, list[float]] | None = None


class SelectionSetReferenceRequest(CommonToolRequest):
    project_id: str
    selection_set_id: str | None = None
    name: str | None = None


class SelectionSetRenameRequest(SelectionSetReferenceRequest):
    new_name: str


class ListSelectionSetsRequest(CommonToolRequest):
    project_id: str


def _failed(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


def _selection_sets(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, SELECTION_SET_ENTITY_TYPE)


def _find_selection_set(
    context,  # type: ignore[no-untyped-def]
    project_id: str,
    *,
    selection_set_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if selection_set_id is not None:
        record = context.entities.get(selection_set_id)
        if record is None or record.project_id != project_id or record.entity_type != SELECTION_SET_ENTITY_TYPE:
            return None
        return json_loads(record.spec_json)
    if name is None:
        return None
    lowered = name.lower()
    for selection_set in _selection_sets(context, project_id):
        if str(selection_set.get("name", "")).lower() == lowered:
            return selection_set
    return None


async def _resolve_and_validate_target_ids(
    context,  # type: ignore[no-untyped-def]
    request: SelectionSetTargetsRequest,
    tool_name: str,
) -> list[str] | CommonToolResult:
    try:
        target_ids = await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
            spatial_range=request.spatial_range,
        )
    except ValueError as exc:
        return _failed(request.request_id, tool_name, "target_not_found", str(exc))
    listed = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    existing_ids = {item["object_id"] for item in listed.get("objects", [])}
    missing = [target_id for target_id in target_ids if target_id not in existing_ids]
    if missing:
        return _failed(
            request.request_id,
            tool_name,
            "target_not_found",
            f"Selection set target(s) were not found: {', '.join(missing)}",
        )
    return target_ids


def _save_selection_set(
    context,  # type: ignore[no-untyped-def]
    project_id: str,
    selection_set: dict[str, Any],
) -> dict[str, Any]:
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(selection_set["selection_set_id"]),
        entity_type=SELECTION_SET_ENTITY_TYPE,
        name=str(selection_set["name"]),
        spec=selection_set,
    )


def _require_selection_set(
    context,  # type: ignore[no-untyped-def]
    request: SelectionSetReferenceRequest,
    tool_name: str,
) -> dict[str, Any] | CommonToolResult:
    selection_set = _find_selection_set(
        context,
        request.project_id,
        selection_set_id=request.selection_set_id,
        name=request.name,
    )
    if selection_set is None:
        selector = request.selection_set_id or request.name or "<missing selector>"
        return _failed(
            request.request_id,
            tool_name,
            "target_not_found",
            f"Selection set '{selector}' was not found.",
        )
    return selection_set


async def save_selection_set(context, request: SelectionSetTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_and_validate_target_ids(context, request, "save_selection_set")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    existing = _find_selection_set(context, project.project_id, name=request.name)
    selection_set = {
        "selection_set_id": existing.get("selection_set_id") if existing else new_id("selset"),
        "project_id": project.project_id,
        "name": request.name,
        "description": request.description or (existing or {}).get("description"),
        "target_ids": target_ids,
        "count": len(target_ids),
    }
    _save_selection_set(context, project.project_id, selection_set)
    return success_result(
        request_id=request.request_id,
        tool_name="save_selection_set",
        summary=f"Saved selection set '{request.name}' with {len(target_ids)} objects.",
        project_id=project.project_id,
        selection_set_id=selection_set["selection_set_id"],
        selection_set=selection_set,
    )


async def list_selection_sets(context, request: ListSelectionSetsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    selection_sets = _selection_sets(context, request.project_id)
    return success_result(
        request_id=request.request_id,
        tool_name="list_selection_sets",
        summary=f"Listed {len(selection_sets)} selection sets.",
        project_id=request.project_id,
        selection_sets=selection_sets,
        count=len(selection_sets),
    )


async def select_selection_set(context, request: SelectionSetReferenceRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    selection_set = _require_selection_set(context, request, "select_selection_set")
    if isinstance(selection_set, CommonToolResult):
        return selection_set
    target_ids = list(selection_set.get("target_ids", []))
    if not target_ids:
        return _failed(request.request_id, "select_selection_set", "validation_error", "Selection set is empty.")
    try:
        result = await context.bridge.invoke(
            "select_objects",
            {"project_id": request.project_id, "target_ids": target_ids},
        )
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return _failed(request.request_id, "select_selection_set", exc.code, exc.message)
        raise
    return success_result(
        request_id=request.request_id,
        tool_name="select_selection_set",
        summary=f"Selected selection set '{selection_set['name']}'.",
        project_id=request.project_id,
        modified_object_ids=result.get("selected_ids", []),
        selected_ids=result.get("selected_ids", []),
        selection_set=selection_set,
        objects=result.get("objects", []),
    )


async def update_selection_set(context, request: SelectionSetTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    selection_set = _find_selection_set(context, project.project_id, name=request.name)
    if selection_set is None:
        return _failed(
            request.request_id,
            "update_selection_set",
            "target_not_found",
            f"Selection set '{request.name}' was not found.",
        )
    target_ids = await _resolve_and_validate_target_ids(context, request, "update_selection_set")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    selection_set["target_ids"] = target_ids
    selection_set["count"] = len(target_ids)
    if request.description is not None:
        selection_set["description"] = request.description
    _save_selection_set(context, project.project_id, selection_set)
    return success_result(
        request_id=request.request_id,
        tool_name="update_selection_set",
        summary=f"Updated selection set '{request.name}'.",
        project_id=project.project_id,
        selection_set_id=selection_set["selection_set_id"],
        selection_set=selection_set,
    )


async def add_to_selection_set(context, request: SelectionSetTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    selection_set = _find_selection_set(context, project.project_id, name=request.name)
    if selection_set is None:
        return _failed(
            request.request_id,
            "add_to_selection_set",
            "target_not_found",
            f"Selection set '{request.name}' was not found.",
        )
    target_ids = await _resolve_and_validate_target_ids(context, request, "add_to_selection_set")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    selection_set["target_ids"] = list(dict.fromkeys([*selection_set.get("target_ids", []), *target_ids]))
    selection_set["count"] = len(selection_set["target_ids"])
    _save_selection_set(context, project.project_id, selection_set)
    return success_result(
        request_id=request.request_id,
        tool_name="add_to_selection_set",
        summary=f"Added {len(target_ids)} objects to selection set '{request.name}'.",
        project_id=project.project_id,
        selection_set_id=selection_set["selection_set_id"],
        selection_set=selection_set,
    )


async def remove_from_selection_set(context, request: SelectionSetTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    selection_set = _find_selection_set(context, project.project_id, name=request.name)
    if selection_set is None:
        return _failed(
            request.request_id,
            "remove_from_selection_set",
            "target_not_found",
            f"Selection set '{request.name}' was not found.",
        )
    target_ids = await _resolve_and_validate_target_ids(context, request, "remove_from_selection_set")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    removed = set(target_ids)
    selection_set["target_ids"] = [target_id for target_id in selection_set.get("target_ids", []) if target_id not in removed]
    selection_set["count"] = len(selection_set["target_ids"])
    _save_selection_set(context, project.project_id, selection_set)
    return success_result(
        request_id=request.request_id,
        tool_name="remove_from_selection_set",
        summary=f"Removed {len(target_ids)} objects from selection set '{request.name}'.",
        project_id=project.project_id,
        selection_set_id=selection_set["selection_set_id"],
        selection_set=selection_set,
    )


async def rename_selection_set(context, request: SelectionSetRenameRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    selection_set = _require_selection_set(context, request, "rename_selection_set")
    if isinstance(selection_set, CommonToolResult):
        return selection_set
    duplicate = _find_selection_set(context, project.project_id, name=request.new_name)
    if duplicate is not None and duplicate.get("selection_set_id") != selection_set.get("selection_set_id"):
        return _failed(
            request.request_id,
            "rename_selection_set",
            "validation_error",
            f"Selection set '{request.new_name}' already exists.",
        )
    old_name = str(selection_set["name"])
    selection_set["name"] = request.new_name
    _save_selection_set(context, project.project_id, selection_set)
    return success_result(
        request_id=request.request_id,
        tool_name="rename_selection_set",
        summary=f"Renamed selection set '{old_name}' to '{request.new_name}'.",
        project_id=project.project_id,
        selection_set_id=selection_set["selection_set_id"],
        old_name=old_name,
        selection_set=selection_set,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("save_selection_set", "Save or replace a named selection set from resolved object targets.", SelectionSetTargetsRequest, save_selection_set, False),
        ("list_selection_sets", "List saved selection sets and their object membership.", ListSelectionSetsRequest, list_selection_sets, True),
        ("select_selection_set", "Select the objects stored in a saved selection set.", SelectionSetReferenceRequest, select_selection_set, False),
        ("update_selection_set", "Replace a saved selection set's object membership.", SelectionSetTargetsRequest, update_selection_set, False),
        ("add_to_selection_set", "Add resolved objects to an existing selection set.", SelectionSetTargetsRequest, add_to_selection_set, False),
        ("remove_from_selection_set", "Remove resolved objects from an existing selection set without deleting scene objects.", SelectionSetTargetsRequest, remove_from_selection_set, False),
        ("rename_selection_set", "Rename a saved selection set while preserving membership.", SelectionSetRenameRequest, rename_selection_set, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="selection_sets",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )