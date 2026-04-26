from __future__ import annotations

import random
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import load_entity_spec, retag_result, save_metadata_entity
from mcp_server.tools.geometry import (
    CreateCurveRequest,
    CreatePrimitiveRequest,
    create_curve,
    create_primitive,
)
from mcp_server.tools.helpers import require_project
from mcp_server.tools.material import (
    ApplyMaterialRequest,
    CreatePBRMaterialRequest,
    apply_material,
    create_pbr_material,
)
from mcp_server.tools.model_generation import CreateBuildingRequest, create_building
from mcp_server.tools.modifiers import AddModifierRequest, add_modifier
from mcp_server.tools.object import TransformObjectRequest, transform_object
from mcp_server.tools.scene import PlaceAssetRequest, place_asset
from mcp_server.utils import new_id


class CreateWorldRequest(CommonToolRequest):
    project_id: str
    name: str
    theme: str | None = None
    create_base_terrain: bool = True
    terrain_size: float = Field(default=48.0, gt=0.0)
    terrain_subdivisions: int = Field(default=20, ge=4, le=128)
    terrain_height_variation: float = Field(default=2.5, ge=0.0)


class GenerateTerrainRequest(CommonToolRequest):
    project_id: str
    world_id: str
    name: str = "Terrain"
    size: float = Field(default=48.0, gt=0.0)
    x_subdivisions: int = Field(default=20, ge=4, le=256)
    y_subdivisions: int = Field(default=20, ge=4, le=256)
    height_variation: float = Field(default=2.5, ge=0.0)
    collection_name: str = "World Terrain"


class GenerateBiomesRequest(CommonToolRequest):
    project_id: str
    world_id: str
    biome_types: list[str] = Field(default_factory=lambda: ["plains", "forest", "rock"])
    dominant_biome: str | None = None


class GenerateRoadsRequest(CommonToolRequest):
    project_id: str
    world_id: str
    road_count: int = Field(default=2, ge=1, le=16)
    extent: float = Field(default=36.0, gt=0.0)
    width: float = Field(default=2.0, gt=0.0)


class GenerateWaterSystemRequest(CommonToolRequest):
    project_id: str
    world_id: str
    water_type: Literal["river", "lake", "coast"] = "river"
    width: float = Field(default=6.0, gt=0.0)
    length: float = Field(default=24.0, gt=0.0)


class PlaceBuildingsRequest(CommonToolRequest):
    project_id: str
    world_id: str
    count: int = Field(default=4, ge=1, le=24)
    asset_ids: list[str] = Field(default_factory=list)
    spacing: float = Field(default=10.0, gt=0.0)
    origin: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    style: str | None = None


class ScatterVegetationRequest(CommonToolRequest):
    project_id: str
    world_id: str
    count: int = Field(default=12, ge=1, le=128)
    area_min: list[float] = Field(default_factory=lambda: [-16.0, -16.0, 0.0])
    area_max: list[float] = Field(default_factory=lambda: [16.0, 16.0, 0.0])
    vegetation_type: Literal["trees", "shrubs", "mixed"] = "mixed"
    collection_name: str = "World Vegetation"


class CreateRegionRequest(CommonToolRequest):
    project_id: str
    world_id: str
    name: str
    min_corner: list[float]
    max_corner: list[float]
    tags: list[str] = Field(default_factory=list)


class DetailRegionRequest(CommonToolRequest):
    project_id: str
    world_id: str
    region_id: str
    detail_type: Literal["vegetation", "buildings", "roads", "water", "mixed"] = "mixed"
    density: int = Field(default=6, ge=1, le=48)


class InspectWorldRequest(CommonToolRequest):
    project_id: str
    world_id: str


def _load_world(context, request_id: str, world_id: str, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    world = load_entity_spec(context, world_id, expected_type="world")
    if world is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"World '{world_id}' was not found.",
            errors=[f"target_not_found: world '{world_id}' does not exist"],
        )
    return world


def _save_world(context, project_id: str, world: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(world["world_id"]),
        entity_type="world",
        name=str(world["name"]),
        spec=world,
    )


def _append_world_id(world: dict[str, Any], field_name: str, entity_id: str) -> None:
    values = list(world.get(field_name, []))
    if entity_id not in values:
        values.append(entity_id)
    world[field_name] = values


def _biome_palette(biome_name: str) -> list[float]:
    normalized = biome_name.strip().lower()
    if "forest" in normalized:
        return [0.25, 0.45, 0.22, 1.0]
    if "desert" in normalized or "sand" in normalized:
        return [0.72, 0.63, 0.36, 1.0]
    if "snow" in normalized or "ice" in normalized:
        return [0.86, 0.9, 0.94, 1.0]
    if "water" in normalized or "coast" in normalized:
        return [0.16, 0.36, 0.62, 1.0]
    if "rock" in normalized or "mountain" in normalized:
        return [0.42, 0.4, 0.38, 1.0]
    return [0.36, 0.58, 0.3, 1.0]


def _world_entities(context, project_id: str, entity_type: str, world_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    entities = []
    for record in context.entities.list_by_type(project_id, entity_type):
        spec = load_entity_spec(context, record.entity_id, expected_type=entity_type)
        if spec is not None and spec.get("world_id") == world_id:
            entities.append(spec)
    return entities


async def create_world(context, request: CreateWorldRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world_id = new_id("world")
    world: dict[str, Any] = {
        "world_id": world_id,
        "name": request.name,
        "theme": request.theme,
        "terrain_ids": [],
        "biome_ids": [],
        "road_ids": [],
        "water_ids": [],
        "building_ids": [],
        "vegetation_ids": [],
        "region_ids": [],
    }
    _save_world(context, project.project_id, world)

    terrain_result: dict[str, Any] | None = None
    created_object_ids: list[str] = []
    if request.create_base_terrain:
        terrain = await generate_terrain(
            context,
            GenerateTerrainRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                world_id=world_id,
                name=f"{request.name}_Terrain",
                size=request.terrain_size,
                x_subdivisions=request.terrain_subdivisions,
                y_subdivisions=request.terrain_subdivisions,
                height_variation=request.terrain_height_variation,
            ),
        )
        if terrain.status != "success":
            return retag_result(terrain, "create_world")
        terrain_result = terrain.model_dump()
        created_object_ids.extend(terrain.created_object_ids)
        loaded_world = _load_world(context, request.request_id, world_id, "create_world")
        if isinstance(loaded_world, CommonToolResult):
            return loaded_world
        world = loaded_world
    return success_result(
        request_id=request.request_id,
        tool_name="create_world",
        summary=f"Created world '{request.name}'.",
        project_id=project.project_id,
        world_id=world_id,
        world=world,
        terrain=terrain_result.get("terrain") if terrain_result else None,
        created_object_ids=created_object_ids,
    )


async def generate_terrain(context, request: GenerateTerrainRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "generate_terrain")
    if isinstance(world, CommonToolResult):
        return world

    terrain_object = await create_primitive(
        context,
        CreatePrimitiveRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            primitive_type="grid",
            name=request.name,
            scale=[request.size, request.size, 1.0],
            collection_name=request.collection_name,
            tags=["terrain", request.world_id],
            parameters={
                "x_subdivisions": request.x_subdivisions,
                "y_subdivisions": request.y_subdivisions,
            },
        ),
    )
    if terrain_object.status != "success":
        return retag_result(terrain_object, "generate_terrain")
    terrain_object_id = str(terrain_object.created_object_ids[0])

    displaced = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=terrain_object_id,
            modifier_type="DISPLACE",
            name="TerrainDisplace",
            params={"strength": request.height_variation},
        ),
    )
    if displaced.status != "success":
        return retag_result(displaced, "generate_terrain")

    material_result = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.name}_Surface",
            base_color=[0.34, 0.48, 0.27, 1.0],
            roughness=0.96,
            metallic=0.0,
        ),
    )
    if material_result.status != "success":
        return retag_result(material_result, "generate_terrain")
    material = material_result.model_dump()["material"]
    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            material_id=str(material["material_id"]),
            target_ids=[terrain_object_id],
        ),
    )
    if applied.status not in {"success", "partial_success"}:
        return retag_result(applied, "generate_terrain")

    terrain_id = new_id("terrain")
    terrain = {
        "terrain_id": terrain_id,
        "world_id": request.world_id,
        "object_id": terrain_object_id,
        "size": request.size,
        "x_subdivisions": request.x_subdivisions,
        "y_subdivisions": request.y_subdivisions,
        "height_variation": request.height_variation,
        "material_id": material["material_id"],
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=terrain_id,
        entity_type="world_terrain",
        name=request.name,
        spec=terrain,
    )
    _append_world_id(world, "terrain_ids", terrain_id)
    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_terrain",
        summary=f"Generated terrain '{request.name}'.",
        project_id=project.project_id,
        world_id=request.world_id,
        terrain_id=terrain_id,
        terrain=terrain,
        material=material,
        created_object_ids=[terrain_object_id],
        objects=terrain_object.model_dump().get("objects", []),
    )


async def generate_biomes(context, request: GenerateBiomesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "generate_biomes")
    if isinstance(world, CommonToolResult):
        return world
    terrain_id = next(iter(world.get("terrain_ids", [])), None)
    terrain = load_entity_spec(context, str(terrain_id), expected_type="world_terrain") if terrain_id else None
    biome_names = request.biome_types or ["plains"]
    dominant = request.dominant_biome or biome_names[0]
    biomes = []
    for index, biome_name in enumerate(biome_names):
        biome_id = new_id("biome")
        biome = {
            "biome_id": biome_id,
            "world_id": request.world_id,
            "name": biome_name,
            "coverage_hint": round(1.0 / len(biome_names), 3),
            "priority": index,
        }
        save_metadata_entity(
            context,
            project_id=project.project_id,
            entity_id=biome_id,
            entity_type="world_biome",
            name=biome_name,
            spec=biome,
        )
        _append_world_id(world, "biome_ids", biome_id)
        biomes.append(biome)

    if terrain is not None:
        material_result = await create_pbr_material(
            context,
            CreatePBRMaterialRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                name=f"{world['name']}_BiomeSurface",
                base_color=_biome_palette(dominant),
                roughness=0.97,
                metallic=0.0,
            ),
        )
        if material_result.status != "success":
            return retag_result(material_result, "generate_biomes")
        applied = await apply_material(
            context,
            ApplyMaterialRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                material_id=str(material_result.model_dump()["material"]["material_id"]),
                target_ids=[str(terrain["object_id"])],
            ),
        )
        if applied.status not in {"success", "partial_success"}:
            return retag_result(applied, "generate_biomes")

    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_biomes",
        summary=f"Generated {len(biomes)} biome definitions.",
        project_id=project.project_id,
        world_id=request.world_id,
        biomes=biomes,
        dominant_biome=dominant,
    )


async def generate_roads(context, request: GenerateRoadsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "generate_roads")
    if isinstance(world, CommonToolResult):
        return world

    roads: list[dict[str, Any]] = []
    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    step = request.extent / max(request.road_count, 1)
    for index in range(request.road_count):
        x_offset = (-request.extent * 0.5) + (index * step)
        points = [
            [x_offset, -request.extent * 0.5, 0.02],
            [x_offset + (request.width * 0.5), -request.extent * 0.15, 0.02],
            [x_offset - (request.width * 0.5), request.extent * 0.15, 0.02],
            [x_offset, request.extent * 0.5, 0.02],
        ]
        road_curve = await create_curve(
            context,
            CreateCurveRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                name=f"Road_{index + 1:02d}",
                curve_type="polyline",
                points=points,
                collection_name="World Roads",
                tags=["road", request.world_id],
            ),
        )
        if road_curve.status != "success":
            return retag_result(road_curve, "generate_roads")
        road_object_id = str(road_curve.created_object_ids[0])
        road_id = new_id("road")
        road = {
            "road_id": road_id,
            "world_id": request.world_id,
            "object_id": road_object_id,
            "width": request.width,
            "points": points,
        }
        save_metadata_entity(
            context,
            project_id=project.project_id,
            entity_id=road_id,
            entity_type="world_road",
            name=f"Road {index + 1}",
            spec=road,
        )
        _append_world_id(world, "road_ids", road_id)
        roads.append(road)
        created_object_ids.extend(road_curve.created_object_ids)
        objects.extend(road_curve.model_dump().get("objects", []))

    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_roads",
        summary=f"Generated {len(roads)} road guides.",
        project_id=project.project_id,
        world_id=request.world_id,
        roads=roads,
        created_object_ids=created_object_ids,
        objects=objects,
    )


async def generate_water_system(context, request: GenerateWaterSystemRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "generate_water_system")
    if isinstance(world, CommonToolResult):
        return world

    if request.water_type == "lake":
        water_object = await create_primitive(
            context,
            CreatePrimitiveRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                primitive_type="plane",
                name="LakeSurface",
                scale=[request.width, request.length, 1.0],
                collection_name="World Water",
                tags=["water", request.world_id],
            ),
        )
    else:
        points = [
            [-request.length * 0.5, -request.width, 0.01],
            [-request.length * 0.1, -request.width * 0.2, 0.01],
            [request.length * 0.15, request.width * 0.35, 0.01],
            [request.length * 0.5, request.width, 0.01],
        ]
        water_object = await create_curve(
            context,
            CreateCurveRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                name=f"{request.water_type.title()}_Guide",
                curve_type="polyline",
                points=points,
                collection_name="World Water",
                tags=["water", request.world_id],
            ),
        )
    if water_object.status != "success":
        return retag_result(water_object, "generate_water_system")

    material_result = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.water_type.title()}Water",
            base_color=[0.12, 0.34, 0.62, 0.9],
            roughness=0.08,
            metallic=0.0,
            alpha=0.9,
        ),
    )
    if material_result.status != "success":
        return retag_result(material_result, "generate_water_system")

    object_id = str(water_object.created_object_ids[0])
    applied = await apply_material(
        context,
        ApplyMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            material_id=str(material_result.model_dump()["material"]["material_id"]),
            target_ids=[object_id],
        ),
    )
    if applied.status not in {"success", "partial_success"}:
        return retag_result(applied, "generate_water_system")

    water_id = new_id("water")
    water = {
        "water_id": water_id,
        "world_id": request.world_id,
        "water_type": request.water_type,
        "object_id": object_id,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=water_id,
        entity_type="world_water",
        name=f"{request.water_type.title()} Water",
        spec=water,
    )
    _append_world_id(world, "water_ids", water_id)
    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_water_system",
        summary=f"Generated {request.water_type} water system.",
        project_id=project.project_id,
        world_id=request.world_id,
        water_id=water_id,
        water=water,
        created_object_ids=[object_id],
        objects=water_object.model_dump().get("objects", []),
    )


async def place_buildings(context, request: PlaceBuildingsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "place_buildings")
    if isinstance(world, CommonToolResult):
        return world

    placements: list[dict[str, Any]] = []
    created_object_ids: list[str] = []
    asset_ids: list[str] = []
    for index in range(request.count):
        x_offset = request.origin[0] + (index * request.spacing)
        y_offset = request.origin[1] + ((index % 2) * request.spacing * 0.35)
        position = [x_offset, y_offset, request.origin[2]]
        if request.asset_ids:
            placed = await place_asset(
                context,
                PlaceAssetRequest(
                    request_id=request.request_id,
                    project_id=request.project_id,
                    asset_id=request.asset_ids[index % len(request.asset_ids)],
                    location=position,
                    collection_name="World Buildings",
                ),
            )
            if placed.status != "success":
                return retag_result(placed, "place_buildings")
            payload = placed.model_dump()
            asset_ids.append(str(payload["asset_id"]))
            building_object_ids = list(payload.get("created_object_ids", []))
        else:
            generated = await create_building(
                context,
                CreateBuildingRequest(
                    request_id=request.request_id,
                    project_id=request.project_id,
                    name=f"WorldBuilding_{index + 1:02d}",
                    style=request.style,
                    width=6.0,
                    depth=4.0,
                    height=7.0,
                    floors=3,
                ),
            )
            if generated.status != "success":
                return retag_result(generated, "place_buildings")
            payload = generated.model_dump()
            asset_ids.append(str(payload["asset_id"]))
            building_object_ids = list(payload.get("created_object_ids", []))
            for object_id in building_object_ids:
                moved = await transform_object(
                    context,
                    TransformObjectRequest(
                        request_id=request.request_id,
                        project_id=request.project_id,
                        target_id=str(object_id),
                        location=position,
                    ),
                )
                if moved.status != "success":
                    return retag_result(moved, "place_buildings")
        building_id = new_id("worldbuilding")
        placement = {
            "building_id": building_id,
            "world_id": request.world_id,
            "asset_id": asset_ids[-1],
            "object_ids": building_object_ids,
            "location": position,
        }
        save_metadata_entity(
            context,
            project_id=project.project_id,
            entity_id=building_id,
            entity_type="world_building",
            name=f"Building {index + 1}",
            spec=placement,
        )
        _append_world_id(world, "building_ids", building_id)
        placements.append(placement)
        created_object_ids.extend(building_object_ids)

    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="place_buildings",
        summary=f"Placed {len(placements)} building groups.",
        project_id=project.project_id,
        world_id=request.world_id,
        asset_ids=asset_ids,
        placements=placements,
        created_object_ids=created_object_ids,
    )


async def scatter_vegetation(context, request: ScatterVegetationRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "scatter_vegetation")
    if isinstance(world, CommonToolResult):
        return world

    rng = random.Random(request.seed)
    material_result = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{world['name']}_Vegetation",
            base_color=[0.18, 0.46, 0.16, 1.0],
            roughness=0.92,
            metallic=0.0,
        ),
    )
    if material_result.status != "success":
        return retag_result(material_result, "scatter_vegetation")
    material_id = str(material_result.model_dump()["material"]["material_id"])

    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []
    for index in range(request.count):
        vegetation_type = request.vegetation_type
        if vegetation_type == "mixed":
            vegetation_type = "trees" if index % 2 == 0 else "shrubs"
        primitive_type = "cone" if vegetation_type == "trees" else "uv_sphere"
        scale = [0.55, 0.55, 1.4] if vegetation_type == "trees" else [0.45, 0.45, 0.45]
        created = await create_primitive(
            context,
            CreatePrimitiveRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                primitive_type=primitive_type,
                name=f"Vegetation_{index + 1:02d}",
                location=[
                    rng.uniform(float(request.area_min[0]), float(request.area_max[0])),
                    rng.uniform(float(request.area_min[1]), float(request.area_max[1])),
                    rng.uniform(float(request.area_min[2]), float(request.area_max[2])),
                ],
                scale=scale,
                collection_name=request.collection_name,
                tags=["vegetation", request.world_id, vegetation_type],
            ),
        )
        if created.status != "success":
            return retag_result(created, "scatter_vegetation")
        object_id = str(created.created_object_ids[0])
        applied = await apply_material(
            context,
            ApplyMaterialRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                material_id=material_id,
                target_ids=[object_id],
            ),
        )
        if applied.status not in {"success", "partial_success"}:
            return retag_result(applied, "scatter_vegetation")
        created_object_ids.append(object_id)
        objects.extend(created.model_dump().get("objects", []))

    vegetation_id = new_id("vegetation")
    vegetation = {
        "vegetation_id": vegetation_id,
        "world_id": request.world_id,
        "count": request.count,
        "object_ids": created_object_ids,
        "vegetation_type": request.vegetation_type,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=vegetation_id,
        entity_type="world_vegetation",
        name=f"Vegetation {vegetation_id}",
        spec=vegetation,
    )
    _append_world_id(world, "vegetation_ids", vegetation_id)
    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="scatter_vegetation",
        summary=f"Scattered {request.count} vegetation objects.",
        project_id=project.project_id,
        world_id=request.world_id,
        vegetation_id=vegetation_id,
        vegetation=vegetation,
        created_object_ids=created_object_ids,
        objects=objects,
    )


async def create_region(context, request: CreateRegionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "create_region")
    if isinstance(world, CommonToolResult):
        return world

    points = [
        [request.min_corner[0], request.min_corner[1], request.min_corner[2]],
        [request.max_corner[0], request.min_corner[1], request.min_corner[2]],
        [request.max_corner[0], request.max_corner[1], request.min_corner[2]],
        [request.min_corner[0], request.max_corner[1], request.min_corner[2]],
        [request.min_corner[0], request.min_corner[1], request.min_corner[2]],
    ]
    border = await create_curve(
        context,
        CreateCurveRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.name}_Border",
            curve_type="polyline",
            points=points,
            collection_name="World Regions",
            tags=["region", request.world_id, *request.tags],
        ),
    )
    if border.status != "success":
        return retag_result(border, "create_region")

    region_id = new_id("region")
    region = {
        "region_id": region_id,
        "world_id": request.world_id,
        "name": request.name,
        "min_corner": request.min_corner,
        "max_corner": request.max_corner,
        "tags": request.tags,
        "object_id": str(border.created_object_ids[0]),
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=region_id,
        entity_type="world_region",
        name=request.name,
        spec=region,
    )
    _append_world_id(world, "region_ids", region_id)
    _save_world(context, project.project_id, world)
    return success_result(
        request_id=request.request_id,
        tool_name="create_region",
        summary=f"Created region '{request.name}'.",
        project_id=project.project_id,
        world_id=request.world_id,
        region_id=region_id,
        region=region,
        created_object_ids=list(border.created_object_ids),
        objects=border.model_dump().get("objects", []),
    )


async def detail_region(context, request: DetailRegionRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "detail_region")
    if isinstance(world, CommonToolResult):
        return world
    region = load_entity_spec(context, request.region_id, expected_type="world_region")
    if region is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="detail_region",
            summary=f"Region '{request.region_id}' was not found.",
            errors=[f"target_not_found: region '{request.region_id}' does not exist"],
        )

    created_object_ids: list[str] = []
    detail_results: list[dict[str, Any]] = []
    if request.detail_type in {"vegetation", "mixed"}:
        vegetation = await scatter_vegetation(
            context,
            ScatterVegetationRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                world_id=request.world_id,
                count=request.density,
                area_min=list(region["min_corner"]),
                area_max=list(region["max_corner"]),
                vegetation_type="mixed",
                collection_name=f"{region['name']}_Vegetation",
            ),
        )
        if vegetation.status != "success":
            return retag_result(vegetation, "detail_region")
        detail_results.append({"detail_type": "vegetation", "result": vegetation.model_dump()})
        created_object_ids.extend(vegetation.created_object_ids)
    if request.detail_type in {"buildings", "mixed"}:
        buildings = await place_buildings(
            context,
            PlaceBuildingsRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                world_id=request.world_id,
                count=max(1, min(4, request.density // 2)),
                origin=[region["min_corner"][0], region["min_corner"][1], region["min_corner"][2]],
                spacing=max(4.0, (region["max_corner"][0] - region["min_corner"][0]) / 2.0),
            ),
        )
        if buildings.status != "success":
            return retag_result(buildings, "detail_region")
        detail_results.append({"detail_type": "buildings", "result": buildings.model_dump()})
        created_object_ids.extend(buildings.created_object_ids)
    if request.detail_type == "roads":
        roads = await generate_roads(
            context,
            GenerateRoadsRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                world_id=request.world_id,
                road_count=max(1, min(3, request.density // 3)),
                extent=max(6.0, region["max_corner"][0] - region["min_corner"][0]),
                width=1.5,
            ),
        )
        if roads.status != "success":
            return retag_result(roads, "detail_region")
        detail_results.append({"detail_type": "roads", "result": roads.model_dump()})
        created_object_ids.extend(roads.created_object_ids)
    if request.detail_type == "water":
        water = await generate_water_system(
            context,
            GenerateWaterSystemRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                world_id=request.world_id,
                water_type="river",
                width=max(2.0, (region["max_corner"][1] - region["min_corner"][1]) / 4.0),
                length=max(8.0, region["max_corner"][0] - region["min_corner"][0]),
            ),
        )
        if water.status != "success":
            return retag_result(water, "detail_region")
        detail_results.append({"detail_type": "water", "result": water.model_dump()})
        created_object_ids.extend(water.created_object_ids)

    region["detail_history"] = [*region.get("detail_history", []), {"detail_type": request.detail_type, "density": request.density}]
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=request.region_id,
        entity_type="world_region",
        name=region["name"],
        spec=region,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="detail_region",
        summary=f"Detailed region '{region['name']}' with {request.detail_type}.",
        project_id=project.project_id,
        world_id=request.world_id,
        region_id=request.region_id,
        detail_results=detail_results,
        created_object_ids=created_object_ids,
    )


async def inspect_world(context, request: InspectWorldRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    world = _load_world(context, request.request_id, request.world_id, "inspect_world")
    if isinstance(world, CommonToolResult):
        return world

    terrain = _world_entities(context, request.project_id, "world_terrain", request.world_id)
    biomes = _world_entities(context, request.project_id, "world_biome", request.world_id)
    roads = _world_entities(context, request.project_id, "world_road", request.world_id)
    water = _world_entities(context, request.project_id, "world_water", request.world_id)
    buildings = _world_entities(context, request.project_id, "world_building", request.world_id)
    vegetation = _world_entities(context, request.project_id, "world_vegetation", request.world_id)
    regions = _world_entities(context, request.project_id, "world_region", request.world_id)
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_world",
        summary=f"Inspected world '{world['name']}'.",
        project_id=request.project_id,
        world=world,
        counts={
            "terrain": len(terrain),
            "biomes": len(biomes),
            "roads": len(roads),
            "water": len(water),
            "buildings": len(buildings),
            "vegetation": len(vegetation),
            "regions": len(regions),
        },
        terrain=terrain,
        biomes=biomes,
        roads=roads,
        water=water,
        buildings=buildings,
        vegetation=vegetation,
        regions=regions,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_world", "Create a managed world container and optional base terrain.", CreateWorldRequest, create_world, False),
        ("generate_terrain", "Generate a terrain mesh for a world.", GenerateTerrainRequest, generate_terrain, False),
        ("generate_biomes", "Attach biome metadata and terrain surfacing hints.", GenerateBiomesRequest, generate_biomes, False),
        ("generate_roads", "Create road guide curves for a world.", GenerateRoadsRequest, generate_roads, False),
        ("generate_water_system", "Create a river or lake proxy for the world.", GenerateWaterSystemRequest, generate_water_system, False),
        ("place_buildings", "Populate a world with managed building groups.", PlaceBuildingsRequest, place_buildings, False),
        ("scatter_vegetation", "Scatter simple vegetation proxies across a region.", ScatterVegetationRequest, scatter_vegetation, False),
        ("create_region", "Register a named world region and border guide.", CreateRegionRequest, create_region, False),
        ("detail_region", "Add localized detail to a world region.", DetailRegionRequest, detail_region, False),
        ("inspect_world", "Return managed world metadata and related counts.", InspectWorldRequest, inspect_world, True),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="world",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )