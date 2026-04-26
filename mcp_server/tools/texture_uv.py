from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import (
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
            "target_id": target_id,
            "method": request.method,
            "margin": request.margin,
            "island_count": max(1, face_count // 6 or 1),
            "packed": False,
            "utilization": round(min(0.92, 0.45 + (face_count * 0.02)), 3),
        }
        save_metadata_entity(
            context,
            project_id=project.project_id,
            entity_id=uv_map_id,
            entity_type="uv_map",
            name=f"UV_{target.get('name', target_id)}",
            spec=uv_map,
        )
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
        save_metadata_entity(
            context,
            project_id=project.project_id,
            entity_id=str(uv_map_id),
            entity_type="uv_map",
            name=f"UV_{uv_map['target_id']}",
            spec=uv_map,
        )
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


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("unwrap_uv", "Create managed UV metadata for one or more mesh targets.", UnwrapUVRequest, unwrap_uv, False),
        ("pack_uv", "Mark managed UV maps as packed with updated utilization metrics.", PackUVRequest, pack_uv, False),
        ("inspect_uv", "Inspect UV metadata for one or more targets.", InspectUVRequest, inspect_uv, True),
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