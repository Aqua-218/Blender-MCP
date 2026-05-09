from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.asset_library import (
    AssetLibraryTargetsRequest,
    register_asset_library_item,
)
from mcp_server.tools.game_prep import (
    CreateCollisionProxySetRequest,
    CreateLODChainRequest,
    CreateSocketMarkerRequest,
    PlanEngineImportChecklistRequest,
    PlanGameExportPackageRequest,
    SetEngineExportProfileRequest,
    ValidateEngineExportPackageRequest,
    ValidateGameExportReadinessRequest,
    WriteGameExportManifestRequest,
    create_collision_proxy_set,
    create_lod_chain,
    create_socket_marker,
    plan_engine_import_checklist,
    plan_game_export_package,
    set_engine_export_profile,
    validate_engine_export_package,
    validate_game_export_readiness,
    write_game_export_manifest,
)
from mcp_server.tools.geometry import CreatePrimitiveRequest, create_primitive
from mcp_server.tools.helpers import require_project
from mcp_server.tools.material import (
    ApplyMaterialRequest,
    CreatePBRMaterialRequest,
    apply_material,
    create_pbr_material,
)
from mcp_server.tools.production_pipeline import (
    CreateAssetBriefRequest,
    PlanLevelStreamingRequest,
    ValidateProductionReadinessRequest,
    WriteGameProductionPackageRequest,
    create_asset_brief,
    plan_level_streaming,
    validate_production_readiness,
    write_game_production_package,
)
from mcp_server.tools.world import (
    CreateNavigationMarkersRequest,
    CreateWorldRequest,
    GenerateBiomesRequest,
    GenerateRoadsRequest,
    GenerateWaterSystemRequest,
    ScatterVegetationRequest,
    ValidateWorldCompositionRequest,
    create_navigation_markers,
    create_world,
    generate_biomes,
    generate_roads,
    generate_water_system,
    scatter_vegetation,
    validate_world_composition,
)

EngineName = Literal["unreal", "unity", "godot", "web"]
AssetBuildType = Literal["prop", "weapon", "vehicle", "character_proxy", "environment_piece", "modular_kit"]


class BuildGameReadyAssetRequest(CommonToolRequest):
    project_id: str
    asset_name: str
    asset_type: AssetBuildType = "prop"
    plan_id: str | None = None
    description: str | None = None
    target_engine: EngineName = "unreal"
    collection_name: str | None = None
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    base_color: tuple[float, float, float, float] = (0.58, 0.58, 0.52, 1.0)
    create_lods: bool = True
    lod_levels: int = Field(default=2, ge=1, le=4)
    create_collision: bool = True
    create_socket: bool = False
    register_library_item: bool = True


class BuildEnvironmentKitRequest(CommonToolRequest):
    project_id: str
    kit_name: str
    plan_id: str | None = None
    target_engine: EngineName = "unreal"
    piece_count: int = Field(default=6, ge=2, le=24)
    spacing: float = Field(default=3.0, gt=0.0)
    collection_name: str | None = None
    base_color: tuple[float, float, float, float] = (0.48, 0.46, 0.42, 1.0)
    create_collision: bool = True
    create_lods: bool = True


class BuildWorldBlockoutRequest(CommonToolRequest):
    project_id: str
    world_name: str
    plan_id: str | None = None
    theme: str | None = None
    target_engine: EngineName = "unreal"
    size: float = Field(default=64.0, gt=0.0)
    terrain_subdivisions: int = Field(default=24, ge=4, le=128)
    road_count: int = Field(default=3, ge=1, le=16)
    vegetation_count: int = Field(default=24, ge=1, le=128)
    navigation_marker_count: int = Field(default=8, ge=1, le=64)
    streaming_cell_size: float = Field(default=32.0, gt=0.0)
    memory_budget_mb: int = Field(default=512, gt=0)


class RunShippingReadinessPassRequest(CommonToolRequest):
    project_id: str
    plan_id: str | None = None
    target_engine: EngineName = "unreal"
    package_name: str = "shipping_candidate"
    require_asset_library: bool = True
    require_streaming_plan: bool = False
    require_approved_briefs: bool = False
    require_aaa_gates: bool = True
    write_manifests: bool = True


def _step(tool_name: str, result: CommonToolResult) -> dict[str, Any]:
    payload = result.model_dump()
    return {
        "tool_name": tool_name,
        "status": payload.get("status"),
        "summary": payload.get("summary"),
        "created_object_ids": payload.get("created_object_ids", []),
        "modified_object_ids": payload.get("modified_object_ids", []),
        "file_paths": payload.get("file_paths", []),
        "errors": payload.get("errors", []),
    }


def _failed_from_step(request: CommonToolRequest, tool_name: str, failed_step: dict[str, Any], steps: list[dict[str, Any]]) -> CommonToolResult:
    return failed_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Workflow stopped at {failed_step['tool_name']}.",
        errors=list(failed_step.get("errors", [])) or [f"workflow_error: {failed_step['summary']}"],
        project_id=request.project_id,
        steps=steps,
    )


def _asset_brief_type(asset_type: AssetBuildType) -> str:
    return {
        "prop": "prop",
        "weapon": "weapon",
        "vehicle": "vehicle",
        "character_proxy": "character",
        "environment_piece": "environment",
        "modular_kit": "kit",
    }[asset_type]


def _asset_primitives(request: BuildGameReadyAssetRequest) -> list[dict[str, Any]]:
    x, y, z = request.location
    sx, sy, sz = request.scale
    if request.asset_type == "weapon":
        return [
            {"name": "body", "primitive_type": "cube", "location": [x, y, z], "scale": [sx * 2.0, sy * 0.18, sz * 0.18]},
            {"name": "grip", "primitive_type": "cube", "location": [x - sx * 0.65, y, z - sz * 0.35], "scale": [sx * 0.25, sy * 0.25, sz * 0.7]},
        ]
    if request.asset_type == "vehicle":
        return [
            {"name": "body", "primitive_type": "cube", "location": [x, y, z + sz * 0.35], "scale": [sx * 2.2, sy * 1.1, sz * 0.55]},
            {"name": "cabin", "primitive_type": "cube", "location": [x - sx * 0.2, y, z + sz * 0.95], "scale": [sx * 0.95, sy * 0.9, sz * 0.45]},
            {"name": "wheel_fl", "primitive_type": "cylinder", "location": [x - sx * 0.75, y - sy * 0.65, z], "scale": [sx * 0.22, sy * 0.22, sz * 0.22]},
            {"name": "wheel_fr", "primitive_type": "cylinder", "location": [x - sx * 0.75, y + sy * 0.65, z], "scale": [sx * 0.22, sy * 0.22, sz * 0.22]},
            {"name": "wheel_rl", "primitive_type": "cylinder", "location": [x + sx * 0.75, y - sy * 0.65, z], "scale": [sx * 0.22, sy * 0.22, sz * 0.22]},
            {"name": "wheel_rr", "primitive_type": "cylinder", "location": [x + sx * 0.75, y + sy * 0.65, z], "scale": [sx * 0.22, sy * 0.22, sz * 0.22]},
        ]
    if request.asset_type == "character_proxy":
        return [
            {"name": "torso", "primitive_type": "cylinder", "location": [x, y, z + sz * 0.9], "scale": [sx * 0.35, sy * 0.35, sz * 0.9]},
            {"name": "head", "primitive_type": "uv_sphere", "location": [x, y, z + sz * 1.9], "scale": [sx * 0.28, sy * 0.28, sz * 0.28]},
            {"name": "feet", "primitive_type": "cube", "location": [x, y, z + sz * 0.05], "scale": [sx * 0.55, sy * 0.35, sz * 0.12]},
        ]
    if request.asset_type == "modular_kit":
        return [
            {"name": "wall_a", "primitive_type": "cube", "location": [x, y, z + sz], "scale": [sx * 2.0, sy * 0.2, sz]},
            {"name": "floor_a", "primitive_type": "cube", "location": [x, y + sy * 1.5, z], "scale": [sx * 2.0, sy * 2.0, sz * 0.12]},
            {"name": "column_a", "primitive_type": "cylinder", "location": [x + sx * 1.2, y, z + sz], "scale": [sx * 0.18, sy * 0.18, sz]},
        ]
    return [{"name": "main", "primitive_type": "cube", "location": [x, y, z], "scale": [sx, sy, sz]}]


async def _build_asset_core(context, request: BuildGameReadyAssetRequest, *, tool_name: str) -> CommonToolResult:  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    steps: list[dict[str, Any]] = []
    collection_name = request.collection_name or f"AAA_{request.asset_name.replace(' ', '_')}"

    brief = await create_asset_brief(
        context,
        CreateAssetBriefRequest(
            request_id=f"{request.request_id}-brief",
            project_id=project.project_id,
            plan_id=request.plan_id,
            asset_name=request.asset_name,
            asset_type=_asset_brief_type(request.asset_type),  # type: ignore[arg-type]
            description=request.description,
            target_quality="hero",
            engine=request.target_engine,
            gameplay_tags=["aaa_orchestrated", request.asset_type],
            requires_collision=request.create_collision,
            requires_sockets=request.create_socket,
        ),
    )
    steps.append(_step("create_asset_brief", brief))
    if brief.status != "success":
        return _failed_from_step(request, tool_name, steps[-1], steps)

    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    for primitive in _asset_primitives(request):
        created = await create_primitive(
            context,
            CreatePrimitiveRequest(
                request_id=f"{request.request_id}-mesh-{primitive['name']}",
                project_id=project.project_id,
                primitive_type=primitive["primitive_type"],  # type: ignore[arg-type]
                name=f"{request.asset_name}_{primitive['name']}",
                location=primitive["location"],
                scale=primitive["scale"],
                collection_name=collection_name,
                tags=["aaa_asset", request.asset_type, f"brief:{brief.model_dump().get('brief_id')}"],
            ),
        )
        steps.append(_step("create_primitive", created))
        if created.status != "success":
            return _failed_from_step(request, tool_name, steps[-1], steps)
        created_object_ids.extend(created.created_object_ids)
        objects.extend(created.model_dump().get("objects", []))
    primary_object_id = created_object_ids[0]

    material = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=f"{request.request_id}-material",
            project_id=project.project_id,
            name=f"{request.asset_name}_PBR",
            base_color=list(request.base_color),
            roughness=0.55,
            metallic=0.0 if request.asset_type not in {"weapon", "vehicle"} else 0.25,
        ),
    )
    steps.append(_step("create_pbr_material", material))
    if material.status != "success":
        return _failed_from_step(request, tool_name, steps[-1], steps)
    material_id = str(material.model_dump()["material"]["material_id"])

    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=f"{request.request_id}-apply-material",
            project_id=project.project_id,
            material_id=material_id,
            target_ids=created_object_ids,
        ),
    )
    steps.append(_step("apply_material", applied))
    if applied.status not in {"success", "partial_success"}:
        return _failed_from_step(request, tool_name, steps[-1], steps)

    lod_object_ids: list[str] = []
    if request.create_lods:
        lod = await create_lod_chain(
            context,
            CreateLODChainRequest(
                request_id=f"{request.request_id}-lod",
                project_id=project.project_id,
                target_id=primary_object_id,
                group_name=request.asset_name.replace(" ", "_"),
                levels=request.lod_levels,
                base_ratio=0.5,
            ),
        )
        steps.append(_step("create_lod_chain", lod))
        if lod.status != "success":
            return _failed_from_step(request, tool_name, steps[-1], steps)
        lod_object_ids = list(lod.model_dump().get("created_object_ids", []))

    collision_object_ids: list[str] = []
    if request.create_collision:
        collision = await create_collision_proxy_set(
            context,
            CreateCollisionProxySetRequest(
                request_id=f"{request.request_id}-collision",
                project_id=project.project_id,
                target_ids=[primary_object_id],
                proxy_types=["box"],
                collection_name=f"{collection_name}_Collision",
            ),
        )
        steps.append(_step("create_collision_proxy_set", collision))
        if collision.status != "success":
            return _failed_from_step(request, tool_name, steps[-1], steps)
        collision_object_ids = list(collision.created_object_ids)

    socket_object_id: str | None = None
    if request.create_socket:
        socket = await create_socket_marker(
            context,
            CreateSocketMarkerRequest(
                request_id=f"{request.request_id}-socket",
                project_id=project.project_id,
                target_id=primary_object_id,
                socket_name="attach",
                location_offset=(0.0, 0.0, 0.75),
                collection_name=f"{collection_name}_Sockets",
            ),
        )
        steps.append(_step("create_socket_marker", socket))
        if socket.status != "success":
            return _failed_from_step(request, tool_name, steps[-1], steps)
        socket_object_id = str(socket.model_dump().get("socket_object_id"))

    asset_id: str | None = None
    if request.register_library_item:
        registered = await register_asset_library_item(
            context,
            AssetLibraryTargetsRequest(
                request_id=f"{request.request_id}-asset-library",
                project_id=project.project_id,
                asset_name=request.asset_name,
                category=_asset_brief_type(request.asset_type),
                description=request.description,
                tags=["aaa", request.asset_type, request.target_engine],
                target_ids=created_object_ids,
                status="draft",
            ),
        )
        steps.append(_step("register_asset_library_item", registered))
        if registered.status != "success":
            return _failed_from_step(request, tool_name, steps[-1], steps)
        asset_id = str(registered.model_dump().get("asset_id"))

    validation = await validate_game_export_readiness(
        context,
        ValidateGameExportReadinessRequest(
            request_id=f"{request.request_id}-validation",
            project_id=project.project_id,
            require_collision=request.create_collision,
            require_lods=request.create_lods,
            require_materials=True,
        ),
    )
    steps.append(_step("validate_game_export_readiness", validation))
    if validation.status != "success":
        return _failed_from_step(request, tool_name, steps[-1], steps)

    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Built game-ready asset '{request.asset_name}' with geometry, material, LOD/collision metadata, library registration, and export validation.",
        project_id=project.project_id,
        created_object_ids=[*created_object_ids, *lod_object_ids, *collision_object_ids, *([socket_object_id] if socket_object_id else [])],
        objects=objects,
        primary_object_id=primary_object_id,
        render_object_ids=created_object_ids,
        lod_object_ids=lod_object_ids,
        collision_object_ids=collision_object_ids,
        socket_object_id=socket_object_id,
        material_id=material_id,
        brief_id=brief.model_dump().get("brief_id"),
        asset_id=asset_id,
        validation=validation.model_dump(),
        steps=steps,
    )


async def build_game_ready_asset(context, request: BuildGameReadyAssetRequest):  # type: ignore[no-untyped-def]
    return await _build_asset_core(context, request, tool_name="build_game_ready_asset")


async def build_environment_kit(context, request: BuildEnvironmentKitRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    steps: list[dict[str, Any]] = []
    collection_name = request.collection_name or f"AAA_{request.kit_name.replace(' ', '_')}_Kit"
    created_object_ids: list[str] = []
    for index in range(request.piece_count):
        piece_kind = ["wall", "floor", "column", "beam"][index % 4]
        piece_request = BuildGameReadyAssetRequest(
            request_id=f"{request.request_id}-{piece_kind}-{index:02d}",
            project_id=project.project_id,
            asset_name=f"{request.kit_name}_{piece_kind}_{index:02d}",
            asset_type="environment_piece" if piece_kind != "floor" else "modular_kit",
            plan_id=request.plan_id,
            target_engine=request.target_engine,
            collection_name=collection_name,
            location=(float(index) * request.spacing, 0.0, 0.0),
            scale=(2.0, 0.25, 2.0) if piece_kind == "wall" else (2.0, 2.0, 0.15) if piece_kind == "floor" else (0.3, 0.3, 2.0),
            base_color=request.base_color,
            create_lods=request.create_lods,
            lod_levels=2,
            create_collision=request.create_collision,
            register_library_item=False,
        )
        built = await _build_asset_core(context, piece_request, tool_name="build_environment_kit_piece")
        steps.append(_step("build_environment_kit_piece", built))
        if built.status != "success":
            return _failed_from_step(request, "build_environment_kit", steps[-1], steps)
        created_object_ids.extend(built.created_object_ids)

    validation = await validate_game_export_readiness(
        context,
        ValidateGameExportReadinessRequest(
            request_id=f"{request.request_id}-validation",
            project_id=project.project_id,
            require_collision=request.create_collision,
            require_lods=request.create_lods,
            require_materials=True,
        ),
    )
    steps.append(_step("validate_game_export_readiness", validation))
    if validation.status != "success":
        return _failed_from_step(request, "build_environment_kit", steps[-1], steps)

    return success_result(
        request_id=request.request_id,
        tool_name="build_environment_kit",
        summary=f"Built environment kit '{request.kit_name}' with {request.piece_count} game-ready pieces.",
        project_id=project.project_id,
        created_object_ids=created_object_ids,
        collection_name=collection_name,
        validation=validation.model_dump(),
        steps=steps,
    )


async def build_world_blockout(context, request: BuildWorldBlockoutRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    steps: list[dict[str, Any]] = []
    world = await create_world(
        context,
        CreateWorldRequest(
            request_id=f"{request.request_id}-world",
            project_id=project.project_id,
            name=request.world_name,
            theme=request.theme,
            terrain_size=request.size,
            terrain_subdivisions=request.terrain_subdivisions,
            terrain_height_variation=2.0,
        ),
    )
    steps.append(_step("create_world", world))
    if world.status != "success":
        return _failed_from_step(request, "build_world_blockout", steps[-1], steps)
    world_id = str(world.model_dump()["world_id"])

    for tool_name, result in [
        (
            "generate_biomes",
            await generate_biomes(
                context,
                GenerateBiomesRequest(
                    request_id=f"{request.request_id}-biomes",
                    project_id=project.project_id,
                    world_id=world_id,
                    biome_types=["plains", "forest", "rock"],
                ),
            ),
        ),
        (
            "generate_roads",
            await generate_roads(
                context,
                GenerateRoadsRequest(
                    request_id=f"{request.request_id}-roads",
                    project_id=project.project_id,
                    world_id=world_id,
                    road_count=request.road_count,
                    extent=request.size * 0.7,
                ),
            ),
        ),
        (
            "generate_water_system",
            await generate_water_system(
                context,
                GenerateWaterSystemRequest(
                    request_id=f"{request.request_id}-water",
                    project_id=project.project_id,
                    world_id=world_id,
                    water_type="river",
                    length=request.size * 0.65,
                ),
            ),
        ),
        (
            "scatter_vegetation",
            await scatter_vegetation(
                context,
                ScatterVegetationRequest(
                    request_id=f"{request.request_id}-vegetation",
                    project_id=project.project_id,
                    world_id=world_id,
                    count=request.vegetation_count,
                    area_min=[-request.size * 0.35, -request.size * 0.35, 0.0],
                    area_max=[request.size * 0.35, request.size * 0.35, 0.0],
                    vegetation_type="mixed",
                ),
            ),
        ),
        (
            "create_navigation_markers",
            await create_navigation_markers(
                context,
                CreateNavigationMarkersRequest(
                    request_id=f"{request.request_id}-navigation",
                    project_id=project.project_id,
                    world_id=world_id,
                    marker_count=request.navigation_marker_count,
                    extent=request.size * 0.35,
                    marker_type="poi",
                ),
            ),
        ),
    ]:
        steps.append(_step(tool_name, result))
        if result.status != "success":
            return _failed_from_step(request, "build_world_blockout", steps[-1], steps)

    streaming = await plan_level_streaming(
        context,
        PlanLevelStreamingRequest(
            request_id=f"{request.request_id}-streaming",
            project_id=project.project_id,
            plan_id=request.plan_id,
            world_id=world_id,
            level_name=request.world_name,
            min_corner=(-request.size * 0.5, -request.size * 0.5, 0.0),
            max_corner=(request.size * 0.5, request.size * 0.5, request.size * 0.25),
            cell_size=request.streaming_cell_size,
            target_platform=request.target_engine,
            memory_budget_mb=request.memory_budget_mb,
        ),
    )
    steps.append(_step("plan_level_streaming", streaming))
    if streaming.status != "success":
        return _failed_from_step(request, "build_world_blockout", steps[-1], steps)

    validation = await validate_world_composition(
        context,
        ValidateWorldCompositionRequest(
            request_id=f"{request.request_id}-validation",
            project_id=project.project_id,
            world_id=world_id,
            require_terrain=True,
            require_biomes=True,
            require_navigation=True,
        ),
    )
    steps.append(_step("validate_world_composition", validation))
    if validation.status != "success":
        return _failed_from_step(request, "build_world_blockout", steps[-1], steps)

    return success_result(
        request_id=request.request_id,
        tool_name="build_world_blockout",
        summary=f"Built world blockout '{request.world_name}' with terrain, roads, water, vegetation, navigation markers, streaming, and validation.",
        project_id=project.project_id,
        created_object_ids=world.created_object_ids,
        world_id=world_id,
        streaming_plan_id=streaming.model_dump().get("streaming_plan_id"),
        validation=validation.model_dump(),
        steps=steps,
    )


async def run_shipping_readiness_pass(context, request: RunShippingReadinessPassRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    steps: list[dict[str, Any]] = []

    profile = await set_engine_export_profile(
        context,
        SetEngineExportProfileRequest(
            request_id=f"{request.request_id}-profile",
            project_id=project.project_id,
            engine=request.target_engine,
        ),
    )
    steps.append(_step("set_engine_export_profile", profile))
    if profile.status != "success":
        return _failed_from_step(request, "run_shipping_readiness_pass", steps[-1], steps)

    production = await validate_production_readiness(
        context,
        ValidateProductionReadinessRequest(
            request_id=f"{request.request_id}-production",
            project_id=project.project_id,
            plan_id=request.plan_id,
            min_asset_briefs=1,
            require_asset_library=request.require_asset_library,
            require_streaming_plan=request.require_streaming_plan,
            require_game_export=True,
            require_approved_briefs=request.require_approved_briefs,
            require_aaa_gates=request.require_aaa_gates,
        ),
    )
    steps.append(_step("validate_production_readiness", production))

    export = await validate_engine_export_package(
        context,
        ValidateEngineExportPackageRequest(
            request_id=f"{request.request_id}-engine-export",
            project_id=project.project_id,
            engine=request.target_engine,
            package_name=request.package_name,
            require_collision=request.require_aaa_gates,
            require_lods=request.require_aaa_gates,
            require_materials=True,
        ),
    )
    steps.append(_step("validate_engine_export_package", export))

    package = await plan_game_export_package(
        context,
        PlanGameExportPackageRequest(
            request_id=f"{request.request_id}-export-package",
            project_id=project.project_id,
            package_name=request.package_name,
            require_collision=request.require_aaa_gates,
            require_lods=request.require_aaa_gates,
            require_materials=True,
        ),
    )
    steps.append(_step("plan_game_export_package", package))

    file_paths: list[str] = []
    if request.write_manifests:
        game_manifest = await write_game_export_manifest(
            context,
            WriteGameExportManifestRequest(
                request_id=f"{request.request_id}-game-manifest",
                project_id=project.project_id,
                package_name=request.package_name,
                require_collision=request.require_aaa_gates,
                require_lods=request.require_aaa_gates,
                require_materials=True,
            ),
        )
        steps.append(_step("write_game_export_manifest", game_manifest))
        if game_manifest.status != "success":
            return _failed_from_step(request, "run_shipping_readiness_pass", steps[-1], steps)
        file_paths.extend(game_manifest.file_paths)

        production_manifest = await write_game_production_package(
            context,
            WriteGameProductionPackageRequest(
                request_id=f"{request.request_id}-production-package",
                project_id=project.project_id,
                plan_id=request.plan_id,
                package_name=request.package_name,
                require_asset_library=request.require_asset_library,
                require_streaming_plan=request.require_streaming_plan,
                require_game_export=True,
                require_approved_briefs=request.require_approved_briefs,
                require_aaa_gates=request.require_aaa_gates,
            ),
        )
        steps.append(_step("write_game_production_package", production_manifest))
        if production_manifest.status != "success":
            return _failed_from_step(request, "run_shipping_readiness_pass", steps[-1], steps)
        file_paths.extend(production_manifest.file_paths)

        checklist = await plan_engine_import_checklist(
            context,
            PlanEngineImportChecklistRequest(
                request_id=f"{request.request_id}-checklist",
                project_id=project.project_id,
                engine=request.target_engine,
                package_name=request.package_name,
                include_validation=True,
            ),
        )
        steps.append(_step("plan_engine_import_checklist", checklist))

    production_summary = production.model_dump().get("severity_summary", {})
    export_summary = export.model_dump().get("severity_summary", {})
    shipping_ready = production_summary.get("error", 0) == 0 and export_summary.get("error", 0) == 0
    return success_result(
        request_id=request.request_id,
        tool_name="run_shipping_readiness_pass",
        summary="Shipping readiness pass completed.",
        project_id=project.project_id,
        file_paths=file_paths,
        shipping_ready=shipping_ready,
        production_readiness=production.model_dump(),
        engine_export_readiness=export.model_dump(),
        export_package=package.model_dump(),
        steps=steps,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("build_game_ready_asset", "Execute a practical AAA asset pipeline: brief, geometry, PBR material, optional LODs, collision, sockets, asset library registration, and export validation.", BuildGameReadyAssetRequest, build_game_ready_asset, False),
        ("build_environment_kit", "Build multiple game-ready modular environment pieces with materials, LOD/collision passes, and export validation.", BuildEnvironmentKitRequest, build_environment_kit, False),
        ("build_world_blockout", "Build a playable world blockout with terrain, biomes, roads, water, vegetation, navigation markers, streaming cells, and validation.", BuildWorldBlockoutRequest, build_world_blockout, False),
        ("run_shipping_readiness_pass", "Run engine profile setup, production readiness checks, engine export checks, manifests, and import checklist generation.", RunShippingReadinessPassRequest, run_shipping_readiness_pass, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="aaa_orchestrator",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
