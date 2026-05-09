from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.helpers import require_project, sync_entities

ModifierType = Literal[
    "SUBSURF",
    "BEVEL",
    "SOLIDIFY",
    "MIRROR",
    "ARRAY",
    "BOOLEAN",
    "DECIMATE",
    "REMESH",
    "SMOOTH",
    "DISPLACE",
    "EDGE_SPLIT",
    "TRIANGULATE",
    "WELD",
    "WEIGHTED_NORMAL",
    "SKIN",
    "NODES",
    "ARMATURE",
]


class AddModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_type: ModifierType
    name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class RemoveModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str


class SetModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ApplyModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str


class ListModifiersRequest(CommonToolRequest):
    project_id: str
    target_id: str


class AddBevelModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Bevel"
    width: float = Field(default=0.05, ge=0.0)
    segments: int = Field(default=1, ge=1, le=64)
    profile: float = Field(default=0.5, ge=0.0, le=1.0)
    harden_normals: bool = False


class AddMirrorModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Mirror"
    use_x: bool = True
    use_y: bool = False
    use_z: bool = False
    use_clip: bool = True
    bisect_x: bool = False
    bisect_y: bool = False
    bisect_z: bool = False


class AddArrayModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Array"
    count: int = Field(default=2, ge=1, le=10_000)
    relative_offset: tuple[float, float, float] = (1.0, 0.0, 0.0)
    use_constant_offset: bool = False
    constant_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    use_merge_vertices: bool = False
    merge_threshold: float = Field(default=0.01, ge=0.0)


class AddSolidifyModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Solidify"
    thickness: float = Field(default=0.1, ge=0.0)
    offset: float = Field(default=0.0, ge=-1.0, le=1.0)
    use_even_offset: bool = True
    use_quality_normals: bool = False


class AddSubdivisionModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Subdivision"
    levels: int = Field(default=1, ge=0, le=6)
    render_levels: int = Field(default=1, ge=0, le=6)
    subdivision_type: Literal["CATMULL_CLARK", "SIMPLE"] = "CATMULL_CLARK"


class AddTriangulateModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Triangulate"
    quad_method: Literal[
        "BEAUTY", "FIXED", "FIXED_ALTERNATE", "SHORTEST_DIAGONAL", "LONGEST_DIAGONAL"
    ] = "BEAUTY"
    ngon_method: Literal["BEAUTY", "CLIP"] = "BEAUTY"
    min_vertices: int = Field(default=4, ge=4)


class AddWeldModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Weld"
    merge_threshold: float = Field(default=0.001, ge=0.0)
    mode: Literal["CONNECTED", "ALL"] = "CONNECTED"


class AddRemeshModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Remesh"
    mode: Literal["BLOCKS", "SMOOTH", "SHARP", "VOXEL"] = "SMOOTH"
    octree_depth: int = Field(default=4, ge=1, le=12)
    scale: float = Field(default=0.9, gt=0.0, le=1.0)
    voxel_size: float = Field(default=0.1, gt=0.0)
    use_remove_disconnected: bool = True


class AddDisplaceModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Displace"
    strength: float = Field(default=0.1, ge=-100.0, le=100.0)
    mid_level: float = Field(default=0.5, ge=0.0, le=1.0)
    direction: Literal["NORMAL", "X", "Y", "Z", "RGB_TO_XYZ"] = "NORMAL"


class AddWeightedNormalModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_name: str = "Weighted Normal"
    keep_sharp: bool = True
    weight: int = Field(default=50, ge=1, le=100)
    mode: Literal["FACE_AREA", "CORNER_ANGLE", "FACE_AREA_WITH_ANGLE"] = "FACE_AREA_WITH_ANGLE"
    thresh: float = Field(default=0.01, ge=0.0)


class ApplyBooleanRequest(CommonToolRequest):
    project_id: str
    target_id: str
    operand_id: str
    operation: Literal["UNION", "INTERSECT", "DIFFERENCE"] = "UNION"
    modifier_name: str = "Boolean"


class ApplyDecimateRequest(CommonToolRequest):
    project_id: str
    target_id: str
    ratio: float = Field(default=0.5, gt=0.0, le=1.0)
    modifier_name: str = "Decimate"


async def _invoke(context, command: str, payload: dict[str, Any], *, request_id: str, tool_name: str):  # type: ignore[no-untyped-def]
    try:
        return await context.bridge.invoke(command, payload)
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return failed_result(
                request_id=request_id,
                tool_name=tool_name,
                summary=exc.message,
                errors=[f"{exc.code}: {exc.message}"],
            )
        raise


async def _add_convenience_modifier(
    context,  # type: ignore[no-untyped-def]
    request: CommonToolRequest,
    *,
    tool_name: str,
    modifier_type: ModifierType,
    modifier_name: str,
    params: dict[str, Any],
):
    result = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request.request_id,
            project_id=str(request.project_id),
            target_id=request.target_id,  # type: ignore[attr-defined]
            modifier_type=modifier_type,
            name=modifier_name,
            params=params,
        ),
    )
    payload = result.model_dump()
    payload["tool_name"] = tool_name
    if payload["status"] == "success":
        payload["summary"] = (
            f"Added non-destructive {modifier_type} modifier '{payload.get('modifier_name', modifier_name)}'."
        )
    return type(result).model_validate(payload)


async def add_modifier(context, request: AddModifierRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "add_modifier",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "modifier_type": request.modifier_type,
            "name": request.name,
            "params": request.params,
        },
        request_id=request.request_id,
        tool_name="add_modifier",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return success_result(
        request_id=request.request_id,
        tool_name="add_modifier",
        summary=f"Added {request.modifier_type} modifier to {request.target_id}.",
        project_id=project.project_id,
        modifier_name=result.get("modifier_name", request.name or request.modifier_type),
        modifiers=result.get("modifiers", []),
        objects=result.get("objects", []),
    )


async def add_bevel_modifier(context, request: AddBevelModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_bevel_modifier",
        modifier_type="BEVEL",
        modifier_name=request.modifier_name,
        params={
            "width": request.width,
            "segments": request.segments,
            "profile": request.profile,
            "harden_normals": request.harden_normals,
        },
    )


async def add_mirror_modifier(context, request: AddMirrorModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_mirror_modifier",
        modifier_type="MIRROR",
        modifier_name=request.modifier_name,
        params={
            "use_axis": [request.use_x, request.use_y, request.use_z],
            "use_clip": request.use_clip,
            "use_bisect_axis": [request.bisect_x, request.bisect_y, request.bisect_z],
        },
    )


async def add_array_modifier(context, request: AddArrayModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_array_modifier",
        modifier_type="ARRAY",
        modifier_name=request.modifier_name,
        params={
            "count": request.count,
            "relative_offset_displace": list(request.relative_offset),
            "use_constant_offset": request.use_constant_offset,
            "constant_offset_displace": list(request.constant_offset),
            "use_merge_vertices": request.use_merge_vertices,
            "merge_threshold": request.merge_threshold,
        },
    )


async def add_solidify_modifier(context, request: AddSolidifyModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_solidify_modifier",
        modifier_type="SOLIDIFY",
        modifier_name=request.modifier_name,
        params={
            "thickness": request.thickness,
            "offset": request.offset,
            "use_even_offset": request.use_even_offset,
            "use_quality_normals": request.use_quality_normals,
        },
    )


async def add_subdivision_modifier(context, request: AddSubdivisionModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_subdivision_modifier",
        modifier_type="SUBSURF",
        modifier_name=request.modifier_name,
        params={
            "levels": request.levels,
            "render_levels": request.render_levels,
            "subdivision_type": request.subdivision_type,
        },
    )


async def add_triangulate_modifier(context, request: AddTriangulateModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_triangulate_modifier",
        modifier_type="TRIANGULATE",
        modifier_name=request.modifier_name,
        params={
            "quad_method": request.quad_method,
            "ngon_method": request.ngon_method,
            "min_vertices": request.min_vertices,
        },
    )


async def add_weld_modifier(context, request: AddWeldModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_weld_modifier",
        modifier_type="WELD",
        modifier_name=request.modifier_name,
        params={"merge_threshold": request.merge_threshold, "mode": request.mode},
    )


async def add_remesh_modifier(context, request: AddRemeshModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_remesh_modifier",
        modifier_type="REMESH",
        modifier_name=request.modifier_name,
        params={
            "mode": request.mode,
            "octree_depth": request.octree_depth,
            "scale": request.scale,
            "voxel_size": request.voxel_size,
            "use_remove_disconnected": request.use_remove_disconnected,
        },
    )


async def add_displace_modifier(context, request: AddDisplaceModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_displace_modifier",
        modifier_type="DISPLACE",
        modifier_name=request.modifier_name,
        params={
            "strength": request.strength,
            "mid_level": request.mid_level,
            "direction": request.direction,
        },
    )


async def add_weighted_normal_modifier(context, request: AddWeightedNormalModifierRequest):  # type: ignore[no-untyped-def]
    return await _add_convenience_modifier(
        context,
        request,
        tool_name="add_weighted_normal_modifier",
        modifier_type="WEIGHTED_NORMAL",
        modifier_name=request.modifier_name,
        params={
            "keep_sharp": request.keep_sharp,
            "weight": request.weight,
            "mode": request.mode,
            "thresh": request.thresh,
        },
    )


async def remove_modifier(context, request: RemoveModifierRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "remove_modifier",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "modifier_name": request.modifier_name,
        },
        request_id=request.request_id,
        tool_name="remove_modifier",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return success_result(
        request_id=request.request_id,
        tool_name="remove_modifier",
        summary=f"Removed modifier '{request.modifier_name}' from {request.target_id}.",
        project_id=project.project_id,
        modifiers=result.get("modifiers", []),
        objects=result.get("objects", []),
    )


async def set_modifier(context, request: SetModifierRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "set_modifier",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "modifier_name": request.modifier_name,
            "params": request.params,
        },
        request_id=request.request_id,
        tool_name="set_modifier",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return success_result(
        request_id=request.request_id,
        tool_name="set_modifier",
        summary=f"Updated modifier '{request.modifier_name}' on {request.target_id}.",
        project_id=project.project_id,
        modifiers=result.get("modifiers", []),
        objects=result.get("objects", []),
    )


async def apply_modifier(context, request: ApplyModifierRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "apply_modifier",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "modifier_name": request.modifier_name,
        },
        request_id=request.request_id,
        tool_name="apply_modifier",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return success_result(
        request_id=request.request_id,
        tool_name="apply_modifier",
        summary=f"Applied modifier '{request.modifier_name}' to {request.target_id}.",
        project_id=project.project_id,
        modifiers=result.get("modifiers", []),
        objects=result.get("objects", []),
    )


async def list_modifiers(context, request: ListModifiersRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await _invoke(
        context,
        "list_modifiers",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
        },
        request_id=request.request_id,
        tool_name="list_modifiers",
    )
    if isinstance(result, CommonToolResult):
        return result
    return success_result(
        request_id=request.request_id,
        tool_name="list_modifiers",
        summary=f"Listed modifiers for {request.target_id}.",
        project_id=request.project_id,
        modifiers=result.get("modifiers", []),
    )


async def apply_boolean(context, request: ApplyBooleanRequest):  # type: ignore[no-untyped-def]
    added = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.target_id,
            modifier_type="BOOLEAN",
            name=request.modifier_name,
            params={"operation": request.operation, "operand_id": request.operand_id},
        ),
    )
    if getattr(added, "status", "failed") != "success":
        result = added.model_dump()
        result["tool_name"] = "apply_boolean"
        return type(added).model_validate(result)
    applied = await apply_modifier(
        context,
        ApplyModifierRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.target_id,
            modifier_name=request.modifier_name,
        ),
    )
    result = applied.model_dump()
    result["tool_name"] = "apply_boolean"
    if result["status"] == "success":
        result["summary"] = f"Applied {request.operation} boolean against {request.operand_id}."
        result["operand_id"] = request.operand_id
        result["operation"] = request.operation
    return type(applied).model_validate(result)


async def apply_decimate(context, request: ApplyDecimateRequest):  # type: ignore[no-untyped-def]
    added = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.target_id,
            modifier_type="DECIMATE",
            name=request.modifier_name,
            params={"ratio": request.ratio},
        ),
    )
    if getattr(added, "status", "failed") != "success":
        result = added.model_dump()
        result["tool_name"] = "apply_decimate"
        return type(added).model_validate(result)
    applied = await apply_modifier(
        context,
        ApplyModifierRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.target_id,
            modifier_name=request.modifier_name,
        ),
    )
    result = applied.model_dump()
    result["tool_name"] = "apply_decimate"
    if result["status"] == "success":
        result["summary"] = f"Applied decimate modifier with ratio {request.ratio}."
        result["ratio"] = request.ratio
    return type(applied).model_validate(result)


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for name, description, handler, model, read_only in (
        (
            "add_modifier",
            "Add a Blender modifier to a mesh object.",
            add_modifier,
            AddModifierRequest,
            False,
        ),
        (
            "add_bevel_modifier",
            "Non-destructively add a bevel modifier with typed width and segment controls.",
            add_bevel_modifier,
            AddBevelModifierRequest,
            False,
        ),
        (
            "add_mirror_modifier",
            "Non-destructively add a mirror modifier with typed axis controls.",
            add_mirror_modifier,
            AddMirrorModifierRequest,
            False,
        ),
        (
            "add_array_modifier",
            "Non-destructively add an array modifier with typed count and offset controls.",
            add_array_modifier,
            AddArrayModifierRequest,
            False,
        ),
        (
            "add_solidify_modifier",
            "Non-destructively add a solidify modifier with typed thickness controls.",
            add_solidify_modifier,
            AddSolidifyModifierRequest,
            False,
        ),
        (
            "add_subdivision_modifier",
            "Non-destructively add a subdivision surface modifier with typed level controls.",
            add_subdivision_modifier,
            AddSubdivisionModifierRequest,
            False,
        ),
        (
            "add_triangulate_modifier",
            "Non-destructively add a triangulate modifier with typed method controls.",
            add_triangulate_modifier,
            AddTriangulateModifierRequest,
            False,
        ),
        (
            "add_weld_modifier",
            "Non-destructively add a weld modifier with typed merge controls.",
            add_weld_modifier,
            AddWeldModifierRequest,
            False,
        ),
        (
            "add_remesh_modifier",
            "Non-destructively add a remesh modifier with typed mode and resolution controls.",
            add_remesh_modifier,
            AddRemeshModifierRequest,
            False,
        ),
        (
            "add_displace_modifier",
            "Non-destructively add a displace modifier with typed strength controls.",
            add_displace_modifier,
            AddDisplaceModifierRequest,
            False,
        ),
        (
            "add_weighted_normal_modifier",
            "Non-destructively add a weighted normal modifier with typed normal weighting controls.",
            add_weighted_normal_modifier,
            AddWeightedNormalModifierRequest,
            False,
        ),
        (
            "set_modifier",
            "Update modifier parameters on a mesh object by name.",
            set_modifier,
            SetModifierRequest,
            False,
        ),
        (
            "remove_modifier",
            "Remove a modifier from a mesh object by name.",
            remove_modifier,
            RemoveModifierRequest,
            False,
        ),
        (
            "apply_modifier",
            "Apply a modifier to a mesh object, baking the effect into geometry.",
            apply_modifier,
            ApplyModifierRequest,
            False,
        ),
        (
            "list_modifiers",
            "List all modifiers currently on a mesh object.",
            list_modifiers,
            ListModifiersRequest,
            True,
        ),
        (
            "apply_boolean",
            "Apply a boolean modifier against another object.",
            apply_boolean,
            ApplyBooleanRequest,
            False,
        ),
        (
            "apply_decimate",
            "Apply a decimate modifier with the requested ratio.",
            apply_decimate,
            ApplyDecimateRequest,
            False,
        ),
    ):
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="modifiers",
                input_model=model,
                handler=handler,
                read_only=read_only,
            )
        )
