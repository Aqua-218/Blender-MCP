from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.helpers import require_project, resolve_target_ids, sync_entities

AxisName = Literal["x", "y", "z"]
AlignMode = Literal["min", "center", "max", "origin"]


class TransformTargetsRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    spatial_range: dict[str, list[float]] | None = None


class ResetObjectTransformsRequest(TransformTargetsRequest):
    reset_location: bool = True
    reset_rotation: bool = True
    reset_scale: bool = True


class OffsetObjectTransformsRequest(TransformTargetsRequest):
    location_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale_multiplier: tuple[float, float, float] = (1.0, 1.0, 1.0)


class MatchObjectTransformRequest(TransformTargetsRequest):
    source_id: str
    match_location: bool = True
    match_rotation: bool = True
    match_scale: bool = True


class AlignObjectsRequest(TransformTargetsRequest):
    axis: AxisName = "x"
    align_to: AlignMode = "origin"
    target_value: float | None = None


class DistributeObjectsRequest(TransformTargetsRequest):
    axis: AxisName = "x"
    spacing: float | None = None
    start_value: float | None = None


class SnapObjectsToGridRequest(TransformTargetsRequest):
    grid_size: float = Field(default=1.0, gt=0.0)
    axes: list[AxisName] = Field(default_factory=lambda: ["x", "y", "z"])


class PlaceObjectsOnGroundRequest(TransformTargetsRequest):
    ground_z: float = 0.0


class ArrangeObjectsInGridRequest(TransformTargetsRequest):
    columns: int = Field(default=4, ge=1, le=256)
    spacing: tuple[float, float, float] = (2.0, 2.0, 0.0)
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    column_axis: AxisName = "x"
    row_axis: AxisName = "y"


class MirrorObjectTransformsRequest(TransformTargetsRequest):
    axis: AxisName = "x"
    pivot: float = 0.0
    flip_scale: bool = False


def _failed(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


async def _resolve_targets(
    context,  # type: ignore[no-untyped-def]
    request: TransformTargetsRequest,
    tool_name: str,
) -> list[str] | CommonToolResult:
    try:
        return await resolve_target_ids(
            context,
            project_id=request.project_id,
            target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
            names=request.names,
            tag=request.tag,
            collection_name=request.match_collection_name,
            spatial_range=request.spatial_range,
        )
    except ValueError as exc:
        return _failed(request.request_id, tool_name, "target_not_found", str(exc))


async def _invoke_transform(
    context,  # type: ignore[no-untyped-def]
    request: TransformTargetsRequest,
    *,
    tool_name: str,
    command: str,
    payload: dict[str, Any],
    summary: str,
) -> CommonToolResult:
    project = require_project(context, request.project_id)
    target_ids = await _resolve_targets(context, request, tool_name)
    if isinstance(target_ids, CommonToolResult):
        return target_ids
    try:
        result = await context.bridge.invoke(
            command,
            {"project_id": project.project_id, "target_ids": target_ids, **payload},
        )
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return _failed(request.request_id, tool_name, exc.code, exc.message)
        raise
    objects = list(result.get("objects", []))
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    modified_object_ids = list(result.get("modified_object_ids", target_ids))
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=summary,
        project_id=project.project_id,
        modified_object_ids=modified_object_ids,
        objects=objects,
    )


async def reset_object_transforms(context, request: ResetObjectTransformsRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="reset_object_transforms",
        command="reset_object_transforms",
        payload={
            "reset_location": request.reset_location,
            "reset_rotation": request.reset_rotation,
            "reset_scale": request.reset_scale,
        },
        summary="Reset object transforms.",
    )


async def offset_object_transforms(context, request: OffsetObjectTransformsRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="offset_object_transforms",
        command="offset_object_transforms",
        payload={
            "location_offset": list(request.location_offset),
            "rotation_offset": list(request.rotation_offset),
            "scale_multiplier": list(request.scale_multiplier),
        },
        summary="Offset object transforms.",
    )


async def match_object_transform(context, request: MatchObjectTransformRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="match_object_transform",
        command="match_object_transform",
        payload={
            "source_id": request.source_id,
            "match_location": request.match_location,
            "match_rotation": request.match_rotation,
            "match_scale": request.match_scale,
        },
        summary=f"Matched transform from {request.source_id}.",
    )


async def align_objects(context, request: AlignObjectsRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="align_objects",
        command="align_objects",
        payload={
            "axis": request.axis,
            "align_to": request.align_to,
            "target_value": request.target_value,
        },
        summary=f"Aligned objects on {request.axis}.",
    )


async def distribute_objects(context, request: DistributeObjectsRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="distribute_objects",
        command="distribute_objects",
        payload={"axis": request.axis, "spacing": request.spacing, "start_value": request.start_value},
        summary=f"Distributed objects on {request.axis}.",
    )


async def snap_objects_to_grid(context, request: SnapObjectsToGridRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="snap_objects_to_grid",
        command="snap_objects_to_grid",
        payload={"grid_size": request.grid_size, "axes": request.axes},
        summary=f"Snapped objects to a {request.grid_size:g} unit grid.",
    )


async def place_objects_on_ground(context, request: PlaceObjectsOnGroundRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="place_objects_on_ground",
        command="place_objects_on_ground",
        payload={"ground_z": request.ground_z},
        summary=f"Placed objects on ground z={request.ground_z:g}.",
    )


async def arrange_objects_in_grid(context, request: ArrangeObjectsInGridRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="arrange_objects_in_grid",
        command="arrange_objects_in_grid",
        payload={
            "columns": request.columns,
            "spacing": list(request.spacing),
            "origin": list(request.origin),
            "column_axis": request.column_axis,
            "row_axis": request.row_axis,
        },
        summary=f"Arranged objects in a {request.columns}-column grid.",
    )


async def mirror_object_transforms(context, request: MirrorObjectTransformsRequest):  # type: ignore[no-untyped-def]
    return await _invoke_transform(
        context,
        request,
        tool_name="mirror_object_transforms",
        command="mirror_object_transforms",
        payload={"axis": request.axis, "pivot": request.pivot, "flip_scale": request.flip_scale},
        summary=f"Mirrored object transforms across {request.axis}={request.pivot:g}.",
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("reset_object_transforms", "Reset location, rotation, and/or scale on resolved objects.", ResetObjectTransformsRequest, reset_object_transforms, False),
        ("offset_object_transforms", "Apply additive location/rotation offsets and multiplicative scale offsets to objects.", OffsetObjectTransformsRequest, offset_object_transforms, False),
        ("match_object_transform", "Copy transform channels from one source object to resolved targets.", MatchObjectTransformRequest, match_object_transform, False),
        ("align_objects", "Align object origins or bounds to a shared axis value.", AlignObjectsRequest, align_objects, False),
        ("distribute_objects", "Distribute resolved objects evenly along one axis.", DistributeObjectsRequest, distribute_objects, False),
        ("snap_objects_to_grid", "Round object locations to a grid on selected axes.", SnapObjectsToGridRequest, snap_objects_to_grid, False),
        ("place_objects_on_ground", "Move objects so their lower bound rests on a ground plane.", PlaceObjectsOnGroundRequest, place_objects_on_ground, False),
        ("arrange_objects_in_grid", "Arrange resolved objects into a deterministic row/column grid.", ArrangeObjectsInGridRequest, arrange_objects_in_grid, False),
        ("mirror_object_transforms", "Mirror object locations across an axis-aligned pivot plane.", MirrorObjectTransformsRequest, mirror_object_transforms, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="transforms",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )