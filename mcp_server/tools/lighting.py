from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.tools.helpers import require_project, sync_entities
from mcp_server.tools.spatial import (
    center_and_extent,
    has_target_filter,
    list_project_objects,
    look_at_rotation,
    resolve_spatial_targets,
)

LightBalanceMode = Literal["normalize", "key_fill_rim", "fade_by_order"]
SoftboxSide = Literal["front", "front_left", "front_right", "top"]


class LightQueryRequest(CommonToolRequest):
    project_id: str


class LightingTargetRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class CreateThreePointLightingRequest(LightingTargetRequest):
    name_prefix: str = "ThreePoint"
    radius: float = Field(default=4.0, gt=0.0)
    height: float = 2.5
    key_intensity: float = Field(default=1600.0, ge=0.0)
    fill_intensity: float = Field(default=650.0, ge=0.0)
    rim_intensity: float = Field(default=900.0, ge=0.0)
    size: float = Field(default=2.0, gt=0.0)


class CreateSoftboxLightingRequest(LightingTargetRequest):
    name: str = "Softbox"
    side: SoftboxSide = "front_left"
    distance: float = Field(default=4.0, gt=0.0)
    height: float = 2.5
    intensity: float = Field(default=1200.0, ge=0.0)
    size: float = Field(default=4.0, gt=0.0)
    color: tuple[float, float, float] = (1.0, 0.97, 0.92)


class CreateLightRingRequest(LightingTargetRequest):
    name_prefix: str = "RingLight"
    count: int = Field(default=6, ge=3, le=32)
    radius: float = Field(default=4.0, gt=0.0)
    height: float = 2.0
    intensity: float = Field(default=500.0, ge=0.0)
    size: float = Field(default=1.0, gt=0.0)
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)


class AimLightsAtTargetRequest(LightingTargetRequest):
    light_id: str | None = None
    light_ids: list[str] = Field(default_factory=list)
    light_names: list[str] = Field(default_factory=list)


class BalanceLightIntensitiesRequest(CommonToolRequest):
    project_id: str
    light_id: str | None = None
    light_ids: list[str] = Field(default_factory=list)
    light_names: list[str] = Field(default_factory=list)
    mode: LightBalanceMode = "normalize"
    target_intensity: float = Field(default=1000.0, ge=0.0)
    fill_ratio: float = Field(default=0.45, ge=0.0, le=1.0)
    rim_ratio: float = Field(default=0.7, ge=0.0, le=2.0)


class SetLightColorTemperatureRequest(CommonToolRequest):
    project_id: str
    light_id: str
    kelvin: float = Field(default=5600.0, ge=1000.0, le=40000.0)


def _lights_from_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in objects if item.get("type") == "LIGHT"]


async def _resolve_light_ids(context, request: Any) -> list[str]:  # type: ignore[no-untyped-def]
    objects = await list_project_objects(context, request.project_id)
    lights = _lights_from_objects(objects)
    explicit_ids = list(getattr(request, "light_ids", []) or [])
    light_id = getattr(request, "light_id", None)
    if light_id:
        explicit_ids.append(light_id)
    if explicit_ids:
        known = {item["object_id"] for item in lights}
        missing = [light_id for light_id in explicit_ids if light_id not in known]
        if missing:
            raise ValueError(f"Unknown light_id: {missing[0]}")
        return list(dict.fromkeys(explicit_ids))
    if getattr(request, "light_names", []):
        wanted = {name.lower() for name in request.light_names}
        return [item["object_id"] for item in lights if str(item.get("name", "")).lower() in wanted]
    return [item["object_id"] for item in lights]


async def _create_light(context, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return await context.bridge.invoke("create_light", {"project_id": project_id, **payload})


async def list_lights(context, request: LightQueryRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    lights = _lights_from_objects(await list_project_objects(context, project.project_id))
    return success_result(
        request_id=request.request_id,
        tool_name="list_lights",
        summary=f"Listed {len(lights)} lights.",
        project_id=project.project_id,
        lights=lights,
        count=len(lights),
    )


async def create_three_point_lighting(context, request: CreateThreePointLightingRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, _extent, _minimum, _maximum = center_and_extent(targets)
    definitions = [
        {
            "name": f"{request.name_prefix}_Key",
            "location": [center[0] + request.radius, center[1] - request.radius, center[2] + request.height],
            "intensity": request.key_intensity,
            "color": [1.0, 0.96, 0.9],
            "size": request.size,
        },
        {
            "name": f"{request.name_prefix}_Fill",
            "location": [center[0] - request.radius, center[1] - (request.radius * 0.65), center[2] + (request.height * 0.65)],
            "intensity": request.fill_intensity,
            "color": [0.88, 0.93, 1.0],
            "size": request.size * 1.35,
        },
        {
            "name": f"{request.name_prefix}_Rim",
            "location": [center[0], center[1] + request.radius, center[2] + request.height],
            "intensity": request.rim_intensity,
            "color": [1.0, 1.0, 1.0],
            "size": request.size,
        },
    ]
    objects: list[dict[str, Any]] = []
    lights: list[dict[str, Any]] = []
    for definition in definitions:
        definition["rotation"] = look_at_rotation(definition["location"], center)
        created = await _create_light(context, project.project_id, definition)
        objects.append(created["object"])
        lights.append(created["light"])
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="create_three_point_lighting",
        summary="Created three-point lighting rig.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in objects],
        objects=objects,
        lights=lights,
        target_center=center,
    )


async def create_softbox_lighting(context, request: CreateSoftboxLightingRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, _extent, _minimum, _maximum = center_and_extent(targets)
    offsets = {
        "front": (0.0, -request.distance, request.height),
        "front_left": (-request.distance, -request.distance, request.height),
        "front_right": (request.distance, -request.distance, request.height),
        "top": (0.0, -request.distance * 0.25, request.distance + request.height),
    }
    offset = offsets[request.side]
    location = [center[axis] + offset[axis] for axis in range(3)]
    created = await _create_light(
        context,
        project.project_id,
        {
            "name": request.name,
            "light_type": "AREA",
            "location": location,
            "rotation": look_at_rotation(location, center),
            "intensity": request.intensity,
            "color": list(request.color),
            "size": request.size,
        },
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [created["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="create_softbox_lighting",
        summary=f"Created softbox light {request.name}.",
        project_id=project.project_id,
        created_object_ids=[created["object"]["object_id"]],
        object=created["object"],
        light=created["light"],
        target_center=center,
    )


async def create_light_ring(context, request: CreateLightRingRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, _extent, _minimum, _maximum = center_and_extent(targets)
    objects: list[dict[str, Any]] = []
    lights: list[dict[str, Any]] = []
    for index in range(request.count):
        angle = (math.tau * index) / request.count
        location = [
            center[0] + (request.radius * math.cos(angle)),
            center[1] + (request.radius * math.sin(angle)),
            center[2] + request.height,
        ]
        created = await _create_light(
            context,
            project.project_id,
            {
                "name": f"{request.name_prefix}_{index + 1:02d}",
                "light_type": "POINT",
                "location": location,
                "rotation": look_at_rotation(location, center),
                "intensity": request.intensity,
                "color": list(request.color),
                "size": request.size,
            },
        )
        objects.append(created["object"])
        lights.append(created["light"])
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="create_light_ring",
        summary=f"Created {len(lights)} ring lights.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in objects],
        objects=objects,
        lights=lights,
        target_center=center,
    )


async def aim_lights_at_target(context, request: AimLightsAtTargetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    try:
        light_ids = await _resolve_light_ids(context, request)
    except ValueError as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="aim_lights_at_target",
            summary=str(exc),
            errors=[f"target_not_found: {exc}"],
        )
    if not light_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="aim_lights_at_target",
            summary="No lights were available to aim.",
            errors=["target_not_found: no lights were resolved"],
        )
    if not has_target_filter(request):
        return failed_result(
            request_id=request.request_id,
            tool_name="aim_lights_at_target",
            summary="A target is required for light aiming.",
            errors=["validation_error: target_id, target_ids, names, tag, or match_collection_name is required"],
        )
    targets = await resolve_spatial_targets(context, request, fallback_to_scene_meshes=False)
    center, _extent, _minimum, _maximum = center_and_extent(targets)
    objects: list[dict[str, Any]] = []
    lights: list[dict[str, Any]] = []
    object_map = {item["object_id"]: item for item in await list_project_objects(context, project.project_id)}
    for light_id in light_ids:
        light_object = object_map[light_id]
        result = await context.bridge.invoke(
            "set_light",
            {
                "project_id": project.project_id,
                "light_id": light_id,
                "rotation": look_at_rotation(list(light_object.get("location", [0.0, 0.0, 0.0])), center),
            },
        )
        objects.append(result["object"])
        lights.append(result["light"])
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="aim_lights_at_target",
        summary=f"Aimed {len(light_ids)} lights at target bounds.",
        project_id=project.project_id,
        modified_object_ids=light_ids,
        objects=objects,
        lights=lights,
        target_center=center,
    )


async def balance_light_intensities(context, request: BalanceLightIntensitiesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    try:
        light_ids = await _resolve_light_ids(context, request)
    except ValueError as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="balance_light_intensities",
            summary=str(exc),
            errors=[f"target_not_found: {exc}"],
        )
    if not light_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="balance_light_intensities",
            summary="No lights were available to balance.",
            errors=["target_not_found: no lights were resolved"],
        )
    objects: list[dict[str, Any]] = []
    lights: list[dict[str, Any]] = []
    for index, light_id in enumerate(light_ids):
        intensity = request.target_intensity
        if request.mode == "key_fill_rim" and index == 1:
            intensity *= request.fill_ratio
        elif request.mode == "key_fill_rim" and index >= 2:
            intensity *= request.rim_ratio
        elif request.mode == "fade_by_order":
            intensity *= max(1.0 - (index * request.fill_ratio), 0.05)
        result = await context.bridge.invoke(
            "set_light",
            {"project_id": project.project_id, "light_id": light_id, "intensity": intensity},
        )
        objects.append(result["object"])
        lights.append(result["light"])
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="balance_light_intensities",
        summary=f"Balanced {len(light_ids)} light intensities.",
        project_id=project.project_id,
        modified_object_ids=light_ids,
        objects=objects,
        lights=lights,
        mode=request.mode,
    )


async def set_light_color_temperature(context, request: SetLightColorTemperatureRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    color = _kelvin_to_rgb(request.kelvin)
    result = await context.bridge.invoke(
        "set_light",
        {"project_id": project.project_id, "light_id": request.light_id, "color": color},
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="set_light_color_temperature",
        summary=f"Set light {request.light_id} to {request.kelvin:g}K.",
        project_id=project.project_id,
        modified_object_ids=[request.light_id],
        object=result["object"],
        light=result["light"],
        color=color,
        kelvin=request.kelvin,
    )


def _kelvin_to_rgb(kelvin: float) -> list[float]:
    temperature = kelvin / 100.0
    if temperature <= 66.0:
        red = 255.0
        green = 99.4708025861 * math.log(max(temperature, 1.0)) - 161.1195681661
        blue = 0.0 if temperature <= 19.0 else 138.5177312231 * math.log(temperature - 10.0) - 305.0447927307
    else:
        red = 329.698727446 * ((temperature - 60.0) ** -0.1332047592)
        green = 288.1221695283 * ((temperature - 60.0) ** -0.0755148492)
        blue = 255.0
    return [max(0.0, min(component, 255.0)) / 255.0 for component in (red, green, blue)]


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("list_lights", "List light objects in the active project.", LightQueryRequest, list_lights, True),
        ("create_three_point_lighting", "Create a key/fill/rim lighting rig around target bounds.", CreateThreePointLightingRequest, create_three_point_lighting, False),
        ("create_softbox_lighting", "Create a large area softbox light aimed at target bounds.", CreateSoftboxLightingRequest, create_softbox_lighting, False),
        ("create_light_ring", "Create an evenly spaced ring of lights around target bounds.", CreateLightRingRequest, create_light_ring, False),
        ("aim_lights_at_target", "Rotate resolved lights toward a target center.", AimLightsAtTargetRequest, aim_lights_at_target, False),
        ("balance_light_intensities", "Normalize or ratio-balance resolved light intensities.", BalanceLightIntensitiesRequest, balance_light_intensities, False),
        ("set_light_color_temperature", "Convert a Kelvin color temperature and apply it to a light.", SetLightColorTemperatureRequest, set_light_color_temperature, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="lighting",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
