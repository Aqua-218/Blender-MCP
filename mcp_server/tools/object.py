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
from mcp_server.tools.helpers import require_project, resolve_target_ids, sync_entities


class ObjectQueryRequest(CommonToolRequest):
    project_id: str


class FindObjectsRequest(CommonToolRequest):
    project_id: str
    names: list[str] = Field(default_factory=list)
    object_type: str | None = None
    tag: str | None = None
    collection_name: str | None = None
    material_id: str | None = None
    spatial_range: dict[str, list[float]] | None = None


class TargetedObjectRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    spatial_range: dict[str, list[float]] | None = None


class RenameObjectRequest(CommonToolRequest):
    project_id: str
    target_id: str
    new_name: str


class TransformObjectRequest(CommonToolRequest):
    project_id: str
    target_id: str
    location: list[float] | None = None
    rotation: list[float] | None = None
    scale: list[float] | None = None


class VisibilityRequest(TargetedObjectRequest):
    visible: bool


class AssignCollectionRequest(TargetedObjectRequest):
    collection_name: str


class TagObjectRequest(TargetedObjectRequest):
    tags: list[str]


class DeleteObjectsRequest(TargetedObjectRequest):
    destructive_confirmation: bool = False


def _object_failed_result(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


async def _resolve_object_target_ids(
    context,  # type: ignore[no-untyped-def]
    request: TargetedObjectRequest,
    tool_name: str,
) -> list[str] | CommonToolResult:
    try:
        return await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
            spatial_range=request.spatial_range,
        )
    except ValueError as exc:
        return _object_failed_result(request.request_id, tool_name, "target_not_found", str(exc))


async def _invoke_object_mutation(
    context,  # type: ignore[no-untyped-def]
    command: str,
    payload: dict[str, Any],
    *,
    request_id: str,
    tool_name: str | None = None,
) -> dict[str, Any] | CommonToolResult:
    try:
        return await context.bridge.invoke(command, payload)
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return _object_failed_result(request_id, tool_name or command, exc.code, exc.message)
        raise


async def list_objects(context, request: ObjectQueryRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    return success_result(
        request_id=request.request_id,
        tool_name="list_objects",
        summary=f"Listed {len(result['objects'])} objects.",
        project_id=request.project_id,
        objects=result["objects"],
    )


async def find_objects(context, request: FindObjectsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await context.bridge.invoke(
        "find_objects",
        request.model_dump(exclude_none=True),
        read_only=True,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="find_objects",
        summary=f"Found {len(result['objects'])} matching objects.",
        project_id=request.project_id,
        objects=result["objects"],
    )


async def select_objects(context, request: TargetedObjectRequest, tool_name: str = "select_objects"):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, tool_name)
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    if tool_name == "select_object" and len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="select_object requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await _invoke_object_mutation(
        context,
        "select_objects",
        {"project_id": request.project_id, "target_ids": target_ids},
        request_id=request.request_id,
        tool_name=tool_name,
    )
    if isinstance(result, CommonToolResult):
        return result
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Selected {len(result['selected_ids'])} objects.",
        project_id=request.project_id,
        modified_object_ids=result["selected_ids"],
        selected_ids=result["selected_ids"],
        objects=result["objects"],
    )


async def delete_objects(context, request: DeleteObjectsRequest, tool_name: str = "delete_objects"):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, tool_name)
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    if tool_name == "delete_object" and len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="delete_object requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await _invoke_object_mutation(
        context,
        "delete_objects",
        {"project_id": request.project_id, "target_ids": target_ids},
        request_id=request.request_id,
        tool_name=tool_name,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Deleted {len(result['deleted_object_ids'])} objects.",
        project_id=request.project_id,
        deleted_object_ids=result["deleted_object_ids"],
    )


async def duplicate_object(context, request: TargetedObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "duplicate_object")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="duplicate_object",
            summary="duplicate_object requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await _invoke_object_mutation(
        context,
        "duplicate_object",
        {"project_id": request.project_id, "target_ids": target_ids},
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["created_objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="duplicate_object",
        summary=f"Duplicated {len(result['created_object_ids'])} objects.",
        project_id=request.project_id,
        created_object_ids=result["created_object_ids"],
        objects=result["created_objects"],
    )


async def rename_object(context, request: RenameObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke_object_mutation(
        context,
        "rename_object",
        request.model_dump(),
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="rename_object",
        summary=f"Renamed object to {request.new_name}.",
        project_id=request.project_id,
        modified_object_ids=[request.target_id],
        object=result["object"],
    )


async def transform_object(context, request: TransformObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke_object_mutation(
        context,
        "transform_object",
        request.model_dump(exclude_none=True),
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="transform_object",
        summary=f"Transformed object {request.target_id}.",
        project_id=request.project_id,
        modified_object_ids=[request.target_id],
        object=result["object"],
    )


async def set_object_visibility(context, request: VisibilityRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "set_object_visibility")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    result = await _invoke_object_mutation(
        context,
        "set_object_visibility",
        {"project_id": request.project_id, "target_ids": target_ids, "visible": request.visible},
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="set_object_visibility",
        summary=f"Updated visibility for {len(target_ids)} objects.",
        project_id=request.project_id,
        modified_object_ids=target_ids,
        objects=result["objects"],
    )


async def assign_collection(context, request: AssignCollectionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "assign_collection")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    result = await _invoke_object_mutation(
        context,
        "assign_collection",
        {"project_id": request.project_id, "target_ids": target_ids, "collection_name": request.collection_name},
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="assign_collection",
        summary=f"Assigned {len(target_ids)} objects to {request.collection_name}.",
        project_id=request.project_id,
        modified_object_ids=target_ids,
        objects=result["objects"],
    )


async def tag_object(context, request: TagObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "tag_object")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    result = await _invoke_object_mutation(
        context,
        "tag_object",
        {"project_id": request.project_id, "target_ids": target_ids, "tags": request.tags},
        request_id=request.request_id,
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="tag_object",
        summary=f"Tagged {len(target_ids)} objects.",
        project_id=request.project_id,
        modified_object_ids=target_ids,
        objects=result["objects"],
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("list_objects", "List scene objects with stable identifiers and transforms.", ObjectQueryRequest, list_objects, True),
        ("find_objects", "Find scene objects deterministically by name, type, tag, collection, material, or range.", FindObjectsRequest, find_objects, True),
        ("select_objects", "Select multiple scene objects.", TargetedObjectRequest, select_objects, False),
        ("select_object", "Select a single scene object.", TargetedObjectRequest, lambda c, r: select_objects(c, r, "select_object"), False),
        ("delete_objects", "Delete multiple scene objects after policy checks.", DeleteObjectsRequest, delete_objects, False),
        ("delete_object", "Delete a single scene object after policy checks.", DeleteObjectsRequest, lambda c, r: delete_objects(c, r, "delete_object"), False),
        ("duplicate_object", "Duplicate one or more scene objects.", TargetedObjectRequest, duplicate_object, False),
        ("rename_object", "Rename a scene object.", RenameObjectRequest, rename_object, False),
        ("transform_object", "Update object transform.", TransformObjectRequest, transform_object, False),
        ("set_object_visibility", "Update object visibility state.", VisibilityRequest, set_object_visibility, False),
        ("assign_collection", "Assign objects to a collection.", AssignCollectionRequest, assign_collection, False),
        ("tag_object", "Attach management tags to objects.", TagObjectRequest, tag_object, False),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="object",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
