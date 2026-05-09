from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from mcp_server.models.common import CommonToolRequest, success_result

WorkflowPhase = Literal[
    "brief",
    "blockout",
    "generate",
    "detail",
    "materialize",
    "rig_setup",
    "optimize",
    "validate",
    "package",
    "review",
]


class AAAWorkflowRequest(CommonToolRequest):
    project_id: str | None = None
    goal: str | None = None
    target_engine: Literal["unreal", "unity", "godot", "web"] = "unreal"
    target_platform: str = "pc_console"
    quality_bar: Literal["draft", "standard", "high", "hero", "shipping"] = "hero"
    constraints: list[str] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)
    include_tool_chain: bool = True
    include_acceptance_criteria: bool = True


DOMAIN_PACKS: list[dict[str, str]] = [
    {"key": "hero_character", "label": "Hero Character", "track": "character_art"},
    {"key": "npc_crowd", "label": "NPC Crowd", "track": "character_art"},
    {"key": "enemy_creature", "label": "Enemy Creature", "track": "creature_art"},
    {"key": "facial_rig", "label": "Facial Rig", "track": "animation"},
    {"key": "locomotion_set", "label": "Locomotion Set", "track": "animation"},
    {"key": "combat_animation", "label": "Combat Animation", "track": "animation"},
    {"key": "firearm_weapon", "label": "Firearm Weapon", "track": "hard_surface"},
    {"key": "melee_weapon", "label": "Melee Weapon", "track": "hard_surface"},
    {"key": "ground_vehicle", "label": "Ground Vehicle", "track": "vehicle_art"},
    {"key": "air_vehicle", "label": "Air Vehicle", "track": "vehicle_art"},
    {"key": "modular_building", "label": "Modular Building", "track": "environment_art"},
    {"key": "interior_set", "label": "Interior Set", "track": "environment_art"},
    {"key": "hero_prop", "label": "Hero Prop", "track": "prop_art"},
    {"key": "filler_prop", "label": "Filler Prop", "track": "prop_art"},
    {"key": "tree_foliage", "label": "Tree Foliage", "track": "foliage"},
    {"key": "groundcover_foliage", "label": "Groundcover Foliage", "track": "foliage"},
    {"key": "terrain_biome", "label": "Terrain Biome", "track": "world_art"},
    {"key": "road_network", "label": "Road Network", "track": "world_art"},
    {"key": "water_system", "label": "Water System", "track": "world_art"},
    {"key": "sky_weather", "label": "Sky Weather", "track": "lighting"},
    {"key": "day_lighting", "label": "Day Lighting", "track": "lighting"},
    {"key": "night_lighting", "label": "Night Lighting", "track": "lighting"},
    {"key": "master_material", "label": "Master Material", "track": "materials"},
    {"key": "trim_sheet", "label": "Trim Sheet", "track": "materials"},
    {"key": "decal_set", "label": "Decal Set", "track": "materials"},
    {"key": "explosion_vfx", "label": "Explosion VFX", "track": "vfx"},
    {"key": "magic_vfx", "label": "Magic VFX", "track": "vfx"},
    {"key": "ui_3d_widget", "label": "3D UI Widget", "track": "ui"},
    {"key": "cinematic_shot", "label": "Cinematic Shot", "track": "cinematics"},
    {"key": "camera_layout", "label": "Camera Layout", "track": "cinematics"},
    {"key": "quest_marker", "label": "Quest Marker", "track": "gameplay"},
    {"key": "navmesh_blockout", "label": "Navmesh Blockout", "track": "gameplay"},
    {"key": "collision_pass", "label": "Collision Pass", "track": "technical_art"},
    {"key": "lod_pass", "label": "LOD Pass", "track": "technical_art"},
    {"key": "occlusion_pass", "label": "Occlusion Pass", "track": "technical_art"},
    {"key": "streaming_cell", "label": "Streaming Cell", "track": "world_art"},
    {"key": "audio_marker", "label": "Audio Marker", "track": "audio"},
    {"key": "haptic_marker", "label": "Haptic Marker", "track": "gameplay"},
    {"key": "multiplayer_spawn", "label": "Multiplayer Spawn", "track": "gameplay"},
    {"key": "destruction_pass", "label": "Destruction Pass", "track": "technical_art"},
    {"key": "scan_cleanup", "label": "Scan Cleanup", "track": "photogrammetry"},
    {"key": "scan_retopology", "label": "Scan Retopology", "track": "photogrammetry"},
    {"key": "marketplace_import", "label": "Marketplace Import", "track": "asset_ingest"},
    {"key": "unreal_import", "label": "Unreal Import", "track": "engine_integration"},
    {"key": "unity_import", "label": "Unity Import", "track": "engine_integration"},
    {"key": "godot_import", "label": "Godot Import", "track": "engine_integration"},
    {"key": "web_glb_delivery", "label": "Web GLB Delivery", "track": "engine_integration"},
    {"key": "visual_qa", "label": "Visual QA", "track": "qa"},
    {"key": "performance_qa", "label": "Performance QA", "track": "qa"},
    {"key": "accessibility_qa", "label": "Accessibility QA", "track": "qa"},
    {"key": "save_package", "label": "Save Package", "track": "release"},
    {"key": "world_signage", "label": "World Signage", "track": "localization"},
]

PHASE_PACKS: list[dict[str, str]] = [
    {"key": "brief", "label": "Brief", "phase": "brief"},
    {"key": "blockout", "label": "Blockout", "phase": "blockout"},
    {"key": "generate", "label": "Generate", "phase": "generate"},
    {"key": "detail", "label": "Detail", "phase": "detail"},
    {"key": "materialize", "label": "Materialize", "phase": "materialize"},
    {"key": "rig_setup", "label": "Rig or Setup", "phase": "rig_setup"},
    {"key": "optimize", "label": "Optimize", "phase": "optimize"},
    {"key": "validate", "label": "Validate", "phase": "validate"},
    {"key": "package", "label": "Package", "phase": "package"},
    {"key": "review", "label": "Review", "phase": "review"},
]


def _workflow_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    index = 1
    for domain in DOMAIN_PACKS:
        for phase in PHASE_PACKS:
            name = f"aaa_{index:03d}_{domain['key']}_{phase['key']}"
            catalog[name] = {
                "workflow_id": name,
                "domain": domain["key"],
                "domain_label": domain["label"],
                "track": domain["track"],
                "phase": phase["phase"],
                "phase_label": phase["label"],
                "objective": _objective(domain, phase),
                "deliverables": _deliverables(domain, phase),
                "acceptance_criteria": _acceptance_criteria(domain, phase),
                "risk_controls": _risk_controls(domain, phase),
                "recommended_tool_chain": _recommended_tool_chain(domain, phase),
            }
            index += 1
    return catalog


def _objective(domain: dict[str, str], phase: dict[str, str]) -> str:
    return f"{phase['label']} the {domain['label']} production slice to a reproducible AAA workflow handoff."


def _deliverables(domain: dict[str, str], phase: dict[str, str]) -> list[str]:
    shared = [
        f"{domain['label']} scope record",
        "machine-readable constraints",
        "owner-independent acceptance notes",
    ]
    by_phase = {
        "brief": ["asset brief", "budget targets", "dependency list"],
        "blockout": ["proxy geometry", "scale reference", "layout collection"],
        "generate": ["source objects", "semantic tags", "initial collection structure"],
        "detail": ["detail pass notes", "variant targets", "silhouette checkpoints"],
        "materialize": ["PBR material plan", "texture-set manifest", "UV density targets"],
        "rig_setup": ["rig or socket plan", "animation hooks", "gameplay attachment markers"],
        "optimize": ["LOD plan", "collision plan", "performance budget report"],
        "validate": ["QA findings", "engine-readiness verdict", "blocked-risk list"],
        "package": ["export manifest", "engine import checklist", "archive metadata"],
        "review": ["shot checklist", "render targets", "human review questions"],
    }
    return [*shared, *by_phase[phase["phase"]]]


def _acceptance_criteria(domain: dict[str, str], phase: dict[str, str]) -> list[str]:
    criteria = [
        f"{domain['label']} has stable names, tags, and collection membership.",
        "Every generated item can be traced back to a brief, plan, or source object.",
        "Outputs avoid destructive edits unless an explicit snapshot and confirmation exist.",
    ]
    phase_specific = {
        "brief": "Budgets include triangle count, texture size, LOD count, collision, and engine target.",
        "blockout": "Proxy scale matches gameplay units and leaves room for collision and navigation.",
        "generate": "Created objects are grouped, tagged, and ready for material or rig passes.",
        "detail": "Detail increases silhouette/readability without breaking established budgets.",
        "materialize": "Materials use PBR-friendly slots and texture manifests.",
        "rig_setup": "Sockets, bones, markers, or animation tracks have deterministic names.",
        "optimize": "LOD/collision/export checks are represented in machine-readable results.",
        "validate": "Findings are severity-tagged and can be acted on by the next agent.",
        "package": "Package paths remain inside the project export directory.",
        "review": "Review output includes concrete shots, deltas, and next tool suggestions.",
    }
    return [*criteria, phase_specific[phase["phase"]]]


def _risk_controls(domain: dict[str, str], phase: dict[str, str]) -> list[str]:
    controls = ["snapshot before broad mutation", "workspace allowlist", "deterministic naming"]
    if phase["phase"] in {"optimize", "validate", "package"}:
        controls.extend(["engine profile check", "export-readiness gate"])
    if domain["track"] in {"qa", "release", "engine_integration"}:
        controls.extend(["manifest diff review", "blocked severity review"])
    if domain["track"] in {"character_art", "creature_art", "animation"}:
        controls.extend(["rig naming convention", "animation track audit"])
    return list(dict.fromkeys(controls))


def _recommended_tool_chain(domain: dict[str, str], phase: dict[str, str]) -> list[dict[str, Any]]:
    phase_tools = {
        "brief": ["create_game_production_plan", "create_asset_brief", "list_asset_briefs"],
        "blockout": ["create_primitive", "arrange_objects_in_grid", "tag_object"],
        "generate": ["create_model", "create_collection", "register_asset_library_item"],
        "detail": ["increase_detail", "add_bevel_modifier", "save_selection_set"],
        "materialize": ["create_pbr_material", "apply_material", "generate_texture_set_manifest"],
        "rig_setup": ["create_simple_rig", "create_socket_marker", "validate_animation_rigging"],
        "optimize": ["create_lod_chain", "create_collision_proxy_set", "validate_game_export_readiness"],
        "validate": ["inspect_scene", "generate_qa_report", "validate_production_readiness"],
        "package": ["plan_game_export_package", "write_game_production_package", "plan_engine_import_checklist"],
        "review": ["create_shot_camera", "render_preview", "save_shot_bookmark"],
    }
    track_tools = {
        "world_art": ["create_world", "plan_level_streaming"],
        "lighting": ["create_three_point_lighting", "balance_light_intensities"],
        "materials": ["validate_uv_layout", "create_trim_sheet_manifest"],
        "engine_integration": ["set_engine_export_profile", "validate_engine_export_package"],
        "qa": ["validate_production_readiness", "generate_qa_report"],
        "release": ["write_game_export_manifest", "write_game_production_package"],
    }
    tools = [*phase_tools[phase["phase"]], *track_tools.get(domain["track"], [])]
    return [
        {"order": index, "tool_name": tool_name, "purpose": _tool_purpose(tool_name)}
        for index, tool_name in enumerate(list(dict.fromkeys(tools)), start=1)
    ]


def _tool_purpose(tool_name: str) -> str:
    purposes = {
        "create_game_production_plan": "establish project-scale content targets",
        "create_asset_brief": "capture asset budget and acceptance criteria",
        "list_asset_briefs": "check existing planned work",
        "create_primitive": "create proxy geometry",
        "arrange_objects_in_grid": "lay out repeatable object sets",
        "tag_object": "attach semantic workflow metadata",
        "create_model": "generate or assemble a model from a brief",
        "create_collection": "isolate related production objects",
        "register_asset_library_item": "make generated objects reusable",
        "increase_detail": "add controlled production detail",
        "add_bevel_modifier": "improve hard-surface readability",
        "save_selection_set": "persist a working target set",
        "create_pbr_material": "create engine-friendly surface material",
        "apply_material": "bind material to target objects",
        "generate_texture_set_manifest": "record texture deliverables",
        "create_simple_rig": "add basic armature structure",
        "create_socket_marker": "add gameplay attachment marker",
        "validate_animation_rigging": "inspect animation and rig metadata",
        "create_lod_chain": "prepare runtime LODs",
        "create_collision_proxy_set": "prepare gameplay collision proxies",
        "validate_game_export_readiness": "check engine export blockers",
        "inspect_scene": "collect scene QA facts",
        "generate_qa_report": "produce severity-tagged QA report",
        "validate_production_readiness": "validate production gates",
        "plan_game_export_package": "assemble export manifest",
        "write_game_production_package": "write project production package",
        "plan_engine_import_checklist": "prepare target-engine import checklist",
        "create_shot_camera": "create review framing",
        "render_preview": "generate visual review output",
        "save_shot_bookmark": "persist camera review state",
        "create_world": "create managed world metadata and base terrain",
        "plan_level_streaming": "budget large world cells",
        "create_three_point_lighting": "create controlled lighting rig",
        "balance_light_intensities": "normalize lighting values",
        "validate_uv_layout": "inspect UV readiness",
        "create_trim_sheet_manifest": "record trim-sheet plan",
        "set_engine_export_profile": "align export settings to engine conventions",
        "validate_engine_export_package": "run engine-specific package checks",
        "write_game_export_manifest": "write game export manifest",
    }
    return purposes.get(tool_name, "advance the workflow")


WORKFLOW_CATALOG = _workflow_catalog()


async def run_aaa_workflow(context, request: AAAWorkflowRequest, workflow_name: str):  # type: ignore[no-untyped-def]
    workflow = WORKFLOW_CATALOG[workflow_name]
    project_context: dict[str, Any] | None = None
    if request.project_id is not None:
        project_context = _project_context(context, request.project_id)
    tailored = {
        **workflow,
        "goal": request.goal or workflow["objective"],
        "target_engine": request.target_engine,
        "target_platform": request.target_platform,
        "quality_bar": request.quality_bar,
        "constraints": request.constraints,
        "reference_asset_ids": request.reference_asset_ids,
    }
    if not request.include_tool_chain:
        tailored.pop("recommended_tool_chain", None)
    if not request.include_acceptance_criteria:
        tailored.pop("acceptance_criteria", None)
    return success_result(
        request_id=request.request_id,
        tool_name=workflow_name,
        summary=f"Planned {workflow['phase_label']} workflow for {workflow['domain_label']}.",
        project_id=request.project_id,
        workflow=tailored,
        project_context=project_context,
        next_suggestions=_next_suggestions(workflow),
    )


def _project_context(context, project_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    entity_counts: dict[str, int] = {}
    for entity_type in (
        "game_production_plan",
        "asset_brief",
        "asset_library_item",
        "level_streaming_plan",
        "world",
    ):
        entity_counts[entity_type] = len(context.entities.list_by_type(project_id, entity_type))
    return {"project_id": project_id, "entity_counts": entity_counts}


def _next_suggestions(workflow: dict[str, Any]) -> list[str]:
    tool_chain = workflow.get("recommended_tool_chain", [])
    if not tool_chain:
        return []
    first = tool_chain[0]["tool_name"]
    second = tool_chain[1]["tool_name"] if len(tool_chain) > 1 else None
    suggestions = [f"Start with `{first}` using the workflow constraints as inputs."]
    if second:
        suggestions.append(f"Then call `{second}` to continue the {workflow['phase']} pass.")
    suggestions.append("Run a validation or QA tool before packaging.")
    return suggestions


def _make_handler(workflow_name: str):  # type: ignore[no-untyped-def]
    async def _handler(context, request: AAAWorkflowRequest):  # type: ignore[no-untyped-def]
        return await run_aaa_workflow(context, request, workflow_name)

    return _handler


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for workflow_name, workflow in WORKFLOW_CATALOG.items():
        app.register_tool(
            app.tool_definition(
                name=workflow_name,
                description=(
                    f"AAA workflow recipe: {workflow['phase_label']} "
                    f"{workflow['domain_label']} with recommended MCP tool chain, deliverables, "
                    "acceptance criteria, and risk controls."
                ),
                family="aaa_workflows",
                input_model=AAAWorkflowRequest,
                handler=_make_handler(workflow_name),
                read_only=True,
            )
        )
