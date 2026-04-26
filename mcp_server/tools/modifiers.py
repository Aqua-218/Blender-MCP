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
    "SKIN",
    "NODES",
    "ARMATURE",
]


class AddModifierRequest(CommonToolRequest):
    project_id: str
    target_id: str
    modifier_type: ModifierType
    name: str | None = None
    params: dict[str, Any] = {}


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
