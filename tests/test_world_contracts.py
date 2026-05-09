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
async def test_world_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "create_world",
            "generate_terrain",
            "generate_biomes",
            "generate_roads",
            "generate_water_system",
            "place_buildings",
            "scatter_vegetation",
            "create_region",
            "detail_region",
            "create_world_preset",
            "generate_mountain_range",
            "create_navigation_markers",
            "validate_world_composition",
            "inspect_world",
        }.issubset(tool_names)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_world_tools_build_up_managed_world_state(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "World Tools"})
        project_id = str(project["project_id"])

        world = await _call(
            app,
            "create_world",
            {
                "request_id": "req-world",
                "project_id": project_id,
                "name": "OpenWorld",
                "theme": "temperate",
            },
        )
        world_id = str(world["world_id"])
        assert world["status"] == "success"
        assert world["terrain"]["world_id"] == world_id

        biomes = await _call(
            app,
            "generate_biomes",
            {
                "request_id": "req-biomes",
                "project_id": project_id,
                "world_id": world_id,
                "biome_types": ["forest", "plains", "rock"],
            },
        )
        assert biomes["status"] == "success"
        assert len(biomes["biomes"]) == 3

        roads = await _call(
            app,
            "generate_roads",
            {
                "request_id": "req-roads",
                "project_id": project_id,
                "world_id": world_id,
                "road_count": 2,
                "extent": 20.0,
            },
        )
        assert roads["status"] == "success"
        assert len(roads["roads"]) == 2

        water = await _call(
            app,
            "generate_water_system",
            {
                "request_id": "req-water",
                "project_id": project_id,
                "world_id": world_id,
                "water_type": "lake",
            },
        )
        assert water["status"] == "success"

        buildings = await _call(
            app,
            "place_buildings",
            {
                "request_id": "req-buildings",
                "project_id": project_id,
                "world_id": world_id,
                "count": 2,
                "origin": [0.0, 0.0, 0.0],
                "spacing": 8.0,
            },
        )
        assert buildings["status"] == "success"
        assert len(buildings["placements"]) == 2

        vegetation = await _call(
            app,
            "scatter_vegetation",
            {
                "request_id": "req-vegetation",
                "project_id": project_id,
                "world_id": world_id,
                "count": 5,
                "area_min": [-4.0, -4.0, 0.0],
                "area_max": [4.0, 4.0, 0.0],
                "seed": 5,
            },
        )
        assert vegetation["status"] == "success"
        assert len(vegetation["created_object_ids"]) == 5

        region = await _call(
            app,
            "create_region",
            {
                "request_id": "req-region",
                "project_id": project_id,
                "world_id": world_id,
                "name": "North District",
                "min_corner": [-6.0, -6.0, 0.0],
                "max_corner": [6.0, 6.0, 0.0],
                "tags": ["playable"],
            },
        )
        assert region["status"] == "success"

        detailed = await _call(
            app,
            "detail_region",
            {
                "request_id": "req-detail-region",
                "project_id": project_id,
                "world_id": world_id,
                "region_id": region["region_id"],
                "detail_type": "mixed",
                "density": 4,
            },
        )
        assert detailed["status"] == "success"
        assert detailed["created_object_ids"]

        mountains = await _call(
            app,
            "generate_mountain_range",
            {
                "request_id": "req-mountains",
                "project_id": project_id,
                "world_id": world_id,
                "name": "North Ridge",
                "count": 3,
                "height": 3.0,
            },
        )
        assert mountains["status"] == "success"
        assert len(mountains["created_object_ids"]) == 3

        navigation = await _call(
            app,
            "create_navigation_markers",
            {
                "request_id": "req-navigation",
                "project_id": project_id,
                "world_id": world_id,
                "marker_count": 3,
                "marker_type": "quest",
            },
        )
        assert navigation["status"] == "success"
        assert len(navigation["markers"]) == 3

        validation = await _call(
            app,
            "validate_world_composition",
            {
                "request_id": "req-world-validation",
                "project_id": project_id,
                "world_id": world_id,
                "require_navigation": True,
            },
        )
        assert validation["severity_summary"]["error"] == 0
        assert validation["counts"]["navigation"] == 3

        inspected = await _call(
            app,
            "inspect_world",
            {
                "request_id": "req-inspect-world",
                "project_id": project_id,
                "world_id": world_id,
            },
        )
        assert inspected["status"] == "success"
        assert inspected["counts"]["terrain"] >= 1
        assert inspected["counts"]["biomes"] == 3
        assert inspected["counts"]["roads"] >= 2
        assert inspected["counts"]["water"] >= 1
        assert inspected["counts"]["buildings"] >= 2
        assert inspected["counts"]["vegetation"] >= 1
        assert inspected["counts"]["regions"] == 1
        assert inspected["counts"]["mountain_ranges"] == 1
        assert inspected["counts"]["navigation"] == 3

        preset = await _call(
            app,
            "create_world_preset",
            {
                "request_id": "req-world-preset",
                "project_id": project_id,
                "name": "Preset Valley",
                "preset_name": "forest_valley",
                "size": 20.0,
                "seed": 7,
            },
        )
        assert preset["status"] == "success"
        assert preset["world_id"] != world_id
        assert preset["created_object_ids"]
    finally:
        await app.stop()