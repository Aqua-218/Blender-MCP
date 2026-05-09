from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import (
    list_entity_specs,
    load_entity_spec,
    save_metadata_entity,
    write_placeholder_png,
)
from mcp_server.tools.collections import (
    CollectionObjectsRequest,
    CreateCollectionRequest,
    create_collection,
    link_objects_to_collection,
)
from mcp_server.tools.helpers import project_paths_for_record, require_project, resolve_target_ids
from mcp_server.tools.object import (
    AssignCollectionRequest,
    TagObjectRequest,
    TargetedObjectRequest,
    TransformObjectRequest,
    assign_collection,
    duplicate_object,
    tag_object,
    transform_object,
)
from mcp_server.tools.spatial import list_project_objects
from mcp_server.utils import new_id, slugify

AssetLibraryStatus = Literal["draft", "approved", "deprecated"]


class AssetLibraryTargetsRequest(CommonToolRequest):
    project_id: str
    asset_name: str
    category: str = "props"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    status: AssetLibraryStatus = "draft"


class AssetLibraryReferenceRequest(CommonToolRequest):
    project_id: str
    asset_id: str | None = None
    asset_name: str | None = None


class ListAssetLibraryItemsRequest(CommonToolRequest):
    project_id: str
    category: str | None = None
    tag: str | None = None
    status: AssetLibraryStatus | None = None


class FindAssetLibraryItemsRequest(ListAssetLibraryItemsRequest):
    query: str = ""
    tags: list[str] = Field(default_factory=list)


class UpdateAssetLibraryItemRequest(AssetLibraryReferenceRequest):
    asset_name: str | None = None
    category: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    status: AssetLibraryStatus | None = None


class AssignAssetCategoryRequest(AssetLibraryReferenceRequest):
    category: str


class AddAssetVariantRequest(AssetLibraryReferenceRequest):
    variant_name: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SetAssetPreviewRequest(AssetLibraryReferenceRequest):
    preview_path: str | None = None
    write_placeholder: bool = True


class CreateAssetCollectionRequest(AssetLibraryReferenceRequest):
    collection_name: str | None = None
    parent_collection_name: str = "Scene Collection"


class InstantiateAssetLibraryItemRequest(AssetLibraryReferenceRequest):
    location_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale_multiplier: tuple[float, float, float] = (1.0, 1.0, 1.0)
    collection_name: str | None = None


class ValidateAssetLibraryRequest(CommonToolRequest):
    project_id: str
    require_preview: bool = False
    require_targets: bool = True
    require_category: bool = True


def _asset_items(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, "asset_library_item")


def _save_asset_item(context, project_id: str, item: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(item["asset_id"]),
        entity_type="asset_library_item",
        name=str(item["asset_name"]),
        spec=item,
    )


def _find_asset_item(context, project_id: str, *, asset_id: str | None = None, asset_name: str | None = None) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    if asset_id is not None:
        record = context.entities.get(asset_id)
        if record is None or record.project_id != project_id or record.entity_type != "asset_library_item":
            return None
        return load_entity_spec(context, asset_id, expected_type="asset_library_item")
    if asset_name is None:
        return None
    lowered = asset_name.lower()
    return next((item for item in _asset_items(context, project_id) if str(item.get("asset_name", "")).lower() == lowered), None)


def _asset_failed(request: CommonToolRequest, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(request_id=request.request_id, tool_name=tool_name, summary=message, errors=[f"{code}: {message}"])


def _require_asset_item(context, request: AssetLibraryReferenceRequest, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    item = _find_asset_item(context, request.project_id, asset_id=request.asset_id, asset_name=request.asset_name)
    if item is None:
        selector = request.asset_id or request.asset_name or "<missing selector>"
        return _asset_failed(request, tool_name, "target_not_found", f"Asset library item '{selector}' was not found.")
    return item


async def _resolve_asset_target_ids(context, request: Any) -> list[str] | CommonToolResult:  # type: ignore[no-untyped-def]
    try:
        target_ids = await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=getattr(request, "target_ids", []) or ([request.target_id] if getattr(request, "target_id", None) else []),
            names=getattr(request, "names", []),
            tag=getattr(request, "tag", None),
            collection_name=getattr(request, "match_collection_name", None),
        )
    except ValueError as exc:
        return failed_result(request_id=request.request_id, tool_name="asset_library", summary=str(exc), errors=[f"target_not_found: {exc}"])
    objects = await list_project_objects(context, request.project_id)
    existing_ids = {str(item["object_id"]) for item in objects}
    missing = [target_id for target_id in target_ids if target_id not in existing_ids]
    if missing:
        return failed_result(request_id=request.request_id, tool_name="asset_library", summary=f"Asset target(s) were not found: {', '.join(missing)}", errors=[f"target_not_found: missing targets {', '.join(missing)}"])
    return target_ids


def _filter_asset_items(items: list[dict[str, Any]], *, category: str | None = None, tag: str | None = None, status: str | None = None, query: str = "", tags: list[str] | None = None) -> list[dict[str, Any]]:
    wanted_tags = {item.lower() for item in tags or []}
    query_text = query.lower().strip()
    filtered: list[dict[str, Any]] = []
    for item in items:
        item_tags = {str(value).lower() for value in item.get("tags", [])}
        haystack = " ".join([str(item.get("asset_name", "")), str(item.get("category", "")), str(item.get("description", "")), " ".join(item_tags)]).lower()
        if category is not None and str(item.get("category")) != category:
            continue
        if tag is not None and tag.lower() not in item_tags:
            continue
        if status is not None and str(item.get("status")) != status:
            continue
        if wanted_tags and not wanted_tags.issubset(item_tags):
            continue
        if query_text and query_text not in haystack:
            continue
        filtered.append(item)
    return filtered


def _asset_collection_name(item: dict[str, Any]) -> str:
    return f"Asset_{slugify(str(item['asset_name'])).replace('-', '_') or item['asset_id']}"


async def register_asset_library_item(context, request: AssetLibraryTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    resolved = await _resolve_asset_target_ids(context, request)
    if isinstance(resolved, CommonToolResult):
        payload = resolved.model_dump()
        payload["tool_name"] = "register_asset_library_item"
        return type(resolved).model_validate(payload)
    asset_id = new_id("assetlib")
    item = {
        "asset_id": asset_id,
        "project_id": project.project_id,
        "asset_name": request.asset_name,
        "category": request.category,
        "description": request.description,
        "tags": list(dict.fromkeys([*request.tags, request.category, "asset_library"])),
        "source_object_ids": resolved,
        "variants": [],
        "status": request.status,
        "preview_path": None,
    }
    _save_asset_item(context, project.project_id, item)
    tagged = await tag_object(
        context,
        TagObjectRequest(
            request_id=f"{request.request_id}-tag",
            project_id=project.project_id,
            target_ids=resolved,
            tags=["asset_library", f"asset:{asset_id}", f"asset_category:{request.category}"],
        ),
    )
    objects = tagged.model_dump().get("objects", []) if tagged.status == "success" else []
    return success_result(
        request_id=request.request_id,
        tool_name="register_asset_library_item",
        summary=f"Registered asset library item '{request.asset_name}' with {len(resolved)} source objects.",
        project_id=project.project_id,
        asset_id=asset_id,
        asset=item,
        modified_object_ids=resolved,
        objects=objects,
    )


async def list_asset_library_items(context, request: ListAssetLibraryItemsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    assets = _filter_asset_items(_asset_items(context, request.project_id), category=request.category, tag=request.tag, status=request.status)
    return success_result(request_id=request.request_id, tool_name="list_asset_library_items", summary=f"Listed {len(assets)} asset library items.", project_id=request.project_id, assets=assets, count=len(assets))


async def find_asset_library_items(context, request: FindAssetLibraryItemsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    assets = _filter_asset_items(_asset_items(context, request.project_id), category=request.category, tag=request.tag, status=request.status, query=request.query, tags=request.tags)
    return success_result(request_id=request.request_id, tool_name="find_asset_library_items", summary=f"Found {len(assets)} asset library items.", project_id=request.project_id, assets=assets, count=len(assets))


async def update_asset_library_item(context, request: UpdateAssetLibraryItemRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "update_asset_library_item")
    if isinstance(item, CommonToolResult):
        return item
    if request.asset_name is not None:
        item["asset_name"] = request.asset_name
    if request.category is not None:
        item["category"] = request.category
    if request.description is not None:
        item["description"] = request.description
    if request.tags is not None:
        item["tags"] = list(dict.fromkeys(request.tags))
    if request.status is not None:
        item["status"] = request.status
    _save_asset_item(context, project.project_id, item)
    return success_result(request_id=request.request_id, tool_name="update_asset_library_item", summary=f"Updated asset library item '{item['asset_name']}'.", project_id=project.project_id, asset_id=item["asset_id"], asset=item)


async def assign_asset_category(context, request: AssignAssetCategoryRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "assign_asset_category")
    if isinstance(item, CommonToolResult):
        return item
    item["category"] = request.category
    item["tags"] = list(dict.fromkeys([*item.get("tags", []), request.category]))
    _save_asset_item(context, project.project_id, item)
    return success_result(request_id=request.request_id, tool_name="assign_asset_category", summary=f"Assigned asset category '{request.category}'.", project_id=project.project_id, asset_id=item["asset_id"], asset=item)


async def add_asset_variant(context, request: AddAssetVariantRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "add_asset_variant")
    if isinstance(item, CommonToolResult):
        return item
    if request.target_id or request.target_ids or request.names:
        resolved = await _resolve_asset_target_ids(context, request)
        if isinstance(resolved, CommonToolResult):
            payload = resolved.model_dump()
            payload["tool_name"] = "add_asset_variant"
            return type(resolved).model_validate(payload)
        target_ids = resolved
    else:
        target_ids = list(item.get("source_object_ids", []))
    variant = {"variant_id": new_id("assetvar"), "variant_name": request.variant_name, "target_ids": target_ids, "notes": request.notes, "tags": request.tags}
    item["variants"] = [*list(item.get("variants", [])), variant]
    _save_asset_item(context, project.project_id, item)
    return success_result(request_id=request.request_id, tool_name="add_asset_variant", summary=f"Added variant '{request.variant_name}' to asset '{item['asset_name']}'.", project_id=project.project_id, asset_id=item["asset_id"], variant=variant, asset=item)


async def set_asset_preview(context, request: SetAssetPreviewRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "set_asset_preview")
    if isinstance(item, CommonToolResult):
        return item
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    if request.preview_path:
        output_path = context.workspace.canonicalize_output_path(Path(request.preview_path), allowed_extensions=[".png"])
    else:
        output_path = context.workspace.canonicalize_output_path(project_paths.export_dir / "asset_previews" / f"{slugify(str(item['asset_name']))}-{item['asset_id']}.png", allowed_extensions=[".png"])
    if request.write_placeholder:
        write_placeholder_png(output_path)
    item["preview_path"] = str(output_path)
    _save_asset_item(context, project.project_id, item)
    return success_result(request_id=request.request_id, tool_name="set_asset_preview", summary=f"Set preview for asset '{item['asset_name']}'.", project_id=project.project_id, asset_id=item["asset_id"], asset=item, file_paths=[str(output_path)])


async def create_asset_collection(context, request: CreateAssetCollectionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "create_asset_collection")
    if isinstance(item, CommonToolResult):
        return item
    collection_name = request.collection_name or _asset_collection_name(item)
    listed = await context.bridge.invoke("list_collections", {"project_id": project.project_id}, read_only=True)
    if collection_name not in {collection["name"] for collection in listed.get("collections", [])}:
        created = await create_collection(
            context,
            CreateCollectionRequest(request_id=f"{request.request_id}-collection", project_id=project.project_id, collection_name=collection_name, parent_collection_name=request.parent_collection_name),
        )
        if created.status != "success":
            payload = created.model_dump()
            payload["tool_name"] = "create_asset_collection"
            return type(created).model_validate(payload)
    linked = await link_objects_to_collection(
        context,
        CollectionObjectsRequest(request_id=f"{request.request_id}-link", project_id=project.project_id, collection_name=collection_name, target_ids=list(item.get("source_object_ids", []))),
    )
    if linked.status != "success":
        payload = linked.model_dump()
        payload["tool_name"] = "create_asset_collection"
        return type(linked).model_validate(payload)
    item["collection_name"] = collection_name
    _save_asset_item(context, project.project_id, item)
    payload = linked.model_dump()
    payload["tool_name"] = "create_asset_collection"
    payload["asset_id"] = item["asset_id"]
    payload["asset"] = item
    payload["summary"] = f"Created asset collection '{collection_name}'."
    return type(linked).model_validate(payload)


async def instantiate_asset_library_item(context, request: InstantiateAssetLibraryItemRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    item = _require_asset_item(context, request, "instantiate_asset_library_item")
    if isinstance(item, CommonToolResult):
        return item
    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    for source_id in list(item.get("source_object_ids", [])):
        duplicated = await duplicate_object(context, TargetedObjectRequest(request_id=f"{request.request_id}-dup-{source_id}", project_id=project.project_id, target_id=source_id))
        if duplicated.status != "success":
            payload = duplicated.model_dump()
            payload["tool_name"] = "instantiate_asset_library_item"
            return type(duplicated).model_validate(payload)
        duplicate_id = str(duplicated.created_object_ids[0])
        duplicate_spec = duplicated.model_dump().get("objects", [{}])[0]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=f"{request.request_id}-transform-{duplicate_id}",
                project_id=project.project_id,
                target_id=duplicate_id,
                location=[float(duplicate_spec.get("location", [0.0, 0.0, 0.0])[index]) + float(request.location_offset[index]) for index in range(3)],
                rotation=[float(duplicate_spec.get("rotation", [0.0, 0.0, 0.0])[index]) + float(request.rotation_offset[index]) for index in range(3)],
                scale=[float(duplicate_spec.get("scale", [1.0, 1.0, 1.0])[index]) * float(request.scale_multiplier[index]) for index in range(3)],
            ),
        )
        if transformed.status != "success":
            payload = transformed.model_dump()
            payload["tool_name"] = "instantiate_asset_library_item"
            return type(transformed).model_validate(payload)
        final_object = transformed.model_dump()["object"]
        if request.collection_name is not None:
            assigned = await assign_collection(context, AssignCollectionRequest(request_id=f"{request.request_id}-collection-{duplicate_id}", project_id=project.project_id, target_id=duplicate_id, collection_name=request.collection_name))
            if assigned.status != "success":
                payload = assigned.model_dump()
                payload["tool_name"] = "instantiate_asset_library_item"
                return type(assigned).model_validate(payload)
            final_object = assigned.model_dump()["objects"][0]
        created_object_ids.append(duplicate_id)
        objects.append(final_object)
    return success_result(request_id=request.request_id, tool_name="instantiate_asset_library_item", summary=f"Instantiated asset '{item['asset_name']}' as {len(created_object_ids)} objects.", project_id=project.project_id, created_object_ids=created_object_ids, objects=objects, asset_id=item["asset_id"], asset=item)


async def validate_asset_library(context, request: ValidateAssetLibraryRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    items = _asset_items(context, request.project_id)
    objects = await list_project_objects(context, request.project_id)
    existing = {str(item["object_id"]) for item in objects}
    findings: list[dict[str, Any]] = []
    for item in items:
        missing = [target_id for target_id in item.get("source_object_ids", []) if target_id not in existing]
        if request.require_targets and not item.get("source_object_ids"):
            findings.append({"severity": "error", "code": "asset_without_targets", "asset_id": item.get("asset_id"), "message": f"Asset '{item.get('asset_name')}' has no source objects."})
        if missing:
            findings.append({"severity": "error", "code": "missing_source_objects", "asset_id": item.get("asset_id"), "message": f"Asset '{item.get('asset_name')}' references missing source objects.", "object_ids": missing})
        if request.require_preview and not item.get("preview_path"):
            findings.append({"severity": "warning", "code": "missing_preview", "asset_id": item.get("asset_id"), "message": f"Asset '{item.get('asset_name')}' has no preview."})
        if request.require_category and not item.get("category"):
            findings.append({"severity": "warning", "code": "missing_category", "asset_id": item.get("asset_id"), "message": f"Asset '{item.get('asset_name')}' has no category."})
    summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in summary:
            summary[severity] += 1
    return success_result(request_id=request.request_id, tool_name="validate_asset_library", summary="Asset library validation completed.", project_id=request.project_id, assets=items, findings=findings, severity_summary=summary, count=len(items))


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("register_asset_library_item", "Register scene objects as a reusable asset library item.", AssetLibraryTargetsRequest, register_asset_library_item, False),
        ("list_asset_library_items", "List registered asset library items.", ListAssetLibraryItemsRequest, list_asset_library_items, True),
        ("find_asset_library_items", "Search registered asset library items by text and tags.", FindAssetLibraryItemsRequest, find_asset_library_items, True),
        ("update_asset_library_item", "Update metadata on an asset library item.", UpdateAssetLibraryItemRequest, update_asset_library_item, False),
        ("assign_asset_category", "Assign or replace an asset library category.", AssignAssetCategoryRequest, assign_asset_category, False),
        ("add_asset_variant", "Add a named source-object variant to an asset library item.", AddAssetVariantRequest, add_asset_variant, False),
        ("set_asset_preview", "Attach a project-scoped preview image to an asset library item.", SetAssetPreviewRequest, set_asset_preview, False),
        ("create_asset_collection", "Create or reuse a collection and link asset source objects into it.", CreateAssetCollectionRequest, create_asset_collection, False),
        ("instantiate_asset_library_item", "Duplicate an asset library item's source objects into the scene.", InstantiateAssetLibraryItemRequest, instantiate_asset_library_item, False),
        ("validate_asset_library", "Validate registered asset library metadata and source object references.", ValidateAssetLibraryRequest, validate_asset_library, True),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="asset_library",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )