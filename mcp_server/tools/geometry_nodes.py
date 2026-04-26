from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import load_entity_spec, retag_result, save_metadata_entity
from mcp_server.tools.helpers import require_project
from mcp_server.tools.modifiers import AddModifierRequest, add_modifier
from mcp_server.utils import new_id


class CreateGeometryNodesRequest(CommonToolRequest):
    project_id: str
    target_id: str
    name: str = "GeometryNodes"


class AddGeometryNodeRequest(CommonToolRequest):
    project_id: str
    setup_id: str
    node_type: str
    node_name: str | None = None
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0])
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectGeometryNodesRequest(CommonToolRequest):
    project_id: str
    setup_id: str
    from_node_id: str
    from_socket: str = "Geometry"
    to_node_id: str
    to_socket: str = "Geometry"


class SetGeometryNodeParamRequest(CommonToolRequest):
    project_id: str
    setup_id: str
    node_id: str
    param_name: str
    value: Any


class CreateScatterNodeSetupRequest(CommonToolRequest):
    project_id: str
    target_id: str
    asset_ids: list[str] = Field(default_factory=list)
    density: float = Field(default=1.0, ge=0.0)


class CreateProceduralBuildingNodesRequest(CommonToolRequest):
    project_id: str
    target_id: str
    floors: int = Field(default=4, ge=1, le=64)
    floor_height: float = Field(default=3.0, gt=0.0)


class CreateProceduralTerrainNodesRequest(CommonToolRequest):
    project_id: str
    target_id: str
    elevation: float = Field(default=2.0, ge=0.0)
    roughness: float = Field(default=0.5, ge=0.0)


def _load_setup(context, request_id: str, setup_id: str, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    setup = load_entity_spec(context, setup_id, expected_type="geometry_nodes")
    if setup is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Geometry nodes setup '{setup_id}' was not found.",
            errors=[f"target_not_found: geometry nodes setup '{setup_id}' does not exist"],
        )
    return setup


def _save_setup(context, project_id: str, setup: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(setup["setup_id"]),
        entity_type="geometry_nodes",
        name=str(setup["name"]),
        spec=setup,
    )


async def _create_setup(
    context,
    *,
    request_id: str,
    project_id: str,
    target_id: str,
    tool_name: str,
    name: str,
    template: str = "custom",
    metadata: dict[str, Any] | None = None,
) -> CommonToolResult:  # type: ignore[no-untyped-def]
    project = require_project(context, project_id)
    modifier = await add_modifier(
        context,
        AddModifierRequest(
            request_id=request_id,
            project_id=project_id,
            target_id=target_id,
            modifier_type="NODES",
            name=name,
            params={},
        ),
    )
    if modifier.status != "success":
        return retag_result(modifier, tool_name)
    setup_id = new_id("gnodes")
    setup = {
        "setup_id": setup_id,
        "name": name,
        "project_id": project_id,
        "target_id": target_id,
        "modifier_name": name,
        "template": template,
        "nodes": [],
        "links": [],
        "metadata": metadata or {},
    }
    _save_setup(context, project.project_id, setup)
    return success_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=f"Created geometry nodes setup '{name}'.",
        project_id=project.project_id,
        setup_id=setup_id,
        setup=setup,
        target_id=target_id,
    )


async def create_geometry_nodes(context, request: CreateGeometryNodesRequest):  # type: ignore[no-untyped-def]
    return await _create_setup(
        context,
        request_id=request.request_id,
        project_id=request.project_id,
        target_id=request.target_id,
        tool_name="create_geometry_nodes",
        name=request.name,
    )


async def add_geometry_node(context, request: AddGeometryNodeRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "add_geometry_node")
    if isinstance(setup, CommonToolResult):
        return setup
    node_id = new_id("node")
    node = {
        "node_id": node_id,
        "node_type": request.node_type,
        "node_name": request.node_name or request.node_type,
        "location": request.location,
        "params": request.params,
    }
    setup["nodes"] = [*setup.get("nodes", []), node]
    _save_setup(context, project.project_id, setup)
    return success_result(
        request_id=request.request_id,
        tool_name="add_geometry_node",
        summary=f"Added node '{node['node_name']}'.",
        project_id=project.project_id,
        setup_id=request.setup_id,
        node=node,
        setup=setup,
    )


async def connect_geometry_nodes(context, request: ConnectGeometryNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "connect_geometry_nodes")
    if isinstance(setup, CommonToolResult):
        return setup
    node_ids = {node["node_id"] for node in setup.get("nodes", [])}
    if request.from_node_id not in node_ids or request.to_node_id not in node_ids:
        return failed_result(
            request_id=request.request_id,
            tool_name="connect_geometry_nodes",
            summary="Both nodes must exist before creating a link.",
            errors=["target_not_found: one or more node ids were not found"],
        )
    link = {
        "link_id": new_id("link"),
        "from_node_id": request.from_node_id,
        "from_socket": request.from_socket,
        "to_node_id": request.to_node_id,
        "to_socket": request.to_socket,
    }
    setup["links"] = [*setup.get("links", []), link]
    _save_setup(context, project.project_id, setup)
    return success_result(
        request_id=request.request_id,
        tool_name="connect_geometry_nodes",
        summary="Connected geometry nodes.",
        project_id=project.project_id,
        setup_id=request.setup_id,
        link=link,
        setup=setup,
    )


async def set_geometry_node_param(context, request: SetGeometryNodeParamRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "set_geometry_node_param")
    if isinstance(setup, CommonToolResult):
        return setup
    updated_node = None
    for node in setup.get("nodes", []):
        if node["node_id"] == request.node_id:
            params = dict(node.get("params", {}))
            params[request.param_name] = request.value
            node["params"] = params
            updated_node = node
            break
    if updated_node is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="set_geometry_node_param",
            summary=f"Node '{request.node_id}' was not found.",
            errors=[f"target_not_found: node '{request.node_id}' does not exist"],
        )
    _save_setup(context, project.project_id, setup)
    return success_result(
        request_id=request.request_id,
        tool_name="set_geometry_node_param",
        summary=f"Updated parameter '{request.param_name}'.",
        project_id=project.project_id,
        setup_id=request.setup_id,
        node=updated_node,
        setup=setup,
    )


async def create_scatter_node_setup(context, request: CreateScatterNodeSetupRequest):  # type: ignore[no-untyped-def]
    setup_result = await _create_setup(
        context,
        request_id=request.request_id,
        project_id=request.project_id,
        target_id=request.target_id,
        tool_name="create_scatter_node_setup",
        name="ScatterNodes",
        template="scatter",
        metadata={"asset_ids": request.asset_ids, "density": request.density},
    )
    if setup_result.status != "success":
        return setup_result
    setup_id = str(setup_result.model_dump()["setup_id"])
    node_specs = [
        ("GroupInput", "Group Input", [0.0, 0.0], {}),
        ("DistributePointsOnFaces", "Distribute Points", [220.0, 0.0], {"density": request.density}),
        ("InstanceOnPoints", "Instance On Points", [440.0, 0.0], {"asset_ids": request.asset_ids}),
        ("RealizeInstances", "Realize Instances", [680.0, 0.0], {}),
        ("GroupOutput", "Group Output", [900.0, 0.0], {}),
    ]
    node_ids: list[str] = []
    for node_type, node_name, location, params in node_specs:
        added = await add_geometry_node(
            context,
            AddGeometryNodeRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                setup_id=setup_id,
                node_type=node_type,
                node_name=node_name,
                location=location,
                params=params,
            ),
        )
        if added.status != "success":
            return retag_result(added, "create_scatter_node_setup")
        node_ids.append(str(added.model_dump()["node"]["node_id"]))
    for from_node_id, to_node_id in zip(node_ids, node_ids[1:], strict=False):
        linked = await connect_geometry_nodes(
            context,
            ConnectGeometryNodesRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                setup_id=setup_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
            ),
        )
        if linked.status != "success":
            return retag_result(linked, "create_scatter_node_setup")
    final_setup = load_entity_spec(context, setup_id, expected_type="geometry_nodes")
    return success_result(
        request_id=request.request_id,
        tool_name="create_scatter_node_setup",
        summary="Created scatter geometry nodes setup.",
        project_id=request.project_id,
        setup_id=setup_id,
        setup=final_setup,
        target_id=request.target_id,
    )


async def create_procedural_building_nodes(context, request: CreateProceduralBuildingNodesRequest):  # type: ignore[no-untyped-def]
    setup_result = await _create_setup(
        context,
        request_id=request.request_id,
        project_id=request.project_id,
        target_id=request.target_id,
        tool_name="create_procedural_building_nodes",
        name="ProceduralBuildingNodes",
        template="procedural_building",
        metadata={"floors": request.floors, "floor_height": request.floor_height},
    )
    if setup_result.status != "success":
        return setup_result
    setup_id = str(setup_result.model_dump()["setup_id"])
    for node_type, node_name, params in (
        ("GroupInput", "Group Input", {}),
        ("MeshCube", "Base Volume", {}),
        ("ExtrudeMesh", "Floor Stack", {"floors": request.floors, "floor_height": request.floor_height}),
        ("Transform", "Roof Offset", {"translation_z": request.floors * request.floor_height}),
        ("GroupOutput", "Group Output", {}),
    ):
        added = await add_geometry_node(
            context,
            AddGeometryNodeRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                setup_id=setup_id,
                node_type=node_type,
                node_name=node_name,
                params=params,
            ),
        )
        if added.status != "success":
            return retag_result(added, "create_procedural_building_nodes")
    final_setup = load_entity_spec(context, setup_id, expected_type="geometry_nodes")
    return success_result(
        request_id=request.request_id,
        tool_name="create_procedural_building_nodes",
        summary="Created procedural building geometry nodes setup.",
        project_id=request.project_id,
        setup_id=setup_id,
        setup=final_setup,
        target_id=request.target_id,
    )


async def create_procedural_terrain_nodes(context, request: CreateProceduralTerrainNodesRequest):  # type: ignore[no-untyped-def]
    setup_result = await _create_setup(
        context,
        request_id=request.request_id,
        project_id=request.project_id,
        target_id=request.target_id,
        tool_name="create_procedural_terrain_nodes",
        name="ProceduralTerrainNodes",
        template="procedural_terrain",
        metadata={"elevation": request.elevation, "roughness": request.roughness},
    )
    if setup_result.status != "success":
        return setup_result
    setup_id = str(setup_result.model_dump()["setup_id"])
    for node_type, node_name, params in (
        ("GroupInput", "Group Input", {}),
        ("NoiseTexture", "Elevation Noise", {"scale": request.roughness * 8.0}),
        ("SetPosition", "Apply Elevation", {"elevation": request.elevation}),
        ("Smooth", "Terrain Smooth", {"factor": 0.35}),
        ("GroupOutput", "Group Output", {}),
    ):
        added = await add_geometry_node(
            context,
            AddGeometryNodeRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                setup_id=setup_id,
                node_type=node_type,
                node_name=node_name,
                params=params,
            ),
        )
        if added.status != "success":
            return retag_result(added, "create_procedural_terrain_nodes")
    final_setup = load_entity_spec(context, setup_id, expected_type="geometry_nodes")
    return success_result(
        request_id=request.request_id,
        tool_name="create_procedural_terrain_nodes",
        summary="Created procedural terrain geometry nodes setup.",
        project_id=request.project_id,
        setup_id=setup_id,
        setup=final_setup,
        target_id=request.target_id,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_geometry_nodes", "Create a managed geometry nodes setup on a mesh target.", CreateGeometryNodesRequest, create_geometry_nodes, False),
        ("add_geometry_node", "Append a node definition to a managed geometry nodes setup.", AddGeometryNodeRequest, add_geometry_node, False),
        ("connect_geometry_nodes", "Connect two nodes inside a managed geometry nodes setup.", ConnectGeometryNodesRequest, connect_geometry_nodes, False),
        ("set_geometry_node_param", "Set a managed geometry node parameter value.", SetGeometryNodeParamRequest, set_geometry_node_param, False),
        ("create_scatter_node_setup", "Create a scatter-oriented geometry nodes template.", CreateScatterNodeSetupRequest, create_scatter_node_setup, False),
        ("create_procedural_building_nodes", "Create a procedural building geometry nodes template.", CreateProceduralBuildingNodesRequest, create_procedural_building_nodes, False),
        ("create_procedural_terrain_nodes", "Create a procedural terrain geometry nodes template.", CreateProceduralTerrainNodesRequest, create_procedural_terrain_nodes, False),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="geometry_nodes",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )