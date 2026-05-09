from __future__ import annotations

from typing import Any

from presets.materials import MATERIAL_PRESETS
from pydantic import Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    partial_success_result,
    success_result,
)
from mcp_server.tools.helpers import (
    require_project,
    resolve_target_ids,
    sync_entities,
    sync_named_entity,
)


class CreateMaterialRequest(CommonToolRequest):
    project_id: str
    name: str
    preset_name: str | None = None


class ApplyMaterialRequest(CommonToolRequest):
    project_id: str
    material_id: str
    target_ids: list[str] = Field(default_factory=list)
    target_id: str | None = None
    names: list[str] = Field(default_factory=list)


class SetMaterialPropertyRequest(CommonToolRequest):
    project_id: str
    material_id: str
    property_name: str
    value: Any


class CreatePBRMaterialRequest(CommonToolRequest):
    project_id: str
    name: str
    base_color: list[float] = Field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    roughness: float = 0.5
    metallic: float = 0.0
    specular: float | None = None
    alpha: float | None = None
    emission_color: list[float] | None = None
    emission_strength: float | None = None


class AddMaterialNodeRequest(CommonToolRequest):
    project_id: str
    material_id: str
    node_type: str
    node_name: str | None = None
    location: tuple[float, float] = (0.0, 0.0)
    params: dict[str, Any] = Field(default_factory=dict)


class SetMaterialNodeParamRequest(CommonToolRequest):
    project_id: str
    material_id: str
    node_id: str
    param_name: str
    value: Any


class ConnectMaterialNodesRequest(CommonToolRequest):
    project_id: str
    material_id: str
    from_node_id: str
    from_socket: str
    to_node_id: str
    to_socket: str


class ListMaterialNodesRequest(CommonToolRequest):
    project_id: str
    material_id: str


def _material_failed_result(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


async def _invoke_material_command(
    context,  # type: ignore[no-untyped-def]
    command: str,
    payload: dict[str, Any],
    *,
    request_id: str,
    tool_name: str,
    read_only: bool = False,
) -> dict[str, Any] | CommonToolResult:
    try:
        return await context.bridge.invoke(command, payload, read_only=read_only)
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return _material_failed_result(request_id, tool_name, exc.code, exc.message)
        raise


async def create_material(context, request: CreateMaterialRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    if request.preset_name is not None and request.preset_name not in MATERIAL_PRESETS:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_material",
            summary="Material preset validation failed.",
            errors=[f"validation_error: unknown material preset '{request.preset_name}'"],
        )
    preset = MATERIAL_PRESETS.get(request.preset_name, {}) if request.preset_name else {}
    result = await context.bridge.invoke(
        "create_material",
        {
            "project_id": project.project_id,
            "name": request.name,
            "properties": preset,
        },
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_material",
        summary=f"Created material {request.name}.",
        project_id=project.project_id,
        material=result["material"],
    )


async def apply_material(context, request: ApplyMaterialRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
    )
    result = await context.bridge.invoke(
        "apply_material",
        {
            "project_id": project.project_id,
            "material_id": request.material_id,
            "target_ids": target_ids,
        },
    )
    modified_object_ids = [item["object_id"] for item in result["objects"]]
    if not modified_object_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="apply_material",
            summary="No requested targets support material assignment.",
            errors=["validation_error: no requested targets support material assignment"],
        )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, result["objects"])
    warnings: list[str] | None = None
    if len(modified_object_ids) != len(target_ids):
        skipped_count = len(target_ids) - len(modified_object_ids)
        warnings = [f"Skipped {skipped_count} targets that do not support material assignment."]
    result_factory = partial_success_result if warnings else success_result
    return result_factory(
        request_id=request.request_id,
        tool_name="apply_material",
        summary=f"Applied material to {len(modified_object_ids)} objects.",
        project_id=project.project_id,
        modified_object_ids=modified_object_ids,
        objects=result["objects"],
        warnings=warnings,
    )


async def set_material_property(context, request: SetMaterialPropertyRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke(
        "set_material_property",
        request.model_dump(),
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="set_material_property",
        summary=f"Updated material property {request.property_name}.",
        project_id=project.project_id,
        material=result["material"],
    )


async def create_pbr_material(context, request: CreatePBRMaterialRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await context.bridge.invoke(
        "create_pbr_material",
        request.model_dump(exclude_none=True),
    )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_pbr_material",
        summary=f"Created PBR material {request.name}.",
        project_id=project.project_id,
        material=result["material"],
    )


async def add_material_node(context, request: AddMaterialNodeRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke_material_command(
        context,
        "add_material_node",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="add_material_node",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="add_material_node",
        summary=f"Added material node '{result['node']['node_name']}'.",
        project_id=project.project_id,
        material=result["material"],
        node=result["node"],
        nodes=result.get("nodes", []),
        links=result.get("links", []),
    )


async def set_material_node_param(context, request: SetMaterialNodeParamRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke_material_command(
        context,
        "set_material_node_param",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="set_material_node_param",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="set_material_node_param",
        summary=f"Updated material node parameter '{request.param_name}'.",
        project_id=project.project_id,
        material=result["material"],
        node=result["node"],
        nodes=result.get("nodes", []),
        links=result.get("links", []),
    )


async def connect_material_nodes(context, request: ConnectMaterialNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    result = await _invoke_material_command(
        context,
        "connect_material_nodes",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="connect_material_nodes",
    )
    if isinstance(result, CommonToolResult):
        return result
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_named_entity(
        context,
        project.project_id,
        result["material"]["material_id"],
        "material",
        result["material"]["name"],
        result["material"],
    )
    return success_result(
        request_id=request.request_id,
        tool_name="connect_material_nodes",
        summary="Connected material nodes.",
        project_id=project.project_id,
        material=result["material"],
        link=result["link"],
        nodes=result.get("nodes", []),
        links=result.get("links", []),
    )


async def list_material_nodes(context, request: ListMaterialNodesRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    result = await _invoke_material_command(
        context,
        "list_material_nodes",
        request.model_dump(),
        request_id=request.request_id,
        tool_name="list_material_nodes",
        read_only=True,
    )
    if isinstance(result, CommonToolResult):
        return result
    return success_result(
        request_id=request.request_id,
        tool_name="list_material_nodes",
        summary=f"Listed {len(result.get('nodes', []))} material nodes.",
        project_id=request.project_id,
        material=result["material"],
        nodes=result.get("nodes", []),
        links=result.get("links", []),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for name, description, input_model, handler, read_only in (
        ("create_material", "Create a new material with optional preset defaults.", CreateMaterialRequest, create_material, False),
        ("apply_material", "Apply a material to one or more objects.", ApplyMaterialRequest, apply_material, False),
        ("set_material_property", "Update a material property.", SetMaterialPropertyRequest, set_material_property, False),
        ("create_pbr_material", "Create a PBR material with explicit parameters.", CreatePBRMaterialRequest, create_pbr_material, False),
        ("add_material_node", "Add a node to a material node graph.", AddMaterialNodeRequest, add_material_node, False),
        ("set_material_node_param", "Set a tracked parameter on a material node.", SetMaterialNodeParamRequest, set_material_node_param, False),
        ("connect_material_nodes", "Connect two material node sockets.", ConnectMaterialNodesRequest, connect_material_nodes, False),
        ("list_material_nodes", "List material node graph nodes and links.", ListMaterialNodesRequest, list_material_nodes, True),
    ):
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="material",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
