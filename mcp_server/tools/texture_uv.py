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
from mcp_server.tools.helpers import project_paths_for_record, require_project, resolve_target_ids
from mcp_server.tools.material import (
    ApplyMaterialRequest,
    CreatePBRMaterialRequest,
    apply_material,
    create_pbr_material,
)
from mcp_server.utils import new_id, slugify
from mcp_server.workspace import WorkspaceViolationError


class UnwrapUVRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    method: str = "smart"
    margin: float = Field(default=0.02, ge=0.0)


class PackUVRequest(CommonToolRequest):
    project_id: str
    uv_map_ids: list[str] = Field(default_factory=list)
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    padding: float = Field(default=0.02, ge=0.0)


class InspectUVRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)


class ApplyTextureRequest(CommonToolRequest):
    project_id: str
    texture_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)


class CreateProceduralTextureRequest(CommonToolRequest):
    project_id: str
    name: str
    texture_type: str = "noise"
    scale: float = Field(default=5.0, gt=0.0)
    colors: list[list[float]] = Field(default_factory=lambda: [[0.78, 0.78, 0.82, 1.0], [0.18, 0.2, 0.24, 1.0]])


class BakeTextureRequest(CommonToolRequest):
    project_id: str
    target_id: str
    texture_id: str | None = None
    bake_type: str = "base_color"
    output_path: str | None = None


class UVMapQueryRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)


class RenameUVMapRequest(CommonToolRequest):
    project_id: str
    uv_map_id: str
    name: str


class SetUVDensityRequest(UVMapQueryRequest):
    uv_map_ids: list[str] = Field(default_factory=list)
    texels_per_unit: float = Field(default=512.0, gt=0.0)
    texture_resolution: int = Field(default=2048, ge=64, le=32768)


class AssignUDIMTileRequest(UVMapQueryRequest):
    uv_map_ids: list[str] = Field(default_factory=list)
    tile_number: int = Field(default=1001, ge=1001, le=1999)
    tile_label: str | None = None


class CreateUDIMTilePlanRequest(UVMapQueryRequest):
    name: str = "UDIM Plan"
    start_tile: int = Field(default=1001, ge=1001, le=1999)
    columns: int = Field(default=10, ge=1, le=10)
    create_missing_uv_maps: bool = True


class MirrorUVLayoutRequest(UVMapQueryRequest):
    uv_map_ids: list[str] = Field(default_factory=list)
    axis: Literal["u", "v"] = "u"
    keep_overlaps: bool = False


class GenerateTextureSetManifestRequest(UVMapQueryRequest):
    name: str = "Texture Set"
    uv_map_ids: list[str] = Field(default_factory=list)
    texture_ids: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=lambda: ["base_color", "normal", "roughness", "metallic"])
    target_resolution: int = Field(default=2048, ge=64, le=32768)


class PlanTextureBakeRequest(UVMapQueryRequest):
    channels: list[str] = Field(default_factory=lambda: ["base_color", "normal", "roughness", "metallic"])
    target_resolution: int = Field(default=2048, ge=64, le=32768)
    require_uvs: bool = True


class BakeTextureSetRequest(CommonToolRequest):
    project_id: str
    target_id: str
    texture_id: str | None = None
    channels: list[str] = Field(default_factory=lambda: ["base_color", "normal", "roughness", "metallic"])
    output_prefix: str | None = None
    target_resolution: int = Field(default=2048, ge=64, le=32768)


class CreateTextureAtlasManifestRequest(UVMapQueryRequest):
    name: str = "Texture Atlas"
    atlas_resolution: int = Field(default=4096, ge=64, le=32768)
    padding: float = Field(default=0.02, ge=0.0)


class CreateTrimSheetManifestRequest(UVMapQueryRequest):
    name: str = "Trim Sheet"
    row_count: int = Field(default=4, ge=1, le=32)
    column_count: int = Field(default=4, ge=1, le=32)
    target_resolution: int = Field(default=2048, ge=64, le=32768)


class ValidateUVLayoutRequest(UVMapQueryRequest):
    min_utilization: float = Field(default=0.5, ge=0.0, le=1.0)
    require_packed: bool = True
    require_udim: bool = False


def _project_scoped_output_path(export_dir: Path, raw_output_path: Path) -> Path:
    resolved_root = export_dir.resolve()
    candidate = raw_output_path.resolve(strict=False) if raw_output_path.is_absolute() else (export_dir / raw_output_path).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise WorkspaceViolationError("Bake output path must stay under the project's export directory.") from exc
    return candidate


def _uv_map_specs_for_targets(context, project_id: str, target_ids: list[str]) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    uv_maps: list[dict[str, Any]] = []
    for record in context.entities.list_by_type(project_id, "uv_map"):
        spec = load_entity_spec(context, record.entity_id, expected_type="uv_map")
        if spec is not None and spec.get("target_id") in target_ids:
            uv_maps.append(spec)
    return uv_maps


def _has_uv_target_filter(request: Any) -> bool:
    return bool(getattr(request, "target_id", None) or getattr(request, "target_ids", []) or getattr(request, "names", []))


def _all_uv_map_specs(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, "uv_map")


def _load_uv_map(context, project_id: str, uv_map_id: str) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    record = context.entities.get(uv_map_id)
    if record is None or record.project_id != project_id or record.entity_type != "uv_map":
        return None
    return load_entity_spec(context, uv_map_id, expected_type="uv_map")


def _save_uv_map(context, project_id: str, uv_map: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    name = str(uv_map.get("name") or f"UV_{uv_map.get('target_id', uv_map['uv_map_id'])}")
    uv_map["name"] = name
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(uv_map["uv_map_id"]),
        entity_type="uv_map",
        name=name,
        spec=uv_map,
    )


async def _resolve_uv_target_ids(context, request: Any) -> list[str]:  # type: ignore[no-untyped-def]
    if not _has_uv_target_filter(request):
        return []
    return await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=getattr(request, "target_ids", []) or ([request.target_id] if getattr(request, "target_id", None) else []),
        names=getattr(request, "names", []),
    )


async def _resolve_uv_maps(context, request: Any, *, tool_name: str) -> list[dict[str, Any]] | CommonToolResult:  # type: ignore[no-untyped-def]
    uv_map_ids = list(getattr(request, "uv_map_ids", []) or [])
    if uv_map_ids:
        uv_maps: list[dict[str, Any]] = []
        for uv_map_id in uv_map_ids:
            uv_map = _load_uv_map(context, request.project_id, str(uv_map_id))
            if uv_map is None:
                return failed_result(
                    request_id=request.request_id,
                    tool_name=tool_name,
                    summary=f"UV map '{uv_map_id}' was not found.",
                    errors=[f"target_not_found: UV map '{uv_map_id}' does not exist"],
                )
            uv_maps.append(uv_map)
        return uv_maps
    target_ids = await _resolve_uv_target_ids(context, request)
    if target_ids:
        return _uv_map_specs_for_targets(context, request.project_id, target_ids)
    return _all_uv_map_specs(context, request.project_id)


def _uv_findings(uv_maps: list[dict[str, Any]], *, min_utilization: float, require_packed: bool, require_udim: bool) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not uv_maps:
        findings.append({"severity": "error", "code": "no_uv_maps", "message": "No managed UV maps were found."})
        return findings
    for uv_map in uv_maps:
        uv_map_id = uv_map.get("uv_map_id")
        utilization = float(uv_map.get("utilization", 0.0))
        if utilization < min_utilization:
            findings.append(
                {
                    "severity": "warning",
                    "code": "low_utilization",
                    "message": f"UV map {uv_map_id} utilization is below {min_utilization:g}.",
                    "uv_map_id": uv_map_id,
                    "utilization": utilization,
                }
            )
        if require_packed and not uv_map.get("packed", False):
            findings.append(
                {"severity": "warning", "code": "not_packed", "message": f"UV map {uv_map_id} is not packed.", "uv_map_id": uv_map_id}
            )
        if require_udim and uv_map.get("udim_tile") is None:
            findings.append(
                {"severity": "warning", "code": "missing_udim", "message": f"UV map {uv_map_id} has no UDIM tile assignment.", "uv_map_id": uv_map_id}
            )
    return findings


def _severity_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in summary:
            summary[severity] += 1
    return summary


def _texture_palette(texture_type: str, colors: list[list[float]]) -> tuple[list[float], float, float, list[float] | None, float | None]:
    primary = colors[0] if colors else [0.78, 0.78, 0.82, 1.0]
    secondary = colors[1] if len(colors) > 1 else [0.18, 0.2, 0.24, 1.0]
    normalized = texture_type.strip().lower()
    if normalized == "checker":
        return primary, 0.75, 0.0, secondary, 0.0
    if normalized == "brick":
        return [0.58, 0.22, 0.16, 1.0], 0.9, 0.0, None, None
    if normalized == "gradient":
        return primary, 0.4, 0.0, None, None
    return primary, 0.62, 0.0, None, None


async def unwrap_uv(context, request: UnwrapUVRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
    )
    uv_maps: list[dict[str, Any]] = []
    created_uv_map_ids: list[str] = []
    for target_id in target_ids:
        target = load_entity_spec(context, str(target_id))
        if target is None:
            return failed_result(
                request_id=request.request_id,
                tool_name="unwrap_uv",
                summary=f"Target '{target_id}' was not found.",
                errors=[f"target_not_found: target '{target_id}' does not exist"],
            )
        face_count = len(target.get("data", {}).get("faces", []))
        uv_map_id = new_id("uv")
        uv_map = {
            "uv_map_id": uv_map_id,
            "project_id": project.project_id,
            "name": f"UV_{target.get('name', target_id)}",
            "target_id": target_id,
            "method": request.method,
            "margin": request.margin,
            "island_count": max(1, face_count // 6 or 1),
            "packed": False,
            "utilization": round(min(0.92, 0.45 + (face_count * 0.02)), 3),
        }
        _save_uv_map(context, project.project_id, uv_map)
        uv_maps.append(uv_map)
        created_uv_map_ids.append(uv_map_id)
    return success_result(
        request_id=request.request_id,
        tool_name="unwrap_uv",
        summary=f"Generated {len(uv_maps)} UV maps.",
        project_id=project.project_id,
        target_ids=target_ids,
        created_uv_map_ids=created_uv_map_ids,
        uv_maps=uv_maps,
    )


async def pack_uv(context, request: PackUVRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    uv_map_ids = list(request.uv_map_ids)
    if not uv_map_ids:
        target_ids = await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        )
        uv_map_ids = [uv_map["uv_map_id"] for uv_map in _uv_map_specs_for_targets(context, request.project_id, target_ids)]
    if not uv_map_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="pack_uv",
            summary="No UV maps were resolved for packing.",
            errors=["target_not_found: no UV maps were resolved for packing"],
        )
    uv_maps: list[dict[str, Any]] = []
    for uv_map_id in uv_map_ids:
        uv_map = load_entity_spec(context, str(uv_map_id), expected_type="uv_map")
        if uv_map is None:
            return failed_result(
                request_id=request.request_id,
                tool_name="pack_uv",
                summary=f"UV map '{uv_map_id}' was not found.",
                errors=[f"target_not_found: UV map '{uv_map_id}' does not exist"],
            )
        uv_map["packed"] = True
        uv_map["padding"] = request.padding
        uv_map["utilization"] = round(max(uv_map.get("utilization", 0.5), 0.82 - request.padding), 3)
        _save_uv_map(context, project.project_id, uv_map)
        uv_maps.append(uv_map)
    return success_result(
        request_id=request.request_id,
        tool_name="pack_uv",
        summary=f"Packed {len(uv_maps)} UV maps.",
        project_id=project.project_id,
        uv_maps=uv_maps,
        uv_map_ids=uv_map_ids,
    )


async def inspect_uv(context, request: InspectUVRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
    )
    uv_maps = _uv_map_specs_for_targets(context, request.project_id, target_ids)
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_uv",
        summary=f"Inspected UV state for {len(target_ids)} target objects.",
        project_id=request.project_id,
        target_ids=target_ids,
        uv_maps=uv_maps,
        count=len(uv_maps),
    )


async def create_procedural_texture(context, request: CreateProceduralTextureRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    base_color, roughness, metallic, emission_color, emission_strength = _texture_palette(request.texture_type, request.colors)
    material_result = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.name}_Material",
            base_color=base_color,
            roughness=roughness,
            metallic=metallic,
            emission_color=emission_color,
            emission_strength=emission_strength,
        ),
    )
    if material_result.status != "success":
        return material_result
    texture_id = new_id("texture")
    material = material_result.model_dump()["material"]
    texture = {
        "texture_id": texture_id,
        "name": request.name,
        "texture_type": request.texture_type,
        "scale": request.scale,
        "colors": request.colors,
        "material_id": material["material_id"],
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=texture_id,
        entity_type="texture",
        name=request.name,
        spec=texture,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_procedural_texture",
        summary=f"Created procedural texture '{request.name}'.",
        project_id=project.project_id,
        texture_id=texture_id,
        texture=texture,
        material=material,
    )


async def apply_texture(context, request: ApplyTextureRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    texture = load_entity_spec(context, request.texture_id, expected_type="texture")
    if texture is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="apply_texture",
            summary=f"Texture '{request.texture_id}' was not found.",
            errors=[f"target_not_found: texture '{request.texture_id}' does not exist"],
        )
    target_ids = await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
    )
    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            material_id=str(texture["material_id"]),
            target_ids=target_ids,
        ),
    )
    if applied.status not in {"success", "partial_success"}:
        return applied
    payload = applied.model_dump()
    payload["tool_name"] = "apply_texture"
    payload["texture_id"] = request.texture_id
    payload["texture"] = texture
    payload["summary"] = f"Applied texture '{texture['name']}' to {len(target_ids)} objects."
    return type(applied).model_validate(payload)


async def bake_texture(context, request: BakeTextureRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    explicit_output_path: str | Path | None = request.output_path
    if request.output_path is not None:
        explicit_output_path = _project_scoped_output_path(project_paths.export_dir, Path(request.output_path))
    output_path = (
        context.workspace.canonicalize_output_path(explicit_output_path, allowed_extensions=[".png"])
        if explicit_output_path is not None
        else context.workspace.canonicalize_output_path(
            project_paths.export_dir / f"{slugify(request.request_id)}-{slugify(request.bake_type)}.png",
            allowed_extensions=[".png"],
        )
    )
    write_placeholder_png(output_path)
    texture = load_entity_spec(context, request.texture_id, expected_type="texture") if request.texture_id is not None else None
    export_record = context.export_records.create(
        export_id=new_id("export"),
        project_id=project.project_id,
        entity_id=request.target_id,
        format="png",
        output_path=str(output_path),
        metadata={
            "scope": "texture_bake",
            "target_id": request.target_id,
            "texture_id": request.texture_id,
            "bake_type": request.bake_type,
        },
        warnings=[],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="bake_texture",
        summary=f"Baked {request.bake_type} texture output.",
        project_id=project.project_id,
        target_id=request.target_id,
        texture=texture,
        export_id=export_record.export_id,
        file_paths=[str(output_path)],
    )


async def list_uv_maps(context, request: UVMapQueryRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, request.project_id, target_ids) if target_ids else _all_uv_map_specs(context, request.project_id)
    return success_result(
        request_id=request.request_id,
        tool_name="list_uv_maps",
        summary=f"Listed {len(uv_maps)} UV maps.",
        project_id=request.project_id,
        target_ids=target_ids,
        uv_maps=uv_maps,
        count=len(uv_maps),
    )


async def rename_uv_map(context, request: RenameUVMapRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    uv_map = _load_uv_map(context, project.project_id, request.uv_map_id)
    if uv_map is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="rename_uv_map",
            summary=f"UV map '{request.uv_map_id}' was not found.",
            errors=[f"target_not_found: UV map '{request.uv_map_id}' does not exist"],
        )
    old_name = str(uv_map.get("name", request.uv_map_id))
    uv_map["name"] = request.name
    _save_uv_map(context, project.project_id, uv_map)
    return success_result(
        request_id=request.request_id,
        tool_name="rename_uv_map",
        summary=f"Renamed UV map '{old_name}' to '{request.name}'.",
        project_id=project.project_id,
        uv_map=uv_map,
        old_name=old_name,
    )


async def set_uv_density(context, request: SetUVDensityRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    uv_maps = await _resolve_uv_maps(context, request, tool_name="set_uv_density")
    if isinstance(uv_maps, CommonToolResult):
        return uv_maps
    if not uv_maps:
        return failed_result(request_id=request.request_id, tool_name="set_uv_density", summary="No UV maps were resolved.", errors=["target_not_found: no UV maps were resolved"])
    updated: list[dict[str, Any]] = []
    for uv_map in uv_maps:
        uv_map["texels_per_unit"] = request.texels_per_unit
        uv_map["texture_resolution"] = request.texture_resolution
        uv_map["density_ratio"] = round(request.texels_per_unit / float(request.texture_resolution), 6)
        updated.append(_save_uv_map(context, project.project_id, uv_map))
    return success_result(
        request_id=request.request_id,
        tool_name="set_uv_density",
        summary=f"Updated texel density on {len(updated)} UV maps.",
        project_id=project.project_id,
        uv_maps=updated,
        uv_map_ids=[item["uv_map_id"] for item in updated],
    )


async def assign_udim_tile(context, request: AssignUDIMTileRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    uv_maps = await _resolve_uv_maps(context, request, tool_name="assign_udim_tile")
    if isinstance(uv_maps, CommonToolResult):
        return uv_maps
    if not uv_maps:
        return failed_result(request_id=request.request_id, tool_name="assign_udim_tile", summary="No UV maps were resolved.", errors=["target_not_found: no UV maps were resolved"])
    updated: list[dict[str, Any]] = []
    for offset, uv_map in enumerate(uv_maps):
        uv_map["udim_tile"] = request.tile_number + offset
        uv_map["udim_label"] = request.tile_label or str(uv_map["udim_tile"])
        updated.append(_save_uv_map(context, project.project_id, uv_map))
    return success_result(
        request_id=request.request_id,
        tool_name="assign_udim_tile",
        summary=f"Assigned UDIM tiles to {len(updated)} UV maps.",
        project_id=project.project_id,
        uv_maps=updated,
        uv_map_ids=[item["uv_map_id"] for item in updated],
    )


async def create_udim_tile_plan(context, request: CreateUDIMTilePlanRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, project.project_id, target_ids) if target_ids else _all_uv_map_specs(context, project.project_id)
    if target_ids and request.create_missing_uv_maps:
        existing_targets = {str(uv_map.get("target_id")) for uv_map in uv_maps}
        for target_id in target_ids:
            if target_id in existing_targets:
                continue
            target = load_entity_spec(context, target_id)
            if target is None:
                continue
            uv_map = {
                "uv_map_id": new_id("uv"),
                "project_id": project.project_id,
                "name": f"UV_{target.get('name', target_id)}",
                "target_id": target_id,
                "method": "managed_udim",
                "margin": 0.02,
                "island_count": 1,
                "packed": False,
                "utilization": 0.5,
            }
            uv_maps.append(_save_uv_map(context, project.project_id, uv_map))
    if not uv_maps:
        return failed_result(request_id=request.request_id, tool_name="create_udim_tile_plan", summary="No UV maps were available for a UDIM plan.", errors=["target_not_found: no UV maps were available"])
    assignments: list[dict[str, Any]] = []
    for index, uv_map in enumerate(uv_maps):
        tile = request.start_tile + (index % request.columns) + ((index // request.columns) * 10)
        uv_map["udim_tile"] = tile
        uv_map["udim_plan"] = request.name
        _save_uv_map(context, project.project_id, uv_map)
        assignments.append({"uv_map_id": uv_map["uv_map_id"], "target_id": uv_map.get("target_id"), "tile_number": tile})
    plan_id = new_id("udim")
    plan = {
        "udim_plan_id": plan_id,
        "project_id": project.project_id,
        "name": request.name,
        "start_tile": request.start_tile,
        "columns": request.columns,
        "assignments": assignments,
    }
    save_metadata_entity(context, project_id=project.project_id, entity_id=plan_id, entity_type="udim_tile_plan", name=request.name, spec=plan)
    return success_result(
        request_id=request.request_id,
        tool_name="create_udim_tile_plan",
        summary=f"Created UDIM plan '{request.name}' for {len(assignments)} UV maps.",
        project_id=project.project_id,
        udim_plan_id=plan_id,
        udim_plan=plan,
        uv_maps=uv_maps,
    )


async def mirror_uv_layout(context, request: MirrorUVLayoutRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    uv_maps = await _resolve_uv_maps(context, request, tool_name="mirror_uv_layout")
    if isinstance(uv_maps, CommonToolResult):
        return uv_maps
    if not uv_maps:
        return failed_result(request_id=request.request_id, tool_name="mirror_uv_layout", summary="No UV maps were resolved.", errors=["target_not_found: no UV maps were resolved"])
    updated: list[dict[str, Any]] = []
    for uv_map in uv_maps:
        history = list(uv_map.get("mirror_history", []))
        history.append({"axis": request.axis, "keep_overlaps": request.keep_overlaps})
        uv_map["mirrored"] = True
        uv_map["mirror_axis"] = request.axis
        uv_map["keep_overlaps"] = request.keep_overlaps
        uv_map["mirror_history"] = history
        updated.append(_save_uv_map(context, project.project_id, uv_map))
    return success_result(
        request_id=request.request_id,
        tool_name="mirror_uv_layout",
        summary=f"Mirrored {len(updated)} UV layouts across {request.axis.upper()}.",
        project_id=project.project_id,
        uv_maps=updated,
    )


async def generate_texture_set_manifest(context, request: GenerateTextureSetManifestRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_map_ids = list(request.uv_map_ids)
    if not uv_map_ids and target_ids:
        uv_map_ids = [str(item["uv_map_id"]) for item in _uv_map_specs_for_targets(context, project.project_id, target_ids)]
    textures = []
    for texture_id in request.texture_ids:
        texture = load_entity_spec(context, texture_id, expected_type="texture")
        if texture is None:
            return failed_result(request_id=request.request_id, tool_name="generate_texture_set_manifest", summary=f"Texture '{texture_id}' was not found.", errors=[f"target_not_found: texture '{texture_id}' does not exist"])
        textures.append(texture)
    manifest_id = new_id("texset")
    manifest = {
        "texture_set_id": manifest_id,
        "project_id": project.project_id,
        "name": request.name,
        "target_ids": target_ids,
        "uv_map_ids": uv_map_ids,
        "texture_ids": request.texture_ids,
        "channels": request.channels,
        "target_resolution": request.target_resolution,
        "textures": textures,
    }
    save_metadata_entity(context, project_id=project.project_id, entity_id=manifest_id, entity_type="texture_set_manifest", name=request.name, spec=manifest)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_texture_set_manifest",
        summary=f"Generated texture set manifest '{request.name}'.",
        project_id=project.project_id,
        texture_set_id=manifest_id,
        texture_set_manifest=manifest,
    )


async def plan_texture_bake(context, request: PlanTextureBakeRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, request.project_id, target_ids) if target_ids else _all_uv_map_specs(context, request.project_id)
    findings: list[dict[str, Any]] = []
    if request.require_uvs and not uv_maps:
        findings.append({"severity": "warning", "code": "missing_uv_maps", "message": "No managed UV maps were found for texture baking."})
    unpacked = [uv_map["uv_map_id"] for uv_map in uv_maps if not uv_map.get("packed", False)]
    if unpacked:
        findings.append({"severity": "warning", "code": "unpacked_uv_maps", "message": f"{len(unpacked)} UV maps are not packed.", "uv_map_ids": unpacked})
    bake_jobs = [
        {
            "target_id": target_id,
            "channels": list(request.channels),
            "target_resolution": request.target_resolution,
            "uv_map_ids": [uv_map["uv_map_id"] for uv_map in uv_maps if uv_map.get("target_id") == target_id],
        }
        for target_id in target_ids
    ]
    return success_result(
        request_id=request.request_id,
        tool_name="plan_texture_bake",
        summary=f"Planned {len(bake_jobs)} texture bake job(s).",
        project_id=request.project_id,
        target_ids=target_ids,
        uv_maps=uv_maps,
        bake_jobs=bake_jobs,
        findings=findings,
        severity_summary=_severity_summary(findings),
    )


async def bake_texture_set(context, request: BakeTextureSetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    channels = list(dict.fromkeys(request.channels)) or ["base_color"]
    output_prefix = request.output_prefix or f"{slugify(request.request_id)}-{slugify(request.target_id)}"
    bakes: list[dict[str, Any]] = []
    file_paths: list[str] = []
    for channel in channels:
        channel_slug = slugify(channel) or "channel"
        baked = await bake_texture(
            context,
            BakeTextureRequest(
                request_id=f"{request.request_id}-{channel_slug}",
                project_id=project.project_id,
                target_id=request.target_id,
                texture_id=request.texture_id,
                bake_type=channel,
                output_path=f"{output_prefix}-{channel_slug}.png",
            ),
        )
        if baked.status != "success":
            payload = baked.model_dump()
            payload["tool_name"] = "bake_texture_set"
            return type(baked).model_validate(payload)
        payload = baked.model_dump()
        bakes.append(payload)
        file_paths.extend(payload.get("file_paths", []))
    texture_set_id = new_id("bakeset")
    texture_set = {
        "texture_set_id": texture_set_id,
        "project_id": project.project_id,
        "target_id": request.target_id,
        "texture_id": request.texture_id,
        "channels": channels,
        "target_resolution": request.target_resolution,
        "file_paths": file_paths,
    }
    save_metadata_entity(context, project_id=project.project_id, entity_id=texture_set_id, entity_type="baked_texture_set", name=output_prefix, spec=texture_set)
    return success_result(
        request_id=request.request_id,
        tool_name="bake_texture_set",
        summary=f"Baked {len(channels)} texture channels for target '{request.target_id}'.",
        project_id=project.project_id,
        target_id=request.target_id,
        texture_set_id=texture_set_id,
        baked_texture_set=texture_set,
        file_paths=file_paths,
        bakes=bakes,
    )


async def create_texture_atlas_manifest(context, request: CreateTextureAtlasManifestRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, project.project_id, target_ids) if target_ids else _all_uv_map_specs(context, project.project_id)
    atlas_id = new_id("atlas")
    atlas = {
        "texture_atlas_id": atlas_id,
        "project_id": project.project_id,
        "name": request.name,
        "target_ids": target_ids,
        "uv_map_ids": [uv_map["uv_map_id"] for uv_map in uv_maps],
        "atlas_resolution": request.atlas_resolution,
        "padding": request.padding,
        "slots": [
            {"slot_index": index, "uv_map_id": uv_map["uv_map_id"], "target_id": uv_map.get("target_id")}
            for index, uv_map in enumerate(uv_maps)
        ],
    }
    save_metadata_entity(context, project_id=project.project_id, entity_id=atlas_id, entity_type="texture_atlas_manifest", name=request.name, spec=atlas)
    return success_result(request_id=request.request_id, tool_name="create_texture_atlas_manifest", summary=f"Created texture atlas manifest '{request.name}'.", project_id=project.project_id, texture_atlas_id=atlas_id, texture_atlas_manifest=atlas)


async def create_trim_sheet_manifest(context, request: CreateTrimSheetManifestRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, project.project_id, target_ids) if target_ids else _all_uv_map_specs(context, project.project_id)
    trim_sheet_id = new_id("trim")
    cells = []
    for row in range(request.row_count):
        for column in range(request.column_count):
            cells.append({"row": row, "column": column, "label": f"R{row:02d}_C{column:02d}"})
    trim_sheet = {
        "trim_sheet_id": trim_sheet_id,
        "project_id": project.project_id,
        "name": request.name,
        "target_ids": target_ids,
        "uv_map_ids": [uv_map["uv_map_id"] for uv_map in uv_maps],
        "row_count": request.row_count,
        "column_count": request.column_count,
        "target_resolution": request.target_resolution,
        "cells": cells,
    }
    save_metadata_entity(context, project_id=project.project_id, entity_id=trim_sheet_id, entity_type="trim_sheet_manifest", name=request.name, spec=trim_sheet)
    return success_result(request_id=request.request_id, tool_name="create_trim_sheet_manifest", summary=f"Created trim sheet manifest '{request.name}'.", project_id=project.project_id, trim_sheet_id=trim_sheet_id, trim_sheet_manifest=trim_sheet)


async def validate_uv_layout(context, request: ValidateUVLayoutRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    target_ids = await _resolve_uv_target_ids(context, request)
    uv_maps = _uv_map_specs_for_targets(context, request.project_id, target_ids) if target_ids else _all_uv_map_specs(context, request.project_id)
    findings = _uv_findings(uv_maps, min_utilization=request.min_utilization, require_packed=request.require_packed, require_udim=request.require_udim)
    return success_result(
        request_id=request.request_id,
        tool_name="validate_uv_layout",
        summary="UV layout validation completed.",
        project_id=request.project_id,
        target_ids=target_ids,
        uv_maps=uv_maps,
        findings=findings,
        severity_summary=_severity_summary(findings),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("unwrap_uv", "Create managed UV metadata for one or more mesh targets.", UnwrapUVRequest, unwrap_uv, False),
        ("pack_uv", "Mark managed UV maps as packed with updated utilization metrics.", PackUVRequest, pack_uv, False),
        ("inspect_uv", "Inspect UV metadata for one or more targets.", InspectUVRequest, inspect_uv, True),
        ("list_uv_maps", "List managed UV map metadata, optionally filtered by target.", UVMapQueryRequest, list_uv_maps, True),
        ("rename_uv_map", "Rename a managed UV map metadata entry.", RenameUVMapRequest, rename_uv_map, False),
        ("set_uv_density", "Set texel density metadata on managed UV maps.", SetUVDensityRequest, set_uv_density, False),
        ("assign_udim_tile", "Assign sequential UDIM tiles to managed UV maps.", AssignUDIMTileRequest, assign_udim_tile, False),
        ("create_udim_tile_plan", "Create and persist a UDIM tile plan for managed UV maps.", CreateUDIMTilePlanRequest, create_udim_tile_plan, False),
        ("mirror_uv_layout", "Record a managed mirror operation on UV layout metadata.", MirrorUVLayoutRequest, mirror_uv_layout, False),
        ("generate_texture_set_manifest", "Create a texture-set manifest linking targets, UV maps, and textures.", GenerateTextureSetManifestRequest, generate_texture_set_manifest, False),
        ("plan_texture_bake", "Plan texture baking jobs from managed UV metadata.", PlanTextureBakeRequest, plan_texture_bake, True),
        ("bake_texture_set", "Bake multiple texture channels to project-scoped artifacts.", BakeTextureSetRequest, bake_texture_set, False),
        ("create_texture_atlas_manifest", "Create a texture atlas manifest for managed UV maps.", CreateTextureAtlasManifestRequest, create_texture_atlas_manifest, False),
        ("create_trim_sheet_manifest", "Create a trim-sheet manifest for game material workflows.", CreateTrimSheetManifestRequest, create_trim_sheet_manifest, False),
        ("validate_uv_layout", "Validate managed UV layout readiness for texturing/export.", ValidateUVLayoutRequest, validate_uv_layout, True),
        ("apply_texture", "Apply a managed texture material to one or more targets.", ApplyTextureRequest, apply_texture, False),
        ("create_procedural_texture", "Create a procedural texture definition backed by a material.", CreateProceduralTextureRequest, create_procedural_texture, False),
        ("bake_texture", "Write a project-scoped baked texture artifact.", BakeTextureRequest, bake_texture, False),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="texture_uv",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )