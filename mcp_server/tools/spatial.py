from __future__ import annotations

import math
from typing import Any, Literal

from mcp_server.tools.helpers import resolve_target_ids

AngleName = Literal["front", "back", "left", "right", "top", "isometric"]
ShotSize = Literal["wide", "medium", "closeup", "detail"]

_ANGLE_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "front": (0.0, -1.0, 0.45),
    "back": (0.0, 1.0, 0.45),
    "left": (-1.0, 0.0, 0.45),
    "right": (1.0, 0.0, 0.45),
    "top": (0.0, -0.25, 1.0),
    "isometric": (1.0, -1.0, 0.65),
}

_SHOT_MULTIPLIERS: dict[str, float] = {
    "wide": 3.8,
    "medium": 2.6,
    "closeup": 1.65,
    "detail": 1.05,
}


async def list_project_objects(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    result = await context.bridge.invoke("list_objects", {"project_id": project_id}, read_only=True)
    return list(result.get("objects", []))


def has_target_filter(request: Any) -> bool:
    return any(
        [
            getattr(request, "target_id", None),
            getattr(request, "target_ids", []),
            getattr(request, "names", []),
            getattr(request, "tag", None),
            getattr(request, "match_collection_name", None),
        ]
    )


async def resolve_spatial_targets(  # type: ignore[no-untyped-def]
    context,
    request: Any,
    *,
    fallback_to_scene_meshes: bool = True,
) -> list[dict[str, Any]]:
    objects = await list_project_objects(context, request.project_id)
    if has_target_filter(request):
        target_id = getattr(request, "target_id", None)
        target_ids = await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=getattr(request, "target_ids", []) or ([target_id] if target_id else []),
            names=getattr(request, "names", []),
            tag=getattr(request, "tag", None),
            collection_name=getattr(request, "match_collection_name", None),
        )
        target_set = set(target_ids)
        return [item for item in objects if item.get("object_id") in target_set]
    if fallback_to_scene_meshes:
        mesh_objects = [item for item in objects if item.get("type") == "MESH"]
        if mesh_objects:
            return mesh_objects
    if objects:
        return objects
    raise ValueError("No matching targets were resolved.")


def bounds_for_objects(objects: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    minimum = [float("inf"), float("inf"), float("inf")]
    maximum = [float("-inf"), float("-inf"), float("-inf")]
    for item in objects:
        obj_min, obj_max = bounds_for_object(item)
        for axis in range(3):
            minimum[axis] = min(minimum[axis], obj_min[axis])
            maximum[axis] = max(maximum[axis], obj_max[axis])
    if any(not math.isfinite(value) for value in [*minimum, *maximum]):
        return [-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]
    return minimum, maximum


def bounds_for_object(item: dict[str, Any]) -> tuple[list[float], list[float]]:
    location = _vector3(item.get("location", [0.0, 0.0, 0.0]))
    scale = _vector3(item.get("scale", [1.0, 1.0, 1.0]))
    vertices = list((item.get("data", {}) or {}).get("vertices", []))
    if vertices:
        transformed = [
            [location[axis] + (float(vertex[axis]) * scale[axis]) for axis in range(3)]
            for vertex in vertices
        ]
        return (
            [min(vertex[axis] for vertex in transformed) for axis in range(3)],
            [max(vertex[axis] for vertex in transformed) for axis in range(3)],
        )
    half_extents = [max(abs(component), 0.5) * 0.5 for component in scale]
    return (
        [location[axis] - half_extents[axis] for axis in range(3)],
        [location[axis] + half_extents[axis] for axis in range(3)],
    )


def center_and_extent(objects: list[dict[str, Any]]) -> tuple[list[float], float, list[float], list[float]]:
    minimum, maximum = bounds_for_objects(objects)
    center = [(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False)]
    dimensions = [max(high - low, 0.001) for low, high in zip(minimum, maximum, strict=False)]
    return center, max(dimensions), minimum, maximum


def camera_plan(
    *,
    center: list[float],
    extent: float,
    angle: AngleName,
    shot_size: ShotSize,
    distance_multiplier: float = 1.0,
    height_offset: float = 0.0,
    composition_offset: tuple[float, float] = (0.0, 0.0),
) -> dict[str, list[float] | float | str]:
    direction = normalize(_ANGLE_DIRECTIONS[angle], default=(0.0, -1.0, 0.45))
    distance = max(extent * _SHOT_MULTIPLIERS[shot_size] * distance_multiplier, 1.0)
    target = [
        center[0] + (composition_offset[0] * extent),
        center[1],
        center[2] + (composition_offset[1] * extent),
    ]
    location = [target[axis] + (direction[axis] * distance) for axis in range(3)]
    location[2] += height_offset
    return {
        "location": location,
        "rotation": look_at_rotation(location, target),
        "target": target,
        "distance": distance,
        "angle": angle,
        "shot_size": shot_size,
    }


def look_at_rotation(location: list[float], target: list[float]) -> list[float]:
    direction = normalize(
        [target[axis] - location[axis] for axis in range(3)],
        default=(0.0, 1.0, -0.5),
    )
    horizontal = math.sqrt((direction[0] * direction[0]) + (direction[1] * direction[1]))
    pitch = math.atan2(horizontal, -direction[2] if abs(direction[2]) > 0.0001 else 0.0001)
    yaw = math.atan2(direction[0], direction[1])
    return [pitch, 0.0, yaw]


def normalize(value: Any, *, default: tuple[float, float, float]) -> list[float]:
    vector = _vector3(value)
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 0.000001:
        return list(default)
    return [component / length for component in vector]


def distance_between(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


def _vector3(value: Any) -> list[float]:
    items = list(value)
    if len(items) < 3:
        items = [*items, *([0.0] * (3 - len(items)))]
    return [float(items[0]), float(items[1]), float(items[2])]
