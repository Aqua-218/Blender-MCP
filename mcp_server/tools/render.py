from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from presets.lighting import LIGHTING_PRESETS
from presets.rendering import RENDER_PRESETS
from pydantic import BaseModel, Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.serialization import json_loads
from mcp_server.tools.helpers import (
    project_paths_for_record,
    require_project,
    resolve_target_ids,
    sync_entities,
)
from mcp_server.utils import slugify
from mcp_server.workspace import WorkspaceViolationError


class CreateLightRequest(CommonToolRequest):
    project_id: str
    name: str
    light_type: str = "AREA"
    location: list[float] = Field(default_factory=lambda: [3.0, -3.0, 4.0])
    rotation: list[float] = Field(default_factory=lambda: [0.9, 0.0, 0.7])
    intensity: float = 1000.0
    color: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    size: float = 1.0


class SetLightRequest(CommonToolRequest):
    project_id: str
    light_id: str
    location: list[float] | None = None
    rotation: list[float] | None = None
    intensity: float | None = None
    color: list[float] | None = None
    size: float | None = None


class LightingPresetRequest(CommonToolRequest):
    project_id: str
    preset_name: str


class AutoLightSubjectRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class CreateCameraRequest(CommonToolRequest):
    project_id: str
    name: str
    location: list[float] = Field(default_factory=lambda: [0.0, -5.0, 3.0])
    rotation: list[float] = Field(default_factory=lambda: [1.1, 0.0, 0.0])
    focal_length: float = 50.0
    field_of_view: float = 0.9


class CreateMultiviewCamerasRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    count: int = Field(default=4, ge=2, le=12)
    radius: float = Field(default=5.0, gt=0)
    height: float = Field(default=2.5)
    prefix: str = "View"
    focal_length: float = 50.0
    field_of_view: float = 0.9


class SetCameraRequest(CommonToolRequest):
    project_id: str
    camera_id: str
    location: list[float] | None = None
    rotation: list[float] | None = None
    focal_length: float | None = None
    field_of_view: float | None = None


class FrameObjectRequest(CommonToolRequest):
    project_id: str
    camera_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class SetActiveCameraRequest(CommonToolRequest):
    project_id: str
    camera_id: str


class RenderSettingsRequest(CommonToolRequest):
    project_id: str
    preset_name: str | None = None
    engine: str | None = None
    resolution_x: int | None = None
    resolution_y: int | None = None
    samples: int | None = None
    transparent_background: bool | None = None


class RenderOutputRequest(CommonToolRequest):
    project_id: str
    output_path: str | None = None
    camera_id: str | None = None


class RenderProfileRequest(CommonToolRequest):
    project_id: str
    preset_name: str


class RenderMultiviewRequest(CommonToolRequest):
    project_id: str
    camera_ids: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    preset_name: str = "standard"


class RenderBatchRequest(CommonToolRequest):
    project_id: str
    camera_ids: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    preset_name: str = "standard"
    output_names: list[str] = Field(default_factory=list)


def _project_scoped_output_path(render_dir: Path, raw_output_path: Path) -> Path:
    resolved_root = render_dir.resolve()
    relative_output_path = raw_output_path
    artifact_root_name = render_dir.parent.name
    if not raw_output_path.is_absolute() and raw_output_path.parts[:1] == (artifact_root_name,):
        relative_output_path = Path(*raw_output_path.parts[1:]) if len(raw_output_path.parts) > 1 else Path()
    candidate = raw_output_path.resolve(strict=False) if raw_output_path.is_absolute() else (render_dir / relative_output_path).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise WorkspaceViolationError("Render output path must stay under the project's render directory.") from exc
    return candidate


async def create_light(context, request: CreateLightRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("create_light", request.model_dump())
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="create_light",
        summary=f"Created light {request.name}.",
        project_id=project.project_id,
        created_object_ids=[result["object"]["object_id"]],
        light=result["light"],
        object=result["object"],
    )


async def set_light(context, request: SetLightRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("set_light", request.model_dump(exclude_none=True))
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="set_light",
        summary=f"Updated light {request.light_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.light_id],
        light=result["light"],
    )


async def apply_lighting_preset(context, request: LightingPresetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    lights = LIGHTING_PRESETS.get(request.preset_name)
    if lights is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="apply_lighting_preset",
            summary="Lighting preset validation failed.",
            errors=[f"validation_error: unknown lighting preset '{request.preset_name}'"],
        )
    result = await context.bridge.invoke(
        "apply_lighting_preset",
        {"project_id": project.project_id, "preset_name": request.preset_name, "lights": lights},
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="apply_lighting_preset",
        summary=f"Applied lighting preset {request.preset_name}.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in result["objects"]],
        objects=result["objects"],
    )


async def auto_light_subject(context, request: AutoLightSubjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="auto_light_subject",
            summary="auto_light_subject requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await context.bridge.invoke(
        "auto_light_subject",
        {"project_id": project.project_id, "target_ids": target_ids},
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    return success_result(
        request_id=request.request_id,
        tool_name="auto_light_subject",
        summary="Created automatic subject lighting.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in result["objects"]],
        objects=result["objects"],
    )


async def create_camera(context, request: CreateCameraRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("create_camera", request.model_dump())
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="create_camera",
        summary=f"Created camera {request.name}.",
        project_id=project.project_id,
        created_object_ids=[result["object"]["object_id"]],
        camera=result["camera"],
    )


async def create_multiview_cameras(context, request: CreateMultiviewCamerasRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    center = [0.0, 0.0, 0.0]
    if request.target_id is not None:
        target = context.entities.get(request.target_id)
        if target is None:
            return failed_result(
                request_id=request.request_id,
                tool_name="create_multiview_cameras",
                summary=f"Target '{request.target_id}' was not found.",
                errors=[f"target_not_found: target '{request.target_id}' does not exist"],
            )
        center = list(json_loads(target.spec_json).get("location", center))
    objects = []
    cameras = []
    created_ids = []
    for index in range(request.count):
        angle = (2.0 * math.pi * index) / request.count
        location = [
            center[0] + (request.radius * math.cos(angle)),
            center[1] + (request.radius * math.sin(angle)),
            center[2] + request.height,
        ]
        rotation = [1.1, 0.0, angle + math.pi / 2.0]
        result = await context.bridge.invoke(
            "create_camera",
            {
                "project_id": project.project_id,
                "name": f"{request.prefix}_{index + 1:02d}",
                "location": location,
                "rotation": rotation,
                "focal_length": request.focal_length,
                "field_of_view": request.field_of_view,
            },
        )
        objects.append(result["object"])
        cameras.append(result["camera"])
        created_ids.append(result["object"]["object_id"])
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="create_multiview_cameras",
        summary=f"Created {len(cameras)} multiview cameras.",
        project_id=project.project_id,
        created_object_ids=created_ids,
        cameras=cameras,
        objects=objects,
    )


async def set_camera(context, request: SetCameraRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("set_camera", request.model_dump(exclude_none=True))
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="set_camera",
        summary=f"Updated camera {request.camera_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        camera=result["camera"],
    )


async def frame_object(context, request: FrameObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="frame_object",
            summary="frame_object requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    result = await context.bridge.invoke(
        "frame_object",
        {"project_id": project.project_id, "camera_id": request.camera_id, "target_ids": target_ids},
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, [result["object"]])
    return success_result(
        request_id=request.request_id,
        tool_name="frame_object",
        summary=f"Framed {len(target_ids)} objects with camera {request.camera_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        camera=result["camera"],
    )


async def set_active_camera(context, request: SetActiveCameraRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("set_active_camera", request.model_dump())
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="set_active_camera",
        summary=f"Set active camera to {request.camera_id}.",
        project_id=project.project_id,
        modified_object_ids=[request.camera_id],
        active_camera_id=result["active_camera_id"],
    )


async def set_render_settings(context, request: RenderSettingsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    payload = {"project_id": project.project_id}
    if request.preset_name is not None:
        preset = RENDER_PRESETS.get(request.preset_name)
        if preset is None:
            return failed_result(
                request_id=request.request_id,
                tool_name="set_render_settings",
                summary="Render preset validation failed.",
                errors=[f"validation_error: unknown render preset '{request.preset_name}'"],
            )
        payload.update(preset)
    for key in ("engine", "resolution_x", "resolution_y", "samples", "transparent_background"):
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    result = await context.bridge.invoke("set_render_settings", payload)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="set_render_settings",
        summary="Updated render settings.",
        project_id=project.project_id,
        render_settings=result["render_settings"],
    )


async def get_render_settings(context, request: RenderSettingsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke("get_render_settings", {"project_id": project.project_id}, read_only=True)
    return success_result(
        request_id=request.request_id,
        tool_name="get_render_settings",
        summary="Retrieved render settings.",
        project_id=project.project_id,
        render_settings=result["render_settings"],
    )


def _render_settings_for_preset(tool_name: str, preset_name: str) -> dict[str, Any]:
    render_settings = RENDER_PRESETS.get(preset_name)
    if render_settings is None:
        raise ValueError(f"{tool_name}: unknown render preset '{preset_name}'")
    return render_settings


def _default_camera_ids(context, project_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    return [record.entity_id for record in context.entities.list_by_type(project_id, "camera")]


async def _render_once(  # type: ignore[no-untyped-def]
    context,
    *,
    request_id: str,
    project_id: str,
    project_name: str,
    active_scene_name: str,
    output_path: Path,
    camera_id: str | None,
    preset_name: str,
):
    result = await context.bridge.invoke(
        "render_preview",
        {
            "project_id": project_id,
            "output_path": str(output_path),
            "camera_id": camera_id,
            **_render_settings_for_preset("render_preview", preset_name),
        },
    )
    returned_image_path = context.workspace.canonicalize_output_path(result["image_path"], allowed_extensions=[".png"])
    if returned_image_path != output_path:
        return failed_result(
            request_id=request_id,
            tool_name="render_preview",
            summary="Controller returned an unexpected render output path.",
            errors=["validation_error: controller returned an unexpected render output path"],
        )
    context.projects.mark_dirty(project_id, active_scene_name)
    return returned_image_path, result


async def _render(context, request: RenderOutputRequest, tool_name: str, preset_name: str):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    explicit_output_path: str | Path | None = request.output_path
    if request.output_path:
        raw_output_path = Path(request.output_path)
        explicit_output_path = _project_scoped_output_path(project_paths.render_dir, raw_output_path)
    output_path = (
        context.workspace.canonicalize_output_path(explicit_output_path, allowed_extensions=[".png"])
        if explicit_output_path is not None
        else context.workspace.canonicalize_output_path(
            project_paths.render_dir / f"{slugify(request.request_id)}.png",
            allowed_extensions=[".png"],
        )
    )
    if preset_name not in RENDER_PRESETS:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="Render preset validation failed.",
            errors=[f"validation_error: unknown render preset '{preset_name}'"],
        )
    rendered = await _render_once(
        context,
        request_id=request.request_id,
        project_id=project.project_id,
        project_name=project.name,
        active_scene_name=project.active_scene_name,
        output_path=output_path,
        camera_id=request.camera_id,
        preset_name=preset_name,
    )
    if not isinstance(rendered, tuple):
        result = rendered.model_dump()
        result["request_id"] = request.request_id
        result["tool_name"] = tool_name
        return type(rendered).model_validate(result)
    returned_image_path, result = rendered
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Rendered {preset_name} image.",
        project_id=project.project_id,
        image_paths=[str(returned_image_path)],
        active_camera_id=result.get("active_camera_id"),
        render={**result, "image_path": str(returned_image_path)},
    )


async def set_render_profile(context, request: RenderProfileRequest):  # type: ignore[no-untyped-def]
    return await set_render_settings(
        context,
        RenderSettingsRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            preset_name=request.preset_name,
        ),
    )


async def _render_many(context, request, tool_name: str):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    if request.preset_name not in RENDER_PRESETS:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="Render preset validation failed.",
            errors=[f"validation_error: unknown render preset '{request.preset_name}'"],
        )
    render_settings = _render_settings_for_preset(tool_name, request.preset_name)
    camera_ids = list(request.camera_ids or _default_camera_ids(context, project.project_id))
    if not camera_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="No cameras were available for batch rendering.",
            errors=["validation_error: at least one camera is required"],
        )
    output_dir = (
        _project_scoped_output_path(project_paths.render_dir, Path(request.output_dir))
        if request.output_dir is not None
        else (project_paths.render_dir / slugify(request.request_id)).resolve(strict=False)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(request, "output_names") and request.output_names and len(request.output_names) != len(camera_ids):
        return failed_result(
            request_id=request.request_id,
            tool_name=tool_name,
            summary="Batch output_names did not match camera_ids length.",
            errors=["validation_error: output_names must match camera_ids length when provided"],
        )
    renders: list[dict[str, Any]] = []
    image_paths: list[str] = []
    for index, camera_id in enumerate(camera_ids, start=1):
        output_name = (
            request.output_names[index - 1]
            if hasattr(request, "output_names") and request.output_names
            else f"view-{index:02d}.png"
        )
        output_path = context.workspace.canonicalize_output_path(output_dir / output_name, allowed_extensions=[".png"])
        rendered = await _render_once(
            context,
            request_id=request.request_id,
            project_id=project.project_id,
            project_name=project.name,
            active_scene_name=project.active_scene_name,
            output_path=output_path,
            camera_id=camera_id,
            preset_name=request.preset_name,
        )
        if not isinstance(rendered, tuple):
            result = rendered.model_dump()
            result["request_id"] = request.request_id
            result["tool_name"] = tool_name
            return type(rendered).model_validate(result)
        returned_image_path, result = rendered
        image_paths.append(str(returned_image_path))
        renders.append(
            {
                "camera_id": camera_id,
                "image_path": str(returned_image_path),
                "render_settings": {**render_settings},
                "active_camera_id": result.get("active_camera_id"),
            }
        )
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=f"Rendered {len(image_paths)} views using the {request.preset_name} preset.",
        project_id=project.project_id,
        image_paths=image_paths,
        renders=renders,
        output_dir=str(output_dir),
        camera_ids=camera_ids,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_light", "Create a light object.", CreateLightRequest, create_light, False),
        ("set_light", "Update light properties.", SetLightRequest, set_light, False),
        ("apply_lighting_preset", "Apply a named lighting preset.", LightingPresetRequest, apply_lighting_preset, False),
        ("auto_light_subject", "Automatically light a target subject.", AutoLightSubjectRequest, auto_light_subject, False),
        ("create_camera", "Create a camera.", CreateCameraRequest, create_camera, False),
        ("create_multiview_cameras", "Create an evenly spaced ring of cameras around the target or scene origin.", CreateMultiviewCamerasRequest, create_multiview_cameras, False),
        ("set_camera", "Update camera properties.", SetCameraRequest, set_camera, False),
        ("frame_object", "Position a camera to frame the requested object.", FrameObjectRequest, frame_object, False),
        ("set_active_camera", "Set the active scene camera.", SetActiveCameraRequest, set_active_camera, False),
        ("set_render_settings", "Update render settings or apply a render preset.", RenderSettingsRequest, set_render_settings, False),
        ("set_render_profile", "Apply a named render profile.", RenderProfileRequest, set_render_profile, False),
        ("get_render_settings", "Get active render settings.", RenderSettingsRequest, get_render_settings, True),
        ("render_preview", "Render a quick preview image.", RenderOutputRequest, lambda c, r: _render(c, r, "render_preview", "preview"), False),
        ("render_thumbnail", "Render a thumbnail image.", RenderOutputRequest, lambda c, r: _render(c, r, "render_thumbnail", "thumbnail"), False),
        ("render_standard", "Render a standard-quality image.", RenderOutputRequest, lambda c, r: _render(c, r, "render_standard", "standard"), False),
        ("render_final", "Render a final-quality image.", RenderOutputRequest, lambda c, r: _render(c, r, "render_final", "final"), False),
        ("render_multiview", "Render one image per camera using a shared preset.", RenderMultiviewRequest, lambda c, r: _render_many(c, r, "render_multiview"), False),
        ("render_batch", "Render a named batch across multiple cameras.", RenderBatchRequest, lambda c, r: _render_many(c, r, "render_batch"), False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="render",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
