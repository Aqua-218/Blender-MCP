from __future__ import annotations

import fnmatch
import re
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
from mcp_server.tools.spatial import bounds_for_object, bounds_for_objects


class ObjectQueryRequest(CommonToolRequest):
    project_id: str


class SceneBoundsRequest(CommonToolRequest):
    project_id: str
    include_hidden: bool = True
    object_type: str | None = None


class FindObjectsRequest(CommonToolRequest):
    project_id: str
    names: list[str] = Field(default_factory=list)
    name_pattern: str | None = None
    name_regex: str | None = None
    name_prefix: str | None = None
    name_suffix: str | None = None
    object_type: str | None = None
    tag: str | None = None
    collection_name: str | None = None
    material_id: str | None = None
    spatial_range: dict[str, list[float]] | None = None
    visible: bool | None = None
    min_dimensions: list[float] | None = None
    max_dimensions: list[float] | None = None
    min_polycount: int | None = Field(default=None, ge=0)
    max_polycount: int | None = Field(default=None, ge=0)


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


def _bounds_payload(minimum: list[float], maximum: list[float]) -> dict[str, list[float]]:
    return {
        "min": minimum,
        "max": maximum,
        "center": [(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False)],
        "dimensions": [max(high - low, 0.0) for low, high in zip(minimum, maximum, strict=False)],
    }


def _triangle_count(item: dict[str, Any]) -> int:
    return sum(max(len(face), 3) - 2 for face in ((item.get("data", {}) or {}).get("faces", [])))


def _vector_in_range(value: list[float], minimum: list[float], maximum: list[float]) -> bool:
    return all(component >= lower and component <= upper for component, lower, upper in zip(value, minimum, maximum, strict=False))


def _matches_find_request(item: dict[str, Any], request: FindObjectsRequest, *, regex: re.Pattern[str] | None) -> bool:
    name = str(item.get("name", ""))
    if request.names and name.lower() not in {candidate.lower() for candidate in request.names}:
        return False
    if request.name_pattern and not fnmatch.fnmatchcase(name, request.name_pattern):
        return False
    if regex is not None and regex.search(name) is None:
        return False
    if request.name_prefix and not name.startswith(request.name_prefix):
        return False
    if request.name_suffix and not name.endswith(request.name_suffix):
        return False
    if request.object_type and str(item.get("type", "")).lower() != request.object_type.lower():
        return False
    if request.tag and request.tag not in item.get("tags", []):
        return False
    if request.collection_name and item.get("collection") != request.collection_name:
        return False
    if request.material_id and request.material_id not in item.get("material_ids", []):
        return False
    if request.visible is not None and bool(item.get("visible", True)) != request.visible:
        return False
    if request.spatial_range:
        minimum = request.spatial_range.get("min", [-1e9, -1e9, -1e9])
        maximum = request.spatial_range.get("max", [1e9, 1e9, 1e9])
        if not _vector_in_range(list(item.get("location", [0.0, 0.0, 0.0])), minimum, maximum):
            return False
    if request.min_dimensions is not None or request.max_dimensions is not None:
        minimum, maximum = bounds_for_object(item)
        dimensions = [max(high - low, 0.0) for low, high in zip(minimum, maximum, strict=False)]
        if request.min_dimensions is not None and any(component < lower for component, lower in zip(dimensions, request.min_dimensions, strict=False)):
            return False
        if request.max_dimensions is not None and any(component > upper for component, upper in zip(dimensions, request.max_dimensions, strict=False)):
            return False
    triangles = _triangle_count(item)
    if request.min_polycount is not None and triangles < request.min_polycount:
        return False
    return not (request.max_polycount is not None and triangles > request.max_polycount)


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
    try:
        regex = re.compile(request.name_regex) if request.name_regex else None
    except re.error as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="find_objects",
            summary="Invalid name_regex supplied.",
            errors=[f"validation_error: invalid name_regex: {exc}"],
        )
    listed = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    objects = [item for item in listed.get("objects", []) if _matches_find_request(item, request, regex=regex)]
    return success_result(
        request_id=request.request_id,
        tool_name="find_objects",
        summary=f"Found {len(objects)} matching objects.",
        project_id=request.project_id,
        objects=objects,
    )


async def get_scene_bounds(context, request: SceneBoundsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    objects = list(result.get("objects", []))
    if not request.include_hidden:
        objects = [item for item in objects if item.get("visible", True)]
    if request.object_type:
        object_type = request.object_type.upper()
        objects = [item for item in objects if str(item.get("type", "")).upper() == object_type]
    minimum, maximum = bounds_for_objects(objects)
    return success_result(
        request_id=request.request_id,
        tool_name="get_scene_bounds",
        summary=f"Computed bounds for {len(objects)} scene objects.",
        project_id=request.project_id,
        bounds=_bounds_payload(minimum, maximum),
        object_count=len(objects),
        coordinate_system={"up_axis": "Z", "forward_axis": "Y", "handedness": "right"},
    )


async def get_object_bounds(context, request: TargetedObjectRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "get_object_bounds")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="get_object_bounds",
            summary="get_object_bounds requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    objects = {item["object_id"]: item for item in result.get("objects", [])}
    target = objects.get(target_ids[0])
    if target is None:
        return _object_failed_result(request.request_id, "get_object_bounds", "target_not_found", f"Unknown object_id: {target_ids[0]}")
    minimum, maximum = bounds_for_object(target)
    return success_result(
        request_id=request.request_id,
        tool_name="get_object_bounds",
        summary=f"Computed bounds for {target.get('name', target_ids[0])}.",
        project_id=request.project_id,
        inspected_object_id=target_ids[0],
        bounds=_bounds_payload(minimum, maximum),
        coordinate_system={"up_axis": "Z", "forward_axis": "Y", "handedness": "right"},
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


async def preview_delete_objects(context, request: TargetedObjectRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_object_target_ids(context, request, "preview_delete_objects")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    listed = await context.bridge.invoke("list_objects", {"project_id": request.project_id}, read_only=True)
    objects_by_id = {item["object_id"]: item for item in listed.get("objects", [])}
    target_objects = [objects_by_id[target_id] for target_id in target_ids if target_id in objects_by_id]
    return success_result(
        request_id=request.request_id,
        tool_name="preview_delete_objects",
        summary=f"Dry-run delete would remove {len(target_objects)} objects.",
        project_id=request.project_id,
        dry_run=True,
        would_delete_object_ids=target_ids,
        affected_object_count=len(target_objects),
        objects=target_objects,
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
        ("get_scene_bounds", "Compute world-space bounds for the scene or a filtered object type.", SceneBoundsRequest, get_scene_bounds, True),
        ("get_object_bounds", "Compute world-space bounds for one resolved object.", TargetedObjectRequest, get_object_bounds, True),
        ("preview_delete_objects", "Dry-run object deletion and return the resolved targets without mutating the scene.", TargetedObjectRequest, preview_delete_objects, True),
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
