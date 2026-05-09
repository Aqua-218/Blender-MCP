from __future__ import annotations

from typing import Any

from pydantic import Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.helpers import require_project, sync_entities


class CollectionQueryRequest(CommonToolRequest):
    project_id: str


class CreateCollectionRequest(CommonToolRequest):
    project_id: str
    collection_name: str
    parent_collection_name: str = "Scene Collection"


class RenameCollectionRequest(CommonToolRequest):
    project_id: str
    collection_name: str
    new_collection_name: str


class DeleteCollectionRequest(CommonToolRequest):
    project_id: str
    collection_name: str
    force: bool = False


class CollectionObjectsRequest(CommonToolRequest):
    project_id: str
    collection_name: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)


class CollectionVisibilityRequest(CommonToolRequest):
    project_id: str
    collection_name: str
    visible: bool
    set_viewport: bool = True
    set_render: bool = True


def _failed_result(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


async def _invoke(
    context,  # type: ignore[no-untyped-def]
    command: str,
    payload: dict[str, Any],
    *,
    request_id: str,
    tool_name: str,
    read_only: bool = False,
) -> dict[str, Any] | CommonToolResult:
    try:
        return await context.bridge.invoke(command, payload, read_only=read_only)
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return _failed_result(request_id, tool_name, exc.code, exc.message)
        raise


def _mark_dirty_and_sync_objects(context, project, result: dict[str, Any]) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    objects = list(result.get("objects", []))
    if objects:
        sync_entities(context, project.project_id, objects)
    return objects


async def list_collections(context, request: CollectionQueryRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await _invoke(
        context,
        "list_collections",
        {"project_id": request.project_id},
        request_id=request.request_id,
        tool_name="list_collections",
        read_only=True,
    )
    if isinstance(result, CommonToolResult):
        return result
    collections = result.get("collections", [])
    return success_result(
        request_id=request.request_id,
        tool_name="list_collections",
        summary=f"Listed {len(collections)} collections.",
        project_id=request.project_id,
        collections=collections,
        count=len(collections),
    )


async def create_collection(context, request: CreateCollectionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "create_collection",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="create_collection",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="create_collection",
        summary=f"Created collection '{request.collection_name}' under '{request.parent_collection_name}'.",
        project_id=project.project_id,
        collection=result["collection"],
    )


async def rename_collection(context, request: RenameCollectionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "rename_collection",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="rename_collection",
    )
    if isinstance(result, CommonToolResult):
        return result
    objects = _mark_dirty_and_sync_objects(context, project, result)
    return success_result(
        request_id=request.request_id,
        tool_name="rename_collection",
        summary=f"Renamed collection '{request.collection_name}' to '{request.new_collection_name}'.",
        project_id=project.project_id,
        modified_object_ids=result.get("modified_object_ids", []),
        old_collection_name=request.collection_name,
        new_collection_name=request.new_collection_name,
        collection=result["collection"],
        objects=objects,
    )


async def delete_collection(context, request: DeleteCollectionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "delete_collection",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="delete_collection",
    )
    if isinstance(result, CommonToolResult):
        return result
    objects = _mark_dirty_and_sync_objects(context, project, result)
    unlinked_object_ids = result.get("unlinked_object_ids", [])
    summary = f"Deleted empty collection '{request.collection_name}'."
    if request.force:
        summary = (
            f"Deleted collection '{request.collection_name}' and removed collection membership for "
            f"{len(unlinked_object_ids)} objects without deleting scene objects."
        )
    return success_result(
        request_id=request.request_id,
        tool_name="delete_collection",
        summary=summary,
        project_id=project.project_id,
        modified_object_ids=result.get("modified_object_ids", []),
        deleted_collection_name=request.collection_name,
        unlinked_object_ids=unlinked_object_ids,
        rehomed_child_collection_names=result.get("rehomed_child_collection_names", []),
        relinked_collection_name=result.get("relinked_collection_name"),
        objects=objects,
    )


async def link_objects_to_collection(context, request: CollectionObjectsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "link_objects_to_collection",
        request.model_dump(exclude_none=True),
        request_id=request.request_id,
        tool_name="link_objects_to_collection",
    )
    if isinstance(result, CommonToolResult):
        return result
    objects = _mark_dirty_and_sync_objects(context, project, result)
    modified_object_ids = result.get("modified_object_ids", [])
    return success_result(
        request_id=request.request_id,
        tool_name="link_objects_to_collection",
        summary=f"Linked {len(modified_object_ids)} objects to collection '{request.collection_name}'.",
        project_id=project.project_id,
        modified_object_ids=modified_object_ids,
        collection=result["collection"],
        objects=objects,
    )


async def unlink_objects_from_collection(context, request: CollectionObjectsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "unlink_objects_from_collection",
        request.model_dump(exclude_none=True),
        request_id=request.request_id,
        tool_name="unlink_objects_from_collection",
    )
    if isinstance(result, CommonToolResult):
        return result
    objects = _mark_dirty_and_sync_objects(context, project, result)
    modified_object_ids = result.get("modified_object_ids", [])
    return success_result(
        request_id=request.request_id,
        tool_name="unlink_objects_from_collection",
        summary=f"Unlinked {len(modified_object_ids)} objects from collection '{request.collection_name}'.",
        project_id=project.project_id,
        modified_object_ids=modified_object_ids,
        collection=result["collection"],
        relinked_collection_name=result.get("relinked_collection_name"),
        objects=objects,
    )


async def set_collection_visibility(context, request: CollectionVisibilityRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "set_collection_visibility",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="set_collection_visibility",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="set_collection_visibility",
        summary=f"Updated visibility for collection '{request.collection_name}'.",
        project_id=project.project_id,
        collection=result["collection"],
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for name, description, handler, model, read_only in (
        (
            "list_collections",
            "List collections, hierarchy, object membership, and visibility state.",
            list_collections,
            CollectionQueryRequest,
            True,
        ),
        (
            "create_collection",
            "Create a collection under an existing parent collection.",
            create_collection,
            CreateCollectionRequest,
            False,
        ),
        (
            "rename_collection",
            "Rename a collection while preserving object membership.",
            rename_collection,
            RenameCollectionRequest,
            False,
        ),
        (
            "delete_collection",
            "Delete an empty collection, or with force remove only collection membership without deleting objects.",
            delete_collection,
            DeleteCollectionRequest,
            False,
        ),
        (
            "link_objects_to_collection",
            "Link one or more existing objects to an existing collection.",
            link_objects_to_collection,
            CollectionObjectsRequest,
            False,
        ),
        (
            "unlink_objects_from_collection",
            "Unlink one or more objects from a collection without deleting the objects.",
            unlink_objects_from_collection,
            CollectionObjectsRequest,
            False,
        ),
        (
            "set_collection_visibility",
            "Set viewport and render visibility for a collection.",
            set_collection_visibility,
            CollectionVisibilityRequest,
            False,
        ),
    ):
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="collections",
                input_model=model,
                handler=handler,
                read_only=read_only,
            )
        )