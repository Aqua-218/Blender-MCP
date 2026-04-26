from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.models.domain import AssetCategory, AssetPurpose, AssetSpec, PartSpec
from mcp_server.serialization import json_loads
from mcp_server.tools.geometry import CreatePrimitiveRequest, create_primitive
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.tools.material import (
    ApplyMaterialRequest,
    CreatePBRMaterialRequest,
    apply_material,
    create_pbr_material,
)
from mcp_server.tools.modifiers import (
    AddModifierRequest,
    SetModifierRequest,
    add_modifier,
    set_modifier,
)
from mcp_server.tools.object import TransformObjectRequest, transform_object
from mcp_server.tools.parts import (
    AddPartRequest,
    UpdatePartDetailRequest,
    add_part,
    update_part_detail,
)
from mcp_server.utils import new_id

DetailLevel = Literal["draft", "base", "refined", "hero"]
FurnitureType = Literal["chair", "table"]
HardSurfaceType = Literal["drone"]
RestyleStyle = Literal["industrial", "low-poly", "miniature", "premium", "realistic", "ruined", "sci-fi"]

DETAIL_LEVELS: list[DetailLevel] = ["draft", "base", "refined", "hero"]


class BaseGenerationRequest(CommonToolRequest):
    project_id: str
    name: str | None = None
    theme: str | None = None
    purpose: AssetPurpose = "prototype"
    polygon_budget: int | None = Field(default=None, ge=0)
    constraints: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)


class CreateModelRequest(BaseGenerationRequest):
    category: AssetCategory | None = None
    hard_surface_type: HardSurfaceType | None = None
    furniture_type: FurnitureType | None = None
    width: float | None = Field(default=None, gt=0.0)
    depth: float | None = Field(default=None, gt=0.0)
    height: float | None = Field(default=None, gt=0.0)
    floors: int | None = Field(default=None, ge=1, le=32)


class CreateHardSurfaceModelRequest(BaseGenerationRequest):
    hard_surface_type: HardSurfaceType = "drone"
    rotor_count: int = Field(default=4, ge=1, le=8)
    accent_color: list[float] = Field(default_factory=lambda: [0.18, 0.45, 1.0, 1.0])


class CreateBuildingRequest(BaseGenerationRequest):
    width: float = Field(default=6.0, gt=0.0)
    depth: float = Field(default=4.0, gt=0.0)
    height: float = Field(default=7.5, gt=0.0)
    floors: int = Field(default=3, ge=1, le=32)
    include_windows: bool = True
    include_door: bool = True


class CreateFurnitureRequest(BaseGenerationRequest):
    furniture_type: FurnitureType = "chair"
    width: float = Field(default=1.0, gt=0.0)
    depth: float = Field(default=1.0, gt=0.0)
    height: float = Field(default=1.0, gt=0.0)


class RevisionTargetRequest(CommonToolRequest):
    project_id: str
    asset_id: str | None = None
    part_id: str | None = None
    part_ids: list[str] = Field(default_factory=list)
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    spatial_range: dict[str, list[float]] | None = None


class IncreaseDetailRequest(RevisionTargetRequest):
    detail_strategy: Literal["auto", "bevel", "subdivision"] = "auto"
    amount: float = Field(default=1.0, gt=0.0, le=4.0)


class ReduceDetailRequest(RevisionTargetRequest):
    ratio: float = Field(default=0.6, gt=0.0, le=1.0)


class ModifySilhouetteRequest(RevisionTargetRequest):
    adjustment: str
    intensity: float = Field(default=0.15, ge=0.0, le=1.0)


class RestyleModelRequest(RevisionTargetRequest):
    style_target: RestyleStyle


def _normalize_name(request_name: str | None, fallback: str) -> str:
    if request_name:
        return request_name
    return fallback


def _normalized_text(*chunks: str | None) -> str:
    return " ".join(chunk.strip().lower() for chunk in chunks if chunk and chunk.strip())


def _retag_result(result: CommonToolResult, tool_name: str, *, summary: str | None = None, **extra: Any) -> CommonToolResult:
    payload = result.model_dump()
    payload["tool_name"] = tool_name
    if summary is not None and payload.get("status") == "success":
        payload["summary"] = summary
    payload.update(extra)
    return type(result).model_validate(payload)


def _safe_mode_budget_guard(context, request: BaseGenerationRequest, tool_name: str) -> CommonToolResult | None:  # type: ignore[no-untyped-def]
    if not request.safe_mode or request.polygon_budget is None:
        return None
    safe_limit = context.settings.max_safe_mode_polygon_budget
    if request.polygon_budget <= safe_limit:
        return None
    return failed_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary="Requested polygon budget exceeds the safe-mode limit.",
        errors=[
            (
                "policy_violation: polygon budget "
                f"{request.polygon_budget} exceeds safe-mode limit {safe_limit}"
            )
        ],
        safe_mode_limit=safe_limit,
    )


def _merge_objects(target: dict[str, dict[str, Any]], objects: list[dict[str, Any]] | None) -> None:
    for obj in objects or []:
        target[str(obj["object_id"])] = obj


def _list_entities_of_type(context, project_id: str, entity_type: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return [json_loads(record.spec_json) for record in context.entities.list_by_type(project_id, entity_type)]


def _load_entity_spec(context, entity_id: str) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    record = context.entities.get(entity_id)
    if record is None:
        return None
    return json_loads(record.spec_json)


def _load_asset(context, asset_id: str | None) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    if asset_id is None:
        return None
    record = context.entities.get(asset_id)
    if record is None or record.entity_type != "asset":
        return None
    return json_loads(record.spec_json)


def _asset_parts(asset: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list(asset.get("parts", [])) if asset else []


def _persist_asset(context, project_id: str, asset: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    context.entities.upsert(
        entity_id=asset["asset_id"],
        project_id=project_id,
        entity_type="asset",
        name=asset["name"],
        spec=asset,
    )


def _detail_index(level: str) -> int:
    try:
        return DETAIL_LEVELS.index(level)  # type: ignore[arg-type]
    except ValueError:
        return DETAIL_LEVELS.index("base")


def _shift_detail_level(level: str, delta: int) -> DetailLevel:
    index = max(0, min(len(DETAIL_LEVELS) - 1, _detail_index(level) + delta))
    return DETAIL_LEVELS[index]


def _first_material_id(result: CommonToolResult) -> str | None:
    material = result.model_dump().get("material")
    if not isinstance(material, dict):
        return None
    material_id = material.get("material_id")
    return str(material_id) if material_id else None


async def _create_pbr_material_for_style(
    context,  # type: ignore[no-untyped-def]
    request_id: str,
    project_id: str,
    *,
    name: str,
    base_color: list[float],
    roughness: float,
    metallic: float,
    emission_color: list[float] | None = None,
    emission_strength: float | None = None,
) -> CommonToolResult:
    return await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request_id,
            project_id=project_id,
            name=name,
            base_color=base_color,
            roughness=roughness,
            metallic=metallic,
            emission_color=emission_color,
            emission_strength=emission_strength,
        ),
    )


async def _apply_material_to_targets(
    context,  # type: ignore[no-untyped-def]
    request_id: str,
    project_id: str,
    material_id: str,
    target_ids: list[str],
) -> CommonToolResult:
    return await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request_id,
            project_id=project_id,
            material_id=material_id,
            target_ids=target_ids,
        ),
    )


async def _create_primitive_part(
    context,  # type: ignore[no-untyped-def]
    request: BaseGenerationRequest,
    *,
    name: str,
    primitive_type: str,
    collection_name: str,
    tags: list[str],
    location: list[float] | None = None,
    rotation: list[float] | None = None,
    scale: list[float] | None = None,
    parameters: dict[str, Any] | None = None,
) -> CommonToolResult:
    return await create_primitive(
        context,
        CreatePrimitiveRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            primitive_type=primitive_type,  # type: ignore[arg-type]
            name=name,
            location=location or [0.0, 0.0, 0.0],
            rotation=rotation or [0.0, 0.0, 0.0],
            scale=scale or [1.0, 1.0, 1.0],
            collection_name=collection_name,
            tags=tags,
            parameters=parameters or {},
        ),
    )


async def _add_part_binding(
    context,  # type: ignore[no-untyped-def]
    request: BaseGenerationRequest,
    *,
    asset_id: str,
    name: str,
    kind: str,
    target_ids: list[str],
    tags: list[str] | None = None,
    parent_part_id: str | None = None,
    detail_level: DetailLevel = "base",
    metadata: dict[str, Any] | None = None,
) -> CommonToolResult:
    part_metadata = {
        "asset_id": asset_id,
        "target_ids": target_ids,
        **(metadata or {}),
    }
    return await add_part(
        context,
        AddPartRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=name,
            kind=kind,
            tags=tags or [],
            detail_level=detail_level,
            parent_part_id=parent_part_id,
            metadata=part_metadata,
        ),
    )


def _palette_from_request(request: BaseGenerationRequest, *, accent_color: list[float] | None = None) -> tuple[list[float], list[float]]:
    text = _normalized_text(request.style, request.instruction, " ".join(request.constraints))
    base = [0.16, 0.18, 0.21, 1.0]
    accent = accent_color or [0.18, 0.45, 1.0, 1.0]
    if "white" in text:
        base = [0.88, 0.9, 0.93, 1.0]
    if "black" in text:
        base = [0.08, 0.09, 0.1, 1.0]
    if "blue" in text or "emissive" in text:
        accent = [0.18, 0.45, 1.0, 1.0]
    if "industrial" in text:
        base = [0.26, 0.26, 0.28, 1.0]
    if "premium" in text:
        base = [0.42, 0.28, 0.18, 1.0]
    return base, accent


def _style_material_properties(style_target: RestyleStyle) -> dict[str, Any]:
    if style_target == "sci-fi":
        return {
            "base_color": [0.12, 0.16, 0.22, 1.0],
            "roughness": 0.28,
            "metallic": 0.72,
            "emission_color": [0.16, 0.5, 1.0, 1.0],
            "emission_strength": 1.2,
        }
    if style_target == "industrial":
        return {"base_color": [0.32, 0.31, 0.29, 1.0], "roughness": 0.66, "metallic": 0.25}
    if style_target == "premium":
        return {"base_color": [0.38, 0.22, 0.13, 1.0], "roughness": 0.4, "metallic": 0.1}
    if style_target == "low-poly":
        return {"base_color": [0.52, 0.62, 0.78, 1.0], "roughness": 0.82, "metallic": 0.0}
    if style_target == "ruined":
        return {"base_color": [0.28, 0.25, 0.22, 1.0], "roughness": 0.9, "metallic": 0.05}
    if style_target == "miniature":
        return {"base_color": [0.72, 0.64, 0.53, 1.0], "roughness": 0.55, "metallic": 0.0}
    if style_target == "realistic":
        return {"base_color": [0.54, 0.5, 0.46, 1.0], "roughness": 0.58, "metallic": 0.08}
    return {"base_color": [0.4, 0.4, 0.42, 1.0], "roughness": 0.6, "metallic": 0.0}


def _silhouette_scale(scale: list[float], adjustment: str, intensity: float) -> list[float]:
    multiplier = 1.0 + intensity
    inverse = max(0.2, 1.0 - intensity)
    normalized = adjustment.strip().lower()
    if normalized in {"thicker", "wider"}:
        return [scale[0] * multiplier, scale[1] * multiplier, scale[2]]
    if normalized in {"thinner", "narrower"}:
        return [scale[0] * inverse, scale[1] * inverse, scale[2]]
    if normalized in {"taller"}:
        return [scale[0], scale[1], scale[2] * multiplier]
    if normalized in {"shorter"}:
        return [scale[0], scale[1], scale[2] * inverse]
    if normalized in {"heavier", "luxurious", "industrial"}:
        return [component * multiplier for component in scale]
    if normalized in {"lighter"}:
        return [component * inverse for component in scale]
    return [component * multiplier for component in scale]


async def _ensure_modifier(
    context,  # type: ignore[no-untyped-def]
    *,
    request_id: str,
    project_id: str,
    target_id: str,
    modifier_type: str,
    modifier_name: str,
    params: dict[str, Any],
) -> CommonToolResult:
    added = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request_id,
            project_id=project_id,
            target_id=target_id,
            modifier_type=modifier_type,  # type: ignore[arg-type]
            name=modifier_name,
            params=params,
        ),
    )
    if added.status == "success":
        return added
    if not any("already exists" in error.lower() for error in added.errors):
        return added
    return await set_modifier(
        context,
        SetModifierRequest(
            request_id=request_id,
            project_id=project_id,
            target_id=target_id,
            modifier_name=modifier_name,
            params=params,
        ),
    )


def _refresh_asset_from_parts(asset: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    updated = dict(asset)
    updated["parts"] = parts
    return updated


async def _resolve_revision_scope(
    context,  # type: ignore[no-untyped-def]
    request: RevisionTargetRequest,
    tool_name: str,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None] | CommonToolResult:
    require_project(context, request.project_id)
    project_parts = _list_entities_of_type(context, request.project_id, "part")
    parts_by_id = {part["part_id"]: part for part in project_parts}
    resolved_asset = _load_asset(context, request.asset_id)
    selected_parts: list[dict[str, Any]] = []
    object_ids: list[str] = []

    for part_id in [*request.part_ids, *([request.part_id] if request.part_id else [])]:
        part = parts_by_id.get(part_id)
        if part is None:
            return failed_result(
                request_id=request.request_id,
                tool_name=tool_name,
                summary=f"Part '{part_id}' not found.",
                errors=[f"target_not_found: part '{part_id}' does not exist"],
            )
        selected_parts.append(part)
        object_ids.extend(part.get("metadata", {}).get("target_ids", []))
        if resolved_asset is None:
            resolved_asset = _load_asset(context, part.get("metadata", {}).get("asset_id"))

    if request.asset_id and resolved_asset is None:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary=f"Asset '{request.asset_id}' not found.",
            errors=[f"target_not_found: asset '{request.asset_id}' does not exist"],
        )

    if not object_ids and request.asset_id and resolved_asset is not None:
        for part in _asset_parts(resolved_asset):
            selected_parts.append(part)
            object_ids.extend(part.get("metadata", {}).get("target_ids", []))
        if not object_ids:
            object_ids.extend(resolved_asset.get("metadata", {}).get("root_object_ids", []))

    if not object_ids:
        try:
            object_ids = await resolve_target_ids(
                context,
                project_id=request.project_id,
                target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
                names=request.names,
                tag=request.tag,
                collection_name=request.match_collection_name,
                spatial_range=request.spatial_range,
            )
        except ValueError as exc:
            return failed_result(
                request_id=request.request_id,
                tool_name=tool_name,
                summary=str(exc),
                errors=[f"target_not_found: {exc}"],
            )

    unique_object_ids = list(dict.fromkeys(object_ids))
    if not selected_parts:
        selected_parts = [
            part
            for part in project_parts
            if set(part.get("metadata", {}).get("target_ids", [])) & set(unique_object_ids)
        ]
        if resolved_asset is None and selected_parts:
            resolved_asset = _load_asset(context, selected_parts[0].get("metadata", {}).get("asset_id"))

    all_parts = _asset_parts(resolved_asset) if resolved_asset is not None else selected_parts
    return unique_object_ids, selected_parts, all_parts, resolved_asset


def _unsupported_generation_result(request: BaseGenerationRequest, tool_name: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=message,
        warnings=[message],
        errors=[f"unsupported_feature: {message}"],
    )


async def create_hard_surface_model(context, request: CreateHardSurfaceModelRequest):  # type: ignore[no-untyped-def]
    budget_guard = _safe_mode_budget_guard(context, request, "create_hard_surface_model")
    if budget_guard is not None:
        return budget_guard
    project = require_project(context, request.project_id)
    if request.hard_surface_type != "drone":
        return _unsupported_generation_result(
            request,
            "create_hard_surface_model",
            "create_hard_surface_model currently supports the drone template only.",
        )

    warnings: list[str] = []
    if request.rotor_count != 4:
        warnings.append("Only a four-rotor drone layout is currently supported; using 4 rotors.")

    asset_id = new_id("asset")
    asset_name = _normalize_name(request.name, "Generated Drone")
    collection_name = f"{asset_name} Collection"
    created_objects: dict[str, dict[str, Any]] = {}
    part_specs: list[dict[str, Any]] = []

    base_color, accent_color = _palette_from_request(request, accent_color=request.accent_color)
    base_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Body",
        base_color=base_color,
        roughness=0.34,
        metallic=0.62,
    )
    if base_material.status != "success":
        return _retag_result(base_material, "create_hard_surface_model")
    accent_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Accent",
        base_color=accent_color,
        roughness=0.22,
        metallic=0.15,
        emission_color=accent_color,
        emission_strength=1.1,
    )
    if accent_material.status != "success":
        return _retag_result(accent_material, "create_hard_surface_model")
    base_material_id = _first_material_id(base_material)
    accent_material_id = _first_material_id(accent_material)
    if base_material_id is None or accent_material_id is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_hard_surface_model",
            summary="Failed to resolve generated materials.",
            errors=["validation_error: generated materials were missing material_id values"],
        )

    common_tags = ["generated", "hard_surface", f"asset:{asset_id}"]
    body = await _create_primitive_part(
        context,
        request,
        name=f"{asset_name}_body",
        primitive_type="cube",
        collection_name=collection_name,
        tags=[*common_tags, "part:body"],
        scale=[0.95, 0.62, 0.18],
    )
    if body.status != "success":
        return _retag_result(body, "create_hard_surface_model")
    _merge_objects(created_objects, body.model_dump().get("objects"))
    body_object_id = body.created_object_ids[0]
    applied = await _apply_material_to_targets(context, request.request_id, request.project_id, base_material_id, [body_object_id])
    if applied.status not in {"success", "partial_success"}:
        return _retag_result(applied, "create_hard_surface_model")
    _merge_objects(created_objects, applied.model_dump().get("objects"))
    body_part = await _add_part_binding(
        context,
        request,
        asset_id=asset_id,
        name="body",
        kind="body",
        target_ids=[body_object_id],
        tags=["hero", "core"],
        metadata={"symmetric_group": "center"},
    )
    if body_part.status != "success":
        return _retag_result(body_part, "create_hard_surface_model")
    part_specs.append(body_part.model_dump()["part"])

    arm_positions = {
        "front_left": ([0.58, 0.58, 0.0], [0.0, 0.0, 0.78]),
        "front_right": ([0.58, -0.58, 0.0], [0.0, 0.0, -0.78]),
        "rear_left": ([-0.58, 0.58, 0.0], [0.0, 0.0, -0.78]),
        "rear_right": ([-0.58, -0.58, 0.0], [0.0, 0.0, 0.78]),
    }
    rotor_positions = {
        "front_left": [1.02, 1.02, 0.04],
        "front_right": [1.02, -1.02, 0.04],
        "rear_left": [-1.02, 1.02, 0.04],
        "rear_right": [-1.02, -1.02, 0.04],
    }
    for key, (location, rotation) in arm_positions.items():
        arm = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_arm_{key}",
            primitive_type="cube",
            collection_name=collection_name,
            tags=[*common_tags, f"part:arm_{key}"],
            location=location,
            rotation=rotation,
            scale=[0.42, 0.05, 0.035],
        )
        if arm.status != "success":
            return _retag_result(arm, "create_hard_surface_model")
        _merge_objects(created_objects, arm.model_dump().get("objects"))
        arm_object_id = arm.created_object_ids[0]
        arm_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, base_material_id, [arm_object_id])
        if arm_applied.status not in {"success", "partial_success"}:
            return _retag_result(arm_applied, "create_hard_surface_model")
        _merge_objects(created_objects, arm_applied.model_dump().get("objects"))
        arm_part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name=f"arm_{key}",
            kind="arm",
            target_ids=[arm_object_id],
            metadata={"symmetric_group": "arm", "mirror_key": key},
        )
        if arm_part.status != "success":
            return _retag_result(arm_part, "create_hard_surface_model")
        part_specs.append(arm_part.model_dump()["part"])

        rotor = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_rotor_{key}",
            primitive_type="cylinder",
            collection_name=collection_name,
            tags=[*common_tags, f"part:rotor_{key}"],
            location=rotor_positions[key],
            scale=[0.22, 0.22, 0.025],
            parameters={"vertices": 24},
        )
        if rotor.status != "success":
            return _retag_result(rotor, "create_hard_surface_model")
        _merge_objects(created_objects, rotor.model_dump().get("objects"))
        rotor_object_id = rotor.created_object_ids[0]
        rotor_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, accent_material_id, [rotor_object_id])
        if rotor_applied.status not in {"success", "partial_success"}:
            return _retag_result(rotor_applied, "create_hard_surface_model")
        _merge_objects(created_objects, rotor_applied.model_dump().get("objects"))
        rotor_part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name=f"rotor_{key}",
            kind="rotor",
            target_ids=[rotor_object_id],
            metadata={"symmetric_group": "rotor", "mirror_key": key},
        )
        if rotor_part.status != "success":
            return _retag_result(rotor_part, "create_hard_surface_model")
        part_specs.append(rotor_part.model_dump()["part"])

    for side, y_coord in (("left", 0.28), ("right", -0.28)):
        skid = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_landing_{side}",
            primitive_type="cube",
            collection_name=collection_name,
            tags=[*common_tags, f"part:landing_{side}"],
            location=[0.0, y_coord, -0.26],
            scale=[0.72, 0.035, 0.03],
        )
        if skid.status != "success":
            return _retag_result(skid, "create_hard_surface_model")
        _merge_objects(created_objects, skid.model_dump().get("objects"))
        skid_object_id = skid.created_object_ids[0]
        skid_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, base_material_id, [skid_object_id])
        if skid_applied.status not in {"success", "partial_success"}:
            return _retag_result(skid_applied, "create_hard_surface_model")
        _merge_objects(created_objects, skid_applied.model_dump().get("objects"))
        skid_part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name=f"landing_{side}",
            kind="landing_gear",
            target_ids=[skid_object_id],
            metadata={"symmetric_group": "landing_gear", "mirror_key": side},
        )
        if skid_part.status != "success":
            return _retag_result(skid_part, "create_hard_surface_model")
        part_specs.append(skid_part.model_dump()["part"])

    sensor = await _create_primitive_part(
        context,
        request,
        name=f"{asset_name}_sensor",
        primitive_type="uv_sphere",
        collection_name=collection_name,
        tags=[*common_tags, "part:sensor"],
        location=[0.66, 0.0, 0.02],
        scale=[0.1, 0.1, 0.1],
        parameters={"segments": 16, "ring_count": 8},
    )
    if sensor.status != "success":
        return _retag_result(sensor, "create_hard_surface_model")
    _merge_objects(created_objects, sensor.model_dump().get("objects"))
    sensor_object_id = sensor.created_object_ids[0]
    sensor_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, accent_material_id, [sensor_object_id])
    if sensor_applied.status not in {"success", "partial_success"}:
        return _retag_result(sensor_applied, "create_hard_surface_model")
    _merge_objects(created_objects, sensor_applied.model_dump().get("objects"))
    sensor_part = await _add_part_binding(
        context,
        request,
        asset_id=asset_id,
        name="sensor",
        kind="sensor",
        target_ids=[sensor_object_id],
        metadata={"accent": True},
    )
    if sensor_part.status != "success":
        return _retag_result(sensor_part, "create_hard_surface_model")
    part_specs.append(sensor_part.model_dump()["part"])

    asset = AssetSpec(
        asset_id=asset_id,
        name=asset_name,
        category="vehicle",
        theme=request.theme,
        style=request.style,
        purpose=request.purpose,
        target_quality=request.quality,
        polygon_budget=request.polygon_budget,
        seed=request.seed,
        constraints=[*request.constraints, "four_rotor_layout"],
        forbidden_elements=request.forbidden_elements,
        parts=[PartSpec.model_validate(part) for part in part_specs],
        materials=[base_material_id, accent_material_id],
        metadata={
            "collection_name": collection_name,
            "root_object_ids": list(created_objects),
            "hard_surface_type": request.hard_surface_type,
        },
    ).model_dump()
    _persist_asset(context, project.project_id, asset)
    return success_result(
        request_id=request.request_id,
        tool_name="create_hard_surface_model",
        summary=f"Created hard-surface drone '{asset_name}' with {len(part_specs)} parts.",
        project_id=project.project_id,
        asset_id=asset_id,
        asset=asset,
        parts=part_specs,
        materials=[base_material.model_dump()["material"], accent_material.model_dump()["material"]],
        objects=list(created_objects.values()),
        created_object_ids=list(created_objects),
        warnings=warnings,
        next_suggestions=["frame_object", "render_preview"],
    )


async def create_building(context, request: CreateBuildingRequest):  # type: ignore[no-untyped-def]
    budget_guard = _safe_mode_budget_guard(context, request, "create_building")
    if budget_guard is not None:
        return budget_guard
    project = require_project(context, request.project_id)
    asset_id = new_id("asset")
    asset_name = _normalize_name(request.name, "Generated Building")
    collection_name = f"{asset_name} Collection"
    created_objects: dict[str, dict[str, Any]] = {}
    part_specs: list[dict[str, Any]] = []

    facade_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Facade",
        base_color=[0.76, 0.78, 0.82, 1.0] if request.style != "near-future" else [0.55, 0.6, 0.68, 1.0],
        roughness=0.68,
        metallic=0.08,
    )
    if facade_material.status != "success":
        return _retag_result(facade_material, "create_building")
    glass_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Glass",
        base_color=[0.36, 0.5, 0.72, 0.75],
        roughness=0.12,
        metallic=0.0,
        emission_color=[0.16, 0.28, 0.52, 1.0] if request.style == "near-future" else None,
        emission_strength=0.6 if request.style == "near-future" else None,
    )
    if glass_material.status != "success":
        return _retag_result(glass_material, "create_building")
    door_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Door",
        base_color=[0.18, 0.15, 0.14, 1.0],
        roughness=0.5,
        metallic=0.18,
    )
    if door_material.status != "success":
        return _retag_result(door_material, "create_building")
    facade_material_id = _first_material_id(facade_material)
    glass_material_id = _first_material_id(glass_material)
    door_material_id = _first_material_id(door_material)
    if not facade_material_id or not glass_material_id or not door_material_id:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_building",
            summary="Failed to resolve generated materials.",
            errors=["validation_error: generated materials were missing material_id values"],
        )

    common_tags = ["generated", "building", f"asset:{asset_id}"]
    shell = await _create_primitive_part(
        context,
        request,
        name=f"{asset_name}_shell",
        primitive_type="cube",
        collection_name=collection_name,
        tags=[*common_tags, "part:shell"],
        location=[0.0, 0.0, request.height / 2.0],
        scale=[request.width / 2.0, request.depth / 2.0, request.height / 2.0],
    )
    if shell.status != "success":
        return _retag_result(shell, "create_building")
    _merge_objects(created_objects, shell.model_dump().get("objects"))
    shell_object_id = shell.created_object_ids[0]
    shell_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, facade_material_id, [shell_object_id])
    if shell_applied.status not in {"success", "partial_success"}:
        return _retag_result(shell_applied, "create_building")
    _merge_objects(created_objects, shell_applied.model_dump().get("objects"))
    shell_part = await _add_part_binding(
        context,
        request,
        asset_id=asset_id,
        name="shell",
        kind="shell",
        target_ids=[shell_object_id],
    )
    if shell_part.status != "success":
        return _retag_result(shell_part, "create_building")
    part_specs.append(shell_part.model_dump()["part"])

    roof_scale = [request.width / 2.0 + 0.2, request.depth / 2.0 + 0.2, 0.12 if request.style == "near-future" else 0.18]
    roof = await _create_primitive_part(
        context,
        request,
        name=f"{asset_name}_roof",
        primitive_type="cube",
        collection_name=collection_name,
        tags=[*common_tags, "part:roof"],
        location=[0.0, 0.0, request.height + roof_scale[2]],
        scale=roof_scale,
    )
    if roof.status != "success":
        return _retag_result(roof, "create_building")
    _merge_objects(created_objects, roof.model_dump().get("objects"))
    roof_object_id = roof.created_object_ids[0]
    roof_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, facade_material_id, [roof_object_id])
    if roof_applied.status not in {"success", "partial_success"}:
        return _retag_result(roof_applied, "create_building")
    _merge_objects(created_objects, roof_applied.model_dump().get("objects"))
    roof_part = await _add_part_binding(
        context,
        request,
        asset_id=asset_id,
        name="roof",
        kind="roof",
        target_ids=[roof_object_id],
    )
    if roof_part.status != "success":
        return _retag_result(roof_part, "create_building")
    part_specs.append(roof_part.model_dump()["part"])

    window_count = max(2, request.floors * 2) if request.include_windows else 0
    for index in range(window_count):
        x_offset = ((index % 2) - 0.5) * (request.width * 0.38)
        floor_index = index // 2
        z_coord = 1.2 + (floor_index * max(1.4, request.height / max(request.floors, 1)))
        window = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_window_{index + 1}",
            primitive_type="cube",
            collection_name=collection_name,
            tags=[*common_tags, f"part:window_{index + 1}"],
            location=[x_offset, (request.depth / 2.0) + 0.06, z_coord],
            scale=[max(0.25, request.width * 0.08), 0.05, max(0.45, request.height * 0.06)],
        )
        if window.status != "success":
            return _retag_result(window, "create_building")
        _merge_objects(created_objects, window.model_dump().get("objects"))
        window_object_id = window.created_object_ids[0]
        window_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, glass_material_id, [window_object_id])
        if window_applied.status not in {"success", "partial_success"}:
            return _retag_result(window_applied, "create_building")
        _merge_objects(created_objects, window_applied.model_dump().get("objects"))
        window_part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name=f"window_{index + 1}",
            kind="window",
            target_ids=[window_object_id],
            metadata={"floor": floor_index + 1},
        )
        if window_part.status != "success":
            return _retag_result(window_part, "create_building")
        part_specs.append(window_part.model_dump()["part"])

    if request.include_door:
        door = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_door",
            primitive_type="cube",
            collection_name=collection_name,
            tags=[*common_tags, "part:door"],
            location=[0.0, (request.depth / 2.0) + 0.07, 0.95],
            scale=[max(0.35, request.width * 0.09), 0.06, 0.9],
        )
        if door.status != "success":
            return _retag_result(door, "create_building")
        _merge_objects(created_objects, door.model_dump().get("objects"))
        door_object_id = door.created_object_ids[0]
        door_applied = await _apply_material_to_targets(context, request.request_id, request.project_id, door_material_id, [door_object_id])
        if door_applied.status not in {"success", "partial_success"}:
            return _retag_result(door_applied, "create_building")
        _merge_objects(created_objects, door_applied.model_dump().get("objects"))
        door_part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name="door",
            kind="door",
            target_ids=[door_object_id],
        )
        if door_part.status != "success":
            return _retag_result(door_part, "create_building")
        part_specs.append(door_part.model_dump()["part"])

    asset = AssetSpec(
        asset_id=asset_id,
        name=asset_name,
        category="building",
        theme=request.theme,
        style=request.style,
        purpose=request.purpose,
        target_quality=request.quality,
        polygon_budget=request.polygon_budget,
        seed=request.seed,
        constraints=request.constraints,
        forbidden_elements=request.forbidden_elements,
        parts=[PartSpec.model_validate(part) for part in part_specs],
        materials=[facade_material_id, glass_material_id, door_material_id],
        metadata={
            "collection_name": collection_name,
            "root_object_ids": list(created_objects),
            "floors": request.floors,
        },
    ).model_dump()
    _persist_asset(context, project.project_id, asset)
    return success_result(
        request_id=request.request_id,
        tool_name="create_building",
        summary=f"Created building shell '{asset_name}' with {len(part_specs)} parts.",
        project_id=project.project_id,
        asset_id=asset_id,
        asset=asset,
        parts=part_specs,
        materials=[facade_material.model_dump()["material"], glass_material.model_dump()["material"], door_material.model_dump()["material"]],
        objects=list(created_objects.values()),
        created_object_ids=list(created_objects),
        next_suggestions=["inspect_scale", "render_preview"],
    )


async def create_furniture(context, request: CreateFurnitureRequest):  # type: ignore[no-untyped-def]
    budget_guard = _safe_mode_budget_guard(context, request, "create_furniture")
    if budget_guard is not None:
        return budget_guard
    project = require_project(context, request.project_id)
    asset_id = new_id("asset")
    asset_name = _normalize_name(request.name, f"Generated {request.furniture_type.title()}")
    collection_name = f"{asset_name} Collection"
    created_objects: dict[str, dict[str, Any]] = {}
    part_specs: list[dict[str, Any]] = []

    wood_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Wood",
        base_color=[0.48, 0.31, 0.18, 1.0] if request.style == "premium" else [0.56, 0.42, 0.24, 1.0],
        roughness=0.52,
        metallic=0.02,
    )
    if wood_material.status != "success":
        return _retag_result(wood_material, "create_furniture")
    frame_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} Frame",
        base_color=[0.18, 0.18, 0.2, 1.0],
        roughness=0.36,
        metallic=0.52,
    )
    if frame_material.status != "success":
        return _retag_result(frame_material, "create_furniture")
    wood_material_id = _first_material_id(wood_material)
    frame_material_id = _first_material_id(frame_material)
    if not wood_material_id or not frame_material_id:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_furniture",
            summary="Failed to resolve generated materials.",
            errors=["validation_error: generated materials were missing material_id values"],
        )

    common_tags = ["generated", "furniture", f"asset:{asset_id}"]
    primary_parts: list[tuple[str, str, list[float], list[float], str]] = []
    secondary_parts: list[tuple[str, str, list[float], list[float], str]] = []
    if request.furniture_type == "chair":
        primary_parts = [
            ("seat", "seat", [0.0, 0.0, 0.56], [request.width * 0.45, request.depth * 0.45, 0.06], wood_material_id),
            ("backrest", "backrest", [0.0, -(request.depth * 0.38), 0.98], [request.width * 0.45, 0.05, request.height * 0.38], wood_material_id),
        ]
        secondary_parts = [
            ("leg_front_left", "leg", [request.width * 0.34, request.depth * 0.34, 0.27], [0.05, 0.05, 0.5], frame_material_id),
            ("leg_front_right", "leg", [request.width * 0.34, -(request.depth * 0.34), 0.27], [0.05, 0.05, 0.5], frame_material_id),
            ("leg_back_left", "leg", [-(request.width * 0.34), request.depth * 0.34, 0.27], [0.05, 0.05, 0.5], frame_material_id),
            ("leg_back_right", "leg", [-(request.width * 0.34), -(request.depth * 0.34), 0.27], [0.05, 0.05, 0.5], frame_material_id),
        ]
    else:
        primary_parts = [
            ("top", "tabletop", [0.0, 0.0, 0.76], [request.width * 0.65, request.depth * 0.45, 0.06], wood_material_id),
        ]
        secondary_parts = [
            ("leg_front_left", "leg", [request.width * 0.48, request.depth * 0.3, 0.35], [0.05, 0.05, 0.7], frame_material_id),
            ("leg_front_right", "leg", [request.width * 0.48, -(request.depth * 0.3), 0.35], [0.05, 0.05, 0.7], frame_material_id),
            ("leg_back_left", "leg", [-(request.width * 0.48), request.depth * 0.3, 0.35], [0.05, 0.05, 0.7], frame_material_id),
            ("leg_back_right", "leg", [-(request.width * 0.48), -(request.depth * 0.3), 0.35], [0.05, 0.05, 0.7], frame_material_id),
        ]

    for part_name, kind, location, scale, material_id in [*primary_parts, *secondary_parts]:
        created = await _create_primitive_part(
            context,
            request,
            name=f"{asset_name}_{part_name}",
            primitive_type="cube",
            collection_name=collection_name,
            tags=[*common_tags, f"part:{part_name}"],
            location=location,
            scale=scale,
        )
        if created.status != "success":
            return _retag_result(created, "create_furniture")
        _merge_objects(created_objects, created.model_dump().get("objects"))
        object_id = created.created_object_ids[0]
        applied = await _apply_material_to_targets(context, request.request_id, request.project_id, material_id, [object_id])
        if applied.status not in {"success", "partial_success"}:
            return _retag_result(applied, "create_furniture")
        _merge_objects(created_objects, applied.model_dump().get("objects"))
        part = await _add_part_binding(
            context,
            request,
            asset_id=asset_id,
            name=part_name,
            kind=kind,
            target_ids=[object_id],
            metadata={"furniture_type": request.furniture_type},
        )
        if part.status != "success":
            return _retag_result(part, "create_furniture")
        part_specs.append(part.model_dump()["part"])

    asset = AssetSpec(
        asset_id=asset_id,
        name=asset_name,
        category="furniture",
        theme=request.theme,
        style=request.style,
        purpose=request.purpose,
        target_quality=request.quality,
        polygon_budget=request.polygon_budget,
        seed=request.seed,
        constraints=request.constraints,
        forbidden_elements=request.forbidden_elements,
        parts=[PartSpec.model_validate(part) for part in part_specs],
        materials=[wood_material_id, frame_material_id],
        metadata={
            "collection_name": collection_name,
            "root_object_ids": list(created_objects),
            "furniture_type": request.furniture_type,
        },
    ).model_dump()
    _persist_asset(context, project.project_id, asset)
    return success_result(
        request_id=request.request_id,
        tool_name="create_furniture",
        summary=f"Created {request.furniture_type} '{asset_name}' with {len(part_specs)} parts.",
        project_id=project.project_id,
        asset_id=asset_id,
        asset=asset,
        parts=part_specs,
        materials=[wood_material.model_dump()["material"], frame_material.model_dump()["material"]],
        objects=list(created_objects.values()),
        created_object_ids=list(created_objects),
        next_suggestions=["render_preview", "increase_detail"],
    )


async def create_model(context, request: CreateModelRequest):  # type: ignore[no-untyped-def]
    budget_guard = _safe_mode_budget_guard(context, request, "create_model")
    if budget_guard is not None:
        return budget_guard
    request_payload = request.model_dump(exclude_none=True)
    text = _normalized_text(request.instruction, request.style, " ".join(request.constraints))
    if request.category == "building":
        building_payload = {
            **request_payload,
            "width": request.width or 6.0,
            "depth": request.depth or 4.0,
            "height": request.height or 7.5,
            "floors": request.floors or 3,
            "name": _normalize_name(request.name, "Generated Building"),
        }
        generated = await create_building(
            context,
            CreateBuildingRequest(**building_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_building.",
            dispatched_tool="create_building",
        )
    if request.category == "furniture":
        furniture_type: FurnitureType = request.furniture_type or ("table" if "table" in text or "desk" in text else "chair")
        furniture_payload = {
            **request_payload,
            "furniture_type": furniture_type,
            "width": request.width or 1.0,
            "depth": request.depth or 1.0,
            "height": request.height or 1.0,
            "name": _normalize_name(request.name, f"Generated {furniture_type.title()}"),
        }
        generated = await create_furniture(
            context,
            CreateFurnitureRequest(**furniture_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_furniture.",
            dispatched_tool="create_furniture",
        )
    if request.category in {"vehicle", "mech", "prop"}:
        hard_surface_payload = {
            **request_payload,
            "hard_surface_type": request.hard_surface_type or "drone",
            "name": _normalize_name(request.name, "Generated Drone"),
        }
        generated = await create_hard_surface_model(
            context,
            CreateHardSurfaceModelRequest(**hard_surface_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_hard_surface_model.",
            dispatched_tool="create_hard_surface_model",
        )
    if any(token in text for token in {"building", "facade", "shell", "tower", "house"}):
        building_payload = {
            **request_payload,
            "width": request.width or 6.0,
            "depth": request.depth or 4.0,
            "height": request.height or 7.5,
            "floors": request.floors or 3,
            "name": _normalize_name(request.name, "Generated Building"),
        }
        generated = await create_building(
            context,
            CreateBuildingRequest(**building_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_building.",
            dispatched_tool="create_building",
        )
    if any(token in text for token in {"chair", "table", "desk", "shelf", "sofa", "bed", "lamp", "furniture"}):
        furniture_type = request.furniture_type or ("table" if "table" in text or "desk" in text else "chair")
        furniture_payload = {
            **request_payload,
            "furniture_type": furniture_type,
            "width": request.width or 1.0,
            "depth": request.depth or 1.0,
            "height": request.height or 1.0,
            "name": _normalize_name(request.name, f"Generated {furniture_type.title()}"),
        }
        generated = await create_furniture(
            context,
            CreateFurnitureRequest(**furniture_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_furniture.",
            dispatched_tool="create_furniture",
        )
    if request.category in {"other", None} or any(token in text for token in {"drone", "hard surface", "hard-surface", "machine", "mech", "vehicle", "sci-fi"}):
        hard_surface_payload = {
            **request_payload,
            "hard_surface_type": request.hard_surface_type or "drone",
            "name": _normalize_name(request.name, "Generated Drone"),
        }
        generated = await create_hard_surface_model(
            context,
            CreateHardSurfaceModelRequest(**hard_surface_payload),
        )
        return _retag_result(
            generated,
            "create_model",
            summary="Created model via create_hard_surface_model.",
            dispatched_tool="create_hard_surface_model",
        )
    return _unsupported_generation_result(
        request,
        "create_model",
        "create_model currently supports hard-surface drones, furniture, and exterior building shells only.",
    )


async def increase_detail(context, request: IncreaseDetailRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    resolved = await _resolve_revision_scope(context, request, "increase_detail")
    if isinstance(resolved, CommonToolResult):
        return resolved
    object_ids, selected_parts, all_parts, asset = resolved
    objects: dict[str, dict[str, Any]] = {}
    strategy = "bevel" if request.detail_strategy == "auto" else request.detail_strategy
    modifier_type = "BEVEL" if strategy == "bevel" else "SUBSURF"
    modifier_name = "MCPDetailBevel" if strategy == "bevel" else "MCPDetailSubsurf"
    params = {
        "width": round(0.01 + (0.015 * request.amount), 4),
        "segments": 2 if request.amount >= 1.5 else 1,
    } if strategy == "bevel" else {"levels": max(1, min(3, int(round(request.amount))))}
    for object_id in object_ids:
        updated = await _ensure_modifier(
            context,
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=object_id,
            modifier_type=modifier_type,
            modifier_name=modifier_name,
            params=params,
        )
        if updated.status != "success":
            return _retag_result(updated, "increase_detail")
        _merge_objects(objects, updated.model_dump().get("objects"))

    updated_parts: list[dict[str, Any]] = []
    for part in selected_parts:
        new_level = _shift_detail_level(part.get("detail_level", "base"), 1)
        changed = await update_part_detail(
            context,
            UpdatePartDetailRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                part_id=part["part_id"],
                detail_level=new_level,
            ),
        )
        if changed.status != "success":
            return _retag_result(changed, "increase_detail")
        updated_parts.append(changed.model_dump()["part"])

    if asset is not None and updated_parts:
        part_map = {part["part_id"]: part for part in _list_entities_of_type(context, request.project_id, "part") if part.get("metadata", {}).get("asset_id") == asset["asset_id"]}
        asset = _refresh_asset_from_parts(asset, list(part_map.values()))
        _persist_asset(context, project.project_id, asset)

    modified_part_ids = [part["part_id"] for part in updated_parts] or [part["part_id"] for part in selected_parts]
    all_part_ids = [part["part_id"] for part in all_parts]
    untouched_part_ids = [part_id for part_id in all_part_ids if part_id not in modified_part_ids]
    return success_result(
        request_id=request.request_id,
        tool_name="increase_detail",
        summary=f"Increased detail on {len(object_ids)} objects.",
        project_id=project.project_id,
        asset_id=asset.get("asset_id") if asset else None,
        modified_object_ids=object_ids,
        modified_part_ids=modified_part_ids,
        untouched_part_ids=untouched_part_ids,
        objects=list(objects.values()),
        parts=updated_parts or selected_parts,
    )


async def reduce_detail(context, request: ReduceDetailRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    resolved = await _resolve_revision_scope(context, request, "reduce_detail")
    if isinstance(resolved, CommonToolResult):
        return resolved
    object_ids, selected_parts, all_parts, asset = resolved
    objects: dict[str, dict[str, Any]] = {}
    for object_id in object_ids:
        updated = await _ensure_modifier(
            context,
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=object_id,
            modifier_type="DECIMATE",
            modifier_name="MCPReduceDetail",
            params={"ratio": request.ratio},
        )
        if updated.status != "success":
            return _retag_result(updated, "reduce_detail")
        _merge_objects(objects, updated.model_dump().get("objects"))

    updated_parts: list[dict[str, Any]] = []
    for part in selected_parts:
        new_level = _shift_detail_level(part.get("detail_level", "base"), -1)
        changed = await update_part_detail(
            context,
            UpdatePartDetailRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                part_id=part["part_id"],
                detail_level=new_level,
            ),
        )
        if changed.status != "success":
            return _retag_result(changed, "reduce_detail")
        updated_parts.append(changed.model_dump()["part"])

    if asset is not None and updated_parts:
        part_map = {part["part_id"]: part for part in _list_entities_of_type(context, request.project_id, "part") if part.get("metadata", {}).get("asset_id") == asset["asset_id"]}
        asset = _refresh_asset_from_parts(asset, list(part_map.values()))
        _persist_asset(context, project.project_id, asset)

    modified_part_ids = [part["part_id"] for part in updated_parts] or [part["part_id"] for part in selected_parts]
    all_part_ids = [part["part_id"] for part in all_parts]
    untouched_part_ids = [part_id for part_id in all_part_ids if part_id not in modified_part_ids]
    return success_result(
        request_id=request.request_id,
        tool_name="reduce_detail",
        summary=f"Reduced detail on {len(object_ids)} objects.",
        project_id=project.project_id,
        asset_id=asset.get("asset_id") if asset else None,
        modified_object_ids=object_ids,
        modified_part_ids=modified_part_ids,
        untouched_part_ids=untouched_part_ids,
        objects=list(objects.values()),
        parts=updated_parts or selected_parts,
        ratio=request.ratio,
    )


async def modify_silhouette(context, request: ModifySilhouetteRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    resolved = await _resolve_revision_scope(context, request, "modify_silhouette")
    if isinstance(resolved, CommonToolResult):
        return resolved
    object_ids, selected_parts, all_parts, asset = resolved
    objects: dict[str, dict[str, Any]] = {}
    normalized = request.adjustment.strip().lower()

    for object_id in object_ids:
        existing = _load_entity_spec(context, object_id)
        if existing is None:
            return failed_result(
                request_id=request.request_id,
                tool_name="modify_silhouette",
                summary=f"Object '{object_id}' is not tracked in entity metadata.",
                errors=[f"target_not_found: object '{object_id}' is not tracked"],
            )
        new_scale = _silhouette_scale(list(existing.get("scale", [1.0, 1.0, 1.0])), normalized, request.intensity)
        changed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=object_id,
                scale=new_scale,
            ),
        )
        if changed.status != "success":
            return _retag_result(changed, "modify_silhouette")
        _merge_objects(objects, [changed.model_dump()["object"]])
        if normalized in {"sharper", "industrial"}:
            outlined = await _ensure_modifier(
                context,
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=object_id,
                modifier_type="BEVEL",
                modifier_name="MCPSilhouetteBevel",
                params={"width": 0.01, "segments": 1},
            )
            if outlined.status != "success":
                return _retag_result(outlined, "modify_silhouette")
            _merge_objects(objects, outlined.model_dump().get("objects"))

    modified_part_ids = [part["part_id"] for part in selected_parts]
    all_part_ids = [part["part_id"] for part in all_parts]
    untouched_part_ids = [part_id for part_id in all_part_ids if part_id not in modified_part_ids]
    return success_result(
        request_id=request.request_id,
        tool_name="modify_silhouette",
        summary=f"Adjusted silhouette with '{request.adjustment}' across {len(object_ids)} objects.",
        project_id=project.project_id,
        asset_id=asset.get("asset_id") if asset else None,
        modified_object_ids=object_ids,
        modified_part_ids=modified_part_ids,
        untouched_part_ids=untouched_part_ids,
        objects=list(objects.values()),
        adjustment=request.adjustment,
    )


async def restyle_model(context, request: RestyleModelRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    resolved = await _resolve_revision_scope(context, request, "restyle_model")
    if isinstance(resolved, CommonToolResult):
        return resolved
    object_ids, selected_parts, all_parts, asset = resolved
    properties = _style_material_properties(request.style_target)
    asset_name = asset.get("name") if asset else _normalize_name(None, "Restyled Asset")
    style_material = await _create_pbr_material_for_style(
        context,
        request.request_id,
        request.project_id,
        name=f"{asset_name} {request.style_target.title()}",
        base_color=properties["base_color"],
        roughness=properties["roughness"],
        metallic=properties["metallic"],
        emission_color=properties.get("emission_color"),
        emission_strength=properties.get("emission_strength"),
    )
    if style_material.status != "success":
        return _retag_result(style_material, "restyle_model")
    material_id = _first_material_id(style_material)
    if material_id is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="restyle_model",
            summary="Failed to resolve the generated style material.",
            errors=["validation_error: generated style material was missing material_id"],
        )

    applied = await _apply_material_to_targets(context, request.request_id, request.project_id, material_id, object_ids)
    if applied.status not in {"success", "partial_success"}:
        return _retag_result(applied, "restyle_model")
    objects = {obj["object_id"]: obj for obj in applied.model_dump().get("objects", [])}

    if request.style_target == "low-poly":
        for object_id in object_ids:
            decimated = await _ensure_modifier(
                context,
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=object_id,
                modifier_type="DECIMATE",
                modifier_name="MCPLowPoly",
                params={"ratio": 0.45},
            )
            if decimated.status != "success":
                return _retag_result(decimated, "restyle_model")
            _merge_objects(objects, decimated.model_dump().get("objects"))

    if asset is not None:
        asset = dict(asset)
        asset["style"] = request.style_target
        existing_materials = list(dict.fromkeys([*asset.get("materials", []), material_id]))
        asset["materials"] = existing_materials
        _persist_asset(context, project.project_id, asset)

    modified_part_ids = [part["part_id"] for part in selected_parts]
    all_part_ids = [part["part_id"] for part in all_parts]
    untouched_part_ids = [part_id for part_id in all_part_ids if part_id not in modified_part_ids]
    return success_result(
        request_id=request.request_id,
        tool_name="restyle_model",
        summary=f"Restyled model toward '{request.style_target}'.",
        project_id=project.project_id,
        asset_id=asset.get("asset_id") if asset else None,
        modified_object_ids=object_ids,
        modified_part_ids=modified_part_ids,
        untouched_part_ids=untouched_part_ids,
        objects=list(objects.values()),
        material=style_material.model_dump()["material"],
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, str, type[BaseModel], Any, bool]] = [
        ("create_model", "Create a core supported model by dispatching to the best-fit generation family.", "model_generation", CreateModelRequest, create_model, False),
        ("create_hard_surface_model", "Create a supported hard-surface asset template.", "category_generation", CreateHardSurfaceModelRequest, create_hard_surface_model, False),
        ("create_building", "Create an exterior building shell with doors, roof, and facade windows.", "category_generation", CreateBuildingRequest, create_building, False),
        ("create_furniture", "Create a core furniture asset with editable semantic parts.", "category_generation", CreateFurnitureRequest, create_furniture, False),
        ("increase_detail", "Add local geometric detail while preserving editability.", "model_generation", IncreaseDetailRequest, increase_detail, False),
        ("reduce_detail", "Reduce local geometric complexity while preserving the broader asset structure.", "model_generation", ReduceDetailRequest, reduce_detail, False),
        ("modify_silhouette", "Adjust the silhouette of a targeted asset region.", "model_generation", ModifySilhouetteRequest, modify_silhouette, False),
        ("restyle_model", "Restyle a targeted asset or part toward a supported visual direction.", "model_generation", RestyleModelRequest, restyle_model, False),
    ]
    for name, description, family, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family=family,
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )