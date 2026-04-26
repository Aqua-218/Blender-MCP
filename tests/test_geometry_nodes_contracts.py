from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port


async def _call(app: MCPServerApplication, name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = await app.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return response["result"]


def _make_settings(tmp_path: Path) -> ServerSettings:
    port = find_free_port()
    return ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_geometry_node_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "create_geometry_nodes",
            "add_geometry_node",
            "connect_geometry_nodes",
            "set_geometry_node_param",
            "create_scatter_node_setup",
            "create_procedural_building_nodes",
            "create_procedural_terrain_nodes",
        }.issubset(tool_names)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_geometry_node_tools_create_metadata_and_runtime_modifiers(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Geometry Nodes"})
        project_id = str(project["project_id"])

        terrain_target = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-grid",
                "project_id": project_id,
                "primitive_type": "grid",
                "name": "TerrainTarget",
            },
        )
        terrain_target_id = str(terrain_target["created_object_ids"][0])

        setup = await _call(
            app,
            "create_geometry_nodes",
            {
                "request_id": "req-setup",
                "project_id": project_id,
                "target_id": terrain_target_id,
                "name": "BaseNodes",
            },
        )
        setup_id = str(setup["setup_id"])
        assert setup["status"] == "success"

        node_a = await _call(
            app,
            "add_geometry_node",
            {
                "request_id": "req-node-a",
                "project_id": project_id,
                "setup_id": setup_id,
                "node_type": "NoiseTexture",
                "node_name": "Noise",
                "params": {"scale": 5.0},
            },
        )
        node_b = await _call(
            app,
            "add_geometry_node",
            {
                "request_id": "req-node-b",
                "project_id": project_id,
                "setup_id": setup_id,
                "node_type": "SetPosition",
                "node_name": "Displace",
            },
        )
        assert node_a["status"] == "success"
        assert node_b["status"] == "success"

        linked = await _call(
            app,
            "connect_geometry_nodes",
            {
                "request_id": "req-link",
                "project_id": project_id,
                "setup_id": setup_id,
                "from_node_id": node_a["node"]["node_id"],
                "to_node_id": node_b["node"]["node_id"],
                "from_socket": "Color",
                "to_socket": "Offset",
            },
        )
        assert linked["status"] == "success"

        updated = await _call(
            app,
            "set_geometry_node_param",
            {
                "request_id": "req-param",
                "project_id": project_id,
                "setup_id": setup_id,
                "node_id": node_b["node"]["node_id"],
                "param_name": "offset_scale",
                "value": 2.25,
            },
        )
        assert updated["status"] == "success"
        assert updated["node"]["params"]["offset_scale"] == 2.25

        scatter = await _call(
            app,
            "create_scatter_node_setup",
            {
                "request_id": "req-scatter",
                "project_id": project_id,
                "target_id": terrain_target_id,
                "density": 3.0,
            },
        )
        assert scatter["status"] == "success"
        assert len(scatter["setup"]["nodes"]) >= 5

        building_target = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-building-target",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "BuildingTarget",
            },
        )
        building_nodes = await _call(
            app,
            "create_procedural_building_nodes",
            {
                "request_id": "req-building-nodes",
                "project_id": project_id,
                "target_id": building_target["created_object_ids"][0],
                "floors": 6,
                "floor_height": 2.8,
            },
        )
        assert building_nodes["status"] == "success"
        assert building_nodes["setup"]["template"] == "procedural_building"

        terrain_nodes = await _call(
            app,
            "create_procedural_terrain_nodes",
            {
                "request_id": "req-terrain-nodes",
                "project_id": project_id,
                "target_id": terrain_target_id,
                "elevation": 4.0,
                "roughness": 0.75,
            },
        )
        assert terrain_nodes["status"] == "success"
        assert terrain_nodes["setup"]["template"] == "procedural_terrain"

        modifiers = await _call(
            app,
            "list_modifiers",
            {
                "request_id": "req-list-modifiers",
                "project_id": project_id,
                "target_id": terrain_target_id,
            },
        )
        modifier_types = {modifier["type"] for modifier in modifiers["modifiers"]}
        assert "NODES" in modifier_types
    finally:
        await app.stop()