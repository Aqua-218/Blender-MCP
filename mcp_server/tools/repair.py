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
from mcp_server.tools.helpers import require_project, sync_entities
from mcp_server.tools.modifiers import ApplyDecimateRequest, apply_decimate
from mcp_server.tools.object import (
    RenameObjectRequest,
    TargetedObjectRequest,
    duplicate_object,
    rename_object,
)


class TargetMeshRequest(CommonToolRequest):
    project_id: str
    target_id: str


class RemoveDuplicateVerticesRequest(TargetMeshRequest):
    threshold: float = 0.0001


class ApplyTransformsRequest(CommonToolRequest):
    project_id: str
    target_id: str
    apply_location: bool = False
    apply_rotation: bool = False
    apply_scale: bool = True


class SetOriginRequest(CommonToolRequest):
    project_id: str
    target_id: str
    mode: Literal["geometry_center", "origin_center_of_mass", "origin_to_3d_cursor"] = "geometry_center"


class OptimizePolycountRequest(CommonToolRequest):
    project_id: str
    target_id: str
    ratio: float = Field(default=0.5, gt=0.0, le=1.0)


class GenerateLODRequest(CommonToolRequest):
    project_id: str
    target_id: str
    levels: int = Field(default=2, ge=1, le=4)
    base_ratio: float = Field(default=0.5, gt=0.0, le=1.0)


class GenerateCollisionMeshRequest(CommonToolRequest):
    project_id: str
    target_id: str
    ratio: float = Field(default=0.2, gt=0.0, le=1.0)


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


def _mutation_success(*, request, tool_name: str, summary: str, project_id: str, result: dict[str, Any]):  # type: ignore[no-untyped-def]
    objects = list(result.get("objects", []))
    return success_result(
        request_id=request.request_id,
        tool_name=tool_name,
        summary=summary,
        project_id=project_id,
        modified_object_ids=list(result.get("modified_object_ids", [])),
        objects=objects,
    )


async def remove_duplicate_vertices(context, request: RemoveDuplicateVerticesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "merge_vertices",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "threshold": request.threshold,
        },
        request_id=request.request_id,
        tool_name="remove_duplicate_vertices",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return _mutation_success(
        request=request,
        tool_name="remove_duplicate_vertices",
        summary="Removed duplicate vertices.",
        project_id=project.project_id,
        result=result,
    )


async def recalculate_normals(context, request: TargetMeshRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "recalculate_normals",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="recalculate_normals",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return _mutation_success(
        request=request,
        tool_name="recalculate_normals",
        summary="Recalculated normals.",
        project_id=project.project_id,
        result=result,
    )


async def fix_mesh(context, request: RemoveDuplicateVerticesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    dedup = await _invoke(
        context,
        "merge_vertices",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
            "threshold": request.threshold,
        },
        request_id=request.request_id,
        tool_name="fix_mesh",
    )
    if isinstance(dedup, CommonToolResult):
        return dedup
    recalc = await _invoke(
        context,
        "recalculate_normals",
        {
            "project_id": request.project_id,
            "target_id": request.target_id,
        },
        request_id=request.request_id,
        tool_name="fix_mesh",
    )
    if isinstance(recalc, CommonToolResult):
        return recalc
    objects = list(recalc.get("objects", []))
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="fix_mesh",
        summary="Applied mesh cleanup pipeline (remove duplicates + recalculate normals).",
        project_id=project.project_id,
        modified_object_ids=list(recalc.get("modified_object_ids", [])),
        objects=objects,
    )


async def apply_transforms(context, request: ApplyTransformsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "apply_transforms",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="apply_transforms",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return _mutation_success(
        request=request,
        tool_name="apply_transforms",
        summary="Applied object transforms.",
        project_id=project.project_id,
        result=result,
    )


async def set_origin(context, request: SetOriginRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke(
        context,
        "set_origin",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="set_origin",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, list(result.get("objects", [])))
    return _mutation_success(
        request=request,
        tool_name="set_origin",
        summary="Updated object origin.",
        project_id=project.project_id,
        result=result,
    )


async def optimize_polycount(context, request: OptimizePolycountRequest):  # type: ignore[no-untyped-def]
    result = await apply_decimate(
        context,
        ApplyDecimateRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.target_id,
            ratio=request.ratio,
            modifier_name="MCPOptimizePolycount",
        ),
    )
    payload = result.model_dump()
    payload["tool_name"] = "optimize_polycount"
    payload["summary"] = f"Optimized polycount with ratio {request.ratio}."
    payload["ratio"] = request.ratio
    return type(result).model_validate(payload)


async def generate_lod(context, request: GenerateLODRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    created_object_ids: list[str] = []
    lod_objects: list[dict[str, Any]] = []
    for index in range(1, request.levels + 1):
        duplicated = await duplicate_object(
            context,
            TargetedObjectRequest(
                request_id=f"{request.request_id}-dup-{index}",
                project_id=request.project_id,
                target_id=request.target_id,
            ),
        )
        duplicated_payload = duplicated.model_dump()
        if duplicated_payload["status"] != "success":
            duplicated_payload["tool_name"] = "generate_lod"
            return type(duplicated).model_validate(duplicated_payload)
        lod_id = str(duplicated_payload["created_object_ids"][0])
        await rename_object(
            context,
            RenameObjectRequest(
                request_id=f"{request.request_id}-rename-{index}",
                project_id=request.project_id,
                target_id=lod_id,
                new_name=f"LOD{index}_{lod_id}",
            ),
        )
        ratio = max(request.base_ratio ** index, 0.05)
        optimized = await optimize_polycount(
            context,
            OptimizePolycountRequest(
                request_id=f"{request.request_id}-opt-{index}",
                project_id=request.project_id,
                target_id=lod_id,
                ratio=ratio,
            ),
        )
        optimized_payload = optimized.model_dump()
        if optimized_payload["status"] != "success":
            optimized_payload["tool_name"] = "generate_lod"
            return type(optimized).model_validate(optimized_payload)
        created_object_ids.append(lod_id)
        lod_objects.extend(optimized_payload.get("objects", []))
    return success_result(
        request_id=request.request_id,
        tool_name="generate_lod",
        summary=f"Generated {len(created_object_ids)} LOD meshes.",
        project_id=request.project_id,
        created_object_ids=created_object_ids,
        objects=lod_objects,
    )


async def generate_collision_mesh(context, request: GenerateCollisionMeshRequest):  # type: ignore[no-untyped-def]
    duplicated = await duplicate_object(
        context,
        TargetedObjectRequest(
            request_id=f"{request.request_id}-dup",
            project_id=request.project_id,
            target_id=request.target_id,
        ),
    )
    duplicated_payload = duplicated.model_dump()
    if duplicated_payload["status"] != "success":
        duplicated_payload["tool_name"] = "generate_collision_mesh"
        return type(duplicated).model_validate(duplicated_payload)
    collision_id = str(duplicated_payload["created_object_ids"][0])
    await rename_object(
        context,
        RenameObjectRequest(
            request_id=f"{request.request_id}-rename",
            project_id=request.project_id,
            target_id=collision_id,
            new_name=f"COL_{collision_id}",
        ),
    )
    optimized = await optimize_polycount(
        context,
        OptimizePolycountRequest(
            request_id=f"{request.request_id}-opt",
            project_id=request.project_id,
            target_id=collision_id,
            ratio=request.ratio,
        ),
    )
    payload = optimized.model_dump()
    payload["tool_name"] = "generate_collision_mesh"
    if payload["status"] == "success":
        payload["summary"] = "Generated collision mesh proxy."
        payload["created_object_ids"] = [collision_id]
        payload["collision_object_id"] = collision_id
    return type(optimized).model_validate(payload)


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("fix_mesh", "Apply common mesh cleanup operations.", RemoveDuplicateVerticesRequest, fix_mesh, False),
        ("remove_duplicate_vertices", "Remove duplicate/near-duplicate mesh vertices.", RemoveDuplicateVerticesRequest, remove_duplicate_vertices, False),
        ("recalculate_normals", "Recalculate mesh normals consistently.", TargetMeshRequest, recalculate_normals, False),
        ("apply_transforms", "Apply selected object transforms into object data.", ApplyTransformsRequest, apply_transforms, False),
        ("set_origin", "Set object origin mode.", SetOriginRequest, set_origin, False),
        ("optimize_polycount", "Reduce polygon count using a decimate helper.", OptimizePolycountRequest, optimize_polycount, False),
        ("generate_lod", "Create lower-detail duplicates of a mesh target.", GenerateLODRequest, generate_lod, False),
        ("generate_collision_mesh", "Create a simplified collision proxy mesh from a target.", GenerateCollisionMeshRequest, generate_collision_mesh, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="repair",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )