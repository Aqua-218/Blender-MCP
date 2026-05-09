from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.serialization import json_dumps
from mcp_server.tools.asset_io import (
    SetExportProfileRequest,
    _load_export_profile,
    set_export_profile,
)
from mcp_server.tools.geometry import CreatePrimitiveRequest, create_primitive
from mcp_server.tools.helpers import project_paths_for_record, require_project, resolve_target_ids
from mcp_server.tools.object import RenameObjectRequest, TagObjectRequest, rename_object, tag_object
from mcp_server.tools.repair import GenerateLODRequest, generate_lod
from mcp_server.tools.spatial import bounds_for_object, list_project_objects
from mcp_server.utils import slugify
from mcp_server.workspace import WorkspaceViolationError

CollisionRole = Literal["simple", "convex", "complex", "trigger", "none"]
CollisionProxyType = Literal["box", "sphere", "capsule"]
ExportRole = Literal["render", "collision", "socket", "lod", "fx", "navmesh", "occluder"]
EngineProfileName = Literal["unreal", "unity", "godot", "web"]

_COLLISION_PREFIXES = ("UCX", "UBX", "UCP", "USP")
_LOD_PATTERN = re.compile(r"(?:^|[_-])LOD(?P<level>\d+)(?:$|[_-])", re.IGNORECASE)


class GamePrepTargetsRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class AssignLODLevelRequest(GamePrepTargetsRequest):
    level: int = Field(default=0, ge=0, le=8)
    group_name: str | None = None
    screen_size: float | None = Field(default=None, ge=0.0, le=1.0)
    rename: bool = True


class CreateLODChainRequest(CommonToolRequest):
    project_id: str
    target_id: str
    group_name: str | None = None
    levels: int = Field(default=3, ge=1, le=4)
    base_ratio: float = Field(default=0.5, gt=0.0, le=1.0)
    tag_source: bool = True


class CreateCollisionProxyRequest(CommonToolRequest):
    project_id: str
    target_id: str
    proxy_type: CollisionProxyType = "box"
    name_prefix: str = "UCX"
    collection_name: str = "Collision"
    padding: float = Field(default=0.05, ge=0.0)


class CreateCollisionProxySetRequest(GamePrepTargetsRequest):
    proxy_types: list[CollisionProxyType] = Field(default_factory=lambda: ["box"])
    name_prefix: str = "UCX"
    collection_name: str = "Collision"
    padding: float = Field(default=0.05, ge=0.0)


class CreateSocketMarkerRequest(CommonToolRequest):
    project_id: str
    target_id: str
    socket_name: str
    location_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius: float = Field(default=0.08, gt=0.0)
    collection_name: str = "Sockets"


class TagGameExportRoleRequest(GamePrepTargetsRequest):
    role: ExportRole = "render"
    export_name: str | None = None


class AssignCollisionRoleRequest(GamePrepTargetsRequest):
    role: CollisionRole = "simple"
    name_prefix: str = "UCX"
    base_name: str | None = None
    rename: bool = True


class NormalizeGameAssetNamesRequest(GamePrepTargetsRequest):
    base_name: str
    prefix: str = ""
    separator: str = "_"
    start_index: int = Field(default=0, ge=0)
    include_type_suffix: bool = False


class ValidateGameExportReadinessRequest(CommonToolRequest):
    project_id: str
    require_collision: bool = True
    require_lods: bool = False
    require_materials: bool = True


class ValidateLODChainRequest(CommonToolRequest):
    project_id: str
    group_name: str | None = None
    required_levels: int = Field(default=2, ge=1, le=8)


class PlanGameExportPackageRequest(CommonToolRequest):
    project_id: str
    package_name: str = "game_export"
    require_collision: bool = True
    require_lods: bool = False
    require_materials: bool = True


class WriteGameExportManifestRequest(PlanGameExportPackageRequest):
    output_path: str | None = None


class SetGameExportProfileRequest(CommonToolRequest):
    project_id: str
    default_format: Literal["glb", "gltf", "fbx", "obj"] = "glb"


class SetEngineExportProfileRequest(CommonToolRequest):
    project_id: str
    engine: EngineProfileName
    default_format: Literal["glb", "gltf", "fbx", "obj"] | None = None


class ValidateEngineExportPackageRequest(PlanGameExportPackageRequest):
    engine: EngineProfileName


class PlanEngineImportChecklistRequest(CommonToolRequest):
    project_id: str
    engine: EngineProfileName
    package_name: str = "game_export"
    include_validation: bool = True


async def _resolve_game_targets(context, request: GamePrepTargetsRequest, tool_name: str):  # type: ignore[no-untyped-def]
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


async def _tag_targets(context, request_id: str, project_id: str, target_ids: list[str], tags: list[str]):  # type: ignore[no-untyped-def]
    return await tag_object(
        context,
        TagObjectRequest(
            request_id=f"{request_id}-tag",
            project_id=project_id,
            target_ids=target_ids,
            tags=tags,
        ),
    )


async def assign_lod_level(context, request: AssignLODLevelRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_game_targets(context, request, "assign_lod_level")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    group_name = request.group_name or "LODGroup"
    tags = ["lod", f"lod:{request.level}", f"lod_group:{group_name}"]
    if request.screen_size is not None:
        tags.append(f"lod_screen:{request.screen_size:g}")
    tagged = await _tag_targets(context, request.request_id, project.project_id, target_ids, tags)
    if tagged.status != "success":
        payload = tagged.model_dump()
        payload["tool_name"] = "assign_lod_level"
        return type(tagged).model_validate(payload)
    renamed_objects: list[dict[str, Any]] = []
    if request.rename:
        object_map = {item["object_id"]: item for item in getattr(tagged, "objects", [])}
        for target_id in target_ids:
            current_name = str(object_map.get(target_id, {}).get("name", target_id))
            base_name = _strip_lod_suffix(current_name)
            renamed = await rename_object(
                context,
                RenameObjectRequest(
                    request_id=f"{request.request_id}-rename-{target_id}",
                    project_id=project.project_id,
                    target_id=target_id,
                    new_name=f"{base_name}_LOD{request.level}",
                ),
            )
            if renamed.status != "success":
                payload = renamed.model_dump()
                payload["tool_name"] = "assign_lod_level"
                return type(renamed).model_validate(payload)
            renamed_objects.extend(_result_objects(renamed.model_dump()))
    return success_result(
        request_id=request.request_id,
        tool_name="assign_lod_level",
        summary=f"Assigned LOD{request.level} metadata to {len(target_ids)} objects.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=renamed_objects or getattr(tagged, "objects", []),
        lod_level=request.level,
        lod_group=group_name,
        screen_size=request.screen_size,
    )


async def create_lod_chain(context, request: CreateLODChainRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    source = next((item for item in objects if item.get("object_id") == request.target_id), None)
    if source is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_lod_chain",
            summary=f"Target '{request.target_id}' was not found.",
            errors=[f"target_not_found: Unknown object_id: {request.target_id}"],
        )
    group_name = request.group_name or _strip_lod_suffix(str(source.get("name", request.target_id)))
    created = await generate_lod(
        context,
        GenerateLODRequest(
            request_id=f"{request.request_id}-generate",
            project_id=project.project_id,
            target_id=request.target_id,
            levels=request.levels,
            base_ratio=request.base_ratio,
        ),
    )
    if created.status != "success":
        payload = created.model_dump()
        payload["tool_name"] = "create_lod_chain"
        return type(created).model_validate(payload)
    created_ids = list(created.created_object_ids)
    lod_objects: list[dict[str, Any]] = []
    source_ids = [request.target_id] if request.tag_source else []
    if source_ids:
        source_lod = await assign_lod_level(
            context,
            AssignLODLevelRequest(
                request_id=f"{request.request_id}-source",
                project_id=project.project_id,
                target_ids=source_ids,
                level=0,
                group_name=group_name,
                screen_size=1.0,
                rename=True,
            ),
        )
        if source_lod.status == "success":
            lod_objects.extend(source_lod.model_dump().get("objects", []))
    for index, object_id in enumerate(created_ids, start=1):
        screen_size = max(1.0 - (index / (request.levels + 1)), 0.05)
        assigned = await assign_lod_level(
            context,
            AssignLODLevelRequest(
                request_id=f"{request.request_id}-lod-{index}",
                project_id=project.project_id,
                target_ids=[object_id],
                level=index,
                group_name=group_name,
                screen_size=screen_size,
                rename=True,
            ),
        )
        if assigned.status != "success":
            payload = assigned.model_dump()
            payload["tool_name"] = "create_lod_chain"
            return type(assigned).model_validate(payload)
        lod_objects.extend(assigned.model_dump().get("objects", []))
    return success_result(
        request_id=request.request_id,
        tool_name="create_lod_chain",
        summary=f"Created LOD chain '{group_name}' with {len(created_ids)} generated levels.",
        project_id=project.project_id,
        created_object_ids=created_ids,
        modified_object_ids=source_ids,
        objects=lod_objects,
        lod_group=group_name,
        lod_object_ids=[*source_ids, *created_ids],
    )


async def create_collision_proxy(context, request: CreateCollisionProxyRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    source = next((item for item in objects if item.get("object_id") == request.target_id), None)
    if source is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_collision_proxy",
            summary=f"Target '{request.target_id}' was not found.",
            errors=[f"target_not_found: Unknown object_id: {request.target_id}"],
        )
    minimum, maximum = bounds_for_object(source)
    center = [(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False)]
    dimensions = [max((high - low) + (request.padding * 2.0), 0.05) for low, high in zip(minimum, maximum, strict=False)]
    primitive_type = {"box": "cube", "sphere": "uv_sphere", "capsule": "cylinder"}[request.proxy_type]
    source_name = slugify(str(source.get("name", request.target_id))).replace("-", "_") or "asset"
    created = await create_primitive(
        context,
        CreatePrimitiveRequest(
            request_id=f"{request.request_id}-primitive",
            project_id=project.project_id,
            primitive_type=primitive_type,
            name=f"{request.name_prefix}_{source_name}_00",
            location=center,
            scale=dimensions,
            collection_name=request.collection_name,
            tags=["collision", f"collision:{request.proxy_type}", f"collision_source:{request.target_id}"],
        ),
    )
    payload = created.model_dump()
    payload["tool_name"] = "create_collision_proxy"
    if payload["status"] == "success":
        payload["summary"] = f"Created {request.proxy_type} collision proxy for {source.get('name', request.target_id)}."
        payload["collision_object_id"] = payload["created_object_ids"][0]
        payload["source_object_id"] = request.target_id
        payload["proxy_type"] = request.proxy_type
    return type(created).model_validate(payload)


async def create_collision_proxy_set(context, request: CreateCollisionProxySetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_game_targets(context, request, "create_collision_proxy_set")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    created_object_ids: list[str] = []
    collision_objects: list[dict[str, Any]] = []
    proxy_records: list[dict[str, Any]] = []
    proxy_types = list(dict.fromkeys(request.proxy_types)) or ["box"]
    for target_id in target_ids:
        for proxy_type in proxy_types:
            created = await create_collision_proxy(
                context,
                CreateCollisionProxyRequest(
                    request_id=f"{request.request_id}-{target_id}-{proxy_type}",
                    project_id=project.project_id,
                    target_id=target_id,
                    proxy_type=proxy_type,
                    name_prefix=request.name_prefix,
                    collection_name=request.collection_name,
                    padding=request.padding,
                ),
            )
            if created.status != "success":
                payload = created.model_dump()
                payload["tool_name"] = "create_collision_proxy_set"
                return type(created).model_validate(payload)
            created_payload = created.model_dump()
            created_object_ids.extend(created_payload.get("created_object_ids", []))
            collision_objects.extend(created_payload.get("objects", []))
            proxy_records.append(
                {
                    "source_object_id": target_id,
                    "collision_object_id": created_payload.get("collision_object_id"),
                    "proxy_type": proxy_type,
                }
            )
    return success_result(
        request_id=request.request_id,
        tool_name="create_collision_proxy_set",
        summary=f"Created {len(created_object_ids)} collision proxies for {len(target_ids)} source objects.",
        project_id=project.project_id,
        created_object_ids=created_object_ids,
        objects=collision_objects,
        proxies=proxy_records,
    )


async def create_socket_marker(context, request: CreateSocketMarkerRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    source = next((item for item in objects if item.get("object_id") == request.target_id), None)
    if source is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_socket_marker",
            summary=f"Target '{request.target_id}' was not found.",
            errors=[f"target_not_found: Unknown object_id: {request.target_id}"],
        )
    minimum, maximum = bounds_for_object(source)
    center = [(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False)]
    location = [center[index] + float(request.location_offset[index]) for index in range(3)]
    socket_slug = slugify(request.socket_name).replace("-", "_") or "socket"
    source_name = slugify(str(source.get("name", request.target_id))).replace("-", "_") or "asset"
    created = await create_primitive(
        context,
        CreatePrimitiveRequest(
            request_id=f"{request.request_id}-marker",
            project_id=project.project_id,
            primitive_type="uv_sphere",
            name=f"SOCKET_{source_name}_{socket_slug}",
            location=location,
            scale=[request.radius, request.radius, request.radius],
            collection_name=request.collection_name,
            tags=["socket", f"socket:{socket_slug}", f"socket_source:{request.target_id}", "export_role:socket"],
        ),
    )
    payload = created.model_dump()
    payload["tool_name"] = "create_socket_marker"
    if payload["status"] == "success":
        payload["summary"] = f"Created socket marker '{request.socket_name}'."
        payload["socket_name"] = socket_slug
        payload["source_object_id"] = request.target_id
        payload["socket_object_id"] = payload["created_object_ids"][0]
    return type(created).model_validate(payload)


async def assign_collision_role(context, request: AssignCollisionRoleRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_game_targets(context, request, "assign_collision_role")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    tagged = await _tag_targets(
        context,
        request.request_id,
        project.project_id,
        target_ids,
        ["collision", f"collision_role:{request.role}"],
    )
    if tagged.status != "success":
        payload = tagged.model_dump()
        payload["tool_name"] = "assign_collision_role"
        return type(tagged).model_validate(payload)
    objects = tagged.model_dump().get("objects", [])
    if request.rename:
        renamed_objects: list[dict[str, Any]] = []
        object_map = {item["object_id"]: item for item in objects}
        for index, target_id in enumerate(target_ids):
            current_name = str(object_map.get(target_id, {}).get("name", target_id))
            base_name = slugify(request.base_name or current_name).replace("-", "_") or "asset"
            renamed = await rename_object(
                context,
                RenameObjectRequest(
                    request_id=f"{request.request_id}-rename-{index}",
                    project_id=project.project_id,
                    target_id=target_id,
                    new_name=f"{request.name_prefix}_{base_name}_{index:02d}",
                ),
            )
            if renamed.status != "success":
                payload = renamed.model_dump()
                payload["tool_name"] = "assign_collision_role"
                return type(renamed).model_validate(payload)
            renamed_objects.extend(_result_objects(renamed.model_dump()))
        objects = renamed_objects
    return success_result(
        request_id=request.request_id,
        tool_name="assign_collision_role",
        summary=f"Assigned collision role '{request.role}' to {len(target_ids)} objects.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=objects,
        collision_role=request.role,
    )


async def tag_game_export_role(context, request: TagGameExportRoleRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_game_targets(context, request, "tag_game_export_role")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    tags = ["game_export", f"export_role:{request.role}"]
    if request.export_name:
        tags.append(f"export_name:{slugify(request.export_name).replace('-', '_')}")
    tagged = await _tag_targets(context, request.request_id, project.project_id, target_ids, tags)
    if tagged.status != "success":
        payload = tagged.model_dump()
        payload["tool_name"] = "tag_game_export_role"
        return type(tagged).model_validate(payload)
    payload = tagged.model_dump()
    payload["tool_name"] = "tag_game_export_role"
    payload["summary"] = f"Tagged {len(target_ids)} objects as game export role '{request.role}'."
    payload["export_role"] = request.role
    return type(tagged).model_validate(payload)


async def normalize_game_asset_names(context, request: NormalizeGameAssetNamesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_game_targets(context, request, "normalize_game_asset_names")
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    objects = await list_project_objects(context, project.project_id)
    object_map = {item["object_id"]: item for item in objects}
    renamed_objects: list[dict[str, Any]] = []
    clean_base = slugify(request.base_name).replace("-", request.separator) or "asset"
    clean_prefix = slugify(request.prefix).replace("-", request.separator) if request.prefix else ""
    for offset, target_id in enumerate(target_ids):
        item = object_map.get(target_id, {})
        parts = [part for part in [clean_prefix, clean_base, f"{request.start_index + offset:02d}"] if part]
        if request.include_type_suffix and item.get("type"):
            parts.append(str(item["type"]).lower())
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
            payload = renamed.model_dump()
            payload["tool_name"] = "normalize_game_asset_names"
            return type(renamed).model_validate(payload)
        renamed_objects.extend(_result_objects(renamed.model_dump()))
    return success_result(
        request_id=request.request_id,
        tool_name="normalize_game_asset_names",
        summary=f"Normalized {len(target_ids)} game asset names.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=renamed_objects,
    )


async def validate_game_export_readiness(context, request: ValidateGameExportReadinessRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    mesh_objects = [item for item in objects if item.get("type") == "MESH"]
    collision_objects = [item for item in mesh_objects if _is_collision_object(item)]
    lod_objects = [item for item in mesh_objects if _lod_level(item) is not None]
    findings: list[dict[str, Any]] = []
    if not mesh_objects:
        findings.append({"severity": "error", "code": "no_mesh_objects", "message": "No mesh objects are available for game export."})
    if request.require_collision and not collision_objects:
        findings.append({"severity": "warning", "code": "missing_collision", "message": "No collision proxy objects were detected."})
    if request.require_lods and not lod_objects:
        findings.append({"severity": "warning", "code": "missing_lods", "message": "No LOD-tagged or LOD-named mesh objects were detected."})
    duplicate_names = _duplicate_names(objects)
    if duplicate_names:
        findings.append({"severity": "warning", "code": "duplicate_names", "message": f"Found {len(duplicate_names)} duplicate object names.", "names": duplicate_names})
    scaled = [item["object_id"] for item in mesh_objects if _has_non_unit_scale(item)]
    if scaled:
        findings.append({"severity": "warning", "code": "non_unit_scale", "message": f"{len(scaled)} mesh objects have non-unit scale.", "object_ids": scaled})
    if request.require_materials:
        without_materials = [item["object_id"] for item in mesh_objects if not item.get("material_ids") and not _is_collision_object(item)]
        if without_materials:
            findings.append({"severity": "warning", "code": "mesh_without_material", "message": f"{len(without_materials)} render meshes have no material assignment.", "object_ids": without_materials})
    severity_summary = _summarize_findings(findings)
    return success_result(
        request_id=request.request_id,
        tool_name="validate_game_export_readiness",
        summary="Game export readiness validation completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=severity_summary,
        blocked_export_formats=["glb", "gltf", "fbx"] if severity_summary.get("error", 0) else [],
        metrics={
            "object_count": len(objects),
            "mesh_object_count": len(mesh_objects),
            "collision_object_count": len(collision_objects),
            "lod_object_count": len(lod_objects),
        },
    )


async def validate_lod_chain(context, request: ValidateLODChainRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in objects:
        level = _lod_level(item)
        if level is None:
            continue
        group_name = _lod_group_name(item)
        if request.group_name is not None and group_name != request.group_name:
            continue
        groups.setdefault(group_name, []).append(item)
    findings: list[dict[str, Any]] = []
    if not groups:
        findings.append({"severity": "warning", "code": "no_lod_groups", "message": "No matching LOD groups were detected."})
    group_reports: list[dict[str, Any]] = []
    for group_name, items in sorted(groups.items()):
        levels = sorted(level for item in items if (level := _lod_level(item)) is not None)
        missing_levels = [level for level in range(request.required_levels + 1) if level not in levels]
        duplicate_levels = sorted({level for level in levels if levels.count(level) > 1})
        if missing_levels:
            findings.append({"severity": "warning", "code": "missing_lod_levels", "message": f"LOD group '{group_name}' is missing levels {missing_levels}.", "group_name": group_name, "levels": missing_levels})
        if duplicate_levels:
            findings.append({"severity": "warning", "code": "duplicate_lod_levels", "message": f"LOD group '{group_name}' has duplicate levels {duplicate_levels}.", "group_name": group_name, "levels": duplicate_levels})
        group_reports.append({"group_name": group_name, "levels": levels, "object_ids": [str(item["object_id"]) for item in items], "missing_levels": missing_levels, "duplicate_levels": duplicate_levels})
    severity_summary = _summarize_findings(findings)
    return success_result(
        request_id=request.request_id,
        tool_name="validate_lod_chain",
        summary="LOD chain validation completed.",
        project_id=project.project_id,
        groups=group_reports,
        findings=findings,
        severity_summary=severity_summary,
    )


async def plan_game_export_package(context, request: PlanGameExportPackageRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    manifest = await _build_game_export_manifest(context, request)
    return success_result(
        request_id=request.request_id,
        tool_name="plan_game_export_package",
        summary=f"Planned game export package '{request.package_name}'.",
        project_id=project.project_id,
        manifest=manifest,
        readiness=manifest["readiness"],
    )


async def write_game_export_manifest(context, request: WriteGameExportManifestRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    manifest = await _build_game_export_manifest(context, request)
    try:
        output_path = _manifest_output_path(context, project, request.output_path, request.package_name)
    except WorkspaceViolationError as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="write_game_export_manifest",
            summary=str(exc),
            errors=[f"validation_error: {exc}"],
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_dumps(manifest, pretty=True) + "\n", encoding="utf-8")
    return success_result(
        request_id=request.request_id,
        tool_name="write_game_export_manifest",
        summary=f"Wrote game export manifest to {output_path.name}.",
        project_id=project.project_id,
        file_paths=[str(output_path)],
        manifest=manifest,
    )


async def set_game_export_profile(context, request: SetGameExportProfileRequest):  # type: ignore[no-untyped-def]
    result = await set_export_profile(
        context,
        SetExportProfileRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            profile_name="game",
            default_format=request.default_format,
            include_cameras=False,
            include_lights=False,
            axis_forward="-Z",
            axis_up="Y",
            apply_scale=1.0,
        ),
    )
    payload = result.model_dump()
    payload["tool_name"] = "set_game_export_profile"
    if payload["status"] == "success":
        payload["summary"] = "Set game export profile defaults."
    return type(result).model_validate(payload)


async def set_engine_export_profile(context, request: SetEngineExportProfileRequest):  # type: ignore[no-untyped-def]
    presets = {
        "unreal": {"default_format": "fbx", "axis_forward": "-Z", "axis_up": "Y", "apply_scale": 1.0},
        "unity": {"default_format": "fbx", "axis_forward": "-Z", "axis_up": "Y", "apply_scale": 1.0},
        "godot": {"default_format": "glb", "axis_forward": "-Z", "axis_up": "Y", "apply_scale": 1.0},
        "web": {"default_format": "glb", "axis_forward": "-Z", "axis_up": "Y", "apply_scale": 1.0},
    }
    preset = dict(presets[request.engine])
    if request.default_format is not None:
        preset["default_format"] = request.default_format
    result = await set_export_profile(
        context,
        SetExportProfileRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            profile_name="game",
            default_format=preset["default_format"],
            include_cameras=False,
            include_lights=False,
            axis_forward=preset["axis_forward"],
            axis_up=preset["axis_up"],
            apply_scale=preset["apply_scale"],
        ),
    )
    payload = result.model_dump()
    payload["tool_name"] = "set_engine_export_profile"
    if payload["status"] == "success":
        payload["summary"] = f"Set {request.engine} game export profile defaults."
        payload["engine"] = request.engine
    return type(result).model_validate(payload)


async def validate_engine_export_package(context, request: ValidateEngineExportPackageRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    manifest = await _build_game_export_manifest(context, request)
    profile = _load_export_profile(context, project.project_id)
    expected_format = _engine_expected_format(request.engine)
    findings: list[dict[str, Any]] = []

    readiness = manifest["readiness"]
    for finding in readiness.get("findings", []):
        if finding.get("severity") == "error":
            findings.append({"severity": "error", "code": "readiness_error", "message": finding.get("message"), "source": finding.get("code")})
    if profile.get("default_format") != expected_format:
        findings.append(
            {
                "severity": "warning",
                "code": "engine_format_mismatch",
                "message": f"{request.engine} export usually expects {expected_format}, active profile defaults to {profile.get('default_format')}.",
                "expected_format": expected_format,
                "actual_format": profile.get("default_format"),
            }
        )
    if request.engine == "unreal":
        invalid_collision = [pair for pair in manifest["collision_pairs"] if not str(_manifest_object_name(manifest, pair["collision_object_id"])).upper().startswith(_COLLISION_PREFIXES)]
        if invalid_collision:
            findings.append({"severity": "warning", "code": "unreal_collision_prefix", "message": "Unreal collision meshes should use UCX/UBX/UCP/USP prefixes.", "collision_object_ids": [pair["collision_object_id"] for pair in invalid_collision]})
        invalid_sockets = [item for item in manifest["socket_markers"] if not str(_manifest_object_name(manifest, item["socket_object_id"])).upper().startswith("SOCKET_")]
        if invalid_sockets:
            findings.append({"severity": "warning", "code": "unreal_socket_prefix", "message": "Unreal socket markers should use SOCKET_ naming.", "socket_object_ids": [item["socket_object_id"] for item in invalid_sockets]})
    if request.engine in {"godot", "web"} and manifest["metrics"]["collision_pair_count"]:
        findings.append({"severity": "info", "code": "collision_metadata_review", "message": f"Review collision metadata after {request.engine} import; GLTF importers vary in collision handling."})

    severity_summary = _summarize_findings(findings)
    return success_result(
        request_id=request.request_id,
        tool_name="validate_engine_export_package",
        summary=f"Validated game export package for {request.engine}.",
        project_id=project.project_id,
        engine=request.engine,
        package_name=request.package_name,
        expected_format=expected_format,
        active_export_profile=profile,
        manifest=manifest,
        findings=findings,
        severity_summary=severity_summary,
        engine_ready=severity_summary.get("error", 0) == 0,
    )


async def plan_engine_import_checklist(context, request: PlanEngineImportChecklistRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    validation_payload: dict[str, Any] | None = None
    if request.include_validation:
        validation = await validate_engine_export_package(
            context,
            ValidateEngineExportPackageRequest(
                request_id=f"{request.request_id}-validation",
                project_id=project.project_id,
                engine=request.engine,
                package_name=request.package_name,
            ),
        )
        if validation.status != "success":
            payload = validation.model_dump()
            payload["tool_name"] = "plan_engine_import_checklist"
            return type(validation).model_validate(payload)
        validation_payload = validation.model_dump()
    checklist = _engine_import_checklist(request.engine)
    return success_result(
        request_id=request.request_id,
        tool_name="plan_engine_import_checklist",
        summary=f"Planned {request.engine} import checklist for package '{request.package_name}'.",
        project_id=project.project_id,
        engine=request.engine,
        package_name=request.package_name,
        checklist=checklist,
        validation=validation_payload,
    )


def _strip_lod_suffix(name: str) -> str:
    stripped = re.sub(r"([_-])LOD\d+$", "", name, flags=re.IGNORECASE)
    return stripped or name


def _result_objects(payload: dict[str, Any]) -> list[dict[str, Any]]:
    objects = list(payload.get("objects", []))
    if not objects and isinstance(payload.get("object"), dict):
        objects.append(payload["object"])
    return objects


def _is_collision_object(item: dict[str, Any]) -> bool:
    name = str(item.get("name", "")).upper()
    tags = {str(tag).lower() for tag in item.get("tags", [])}
    return name.startswith(_COLLISION_PREFIXES) or "collision" in tags or any(tag.startswith("collision:") for tag in tags)


def _lod_level(item: dict[str, Any]) -> int | None:
    tags = [str(tag).lower() for tag in item.get("tags", [])]
    for tag in tags:
        if tag.startswith("lod:"):
            try:
                return int(tag.split(":", 1)[1])
            except ValueError:
                return None
    match = _LOD_PATTERN.search(str(item.get("name", "")))
    return int(match.group("level")) if match else None


def _lod_group_name(item: dict[str, Any]) -> str:
    for tag in item.get("tags", []):
        tag_text = str(tag)
        if tag_text.startswith("lod_group:"):
            return tag_text.split(":", 1)[1]
    return _strip_lod_suffix(str(item.get("name", "LODGroup"))) or "LODGroup"


def _tag_value(item: dict[str, Any], prefix: str) -> str | None:
    for tag in item.get("tags", []):
        tag_text = str(tag)
        if tag_text.startswith(prefix):
            return tag_text.split(":", 1)[1]
    return None


def _export_role(item: dict[str, Any]) -> str:
    role = _tag_value(item, "export_role:")
    if role is not None:
        return role
    if _is_collision_object(item):
        return "collision"
    if _tag_value(item, "socket:") is not None:
        return "socket"
    if _lod_level(item) is not None:
        return "lod"
    return "render"


def _engine_expected_format(engine: EngineProfileName) -> str:
    return "fbx" if engine in {"unreal", "unity"} else "glb"


def _manifest_object_name(manifest: dict[str, Any], object_id: str | None) -> str | None:
    if object_id is None:
        return None
    for item in manifest.get("objects", []):
        if item.get("object_id") == object_id:
            return str(item.get("name"))
    return None


def _engine_import_checklist(engine: EngineProfileName) -> list[dict[str, Any]]:
    shared = [
        {"id": "verify_scale", "label": "Verify imported scale and unit conversion."},
        {"id": "verify_materials", "label": "Check material slot assignment and texture relinking."},
        {"id": "verify_lods", "label": "Confirm LOD objects or groups imported with expected order."},
    ]
    engine_specific = {
        "unreal": [
            {"id": "unreal_collision_prefix", "label": "Confirm UCX/UBX/UCP/USP collision meshes are recognized."},
            {"id": "unreal_sockets", "label": "Confirm SOCKET_ markers became sockets on the static mesh."},
        ],
        "unity": [
            {"id": "unity_prefab_root", "label": "Create a prefab root and check model import scale."},
            {"id": "unity_colliders", "label": "Map collision meshes or add collider components."},
        ],
        "godot": [
            {"id": "godot_import_flags", "label": "Review mesh import flags and material remapping."},
            {"id": "godot_collision_nodes", "label": "Create collision nodes from collision metadata where needed."},
        ],
        "web": [
            {"id": "web_binary_size", "label": "Check GLB size and texture compression budget."},
            {"id": "web_runtime_materials", "label": "Verify runtime material compatibility in the target viewer."},
        ],
    }
    return [*shared, *engine_specific[engine]]


async def _build_game_export_manifest(context, request: PlanGameExportPackageRequest) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    objects = await list_project_objects(context, request.project_id)
    readiness = await validate_game_export_readiness(
        context,
        ValidateGameExportReadinessRequest(
            request_id=f"{request.request_id}-readiness",
            project_id=request.project_id,
            require_collision=request.require_collision,
            require_lods=request.require_lods,
            require_materials=request.require_materials,
        ),
    )
    lod_groups: dict[str, dict[str, Any]] = {}
    collision_pairs: list[dict[str, Any]] = []
    socket_markers: list[dict[str, Any]] = []
    export_objects: list[dict[str, Any]] = []
    for item in objects:
        object_id = str(item.get("object_id"))
        role = _export_role(item)
        level = _lod_level(item)
        if level is not None:
            group_name = _lod_group_name(item)
            group = lod_groups.setdefault(group_name, {"group_name": group_name, "levels": {}, "object_ids": []})
            group["levels"][str(level)] = object_id
            group["object_ids"].append(object_id)
        if role == "collision":
            collision_pairs.append({"collision_object_id": object_id, "source_object_id": _tag_value(item, "collision_source:"), "collision_role": _tag_value(item, "collision_role:")})
        if role == "socket":
            socket_markers.append({"socket_object_id": object_id, "socket_name": _tag_value(item, "socket:"), "source_object_id": _tag_value(item, "socket_source:")})
        export_objects.append(
            {
                "object_id": object_id,
                "name": item.get("name"),
                "type": item.get("type"),
                "role": role,
                "lod_level": level,
                "collection": item.get("collection"),
                "material_ids": item.get("material_ids", []),
            }
        )
    return {
        "package_name": request.package_name,
        "project_id": request.project_id,
        "objects": export_objects,
        "lod_groups": sorted(lod_groups.values(), key=lambda group: group["group_name"]),
        "collision_pairs": collision_pairs,
        "socket_markers": socket_markers,
        "readiness": readiness.model_dump(),
        "metrics": {
            "object_count": len(objects),
            "export_object_count": len(export_objects),
            "lod_group_count": len(lod_groups),
            "collision_pair_count": len(collision_pairs),
            "socket_marker_count": len(socket_markers),
        },
    }


def _manifest_output_path(context, project, raw_output_path: str | None, package_name: str) -> Path:  # type: ignore[no-untyped-def]
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    export_dir = project_paths.export_dir.resolve()
    relative_path = Path(raw_output_path) if raw_output_path else Path(f"{slugify(package_name) or 'game_export'}-manifest.json")
    candidate = relative_path.resolve(strict=False) if relative_path.is_absolute() else (export_dir / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(export_dir)
    except ValueError as exc:
        raise WorkspaceViolationError("Game export manifest path must stay under the project's export directory.") from exc
    if candidate.suffix.lower() != ".json":
        candidate = candidate.with_suffix(".json")
    return candidate


def _duplicate_names(objects: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for item in objects:
        name = str(item.get("name", ""))
        counts[name] = counts.get(name, 0) + 1
    return sorted(name for name, count in counts.items() if name and count > 1)


def _has_non_unit_scale(item: dict[str, Any]) -> bool:
    return any(abs(float(component) - 1.0) > 0.0001 for component in item.get("scale", [1.0, 1.0, 1.0]))


def _summarize_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in summary:
            summary[severity] += 1
    return summary


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("assign_lod_level", "Tag and optionally rename resolved objects as a LOD level.", AssignLODLevelRequest, assign_lod_level, False),
        ("create_lod_chain", "Duplicate a mesh into a tagged LOD chain using decimate helpers.", CreateLODChainRequest, create_lod_chain, False),
        ("create_collision_proxy", "Create a non-destructive collision proxy around target bounds.", CreateCollisionProxyRequest, create_collision_proxy, False),
        ("create_collision_proxy_set", "Create collision proxy sets around resolved targets.", CreateCollisionProxySetRequest, create_collision_proxy_set, False),
        ("create_socket_marker", "Create a game-engine socket marker on a target.", CreateSocketMarkerRequest, create_socket_marker, False),
        ("assign_collision_role", "Tag and optionally rename resolved objects with a collision role.", AssignCollisionRoleRequest, assign_collision_role, False),
        ("tag_game_export_role", "Tag resolved objects with a game-export role.", TagGameExportRoleRequest, tag_game_export_role, False),
        ("normalize_game_asset_names", "Rename resolved objects into deterministic game-asset names.", NormalizeGameAssetNamesRequest, normalize_game_asset_names, False),
        ("validate_game_export_readiness", "Inspect game-export naming, LOD, collision, scale, and material readiness.", ValidateGameExportReadinessRequest, validate_game_export_readiness, True),
        ("validate_lod_chain", "Validate LOD group coverage and duplicate levels.", ValidateLODChainRequest, validate_lod_chain, True),
        ("plan_game_export_package", "Plan a game export package manifest without writing files.", PlanGameExportPackageRequest, plan_game_export_package, True),
        ("write_game_export_manifest", "Write a project-scoped game export manifest JSON file.", WriteGameExportManifestRequest, write_game_export_manifest, False),
        ("set_game_export_profile", "Apply game-oriented export profile defaults.", SetGameExportProfileRequest, set_game_export_profile, False),
        ("set_engine_export_profile", "Apply engine-specific game export profile defaults.", SetEngineExportProfileRequest, set_engine_export_profile, False),
        ("validate_engine_export_package", "Validate a game export package against engine-specific expectations.", ValidateEngineExportPackageRequest, validate_engine_export_package, True),
        ("plan_engine_import_checklist", "Plan an engine-specific import checklist for a game export package.", PlanEngineImportChecklistRequest, plan_engine_import_checklist, True),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="game_prep",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
