from __future__ import annotations

import re
from pathlib import Path
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


class ClassifyPBRTextureSetRequest(CommonToolRequest):
    project_id: str
    texture_paths: list[str] = Field(default_factory=list)


class CreatePBRMaterialFromTexturesRequest(CommonToolRequest):
    project_id: str
    name: str
    texture_paths: list[str] = Field(default_factory=list)
    base_color: list[float] = Field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    roughness: float = 0.5
    metallic: float = 0.0
    auto_connect: bool = True


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


_PBR_TEXTURE_PATTERNS: dict[str, tuple[str, ...]] = {
    "base_color": (r"base[ _-]?color", r"basecolor", r"albedo", r"diffuse", r"\bcolor\b", r"\bcol\b"),
    "normal": (r"normal", r"\bnrm\b", r"\bnor\b"),
    "roughness": (r"roughness", r"\brough\b", r"\brgh\b"),
    "metallic": (r"metallic", r"metalness", r"\bmetal\b", r"\bmtl\b"),
    "ao": (r"ambient[ _-]?occlusion", r"(?:^|_)ao(?:_|$)"),
    "height": (r"height", r"displacement", r"\bdisp\b"),
    "opacity": (r"opacity", r"alpha", r"transparent", r"transparency"),
}
_PBR_COLOR_SPACES = {
    "base_color": "sRGB",
    "opacity": "Non-Color",
    "normal": "Non-Color",
    "roughness": "Non-Color",
    "metallic": "Non-Color",
    "ao": "Non-Color",
    "height": "Non-Color",
}


def _texture_role(path: str) -> str | None:
    normalized = re.sub(r"[.\s]+", "_", Path(path).stem.lower())
    for role, patterns in _PBR_TEXTURE_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return role
    return None


def _classify_pbr_textures(texture_paths: list[str]) -> tuple[dict[str, Any], list[str]]:
    roles: dict[str, dict[str, Any]] = {}
    unclassified: list[str] = []
    duplicate_roles: dict[str, list[str]] = {}
    for texture_path in texture_paths:
        role = _texture_role(texture_path)
        if role is None:
            unclassified.append(texture_path)
            continue
        record = {
            "path": texture_path,
            "role": role,
            "color_space": _PBR_COLOR_SPACES[role],
        }
        if role in roles:
            duplicate_roles.setdefault(role, [roles[role]["path"]]).append(texture_path)
            continue
        roles[role] = record
    warnings: list[str] = []
    if "base_color" not in roles:
        warnings.append("Texture set has no detected base color texture.")
    if duplicate_roles:
        warnings.append(f"Duplicate texture roles ignored: {sorted(duplicate_roles)}")
    if unclassified:
        warnings.append(f"Unclassified textures: {len(unclassified)}")
    return {
        "roles": roles,
        "unclassified": unclassified,
        "duplicate_roles": duplicate_roles,
        "detected_roles": sorted(roles),
        "missing_recommended_roles": [role for role in ["base_color", "normal", "roughness"] if role not in roles],
    }, warnings


def _material_failed_result(request_id: str, tool_name: str, code: str, message: str) -> CommonToolResult:
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


def _retag_material_result(result: CommonToolResult, tool_name: str) -> CommonToolResult:
    payload = result.model_dump()
    payload["tool_name"] = tool_name
    return CommonToolResult.model_validate(payload)


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


async def classify_pbr_texture_set(context, request: ClassifyPBRTextureSetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    texture_set, warnings = _classify_pbr_textures(request.texture_paths)
    return success_result(
        request_id=request.request_id,
        tool_name="classify_pbr_texture_set",
        summary=f"Classified {len(request.texture_paths)} texture paths into {len(texture_set['roles'])} PBR roles.",
        project_id=project.project_id,
        texture_set=texture_set,
        warnings=warnings,
    )


async def create_pbr_material_from_textures(context, request: CreatePBRMaterialFromTexturesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    texture_set, warnings = _classify_pbr_textures(request.texture_paths)
    created = await create_pbr_material(
        context,
        CreatePBRMaterialRequest(
            request_id=f"{request.request_id}-pbr",
            project_id=project.project_id,
            name=request.name,
            base_color=request.base_color,
            roughness=request.roughness,
            metallic=request.metallic,
        ),
    )
    if created.status != "success":
        return _retag_material_result(created, "create_pbr_material_from_textures")
    material = created.model_dump()["material"]
    material_id = material["material_id"]
    principled = await add_material_node(
        context,
        AddMaterialNodeRequest(
            request_id=f"{request.request_id}-principled",
            project_id=project.project_id,
            material_id=material_id,
            node_type="ShaderNodeBsdfPrincipled",
            node_name="Principled BSDF",
            location=(320.0, 0.0),
            params={"texture_set": texture_set},
        ),
    )
    if principled.status != "success":
        return _retag_material_result(principled, "create_pbr_material_from_textures")
    principled_node_id = principled.model_dump()["node"]["node_id"]
    nodes = list(principled.model_dump().get("nodes", []))
    links = list(principled.model_dump().get("links", []))
    role_nodes: dict[str, str] = {}
    for index, (role, texture) in enumerate(texture_set["roles"].items()):
        added = await add_material_node(
            context,
            AddMaterialNodeRequest(
                request_id=f"{request.request_id}-{role}",
                project_id=project.project_id,
                material_id=material_id,
                node_type="ShaderNodeTexImage",
                node_name=f"{role}_texture",
                location=(-520.0, 180.0 - (index * 140.0)),
                params=texture,
            ),
        )
        if added.status != "success":
            return _retag_material_result(added, "create_pbr_material_from_textures")
        role_nodes[role] = added.model_dump()["node"]["node_id"]
        nodes = list(added.model_dump().get("nodes", nodes))
        links = list(added.model_dump().get("links", links))
    if request.auto_connect:
        for role, socket in (("base_color", "Base Color"), ("roughness", "Roughness"), ("metallic", "Metallic"), ("opacity", "Alpha")):
            if role not in role_nodes:
                continue
            linked = await connect_material_nodes(
                context,
                ConnectMaterialNodesRequest(
                    request_id=f"{request.request_id}-link-{role}",
                    project_id=project.project_id,
                    material_id=material_id,
                    from_node_id=role_nodes[role],
                    from_socket="Alpha" if role == "opacity" else "Color",
                    to_node_id=principled_node_id,
                    to_socket=socket,
                ),
            )
            if linked.status == "success":
                links = list(linked.model_dump().get("links", links))
        if "normal" in role_nodes:
            normal = await add_material_node(
                context,
                AddMaterialNodeRequest(
                    request_id=f"{request.request_id}-normal-map",
                    project_id=project.project_id,
                    material_id=material_id,
                    node_type="ShaderNodeNormalMap",
                    node_name="Normal Map",
                    location=(-120.0, -260.0),
                ),
            )
            if normal.status == "success":
                normal_node_id = normal.model_dump()["node"]["node_id"]
                await connect_material_nodes(context, ConnectMaterialNodesRequest(request_id=f"{request.request_id}-link-normal-color", project_id=project.project_id, material_id=material_id, from_node_id=role_nodes["normal"], from_socket="Color", to_node_id=normal_node_id, to_socket="Color"))
                linked = await connect_material_nodes(context, ConnectMaterialNodesRequest(request_id=f"{request.request_id}-link-normal", project_id=project.project_id, material_id=material_id, from_node_id=normal_node_id, from_socket="Normal", to_node_id=principled_node_id, to_socket="Normal"))
                nodes = list(linked.model_dump().get("nodes", nodes)) if linked.status == "success" else nodes
                links = list(linked.model_dump().get("links", links)) if linked.status == "success" else links
    listed = await list_material_nodes(context, ListMaterialNodesRequest(request_id=f"{request.request_id}-nodes", project_id=project.project_id, material_id=material_id))
    if listed.status == "success":
        nodes = list(listed.model_dump().get("nodes", nodes))
        links = list(listed.model_dump().get("links", links))
        material = listed.model_dump().get("material", material)
    return success_result(
        request_id=request.request_id,
        tool_name="create_pbr_material_from_textures",
        summary=f"Created PBR material '{request.name}' from {len(texture_set['roles'])} classified textures.",
        project_id=project.project_id,
        material=material,
        texture_set=texture_set,
        nodes=nodes,
        links=links,
        warnings=warnings,
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
        ("classify_pbr_texture_set", "Classify texture filenames into PBR material roles and color spaces.", ClassifyPBRTextureSetRequest, classify_pbr_texture_set, True),
        ("create_pbr_material_from_textures", "Create a PBR material node graph from classified texture paths.", CreatePBRMaterialFromTexturesRequest, create_pbr_material_from_textures, False),
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
