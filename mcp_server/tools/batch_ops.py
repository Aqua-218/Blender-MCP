from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.asset_io import (
    ExportAssetRequest,
    ExportFormat,
    ImportAssetRequest,
    export_asset,
    import_asset,
)
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.tools.material import ApplyMaterialRequest, apply_material
from mcp_server.tools.modifiers import AddModifierRequest, ModifierType, add_modifier
from mcp_server.tools.object import (
    AssignCollectionRequest,
    RenameObjectRequest,
    TagObjectRequest,
    TargetedObjectRequest,
    TransformObjectRequest,
    VisibilityRequest,
    assign_collection,
    duplicate_object,
    rename_object,
    set_object_visibility,
    tag_object,
    transform_object,
)
from mcp_server.tools.spatial import list_project_objects


class BatchTargetsRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class BatchRenameObjectsRequest(BatchTargetsRequest):
    base_name: str
    prefix: str = ""
    separator: str = "_"
    start_index: int = Field(default=1, ge=0)


class BatchTagObjectsRequest(BatchTargetsRequest):
    tags: list[str] = Field(default_factory=list)


class BatchAssignCollectionRequest(BatchTargetsRequest):
    collection_name: str


class BatchVisibilityRequest(BatchTargetsRequest):
    visible: bool


class BatchTransformOffsetsRequest(BatchTargetsRequest):
    location_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale_multiplier: tuple[float, float, float] = (1.0, 1.0, 1.0)


class BatchApplyMaterialRequest(BatchTargetsRequest):
    material_id: str


class BatchAddModifierRequest(BatchTargetsRequest):
    modifier_type: ModifierType
    modifier_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class BatchDuplicateObjectsRequest(BatchTargetsRequest):
    location_step: tuple[float, float, float] = (0.0, 0.0, 0.0)
    collection_name: str | None = None


class BatchExportAssetsRequest(BatchTargetsRequest):
    output_prefix: str = "batch_export"
    export_format: ExportFormat | None = None
    separate_files: bool = True


class BatchImportAssetsRequest(CommonToolRequest):
    project_id: str
    input_paths: list[str] = Field(min_length=1)
    name_prefix: str | None = None
    collection_name: str | None = None


async def _resolve_batch_targets(context, request: BatchTargetsRequest, tool_name: str) -> list[str] | CommonToolResult:  # type: ignore[no-untyped-def]
    try:
        return await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
        )
    except ValueError as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary=str(exc),
            errors=[f"target_not_found: {exc}"],
        )


def _retag(result: CommonToolResult, tool_name: str, summary: str | None = None) -> CommonToolResult:
    payload = result.model_dump()
    payload["tool_name"] = tool_name
    if summary is not None:
        payload["summary"] = summary
    return CommonToolResult.model_validate(payload)


async def preview_batch_targets(context, request: BatchTargetsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "preview_batch_targets")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    objects = await list_project_objects(context, request.project_id)
    target_set = set(target_ids)
    selected = [item for item in objects if item.get("object_id") in target_set]
    return success_result(
        request_id=request.request_id,
        tool_name="preview_batch_targets",
        summary=f"Previewed {len(selected)} batch targets.",
        project_id=request.project_id,
        target_ids=target_ids,
        objects=selected,
        count=len(selected),
    )


async def batch_tag_objects(context, request: BatchTagObjectsRequest):  # type: ignore[no-untyped-def]
    target_ids = await _resolve_batch_targets(context, request, "batch_tag_objects")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    tags = request.tags or ([request.tag] if request.tag else ["batch_tagged"])
    tagged = await tag_object(
        context,
        TagObjectRequest(request_id=request.request_id, project_id=request.project_id, target_ids=target_ids, tags=tags),
    )
    return _retag(tagged, "batch_tag_objects", f"Tagged {len(target_ids)} batch objects.")


async def batch_rename_objects(context, request: BatchRenameObjectsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "batch_rename_objects")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    objects: list[dict[str, Any]] = []
    for offset, target_id in enumerate(target_ids):
        parts = [part for part in [request.prefix, request.base_name, f"{request.start_index + offset:02d}"] if part]
        renamed = await rename_object(
            context,
            RenameObjectRequest(
                request_id=f"{request.request_id}-rename-{offset}",
                project_id=project.project_id,
                target_id=target_id,
                new_name=request.separator.join(parts),
            ),
        )
        if renamed.status != "success":
            return _retag(renamed, "batch_rename_objects")
        objects.append(renamed.model_dump()["object"])
    return success_result(
        request_id=request.request_id,
        tool_name="batch_rename_objects",
        summary=f"Renamed {len(objects)} objects.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=objects,
    )


async def batch_assign_collection(context, request: BatchAssignCollectionRequest):  # type: ignore[no-untyped-def]
    target_ids = await _resolve_batch_targets(context, request, "batch_assign_collection")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    assigned = await assign_collection(
        context,
        AssignCollectionRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_ids=target_ids,
            collection_name=request.collection_name,
        ),
    )
    return _retag(assigned, "batch_assign_collection", f"Assigned {len(target_ids)} objects to {request.collection_name}.")


async def batch_set_visibility(context, request: BatchVisibilityRequest):  # type: ignore[no-untyped-def]
    target_ids = await _resolve_batch_targets(context, request, "batch_set_visibility")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    updated = await set_object_visibility(
        context,
        VisibilityRequest(request_id=request.request_id, project_id=request.project_id, target_ids=target_ids, visible=request.visible),
    )
    return _retag(updated, "batch_set_visibility", f"Updated visibility for {len(target_ids)} objects.")


async def batch_transform_offsets(context, request: BatchTransformOffsetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "batch_transform_offsets")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    current = {item["object_id"]: item for item in await list_project_objects(context, project.project_id)}
    objects: list[dict[str, Any]] = []
    for target_id in target_ids:
        item = current[target_id]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=f"{request.request_id}-transform-{target_id}",
                project_id=project.project_id,
                target_id=target_id,
                location=[float(item.get("location", [0, 0, 0])[index]) + float(request.location_offset[index]) for index in range(3)],
                rotation=[float(item.get("rotation", [0, 0, 0])[index]) + float(request.rotation_offset[index]) for index in range(3)],
                scale=[float(item.get("scale", [1, 1, 1])[index]) * float(request.scale_multiplier[index]) for index in range(3)],
            ),
        )
        if transformed.status != "success":
            return _retag(transformed, "batch_transform_offsets")
        objects.append(transformed.model_dump()["object"])
    return success_result(
        request_id=request.request_id,
        tool_name="batch_transform_offsets",
        summary=f"Offset transforms for {len(objects)} objects.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=objects,
    )


async def batch_apply_material(context, request: BatchApplyMaterialRequest):  # type: ignore[no-untyped-def]
    target_ids = await _resolve_batch_targets(context, request, "batch_apply_material")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            material_id=request.material_id,
            target_ids=target_ids,
        ),
    )
    return _retag(applied, "batch_apply_material", "Applied material to batch targets.")


async def batch_add_modifier(context, request: BatchAddModifierRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "batch_add_modifier")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    modifiers: list[dict[str, Any]] = []
    for target_id in target_ids:
        added = await add_modifier(
            context,
            AddModifierRequest(
                request_id=f"{request.request_id}-modifier-{target_id}",
                project_id=project.project_id,
                target_id=target_id,
                modifier_type=request.modifier_type,
                name=request.modifier_name,
                params=request.params,
            ),
        )
        if added.status != "success":
            return _retag(added, "batch_add_modifier")
        modifiers.extend(added.model_dump().get("modifiers", []))
    return success_result(
        request_id=request.request_id,
        tool_name="batch_add_modifier",
        summary=f"Added {request.modifier_type} modifiers to {len(target_ids)} objects.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        modifiers=modifiers,
    )


async def batch_duplicate_objects(context, request: BatchDuplicateObjectsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "batch_duplicate_objects")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    for index, target_id in enumerate(target_ids, start=1):
        duplicated = await duplicate_object(
            context,
            TargetedObjectRequest(request_id=f"{request.request_id}-dup-{target_id}", project_id=project.project_id, target_id=target_id),
        )
        if duplicated.status != "success":
            return _retag(duplicated, "batch_duplicate_objects")
        duplicate_id = str(duplicated.created_object_ids[0])
        duplicate_spec = duplicated.model_dump().get("objects", [{}])[0]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=f"{request.request_id}-step-{duplicate_id}",
                project_id=project.project_id,
                target_id=duplicate_id,
                location=[float(duplicate_spec.get("location", [0, 0, 0])[axis]) + float(request.location_step[axis]) * index for axis in range(3)],
            ),
        )
        if transformed.status != "success":
            return _retag(transformed, "batch_duplicate_objects")
        final_object = transformed.model_dump()["object"]
        if request.collection_name is not None:
            assigned = await assign_collection(
                context,
                AssignCollectionRequest(
                    request_id=f"{request.request_id}-collection-{duplicate_id}",
                    project_id=project.project_id,
                    target_id=duplicate_id,
                    collection_name=request.collection_name,
                ),
            )
            if assigned.status != "success":
                return _retag(assigned, "batch_duplicate_objects")
            final_object = assigned.model_dump()["objects"][0]
        created_object_ids.append(duplicate_id)
        objects.append(final_object)
    return success_result(
        request_id=request.request_id,
        tool_name="batch_duplicate_objects",
        summary=f"Duplicated {len(created_object_ids)} batch objects.",
        project_id=project.project_id,
        created_object_ids=created_object_ids,
        objects=objects,
    )


async def batch_export_assets(context, request: BatchExportAssetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_batch_targets(context, request, "batch_export_assets")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    objects_by_id = {item["object_id"]: item for item in await list_project_objects(context, project.project_id)}
    export_format = request.export_format or "glb"
    exports: list[dict[str, Any]] = []
    file_paths: list[str] = []
    if not request.separate_files:
        exported = await export_asset(
            context,
            ExportAssetRequest(
                request_id=f"{request.request_id}-export-all",
                project_id=project.project_id,
                target_ids=target_ids,
                output_path=f"{request.output_prefix}.{export_format}",
                export_format=export_format,
            ),
        )
        if exported.status != "success":
            return _retag(exported, "batch_export_assets")
        payload = exported.model_dump()
        exports.append(payload)
        file_paths.extend(payload.get("file_paths", []))
    else:
        for index, target_id in enumerate(target_ids, start=1):
            object_name = str(objects_by_id.get(target_id, {}).get("name", target_id)).lower().replace(" ", "_")
            exported = await export_asset(
                context,
                ExportAssetRequest(
                    request_id=f"{request.request_id}-export-{index}",
                    project_id=project.project_id,
                    target_id=target_id,
                    output_path=f"{request.output_prefix}-{index:02d}-{object_name}.{export_format}",
                    export_format=export_format,
                ),
            )
            if exported.status != "success":
                return _retag(exported, "batch_export_assets")
            payload = exported.model_dump()
            exports.append(payload)
            file_paths.extend(payload.get("file_paths", []))
    return success_result(
        request_id=request.request_id,
        tool_name="batch_export_assets",
        summary=f"Exported {len(exports)} batch asset job(s).",
        project_id=project.project_id,
        file_paths=file_paths,
        exported_object_ids=target_ids,
        exports=exports,
    )


async def batch_import_assets(context, request: BatchImportAssetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    imports: list[dict[str, Any]] = []
    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    file_paths: list[str] = []
    for index, input_path in enumerate(request.input_paths, start=1):
        name_prefix = f"{request.name_prefix}_{index:02d}" if request.name_prefix else None
        imported = await import_asset(
            context,
            ImportAssetRequest(
                request_id=f"{request.request_id}-import-{index}",
                project_id=project.project_id,
                input_path=input_path,
                name_prefix=name_prefix,
            ),
        )
        if imported.status != "success":
            return _retag(imported, "batch_import_assets")
        payload = imported.model_dump()
        imported_ids = [str(item) for item in payload.get("created_object_ids", [])]
        final_objects = payload.get("objects", [])
        if request.collection_name is not None and imported_ids:
            assigned = await assign_collection(
                context,
                AssignCollectionRequest(
                    request_id=f"{request.request_id}-collection-{index}",
                    project_id=project.project_id,
                    target_ids=imported_ids,
                    collection_name=request.collection_name,
                ),
            )
            if assigned.status != "success":
                return _retag(assigned, "batch_import_assets")
            final_objects = assigned.model_dump().get("objects", [])
        imports.append(payload)
        created_object_ids.extend(imported_ids)
        objects.extend(final_objects)
        file_paths.extend(payload.get("file_paths", []))
    return success_result(
        request_id=request.request_id,
        tool_name="batch_import_assets",
        summary=f"Imported {len(request.input_paths)} asset file(s).",
        project_id=project.project_id,
        created_object_ids=created_object_ids,
        file_paths=file_paths,
        objects=objects,
        imports=imports,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("preview_batch_targets", "Resolve and preview targets for a batch operation.", BatchTargetsRequest, preview_batch_targets, True),
        ("batch_tag_objects", "Apply tags to resolved batch targets.", BatchTagObjectsRequest, batch_tag_objects, False),
        ("batch_rename_objects", "Rename resolved batch targets with a deterministic sequence.", BatchRenameObjectsRequest, batch_rename_objects, False),
        ("batch_assign_collection", "Assign resolved batch targets to a collection.", BatchAssignCollectionRequest, batch_assign_collection, False),
        ("batch_set_visibility", "Set visibility for resolved batch targets.", BatchVisibilityRequest, batch_set_visibility, False),
        ("batch_transform_offsets", "Apply transform offsets to resolved batch targets.", BatchTransformOffsetsRequest, batch_transform_offsets, False),
        ("batch_apply_material", "Apply one material to resolved batch targets.", BatchApplyMaterialRequest, batch_apply_material, False),
        ("batch_add_modifier", "Add the same modifier to resolved batch targets.", BatchAddModifierRequest, batch_add_modifier, False),
        ("batch_duplicate_objects", "Duplicate resolved batch targets with an optional stepped offset.", BatchDuplicateObjectsRequest, batch_duplicate_objects, False),
        ("batch_export_assets", "Export resolved batch targets as one or more asset files.", BatchExportAssetsRequest, batch_export_assets, False),
        ("batch_import_assets", "Import multiple asset files into the active project.", BatchImportAssetsRequest, batch_import_assets, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="batch_ops",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )