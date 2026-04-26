from __future__ import annotations

import math
import random
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import (
    duplicate_asset_objects,
    load_entity_spec,
    retag_result,
    save_metadata_entity,
)
from mcp_server.tools.geometry import CreatePrimitiveRequest, create_primitive
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.tools.material import (
    ApplyMaterialRequest,
    CreatePBRMaterialRequest,
    apply_material,
    create_pbr_material,
)
from mcp_server.tools.object import TransformObjectRequest, transform_object
from mcp_server.tools.render import (
    CreateCameraRequest,
    FrameObjectRequest,
    LightingPresetRequest,
    RenderSettingsRequest,
    SetActiveCameraRequest,
    apply_lighting_preset,
    create_camera,
    frame_object,
    set_active_camera,
    set_render_settings,
)
from mcp_server.utils import new_id


class CreateSceneRequest(CommonToolRequest):
    project_id: str
    name: str
    scene_type: Literal["studio", "interior", "exterior"] = "studio"
    collection_name: str = "Scene Layout"
    create_ground: bool = True
    ground_size: float = Field(default=12.0, gt=0.0)
    ground_material_color: list[float] = Field(default_factory=lambda: [0.58, 0.58, 0.58, 1.0])


class PlaceAssetRequest(CommonToolRequest):
    project_id: str
    asset_id: str
    scene_id: str | None = None
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    collection_name: str = "Scene Assets"


class ScatterAssetsRequest(CommonToolRequest):
    project_id: str
    asset_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    count: int = Field(default=5, ge=1, le=64)
    area_min: list[float] = Field(default_factory=lambda: [-5.0, -5.0, 0.0])
    area_max: list[float] = Field(default_factory=lambda: [5.0, 5.0, 0.0])
    random_yaw: bool = True
    scale_jitter: float = Field(default=0.15, ge=0.0, le=1.0)
    collection_name: str = "Scene Scatter"


class ArrangeSceneRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    arrangement: Literal["grid", "line", "circle"] = "grid"
    origin: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    spacing: float = Field(default=2.0, gt=0.0)
    columns: int = Field(default=3, ge=1, le=12)
    radius: float = Field(default=4.0, gt=0.0)


class GenerateBackgroundRequest(CommonToolRequest):
    project_id: str
    scene_id: str | None = None
    name: str = "Background"
    style: Literal["studio", "sunset", "night", "forest"] = "studio"
    width: float = Field(default=18.0, gt=0.0)
    height: float = Field(default=10.0, gt=0.0)
    distance: float = Field(default=8.0, gt=0.0)
    collection_name: str = "Scene Background"


class GenerateEnvironmentRequest(CommonToolRequest):
    project_id: str
    scene_id: str | None = None
    preset_name: Literal["product_shot", "sci_fi"] | None = None
    mood: str | None = None
    render_preset_name: Literal["preview", "standard", "thumbnail", "final"] = "preview"


class CreateCompositionRequest(CommonToolRequest):
    project_id: str
    scene_id: str | None = None
    name: str = "Composition"
    camera_id: str | None = None
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    camera_name: str = "CompositionCamera"
    preset_name: Literal["preview", "standard", "thumbnail", "final"] = "standard"


def _background_palette(style: str) -> tuple[list[float], float, float]:
    if style == "sunset":
        return [0.92, 0.48, 0.28, 1.0], 0.85, 0.0
    if style == "night":
        return [0.06, 0.08, 0.16, 1.0], 0.3, 0.0
    if style == "forest":
        return [0.24, 0.38, 0.22, 1.0], 0.75, 0.0
    return [0.76, 0.76, 0.78, 1.0], 0.92, 0.0


def _environment_preset(request: GenerateEnvironmentRequest) -> str:
    if request.preset_name is not None:
        return request.preset_name
    mood = (request.mood or request.style or "").strip().lower() if hasattr(request, "style") else (request.mood or "").strip().lower()
    return "sci_fi" if any(token in mood for token in {"future", "sci", "cyber", "neon"}) else "product_shot"


def _require_scene(context, request_id: str, scene_id: str | None, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    if scene_id is None:
        return {}
    scene = load_entity_spec(context, scene_id, expected_type="scene")
    if scene is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Scene '{scene_id}' was not found.",
            errors=[f"target_not_found: scene '{scene_id}' does not exist"],
        )
    return scene


async def create_scene(context, request: CreateSceneRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    scene_id = new_id("scene")
    created_object_ids: list[str] = []
    scene_objects: list[dict[str, Any]] = []
    ground_material: dict[str, Any] | None = None

    if request.create_ground:
        ground = await create_primitive(
            context,
            CreatePrimitiveRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                primitive_type="plane",
                name=f"{request.name}_Ground",
                scale=[request.ground_size, request.ground_size, 1.0],
                collection_name=request.collection_name,
                tags=["scene_ground", request.scene_type],
            ),
        )
        if ground.status != "success":
            return retag_result(ground, "create_scene")
        created_object_ids.extend(ground.created_object_ids)
        scene_objects.extend(ground.model_dump().get("objects", []))

        ground_material_result = await create_pbr_material(
            context,
            CreatePBRMaterialRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                name=f"{request.name}_GroundMaterial",
                base_color=request.ground_material_color,
                roughness=0.88,
                metallic=0.0,
            ),
        )
        if ground_material_result.status != "success":
            return retag_result(ground_material_result, "create_scene")
        ground_material = ground_material_result.model_dump().get("material")
        applied = await apply_material(
            context,
            ApplyMaterialRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                material_id=str(ground_material["material_id"]),
                target_ids=created_object_ids,
            ),
        )
        if applied.status not in {"success", "partial_success"}:
            return retag_result(applied, "create_scene")

    scene = {
        "scene_id": scene_id,
        "name": request.name,
        "scene_type": request.scene_type,
        "collection_name": request.collection_name,
        "ground_object_ids": created_object_ids,
        "background_id": None,
        "environment_id": None,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=scene_id,
        entity_type="scene",
        name=request.name,
        spec=scene,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_scene",
        summary=f"Created scene '{request.name}'.",
        project_id=project.project_id,
        scene_id=scene_id,
        scene=scene,
        created_object_ids=created_object_ids,
        objects=scene_objects,
        material=ground_material,
    )


async def place_asset(context, request: PlaceAssetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    maybe_scene = _require_scene(context, request.request_id, request.scene_id, "place_asset")
    if isinstance(maybe_scene, CommonToolResult):
        return maybe_scene

    placed = await duplicate_asset_objects(
        context,
        request_id=request.request_id,
        project_id=request.project_id,
        tool_name="place_asset",
        asset_id=request.asset_id,
        location_offset=request.location,
        rotation_offset=request.rotation,
        scale_multiplier=request.scale,
        collection_name=request.collection_name,
    )
    if isinstance(placed, CommonToolResult):
        return placed

    placed_asset_id = new_id("sceneasset")
    placed_asset = {
        "placed_asset_id": placed_asset_id,
        "scene_id": request.scene_id,
        "asset_id": request.asset_id,
        "object_ids": placed["created_object_ids"],
        "location": request.location,
        "rotation": request.rotation,
        "scale": request.scale,
        "collection_name": request.collection_name,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=placed_asset_id,
        entity_type="scene_asset",
        name=f"{placed['asset'].get('name', 'Asset')} Placement",
        spec=placed_asset,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="place_asset",
        summary=f"Placed asset '{request.asset_id}'.",
        project_id=project.project_id,
        asset_id=request.asset_id,
        scene_id=request.scene_id,
        placed_asset=placed_asset,
        created_object_ids=placed["created_object_ids"],
        objects=placed["objects"],
    )


async def scatter_assets(context, request: ScatterAssetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    maybe_scene = _require_scene(context, request.request_id, request.scene_id, "scatter_assets")
    if isinstance(maybe_scene, CommonToolResult):
        return maybe_scene
    if not request.asset_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="scatter_assets",
            summary="scatter_assets requires at least one asset_id.",
            errors=["validation_error: at least one asset_id is required"],
        )

    rng = random.Random(request.seed)
    created_object_ids: list[str] = []
    placements: list[dict[str, Any]] = []
    placed_objects: list[dict[str, Any]] = []
    for index in range(request.count):
        asset_id = request.asset_ids[index % len(request.asset_ids)]
        offset = [
            rng.uniform(float(request.area_min[0]), float(request.area_max[0])),
            rng.uniform(float(request.area_min[1]), float(request.area_max[1])),
            rng.uniform(float(request.area_min[2]), float(request.area_max[2])),
        ]
        yaw = rng.uniform(-math.pi, math.pi) if request.random_yaw else 0.0
        scale_factor = max(0.2, 1.0 + rng.uniform(-request.scale_jitter, request.scale_jitter))
        placed = await place_asset(
            context,
            PlaceAssetRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                asset_id=asset_id,
                scene_id=request.scene_id,
                location=offset,
                rotation=[0.0, 0.0, yaw],
                scale=[scale_factor, scale_factor, scale_factor],
                collection_name=request.collection_name,
            ),
        )
        if placed.status != "success":
            return retag_result(placed, "scatter_assets")
        payload = placed.model_dump()
        created_object_ids.extend(payload.get("created_object_ids", []))
        placed_objects.extend(payload.get("objects", []))
        placements.append(payload["placed_asset"])

    scatter_id = new_id("scatter")
    scatter = {
        "scatter_id": scatter_id,
        "scene_id": request.scene_id,
        "asset_ids": request.asset_ids,
        "count": request.count,
        "placements": placements,
        "collection_name": request.collection_name,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=scatter_id,
        entity_type="scene_scatter",
        name=f"Scatter {scatter_id}",
        spec=scatter,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="scatter_assets",
        summary=f"Scattered {request.count} asset placements.",
        project_id=project.project_id,
        scene_id=request.scene_id,
        scatter_id=scatter_id,
        placements=placements,
        created_object_ids=created_object_ids,
        objects=placed_objects,
    )


async def arrange_scene(context, request: ArrangeSceneRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    objects: list[dict[str, Any]] = []
    for index, target_id in enumerate(target_ids):
        if request.arrangement == "line":
            location = [request.origin[0] + (index * request.spacing), request.origin[1], request.origin[2]]
        elif request.arrangement == "circle":
            angle = (2.0 * math.pi * index) / max(len(target_ids), 1)
            location = [
                request.origin[0] + (request.radius * math.cos(angle)),
                request.origin[1] + (request.radius * math.sin(angle)),
                request.origin[2],
            ]
        else:
            row = index // request.columns
            column = index % request.columns
            location = [
                request.origin[0] + (column * request.spacing),
                request.origin[1] + (row * request.spacing),
                request.origin[2],
            ]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=target_id,
                location=location,
            ),
        )
        if transformed.status != "success":
            return retag_result(transformed, "arrange_scene")
        objects.append(transformed.model_dump()["object"])
    return success_result(
        request_id=request.request_id,
        tool_name="arrange_scene",
        summary=f"Arranged {len(target_ids)} objects in a {request.arrangement} layout.",
        project_id=project.project_id,
        modified_object_ids=target_ids,
        objects=objects,
    )


async def generate_background(context, request: GenerateBackgroundRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    maybe_scene = _require_scene(context, request.request_id, request.scene_id, "generate_background")
    if isinstance(maybe_scene, CommonToolResult):
        return maybe_scene

    background = await create_primitive(
        context,
        CreatePrimitiveRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            primitive_type="plane",
            name=request.name,
            location=[0.0, request.distance, request.height * 0.5],
            rotation=[math.pi / 2.0, 0.0, 0.0],
            scale=[request.width, request.height, 1.0],
            collection_name=request.collection_name,
            tags=["scene_background", request.style],
        ),
    )
    if background.status != "success":
        return retag_result(background, "generate_background")

    base_color, roughness, metallic = _background_palette(request.style)
    material_result = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.name}_Material",
            base_color=base_color,
            roughness=roughness,
            metallic=metallic,
        ),
    )
    if material_result.status != "success":
        return retag_result(material_result, "generate_background")
    material = material_result.model_dump()["material"]

    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            material_id=str(material["material_id"]),
            target_ids=list(background.created_object_ids),
        ),
    )
    if applied.status not in {"success", "partial_success"}:
        return retag_result(applied, "generate_background")

    background_id = new_id("background")
    object_id = str(background.created_object_ids[0])
    background_spec = {
        "background_id": background_id,
        "scene_id": request.scene_id,
        "object_id": object_id,
        "material_id": material["material_id"],
        "style": request.style,
        "distance": request.distance,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=background_id,
        entity_type="scene_background",
        name=request.name,
        spec=background_spec,
    )
    if request.scene_id is not None:
        scene = load_entity_spec(context, request.scene_id, expected_type="scene")
        if scene is not None:
            scene["background_id"] = background_id
            save_metadata_entity(
                context,
                project_id=project.project_id,
                entity_id=request.scene_id,
                entity_type="scene",
                name=scene["name"],
                spec=scene,
            )
    return success_result(
        request_id=request.request_id,
        tool_name="generate_background",
        summary=f"Generated {request.style} background.",
        project_id=project.project_id,
        background_id=background_id,
        background=background_spec,
        material=material,
        created_object_ids=list(background.created_object_ids),
        objects=background.model_dump().get("objects", []),
    )


async def generate_environment(context, request: GenerateEnvironmentRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    maybe_scene = _require_scene(context, request.request_id, request.scene_id, "generate_environment")
    if isinstance(maybe_scene, CommonToolResult):
        return maybe_scene

    preset_name = _environment_preset(request)
    lights = await apply_lighting_preset(
        context,
        LightingPresetRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            preset_name=preset_name,
        ),
    )
    if lights.status != "success":
        return retag_result(lights, "generate_environment")

    render = await set_render_settings(
        context,
        RenderSettingsRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            preset_name=request.render_preset_name,
        ),
    )
    if render.status != "success":
        return retag_result(render, "generate_environment")

    environment_id = new_id("environment")
    environment = {
        "environment_id": environment_id,
        "scene_id": request.scene_id,
        "preset_name": preset_name,
        "light_ids": list(lights.created_object_ids),
        "render_settings": render.model_dump()["render_settings"],
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=environment_id,
        entity_type="scene_environment",
        name=f"{preset_name} environment",
        spec=environment,
    )
    if request.scene_id is not None:
        scene = load_entity_spec(context, request.scene_id, expected_type="scene")
        if scene is not None:
            scene["environment_id"] = environment_id
            save_metadata_entity(
                context,
                project_id=project.project_id,
                entity_id=request.scene_id,
                entity_type="scene",
                name=scene["name"],
                spec=scene,
            )
    return success_result(
        request_id=request.request_id,
        tool_name="generate_environment",
        summary=f"Generated environment using {preset_name}.",
        project_id=project.project_id,
        scene_id=request.scene_id,
        environment_id=environment_id,
        environment=environment,
        created_object_ids=list(lights.created_object_ids),
        objects=lights.model_dump().get("objects", []),
        render_settings=render.model_dump()["render_settings"],
    )


async def create_composition(context, request: CreateCompositionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    maybe_scene = _require_scene(context, request.request_id, request.scene_id, "create_composition")
    if isinstance(maybe_scene, CommonToolResult):
        return maybe_scene

    camera_payload: dict[str, Any] | None = None
    camera_id = request.camera_id
    created_object_ids: list[str] = []
    if camera_id is None:
        camera = await create_camera(
            context,
            CreateCameraRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                name=request.camera_name,
            ),
        )
        if camera.status != "success":
            return retag_result(camera, "create_composition")
        camera_payload = camera.model_dump()["camera"]
        camera_id = str(camera_payload["camera_id"])
        created_object_ids.extend(camera.created_object_ids)
    elif load_entity_spec(context, camera_id, expected_type="camera") is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_composition",
            summary=f"Camera '{camera_id}' was not found.",
            errors=[f"target_not_found: camera '{camera_id}' does not exist"],
        )
    else:
        camera_payload = load_entity_spec(context, camera_id, expected_type="camera")

    target_ids = []
    if request.target_id is not None or request.target_ids or request.names or request.tag is not None or request.match_collection_name is not None:
        target_ids = await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
        )
        if len(target_ids) >= 1:
            framed = await frame_object(
                context,
                FrameObjectRequest(
                    request_id=request.request_id,
                    project_id=request.project_id,
                    camera_id=camera_id,
                    target_id=target_ids[0],
                ),
            )
            if framed.status != "success":
                return retag_result(framed, "create_composition")
            camera_payload = framed.model_dump().get("camera", camera_payload)

    active_camera = await set_active_camera(
        context,
        SetActiveCameraRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            camera_id=camera_id,
        ),
    )
    if active_camera.status != "success":
        return retag_result(active_camera, "create_composition")
    render = await set_render_settings(
        context,
        RenderSettingsRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            preset_name=request.preset_name,
        ),
    )
    if render.status != "success":
        return retag_result(render, "create_composition")

    composition_id = new_id("composition")
    composition = {
        "composition_id": composition_id,
        "scene_id": request.scene_id,
        "camera_id": camera_id,
        "target_ids": target_ids,
        "preset_name": request.preset_name,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=composition_id,
        entity_type="composition",
        name=request.name,
        spec=composition,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_composition",
        summary=f"Created composition '{request.name}'.",
        project_id=project.project_id,
        composition_id=composition_id,
        composition=composition,
        camera=camera_payload,
        created_object_ids=created_object_ids,
        active_camera_id=active_camera.model_dump()["active_camera_id"],
        render_settings=render.model_dump()["render_settings"],
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_scene", "Create a scene scaffold with a managed ground plane.", CreateSceneRequest, create_scene, False),
        ("place_asset", "Duplicate an existing managed asset into the active scene.", PlaceAssetRequest, place_asset, False),
        ("scatter_assets", "Place repeated asset instances across a bounded area.", ScatterAssetsRequest, scatter_assets, False),
        ("arrange_scene", "Arrange scene objects into a deterministic layout.", ArrangeSceneRequest, arrange_scene, False),
        ("generate_background", "Generate a simple backdrop card and material.", GenerateBackgroundRequest, generate_background, False),
        ("generate_environment", "Create a lighting environment and render preset pairing.", GenerateEnvironmentRequest, generate_environment, False),
        ("create_composition", "Create or configure a camera composition for the current scene.", CreateCompositionRequest, create_composition, False),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="scene",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )