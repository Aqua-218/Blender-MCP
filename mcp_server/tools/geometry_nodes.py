from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import (
    list_entity_specs,
    load_entity_spec,
    retag_result,
    save_metadata_entity,
)
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


class GeometryNodesQueryRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None


class GeometryNodesSetupRequest(CommonToolRequest):
    project_id: str
    setup_id: str


class DuplicateGeometryNodesSetupRequest(GeometryNodesSetupRequest):
    target_id: str | None = None
    name: str | None = None


class AddNoiseDisplaceNodesRequest(GeometryNodesSetupRequest):
    scale: float = Field(default=8.0, gt=0.0)
    strength: float = 0.35


class AddCurveScatterNodesRequest(GeometryNodesSetupRequest):
    count: int = Field(default=32, ge=1, le=10000)
    radius: float = Field(default=0.15, gt=0.0)


class AddInstanceCollectionNodesRequest(GeometryNodesSetupRequest):
    collection_name: str
    density: float = Field(default=1.0, ge=0.0)


class AddLODSwitchNodesRequest(GeometryNodesSetupRequest):
    lod_count: int = Field(default=3, ge=1, le=8)


class ExposeGeometryNodesParameterRequest(GeometryNodesSetupRequest):
    node_id: str
    param_name: str
    label: str | None = None
    default_value: Any = None


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


def _append_preset_nodes(setup: dict[str, Any], specs: list[tuple[str, str, dict[str, Any]]]) -> list[dict[str, Any]]:
    nodes = list(setup.get("nodes", []))
    links = list(setup.get("links", []))
    created: list[dict[str, Any]] = []
    previous_id = nodes[-1]["node_id"] if nodes else None
    for index, (node_type, node_name, params) in enumerate(specs):
        node = {
            "node_id": new_id("node"),
            "node_type": node_type,
            "node_name": node_name,
            "location": [float((len(nodes) + index) * 220), 0.0],
            "params": params,
        }
        nodes.append(node)
        created.append(node)
        if previous_id is not None:
            links.append(
                {
                    "link_id": new_id("link"),
                    "from_node_id": previous_id,
                    "from_socket": "Geometry",
                    "to_node_id": node["node_id"],
                    "to_socket": "Geometry",
                }
            )
        previous_id = node["node_id"]
    setup["nodes"] = nodes
    setup["links"] = links
    return created


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


async def list_geometry_nodes_setups(context, request: GeometryNodesQueryRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    setups = list_entity_specs(context, request.project_id, "geometry_nodes")
    if request.target_id is not None:
        setups = [setup for setup in setups if setup.get("target_id") == request.target_id]
    return success_result(
        request_id=request.request_id,
        tool_name="list_geometry_nodes_setups",
        summary=f"Listed {len(setups)} geometry nodes setups.",
        project_id=request.project_id,
        setups=setups,
        count=len(setups),
    )


async def duplicate_geometry_nodes_setup(context, request: DuplicateGeometryNodesSetupRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    source = _load_setup(context, request.request_id, request.setup_id, "duplicate_geometry_nodes_setup")
    if isinstance(source, CommonToolResult):
        return source
    target_id = request.target_id or str(source["target_id"])
    name = request.name or f"{source['name']}_Copy"
    created = await _create_setup(
        context,
        request_id=request.request_id,
        project_id=project.project_id,
        target_id=target_id,
        tool_name="duplicate_geometry_nodes_setup",
        name=name,
        template=str(source.get("template", "custom")),
        metadata=dict(source.get("metadata", {})),
    )
    if created.status != "success":
        return created
    setup = created.model_dump()["setup"]
    setup["nodes"] = [dict(node, node_id=new_id("node")) for node in source.get("nodes", [])]
    id_map = {old["node_id"]: new["node_id"] for old, new in zip(source.get("nodes", []), setup["nodes"], strict=False)}
    setup["links"] = [
        {
            **link,
            "link_id": new_id("link"),
            "from_node_id": id_map.get(link.get("from_node_id"), link.get("from_node_id")),
            "to_node_id": id_map.get(link.get("to_node_id"), link.get("to_node_id")),
        }
        for link in source.get("links", [])
    ]
    setup["exposed_parameters"] = [
        dict(item, parameter_id=new_id("gnparam"), node_id=id_map.get(item.get("node_id"), item.get("node_id")))
        for item in source.get("exposed_parameters", [])
    ]
    _save_setup(context, project.project_id, setup)
    return success_result(
        request_id=request.request_id,
        tool_name="duplicate_geometry_nodes_setup",
        summary=f"Duplicated geometry nodes setup '{source['name']}'.",
        project_id=project.project_id,
        setup_id=setup["setup_id"],
        source_setup_id=request.setup_id,
        setup=setup,
        target_id=target_id,
    )


async def add_noise_displace_nodes(context, request: AddNoiseDisplaceNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "add_noise_displace_nodes")
    if isinstance(setup, CommonToolResult):
        return setup
    nodes = _append_preset_nodes(setup, [("NoiseTexture", "Preset Noise", {"scale": request.scale}), ("SetPosition", "Noise Displace", {"strength": request.strength})])
    setup["template"] = "noise_displace"
    _save_setup(context, project.project_id, setup)
    return success_result(request_id=request.request_id, tool_name="add_noise_displace_nodes", summary="Added noise displacement preset nodes.", project_id=project.project_id, setup_id=request.setup_id, nodes=nodes, setup=setup)


async def add_curve_scatter_nodes(context, request: AddCurveScatterNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "add_curve_scatter_nodes")
    if isinstance(setup, CommonToolResult):
        return setup
    nodes = _append_preset_nodes(
        setup,
        [("ResampleCurve", "Scatter Curve Samples", {"count": request.count}), ("CurveToMesh", "Curve Radius", {"radius": request.radius}), ("InstanceOnPoints", "Curve Instances", {})],
    )
    setup["template"] = "curve_scatter"
    _save_setup(context, project.project_id, setup)
    return success_result(request_id=request.request_id, tool_name="add_curve_scatter_nodes", summary="Added curve scatter preset nodes.", project_id=project.project_id, setup_id=request.setup_id, nodes=nodes, setup=setup)


async def add_instance_collection_nodes(context, request: AddInstanceCollectionNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "add_instance_collection_nodes")
    if isinstance(setup, CommonToolResult):
        return setup
    nodes = _append_preset_nodes(
        setup,
        [("CollectionInfo", "Source Collection", {"collection_name": request.collection_name}), ("DistributePointsOnFaces", "Distribution", {"density": request.density}), ("InstanceOnPoints", "Collection Instances", {"collection_name": request.collection_name})],
    )
    setup["metadata"] = {**setup.get("metadata", {}), "collection_name": request.collection_name, "density": request.density}
    _save_setup(context, project.project_id, setup)
    return success_result(request_id=request.request_id, tool_name="add_instance_collection_nodes", summary=f"Added collection instancing preset for '{request.collection_name}'.", project_id=project.project_id, setup_id=request.setup_id, nodes=nodes, setup=setup)


async def add_lod_switch_nodes(context, request: AddLODSwitchNodesRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "add_lod_switch_nodes")
    if isinstance(setup, CommonToolResult):
        return setup
    nodes = _append_preset_nodes(setup, [("Switch", f"LOD {index} Switch", {"lod_level": index}) for index in range(request.lod_count)])
    setup["metadata"] = {**setup.get("metadata", {}), "lod_count": request.lod_count}
    _save_setup(context, project.project_id, setup)
    return success_result(request_id=request.request_id, tool_name="add_lod_switch_nodes", summary=f"Added {request.lod_count} LOD switch nodes.", project_id=project.project_id, setup_id=request.setup_id, nodes=nodes, setup=setup)


async def expose_geometry_nodes_parameter(context, request: ExposeGeometryNodesParameterRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "expose_geometry_nodes_parameter")
    if isinstance(setup, CommonToolResult):
        return setup
    node_ids = {node["node_id"] for node in setup.get("nodes", [])}
    if request.node_id not in node_ids:
        return failed_result(request_id=request.request_id, tool_name="expose_geometry_nodes_parameter", summary=f"Node '{request.node_id}' was not found.", errors=[f"target_not_found: node '{request.node_id}' does not exist"])
    exposed = {"parameter_id": new_id("gnparam"), "node_id": request.node_id, "param_name": request.param_name, "label": request.label or request.param_name, "default_value": request.default_value}
    setup["exposed_parameters"] = [*setup.get("exposed_parameters", []), exposed]
    _save_setup(context, project.project_id, setup)
    return success_result(request_id=request.request_id, tool_name="expose_geometry_nodes_parameter", summary=f"Exposed geometry nodes parameter '{exposed['label']}'.", project_id=project.project_id, setup_id=request.setup_id, exposed_parameter=exposed, setup=setup)


async def validate_geometry_nodes_setup(context, request: GeometryNodesSetupRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    setup = _load_setup(context, request.request_id, request.setup_id, "validate_geometry_nodes_setup")
    if isinstance(setup, CommonToolResult):
        return setup
    node_ids = {node["node_id"] for node in setup.get("nodes", [])}
    findings: list[dict[str, Any]] = []
    if not node_ids:
        findings.append({"severity": "warning", "code": "empty_setup", "message": "Geometry nodes setup has no nodes."})
    for link in setup.get("links", []):
        if link.get("from_node_id") not in node_ids or link.get("to_node_id") not in node_ids:
            findings.append({"severity": "error", "code": "broken_link", "message": "Geometry nodes setup contains a link to a missing node.", "link_id": link.get("link_id")})
    severity_summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in severity_summary:
            severity_summary[severity] += 1
    return success_result(request_id=request.request_id, tool_name="validate_geometry_nodes_setup", summary="Geometry nodes setup validation completed.", project_id=request.project_id, setup_id=request.setup_id, setup=setup, findings=findings, severity_summary=severity_summary)


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_geometry_nodes", "Create a managed geometry nodes setup on a mesh target.", CreateGeometryNodesRequest, create_geometry_nodes, False),
        ("add_geometry_node", "Append a node definition to a managed geometry nodes setup.", AddGeometryNodeRequest, add_geometry_node, False),
        ("connect_geometry_nodes", "Connect two nodes inside a managed geometry nodes setup.", ConnectGeometryNodesRequest, connect_geometry_nodes, False),
        ("set_geometry_node_param", "Set a managed geometry node parameter value.", SetGeometryNodeParamRequest, set_geometry_node_param, False),
        ("create_scatter_node_setup", "Create a scatter-oriented geometry nodes template.", CreateScatterNodeSetupRequest, create_scatter_node_setup, False),
        ("create_procedural_building_nodes", "Create a procedural building geometry nodes template.", CreateProceduralBuildingNodesRequest, create_procedural_building_nodes, False),
        ("create_procedural_terrain_nodes", "Create a procedural terrain geometry nodes template.", CreateProceduralTerrainNodesRequest, create_procedural_terrain_nodes, False),
        ("list_geometry_nodes_setups", "List managed geometry nodes setups.", GeometryNodesQueryRequest, list_geometry_nodes_setups, True),
        ("duplicate_geometry_nodes_setup", "Duplicate a managed geometry nodes setup to a target.", DuplicateGeometryNodesSetupRequest, duplicate_geometry_nodes_setup, False),
        ("add_noise_displace_nodes", "Append a noise displacement preset to a managed setup.", AddNoiseDisplaceNodesRequest, add_noise_displace_nodes, False),
        ("add_curve_scatter_nodes", "Append a curve scatter preset to a managed setup.", AddCurveScatterNodesRequest, add_curve_scatter_nodes, False),
        ("add_instance_collection_nodes", "Append collection instancing preset nodes to a managed setup.", AddInstanceCollectionNodesRequest, add_instance_collection_nodes, False),
        ("add_lod_switch_nodes", "Append LOD switch preset nodes to a managed setup.", AddLODSwitchNodesRequest, add_lod_switch_nodes, False),
        ("expose_geometry_nodes_parameter", "Expose a managed geometry node parameter.", ExposeGeometryNodesParameterRequest, expose_geometry_nodes_parameter, False),
        ("validate_geometry_nodes_setup", "Validate managed geometry nodes metadata.", GeometryNodesSetupRequest, validate_geometry_nodes_setup, True),
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