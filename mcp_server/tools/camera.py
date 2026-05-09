from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.serialization import json_loads
from mcp_server.tools.helpers import (
    require_project,
    resolve_target_ids,
    sync_entities,
    sync_named_entity,
)
from mcp_server.tools.spatial import (
    AngleName,
    ShotSize,
    camera_plan,
    center_and_extent,
    distance_between,
    has_target_filter,
    list_project_objects,
    look_at_rotation,
    normalize,
    resolve_spatial_targets,
)
from mcp_server.utils import new_id

LensProfile = Literal["wide_angle", "standard", "portrait", "telephoto", "isometric_review"]

_LENS_PROFILES: dict[str, dict[str, float]] = {
    "wide_angle": {"focal_length": 24.0, "field_of_view": 1.15},
    "standard": {"focal_length": 35.0, "field_of_view": 0.9},
    "portrait": {"focal_length": 70.0, "field_of_view": 0.55},
    "telephoto": {"focal_length": 120.0, "field_of_view": 0.32},
    "isometric_review": {"focal_length": 50.0, "field_of_view": 0.75},
}


class CameraQueryRequest(CommonToolRequest):
    project_id: str


class CameraTargetRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class CreateShotCameraRequest(CameraTargetRequest):
    name: str = "ShotCamera"
    shot_size: ShotSize = "medium"
    angle: AngleName = "front"
    distance_multiplier: float = Field(default=1.0, gt=0.0)
    height_offset: float = 0.0
    composition_offset: tuple[float, float] = (0.0, 0.0)
    focal_length: float = Field(default=50.0, gt=0.0)
    field_of_view: float = Field(default=0.9, gt=0.0)
    set_active: bool = True


class FrameCameraToTargetsRequest(CameraTargetRequest):
    camera_id: str
    shot_size: ShotSize = "medium"
    angle: AngleName = "front"
    margin: float = Field(default=1.0, gt=0.0)
    height_offset: float = 0.0
    composition_offset: tuple[float, float] = (0.0, 0.0)
    focal_length: float | None = Field(default=None, gt=0.0)
    field_of_view: float | None = Field(default=None, gt=0.0)


class CreateCameraOrbitRequest(CameraTargetRequest):
    name_prefix: str = "OrbitCamera"
    count: int = Field(default=6, ge=2, le=32)
    radius: float = Field(default=5.0, gt=0.0)
    height: float = 2.5
    start_angle_degrees: float = 0.0
    focal_length: float = Field(default=50.0, gt=0.0)
    field_of_view: float = Field(default=0.9, gt=0.0)
    set_first_active: bool = True


class DollyCameraRequest(CameraTargetRequest):
    camera_id: str
    distance_delta: float = 0.0
    min_distance: float = Field(default=0.25, gt=0.0)


class SetCameraLensProfileRequest(CommonToolRequest):
    project_id: str
    camera_id: str
    profile_name: LensProfile = "standard"
    focal_length: float | None = Field(default=None, gt=0.0)
    field_of_view: float | None = Field(default=None, gt=0.0)


class SaveShotBookmarkRequest(CameraTargetRequest):
    name: str
    camera_id: str
    shot_type: str = "composition"
    notes: str | None = None


class ApplyShotBookmarkRequest(CommonToolRequest):
    project_id: str
    shot_id: str
    set_active: bool = True


def _cameras_from_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in objects if item.get("type") == "CAMERA"]


def _object_by_id(objects: list[dict[str, Any]], object_id: str) -> dict[str, Any] | None:
    return next((item for item in objects if item.get("object_id") == object_id), None)


async def list_cameras(context, request: CameraQueryRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    cameras = _cameras_from_objects(await list_project_objects(context, project.project_id))
    return success_result(
        request_id=request.request_id,
        tool_name="list_cameras",
        summary=f"Listed {len(cameras)} cameras.",
        project_id=project.project_id,
        cameras=cameras,
        count=len(cameras),
    )


async def create_shot_camera(context, request: CreateShotCameraRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, extent, _minimum, _maximum = center_and_extent(targets)
    plan = camera_plan(
        center=center,
        extent=extent,
        angle=request.angle,
        shot_size=request.shot_size,
        distance_multiplier=request.distance_multiplier,
        height_offset=request.height_offset,
        composition_offset=request.composition_offset,
    )
    result = await context.bridge.invoke(
        "create_camera",
        {
            "project_id": project.project_id,
            "name": request.name,
            "location": plan["location"],
            "rotation": plan["rotation"],
            "focal_length": request.focal_length,
            "field_of_view": request.field_of_view,
        },
    )
    if request.set_active:
        await context.bridge.invoke(
            "set_active_camera",
            {"project_id": project.project_id, "camera_id": result["camera"]["camera_id"]},
        )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="create_shot_camera",
        summary=f"Created shot camera {request.name}.",
        project_id=project.project_id,
        created_object_ids=[result["object"]["object_id"]],
        camera=result["camera"],
        object=result["object"],
        shot_plan=plan,
        framed_object_ids=[item["object_id"] for item in targets],
    )


async def frame_camera_to_targets(context, request: FrameCameraToTargetsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, extent, _minimum, _maximum = center_and_extent(targets)
    plan = camera_plan(
        center=center,
        extent=extent,
        angle=request.angle,
        shot_size=request.shot_size,
        distance_multiplier=request.margin,
        height_offset=request.height_offset,
        composition_offset=request.composition_offset,
    )
    payload: dict[str, Any] = {
        "project_id": project.project_id,
        "camera_id": request.camera_id,
        "location": plan["location"],
        "rotation": plan["rotation"],
    }
    if request.focal_length is not None:
        payload["focal_length"] = request.focal_length
    if request.field_of_view is not None:
        payload["field_of_view"] = request.field_of_view
    result = await context.bridge.invoke("set_camera", payload)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="frame_camera_to_targets",
        summary=f"Framed {len(targets)} target objects with camera {request.camera_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        camera=result["camera"],
        object=result["object"],
        shot_plan=plan,
        framed_object_ids=[item["object_id"] for item in targets],
    )


async def create_camera_orbit(context, request: CreateCameraOrbitRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    targets = await resolve_spatial_targets(context, request)
    center, _extent, _minimum, _maximum = center_and_extent(targets)
    created_objects: list[dict[str, Any]] = []
    cameras: list[dict[str, Any]] = []
    start_angle = math.radians(request.start_angle_degrees)
    for index in range(request.count):
        angle = start_angle + ((math.tau * index) / request.count)
        location = [
            center[0] + (request.radius * math.cos(angle)),
            center[1] + (request.radius * math.sin(angle)),
            center[2] + request.height,
        ]
        result = await context.bridge.invoke(
            "create_camera",
            {
                "project_id": project.project_id,
                "name": f"{request.name_prefix}_{index + 1:02d}",
                "location": location,
                "rotation": look_at_rotation(location, center),
                "focal_length": request.focal_length,
                "field_of_view": request.field_of_view,
            },
        )
        created_objects.append(result["object"])
        cameras.append(result["camera"])
    if request.set_first_active and cameras:
        await context.bridge.invoke(
            "set_active_camera",
            {"project_id": project.project_id, "camera_id": cameras[0]["camera_id"]},
        )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, created_objects)
    return success_result(
        request_id=request.request_id,
        tool_name="create_camera_orbit",
        summary=f"Created {len(cameras)} orbit cameras.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in created_objects],
        cameras=cameras,
        objects=created_objects,
        orbit_center=center,
        framed_object_ids=[item["object_id"] for item in targets],
    )


async def dolly_camera(context, request: DollyCameraRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await list_project_objects(context, project.project_id)
    camera = _object_by_id(objects, request.camera_id)
    if camera is None or camera.get("type") != "CAMERA":
        return failed_result(
            request_id=request.request_id,
            tool_name="dolly_camera",
            summary=f"Camera '{request.camera_id}' was not found.",
            errors=[f"target_not_found: Unknown camera_id: {request.camera_id}"],
        )
    if has_target_filter(request):
        targets = await resolve_spatial_targets(context, request, fallback_to_scene_meshes=False)
        center, _extent, _minimum, _maximum = center_and_extent(targets)
    else:
        targets = []
        center = [0.0, 0.0, 0.0]
    current_location = [float(value) for value in camera.get("location", [0.0, -5.0, 3.0])]
    direction = normalize(
        [current_location[axis] - center[axis] for axis in range(3)],
        default=(0.0, -1.0, 0.45),
    )
    current_distance = distance_between(current_location, center)
    next_distance = max(current_distance + request.distance_delta, request.min_distance)
    next_location = [center[axis] + (direction[axis] * next_distance) for axis in range(3)]
    result = await context.bridge.invoke(
        "set_camera",
        {
            "project_id": project.project_id,
            "camera_id": request.camera_id,
            "location": next_location,
            "rotation": look_at_rotation(next_location, center),
        },
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="dolly_camera",
        summary=f"Moved camera {request.camera_id} by {request.distance_delta:g} units.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        camera=result["camera"],
        object=result["object"],
        target_center=center,
        distance=next_distance,
        framed_object_ids=[item["object_id"] for item in targets],
    )


async def set_camera_lens_profile(context, request: SetCameraLensProfileRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    profile = dict(_LENS_PROFILES[request.profile_name])
    if request.focal_length is not None:
        profile["focal_length"] = request.focal_length
    if request.field_of_view is not None:
        profile["field_of_view"] = request.field_of_view
    result = await context.bridge.invoke(
        "set_camera",
        {"project_id": project.project_id, "camera_id": request.camera_id, **profile},
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="set_camera_lens_profile",
        summary=f"Applied {request.profile_name} lens profile to {request.camera_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        camera=result["camera"],
        object=result["object"],
        lens_profile={"profile_name": request.profile_name, **profile},
    )


async def save_shot_bookmark(context, request: SaveShotBookmarkRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids: list[str] = []
    if has_target_filter(request):
        target_ids = await resolve_target_ids(
            context,
            project_id=project.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
        )
    shot_id = new_id("shot")
    shot = {
        "shot_id": shot_id,
        "name": request.name,
        "camera_id": request.camera_id,
        "target_ids": target_ids,
        "shot_type": request.shot_type,
        "notes": request.notes,
    }
    sync_named_entity(context, project.project_id, shot_id, "shot", request.name, shot)
    return success_result(
        request_id=request.request_id,
        tool_name="save_shot_bookmark",
        summary=f"Saved shot bookmark '{request.name}'.",
        project_id=project.project_id,
        shot_id=shot_id,
        shot=shot,
    )


async def apply_shot_bookmark(context, request: ApplyShotBookmarkRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    record = context.entities.get(request.shot_id)
    if record is None or record.project_id != project.project_id or record.entity_type != "shot":
        return failed_result(
            request_id=request.request_id,
            tool_name="apply_shot_bookmark",
            summary=f"Shot bookmark '{request.shot_id}' was not found.",
            errors=[f"target_not_found: Unknown shot_id: {request.shot_id}"],
        )
    shot = json_loads(record.spec_json)
    active_camera_id = None
    if request.set_active:
        result = await context.bridge.invoke(
            "set_active_camera",
            {"project_id": project.project_id, "camera_id": shot["camera_id"]},
        )
        active_camera_id = result["active_camera_id"]
        context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="apply_shot_bookmark",
        summary=f"Applied shot bookmark '{record.name}'.",
        project_id=project.project_id,
        modified_object_ids=[shot["camera_id"]] if request.set_active else [],
        active_camera_id=active_camera_id,
        shot=shot,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("list_cameras", "List camera objects in the active project.", CameraQueryRequest, list_cameras, True),
        ("create_shot_camera", "Create a camera planned from target bounds, shot size, and angle.", CreateShotCameraRequest, create_shot_camera, False),
        ("frame_camera_to_targets", "Reposition a camera to frame resolved target objects.", FrameCameraToTargetsRequest, frame_camera_to_targets, False),
        ("create_camera_orbit", "Create an orbit of cameras around target bounds.", CreateCameraOrbitRequest, create_camera_orbit, False),
        ("dolly_camera", "Move a camera toward or away from a target center.", DollyCameraRequest, dolly_camera, False),
        ("set_camera_lens_profile", "Apply a named or overridden lens profile to a camera.", SetCameraLensProfileRequest, set_camera_lens_profile, False),
        ("save_shot_bookmark", "Persist a reusable camera shot bookmark.", SaveShotBookmarkRequest, save_shot_bookmark, False),
        ("apply_shot_bookmark", "Activate a saved shot bookmark camera.", ApplyShotBookmarkRequest, apply_shot_bookmark, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="camera",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
