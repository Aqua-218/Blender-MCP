from __future__ import annotations

import math
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
from mcp_server.tools.advanced_helpers import (
    list_entity_specs,
    load_entity_spec,
    save_metadata_entity,
)
from mcp_server.tools.game_prep import (
    ValidateGameExportReadinessRequest,
    validate_game_export_readiness,
)
from mcp_server.tools.helpers import project_paths_for_record, require_project
from mcp_server.utils import new_id, slugify, utc_now_iso
from mcp_server.workspace import WorkspaceViolationError

EngineName = Literal["unreal", "unity", "godot", "web"]
ContentScale = Literal["prototype", "vertical_slice", "indie", "aa", "aaa"]
WorldScope = Literal["linear", "hub", "open_world", "arena", "sandbox"]
AssetBriefType = Literal[
    "character",
    "creature",
    "weapon",
    "vehicle",
    "prop",
    "environment",
    "foliage",
    "vfx",
    "material",
    "kit",
    "animation",
    "cinematic",
]
AssetBriefStatus = Literal["planned", "blocked", "in_progress", "review", "approved", "cut"]
StreamingStrategy = Literal["grid", "world_partition", "additive_scenes", "manual_zones"]


class CreateGameProductionPlanRequest(CommonToolRequest):
    project_id: str
    game_title: str
    genre: str = "action adventure"
    content_scale: ContentScale = "aaa"
    target_engines: list[EngineName] = Field(default_factory=lambda: ["unreal"])
    target_platforms: list[str] = Field(default_factory=lambda: ["pc", "console"])
    world_scope: WorldScope = "open_world"
    art_direction: str | None = None
    gameplay_pillars: list[str] = Field(default_factory=lambda: ["exploration", "combat", "progression"])
    hours_of_content: float = Field(default=20.0, gt=0.0, le=500.0)
    production_tracks: list[str] = Field(default_factory=list)


class ListGameProductionPlansRequest(CommonToolRequest):
    project_id: str
    content_scale: ContentScale | None = None
    title_query: str = ""


class CreateAssetBriefRequest(CommonToolRequest):
    project_id: str
    asset_name: str
    asset_type: AssetBriefType = "prop"
    plan_id: str | None = None
    description: str | None = None
    target_quality: Literal["draft", "standard", "high", "hero"] = "high"
    engine: EngineName = "unreal"
    gameplay_tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    status: AssetBriefStatus = "planned"
    triangle_budget: int | None = Field(default=None, gt=0)
    texture_resolution: int | None = Field(default=None, gt=0)
    lod_count: int | None = Field(default=None, ge=0, le=8)
    requires_collision: bool | None = None
    requires_sockets: bool = False
    animation_requirements: list[str] = Field(default_factory=list)


class ListAssetBriefsRequest(CommonToolRequest):
    project_id: str
    plan_id: str | None = None
    asset_type: AssetBriefType | None = None
    status: AssetBriefStatus | None = None
    query: str = ""


class UpdateAssetBriefStatusRequest(CommonToolRequest):
    project_id: str
    brief_id: str
    status: AssetBriefStatus
    notes: str | None = None


class PlanLevelStreamingRequest(CommonToolRequest):
    project_id: str
    level_name: str
    plan_id: str | None = None
    world_id: str | None = None
    min_corner: tuple[float, float, float] = (-1024.0, -1024.0, 0.0)
    max_corner: tuple[float, float, float] = (1024.0, 1024.0, 256.0)
    cell_size: float = Field(default=256.0, gt=0.0)
    strategy: StreamingStrategy = "world_partition"
    target_platform: str = "pc"
    memory_budget_mb: int = Field(default=512, gt=0)
    object_budget_per_cell: int = Field(default=2500, gt=0)


class ListLevelStreamingPlansRequest(CommonToolRequest):
    project_id: str
    plan_id: str | None = None
    world_id: str | None = None


class ValidateProductionReadinessRequest(CommonToolRequest):
    project_id: str
    plan_id: str | None = None
    min_asset_briefs: int = Field(default=1, ge=0)
    require_asset_library: bool = False
    require_streaming_plan: bool = False
    require_game_export: bool = True
    require_approved_briefs: bool = False
    require_aaa_gates: bool = False


class PlanGameProductionPackageRequest(ValidateProductionReadinessRequest):
    package_name: str = "game_production_package"


class WriteGameProductionPackageRequest(PlanGameProductionPackageRequest):
    output_path: str | None = None


def _production_plans(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, "game_production_plan")


def _asset_briefs(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, "asset_brief")


def _streaming_plans(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return list_entity_specs(context, project_id, "level_streaming_plan")


def _save_entity(context, project_id: str, entity_type: str, entity_id: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=entity_id,
        entity_type=entity_type,
        name=name,
        spec=spec,
    )


def _load_project_entity(
    context,
    project_id: str,
    entity_id: str,
    entity_type: str,
    request_id: str,
    tool_name: str,
) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    spec = load_entity_spec(context, entity_id, expected_type=entity_type)
    if spec is None or spec.get("project_id") != project_id:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"{entity_type} '{entity_id}' was not found.",
            errors=[f"target_not_found: {entity_type} '{entity_id}' does not exist in this project"],
        )
    return spec


def _content_profile(scale: ContentScale) -> dict[str, int]:
    profiles = {
        "prototype": {"multiplier": 1, "milestones": 3},
        "vertical_slice": {"multiplier": 3, "milestones": 4},
        "indie": {"multiplier": 6, "milestones": 5},
        "aa": {"multiplier": 12, "milestones": 6},
        "aaa": {"multiplier": 24, "milestones": 7},
    }
    return profiles[scale]


def _default_tracks(requested: list[str]) -> list[str]:
    defaults = [
        "game_design",
        "world_art",
        "character_art",
        "hard_surface",
        "materials",
        "animation",
        "cinematics",
        "technical_art",
        "lighting",
        "qa",
    ]
    return list(dict.fromkeys([*requested, *defaults]))


def _asset_backlog(scale: ContentScale, world_scope: WorldScope) -> list[dict[str, Any]]:
    multiplier = _content_profile(scale)["multiplier"]
    scope_boost = 2 if world_scope in {"open_world", "sandbox"} else 1
    counts = {
        "character": max(1, multiplier // 2),
        "creature": max(0, multiplier // 3),
        "weapon": multiplier * 3,
        "vehicle": max(1, multiplier // 2) if world_scope in {"open_world", "sandbox", "hub"} else max(0, multiplier // 6),
        "prop": multiplier * 24 * scope_boost,
        "environment": multiplier * 2 * scope_boost,
        "foliage": multiplier * 5 * scope_boost,
        "vfx": multiplier * 4,
        "material": multiplier * 8 * scope_boost,
        "kit": multiplier * scope_boost,
        "animation": multiplier * 5,
        "cinematic": max(1, multiplier // 2),
    }
    return [
        {
            "asset_type": asset_type,
            "target_count": count,
            "hero_count": max(1, count // 10) if count else 0,
            "quality_floor": "hero" if asset_type in {"character", "vehicle", "weapon", "cinematic"} else "high",
            "lod_policy": "required" if asset_type in {"character", "creature", "vehicle", "prop", "environment", "foliage", "kit"} else "as_needed",
            "collision_policy": "required" if asset_type in {"character", "creature", "vehicle", "weapon", "prop", "environment", "kit"} else "none",
            "texture_policy": "pbr_texture_set",
        }
        for asset_type, count in counts.items()
        if count > 0
    ]


def _production_milestones(scale: ContentScale) -> list[dict[str, Any]]:
    base = [
        ("concept_lock", "Core fantasy, pillars, art direction, and technical constraints are signed off."),
        ("prototype", "Playable loop uses proxy assets and validates scope risks."),
        ("vertical_slice", "One production-quality gameplay slice proves asset, lighting, export, and QA gates."),
        ("content_alpha", "All planned content is present with rough polish and no missing critical assets."),
        ("beta", "Content complete, performance budget tracked, and import/export regressions locked down."),
        ("release_candidate", "Only ship-blocking fixes remain; production package manifests are reproducible."),
        ("gold_master", "Final package passes engine import, visual QA, gameplay collision, and archive checks."),
    ]
    count = _content_profile(scale)["milestones"]
    return [
        {
            "milestone_id": milestone_id,
            "label": milestone_id.replace("_", " ").title(),
            "acceptance": acceptance,
            "gate": "required",
        }
        for milestone_id, acceptance in base[:count]
    ]


def _quality_gates(scale: ContentScale, engines: list[str]) -> list[dict[str, Any]]:
    gates = [
        {"gate_id": "asset_briefs", "severity": "error", "description": "Every production asset has an approved brief with budget, dependencies, and gameplay tags."},
        {"gate_id": "lod_collision", "severity": "error", "description": "Runtime meshes have LOD metadata and collision strategy before engine export."},
        {"gate_id": "pbr_materials", "severity": "warning", "description": "Render meshes have PBR material slots and texture set manifests."},
        {"gate_id": "streaming_budget", "severity": "warning", "description": "Large worlds are divided into memory-budgeted streaming cells."},
        {"gate_id": "engine_import", "severity": "error", "description": f"Package validates against target engines: {', '.join(engines)}."},
    ]
    if scale == "aaa":
        gates.extend(
            [
                {"gate_id": "cinematic_review", "severity": "warning", "description": "Hero shots, camera bookmarks, and lighting setups exist for market-facing assets."},
                {"gate_id": "performance_budget", "severity": "error", "description": "Polycount, draw-call, texture memory, and streaming budgets are tracked per asset class."},
            ]
        )
    return gates


def _default_asset_budget(asset_type: str, quality: str, engine: str) -> dict[str, Any]:
    quality_multiplier = {"draft": 0.25, "standard": 0.5, "high": 1.0, "hero": 1.8}[quality]
    base_triangles = {
        "character": 80000,
        "creature": 90000,
        "weapon": 20000,
        "vehicle": 120000,
        "prop": 12000,
        "environment": 60000,
        "foliage": 8000,
        "vfx": 4000,
        "material": 1000,
        "kit": 50000,
        "animation": 1000,
        "cinematic": 160000,
    }
    base_texture = 4096 if quality in {"high", "hero"} else 2048
    if asset_type in {"foliage", "vfx", "material"}:
        base_texture = min(base_texture, 2048)
    requires_collision = asset_type in {"character", "creature", "weapon", "vehicle", "prop", "environment", "kit"}
    return {
        "triangle_budget": max(250, int(base_triangles.get(asset_type, 12000) * quality_multiplier)),
        "texture_resolution": base_texture,
        "texture_sets": ["base_color", "normal", "orm"] if engine in {"unreal", "unity", "godot"} else ["base_color", "normal"],
        "lod_count": 4 if quality == "hero" else 3 if quality == "high" else 2,
        "requires_collision": requires_collision,
        "requires_sockets": asset_type in {"weapon", "vehicle"},
    }


async def create_game_production_plan(context, request: CreateGameProductionPlanRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    plan_id = new_id("gameplan")
    engines = list(dict.fromkeys(request.target_engines or ["unreal"]))
    plan = {
        "plan_id": plan_id,
        "project_id": project.project_id,
        "game_title": request.game_title,
        "genre": request.genre,
        "content_scale": request.content_scale,
        "target_engines": engines,
        "target_platforms": list(dict.fromkeys(request.target_platforms)),
        "world_scope": request.world_scope,
        "art_direction": request.art_direction,
        "gameplay_pillars": list(dict.fromkeys(request.gameplay_pillars)),
        "hours_of_content": request.hours_of_content,
        "production_tracks": _default_tracks(request.production_tracks),
        "milestones": _production_milestones(request.content_scale),
        "asset_backlog": _asset_backlog(request.content_scale, request.world_scope),
        "quality_gates": _quality_gates(request.content_scale, engines),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    _save_entity(context, project.project_id, "game_production_plan", plan_id, request.game_title, plan)
    return success_result(
        request_id=request.request_id,
        tool_name="create_game_production_plan",
        summary=f"Created {request.content_scale.upper()} production plan for '{request.game_title}'.",
        project_id=project.project_id,
        plan_id=plan_id,
        plan=plan,
    )


async def list_game_production_plans(context, request: ListGameProductionPlansRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    query = request.title_query.lower().strip()
    plans = []
    for plan in _production_plans(context, request.project_id):
        if request.content_scale is not None and plan.get("content_scale") != request.content_scale:
            continue
        if query and query not in str(plan.get("game_title", "")).lower():
            continue
        plans.append(plan)
    return success_result(
        request_id=request.request_id,
        tool_name="list_game_production_plans",
        summary=f"Listed {len(plans)} game production plan(s).",
        project_id=request.project_id,
        plans=plans,
        count=len(plans),
    )


async def create_asset_brief(context, request: CreateAssetBriefRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    plan: dict[str, Any] | None = None
    if request.plan_id is not None:
        loaded = _load_project_entity(
            context,
            project.project_id,
            request.plan_id,
            "game_production_plan",
            request.request_id,
            "create_asset_brief",
        )
        if isinstance(loaded, CommonToolResult):
            return loaded
        plan = loaded
    budget = _default_asset_budget(request.asset_type, request.target_quality, request.engine)
    if request.triangle_budget is not None:
        budget["triangle_budget"] = request.triangle_budget
    if request.texture_resolution is not None:
        budget["texture_resolution"] = request.texture_resolution
    if request.lod_count is not None:
        budget["lod_count"] = request.lod_count
    if request.requires_collision is not None:
        budget["requires_collision"] = request.requires_collision
    brief_id = new_id("brief")
    brief = {
        "brief_id": brief_id,
        "project_id": project.project_id,
        "plan_id": request.plan_id,
        "asset_name": request.asset_name,
        "asset_type": request.asset_type,
        "description": request.description,
        "target_quality": request.target_quality,
        "engine": request.engine,
        "gameplay_tags": list(dict.fromkeys(request.gameplay_tags)),
        "dependencies": list(dict.fromkeys(request.dependencies)),
        "status": request.status,
        "budget": {
            **budget,
            "requires_sockets": request.requires_sockets or bool(budget["requires_sockets"]),
            "animation_requirements": list(dict.fromkeys(request.animation_requirements)),
        },
        "source_plan_title": plan.get("game_title") if plan else None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "status_history": [{"status": request.status, "at": utc_now_iso(), "notes": "created"}],
    }
    _save_entity(context, project.project_id, "asset_brief", brief_id, request.asset_name, brief)
    return success_result(
        request_id=request.request_id,
        tool_name="create_asset_brief",
        summary=f"Created asset brief '{request.asset_name}'.",
        project_id=project.project_id,
        brief_id=brief_id,
        brief=brief,
    )


async def list_asset_briefs(context, request: ListAssetBriefsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    query = request.query.lower().strip()
    briefs: list[dict[str, Any]] = []
    for brief in _asset_briefs(context, request.project_id):
        if request.plan_id is not None and brief.get("plan_id") != request.plan_id:
            continue
        if request.asset_type is not None and brief.get("asset_type") != request.asset_type:
            continue
        if request.status is not None and brief.get("status") != request.status:
            continue
        haystack = " ".join(
            [
                str(brief.get("asset_name", "")),
                str(brief.get("asset_type", "")),
                str(brief.get("description", "")),
                " ".join(str(tag) for tag in brief.get("gameplay_tags", [])),
            ]
        ).lower()
        if query and query not in haystack:
            continue
        briefs.append(brief)
    return success_result(
        request_id=request.request_id,
        tool_name="list_asset_briefs",
        summary=f"Listed {len(briefs)} asset brief(s).",
        project_id=request.project_id,
        briefs=briefs,
        count=len(briefs),
    )


async def update_asset_brief_status(context, request: UpdateAssetBriefStatusRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    brief = _load_project_entity(
        context,
        project.project_id,
        request.brief_id,
        "asset_brief",
        request.request_id,
        "update_asset_brief_status",
    )
    if isinstance(brief, CommonToolResult):
        return brief
    brief["status"] = request.status
    brief["updated_at"] = utc_now_iso()
    brief["status_history"] = [
        *list(brief.get("status_history", [])),
        {"status": request.status, "at": utc_now_iso(), "notes": request.notes},
    ]
    _save_entity(context, project.project_id, "asset_brief", request.brief_id, str(brief["asset_name"]), brief)
    return success_result(
        request_id=request.request_id,
        tool_name="update_asset_brief_status",
        summary=f"Updated asset brief '{brief['asset_name']}' to {request.status}.",
        project_id=project.project_id,
        brief_id=request.brief_id,
        brief=brief,
    )


async def plan_level_streaming(context, request: PlanLevelStreamingRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    if request.plan_id is not None:
        loaded_plan = _load_project_entity(
            context,
            project.project_id,
            request.plan_id,
            "game_production_plan",
            request.request_id,
            "plan_level_streaming",
        )
        if isinstance(loaded_plan, CommonToolResult):
            return loaded_plan
    min_corner = list(request.min_corner)
    max_corner = list(request.max_corner)
    if any(max_corner[index] <= min_corner[index] for index in range(3)):
        return failed_result(
            request_id=request.request_id,
            tool_name="plan_level_streaming",
            summary="Level bounds are invalid.",
            errors=["validation_error: max_corner must be greater than min_corner on every axis"],
        )
    axis_counts = [max(1, math.ceil((max_corner[index] - min_corner[index]) / request.cell_size)) for index in range(3)]
    cell_count = axis_counts[0] * axis_counts[1] * axis_counts[2]
    if cell_count > 512:
        return failed_result(
            request_id=request.request_id,
            tool_name="plan_level_streaming",
            summary=f"Streaming plan would create {cell_count} cells, above the 512-cell guardrail.",
            errors=["validation_error: increase cell_size or reduce bounds"],
        )
    memory_per_cell = round(request.memory_budget_mb / cell_count, 3)
    cells: list[dict[str, Any]] = []
    for z_index in range(axis_counts[2]):
        for y_index in range(axis_counts[1]):
            for x_index in range(axis_counts[0]):
                cell_min = [
                    min_corner[0] + (x_index * request.cell_size),
                    min_corner[1] + (y_index * request.cell_size),
                    min_corner[2] + (z_index * request.cell_size),
                ]
                cell_max = [
                    min(max_corner[0], cell_min[0] + request.cell_size),
                    min(max_corner[1], cell_min[1] + request.cell_size),
                    min(max_corner[2], cell_min[2] + request.cell_size),
                ]
                cells.append(
                    {
                        "cell_id": f"{slugify(request.level_name)}_{x_index:02d}_{y_index:02d}_{z_index:02d}",
                        "grid": [x_index, y_index, z_index],
                        "bounds": {"min": cell_min, "max": cell_max},
                        "memory_budget_mb": memory_per_cell,
                        "object_budget": request.object_budget_per_cell,
                        "streaming_tags": [request.strategy, request.target_platform],
                    }
                )
    streaming_plan_id = new_id("stream")
    streaming_plan = {
        "streaming_plan_id": streaming_plan_id,
        "project_id": project.project_id,
        "plan_id": request.plan_id,
        "world_id": request.world_id,
        "level_name": request.level_name,
        "strategy": request.strategy,
        "target_platform": request.target_platform,
        "bounds": {"min": min_corner, "max": max_corner},
        "cell_size": request.cell_size,
        "grid_size": axis_counts,
        "cell_count": cell_count,
        "memory_budget_mb": request.memory_budget_mb,
        "object_budget_per_cell": request.object_budget_per_cell,
        "cells": cells,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    _save_entity(
        context,
        project.project_id,
        "level_streaming_plan",
        streaming_plan_id,
        request.level_name,
        streaming_plan,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="plan_level_streaming",
        summary=f"Planned {cell_count} streaming cell(s) for '{request.level_name}'.",
        project_id=project.project_id,
        streaming_plan_id=streaming_plan_id,
        streaming_plan=streaming_plan,
    )


async def list_level_streaming_plans(context, request: ListLevelStreamingPlansRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    plans = []
    for plan in _streaming_plans(context, request.project_id):
        if request.plan_id is not None and plan.get("plan_id") != request.plan_id:
            continue
        if request.world_id is not None and plan.get("world_id") != request.world_id:
            continue
        plans.append(plan)
    return success_result(
        request_id=request.request_id,
        tool_name="list_level_streaming_plans",
        summary=f"Listed {len(plans)} level streaming plan(s).",
        project_id=request.project_id,
        streaming_plans=plans,
        count=len(plans),
    )


async def validate_production_readiness(context, request: ValidateProductionReadinessRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    findings: list[dict[str, Any]] = []
    gate_reports: list[dict[str, Any]] = []
    plans = _production_plans(context, project.project_id)
    if request.plan_id is not None:
        plans = [plan for plan in plans if plan.get("plan_id") == request.plan_id]
        if not plans:
            findings.append({"severity": "error", "code": "missing_production_plan", "message": f"Production plan '{request.plan_id}' was not found."})
    elif not plans:
        findings.append({"severity": "error", "code": "missing_production_plan", "message": "No game production plan has been created."})

    selected_plan = plans[0] if plans else None
    if selected_plan is not None:
        if not selected_plan.get("gameplay_pillars"):
            findings.append({"severity": "warning", "code": "missing_gameplay_pillars", "message": "Production plan has no gameplay pillars."})
        if not selected_plan.get("target_engines"):
            findings.append({"severity": "error", "code": "missing_target_engines", "message": "Production plan has no target engine."})

    briefs = _asset_briefs(context, project.project_id)
    if selected_plan is not None:
        briefs = [brief for brief in briefs if brief.get("plan_id") in {None, selected_plan.get("plan_id")}]
    if len(briefs) < request.min_asset_briefs:
        findings.append({"severity": "error", "code": "not_enough_asset_briefs", "message": f"Expected at least {request.min_asset_briefs} asset brief(s), found {len(briefs)}."})
    approved_count = sum(1 for brief in briefs if brief.get("status") == "approved")
    if request.require_approved_briefs and briefs and approved_count < len(briefs):
        findings.append({"severity": "warning", "code": "unapproved_asset_briefs", "message": f"{len(briefs) - approved_count} asset brief(s) are not approved."})

    assets = list_entity_specs(context, project.project_id, "asset_library_item")
    if request.require_asset_library and not assets:
        findings.append({"severity": "error", "code": "missing_asset_library", "message": "No asset library items are registered."})
    coverage = _asset_library_coverage(briefs, assets)
    if briefs and assets and coverage["coverage_ratio"] < 0.5:
        findings.append({"severity": "warning", "code": "low_asset_library_coverage", "message": "Less than half of asset briefs have matching asset library items.", "coverage": coverage})

    streaming = _streaming_plans(context, project.project_id)
    if selected_plan is not None:
        streaming = [plan for plan in streaming if plan.get("plan_id") in {None, selected_plan.get("plan_id")}]
    if request.require_streaming_plan and not streaming:
        findings.append({"severity": "error", "code": "missing_streaming_plan", "message": "No level streaming plan exists."})
    worlds = list_entity_specs(context, project.project_id, "world")
    if selected_plan is not None and selected_plan.get("world_scope") in {"open_world", "sandbox", "hub"} and not worlds:
        findings.append({"severity": "warning", "code": "missing_world_entity", "message": "Production plan expects a large world, but no world entity exists."})

    export_readiness_payload: dict[str, Any] | None = None
    if request.require_game_export:
        export_readiness = await validate_game_export_readiness(
            context,
            ValidateGameExportReadinessRequest(
                request_id=f"{request.request_id}-game-export",
                project_id=project.project_id,
                require_collision=request.require_aaa_gates,
                require_lods=request.require_aaa_gates,
                require_materials=True,
            ),
        )
        export_readiness_payload = export_readiness.model_dump()
        for finding in export_readiness_payload.get("findings", []):
            severity = "error" if request.require_aaa_gates and finding.get("severity") == "warning" else finding.get("severity", "info")
            findings.append(
                {
                    "severity": severity,
                    "code": f"game_export_{finding.get('code')}",
                    "message": finding.get("message"),
                    "source": "validate_game_export_readiness",
                }
            )

    gate_reports.extend(
        [
            _gate("planning", not any(item["code"].startswith("missing_production_plan") for item in findings), "Production plan exists and has core targets."),
            _gate("asset_briefs", len(briefs) >= request.min_asset_briefs, "Minimum asset brief coverage is present."),
            _gate("asset_library", bool(assets) or not request.require_asset_library, "Asset library is registered when required."),
            _gate("streaming", bool(streaming) or not request.require_streaming_plan, "Level streaming plan is available when required."),
            _gate("game_export", not any(str(item["code"]).startswith("game_export_no_mesh") for item in findings), "Scene has exportable meshes when export readiness is required."),
        ]
    )
    severity_summary = _summarize_findings(findings)
    return success_result(
        request_id=request.request_id,
        tool_name="validate_production_readiness",
        summary="Production readiness validation completed.",
        project_id=project.project_id,
        production_ready=severity_summary.get("error", 0) == 0,
        findings=findings,
        severity_summary=severity_summary,
        gates=gate_reports,
        metrics={
            "production_plan_count": len(plans),
            "asset_brief_count": len(briefs),
            "approved_asset_brief_count": approved_count,
            "asset_library_count": len(assets),
            "asset_library_coverage_ratio": coverage["coverage_ratio"],
            "streaming_plan_count": len(streaming),
            "world_count": len(worlds),
        },
        export_readiness=export_readiness_payload,
    )


async def plan_game_production_package(context, request: PlanGameProductionPackageRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    manifest = await _build_production_package(context, request)
    return success_result(
        request_id=request.request_id,
        tool_name="plan_game_production_package",
        summary=f"Planned game production package '{request.package_name}'.",
        project_id=project.project_id,
        package=manifest,
        readiness=manifest["readiness"],
    )


async def write_game_production_package(context, request: WriteGameProductionPackageRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    manifest = await _build_production_package(context, request)
    try:
        output_path = _package_output_path(context, project, request.output_path, request.package_name)
    except WorkspaceViolationError as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="write_game_production_package",
            summary=str(exc),
            errors=[f"validation_error: {exc}"],
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_dumps(manifest, pretty=True) + "\n", encoding="utf-8")
    return success_result(
        request_id=request.request_id,
        tool_name="write_game_production_package",
        summary=f"Wrote game production package to {output_path.name}.",
        project_id=project.project_id,
        file_paths=[str(output_path)],
        package=manifest,
        readiness=manifest["readiness"],
    )


async def _build_production_package(context, request: PlanGameProductionPackageRequest) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    readiness = await validate_production_readiness(
        context,
        ValidateProductionReadinessRequest(
            request_id=f"{request.request_id}-readiness",
            project_id=request.project_id,
            plan_id=request.plan_id,
            min_asset_briefs=request.min_asset_briefs,
            require_asset_library=request.require_asset_library,
            require_streaming_plan=request.require_streaming_plan,
            require_game_export=request.require_game_export,
            require_approved_briefs=request.require_approved_briefs,
            require_aaa_gates=request.require_aaa_gates,
        ),
    )
    plans = _production_plans(context, request.project_id)
    if request.plan_id is not None:
        plans = [plan for plan in plans if plan.get("plan_id") == request.plan_id]
    briefs = _asset_briefs(context, request.project_id)
    if request.plan_id is not None:
        briefs = [brief for brief in briefs if brief.get("plan_id") in {None, request.plan_id}]
    return {
        "package_name": request.package_name,
        "project_id": request.project_id,
        "created_at": utc_now_iso(),
        "production_plans": plans,
        "asset_briefs": briefs,
        "level_streaming_plans": _streaming_plans(context, request.project_id),
        "asset_library_items": list_entity_specs(context, request.project_id, "asset_library_item"),
        "worlds": list_entity_specs(context, request.project_id, "world"),
        "readiness": readiness.model_dump(),
        "metrics": {
            "production_plan_count": len(plans),
            "asset_brief_count": len(briefs),
            "level_streaming_plan_count": len(_streaming_plans(context, request.project_id)),
        },
    }


def _asset_library_coverage(briefs: list[dict[str, Any]], assets: list[dict[str, Any]]) -> dict[str, Any]:
    asset_names = {str(item.get("asset_name", "")).lower() for item in assets}
    matched = [
        brief
        for brief in briefs
        if str(brief.get("asset_name", "")).lower() in asset_names
    ]
    return {
        "brief_count": len(briefs),
        "matched_count": len(matched),
        "coverage_ratio": round(len(matched) / len(briefs), 4) if briefs else 1.0,
        "matched_brief_ids": [brief.get("brief_id") for brief in matched],
    }


def _gate(gate_id: str, passed: bool, description: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "status": "passed" if passed else "blocked", "description": description}


def _summarize_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in summary:
            summary[severity] += 1
    return summary


def _package_output_path(context, project, raw_output_path: str | None, package_name: str) -> Path:  # type: ignore[no-untyped-def]
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    export_dir = project_paths.export_dir.resolve()
    relative_path = Path(raw_output_path) if raw_output_path else Path(f"{slugify(package_name) or 'game-production-package'}.json")
    candidate = relative_path.resolve(strict=False) if relative_path.is_absolute() else (export_dir / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(export_dir)
    except ValueError as exc:
        raise WorkspaceViolationError("Game production package path must stay under the project's export directory.") from exc
    if candidate.suffix.lower() != ".json":
        candidate = candidate.with_suffix(".json")
    return candidate


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_game_production_plan", "Create a machine-readable AAA-scale game production plan with milestones, asset backlog, and quality gates.", CreateGameProductionPlanRequest, create_game_production_plan, False),
        ("list_game_production_plans", "List stored game production plans.", ListGameProductionPlansRequest, list_game_production_plans, True),
        ("create_asset_brief", "Create a production asset brief with budgets, dependencies, gameplay tags, LOD, texture, and collision expectations.", CreateAssetBriefRequest, create_asset_brief, False),
        ("list_asset_briefs", "List production asset briefs by plan, type, status, or text query.", ListAssetBriefsRequest, list_asset_briefs, True),
        ("update_asset_brief_status", "Move an asset brief through planned, blocked, in-progress, review, approved, or cut states.", UpdateAssetBriefStatusRequest, update_asset_brief_status, False),
        ("plan_level_streaming", "Create a grid/world-partition level streaming plan with per-cell memory and object budgets.", PlanLevelStreamingRequest, plan_level_streaming, False),
        ("list_level_streaming_plans", "List stored level streaming plans.", ListLevelStreamingPlansRequest, list_level_streaming_plans, True),
        ("validate_production_readiness", "Validate production planning, asset briefs, asset library coverage, streaming plans, and game export readiness.", ValidateProductionReadinessRequest, validate_production_readiness, True),
        ("plan_game_production_package", "Assemble a production package manifest without writing files.", PlanGameProductionPackageRequest, plan_game_production_package, True),
        ("write_game_production_package", "Write a project-scoped production package manifest JSON file.", WriteGameProductionPackageRequest, write_game_production_package, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="production_pipeline",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
