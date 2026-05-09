from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

AAA_ORCHESTRATOR_TOOLS = {
    "build_game_ready_asset",
    "build_environment_kit",
    "build_world_blockout",
    "run_shipping_readiness_pass",
}


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


def _build_app(tmp_path: Path) -> MCPServerApplication:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    return MCPServerApplication(settings)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aaa_orchestrator_tools_are_registered(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert AAA_ORCHESTRATOR_TOOLS.issubset(tools)
        for tool_name in AAA_ORCHESTRATOR_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "aaa_orchestrator"
            assert tools[tool_name]["annotations"]["readOnlyHint"] is False
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_build_game_ready_asset_executes_real_pipeline(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-orch-project", "name": "AAA Orchestrator"})
        project_id = str(project["project_id"])
        plan = await _call(
            app,
            "create_game_production_plan",
            {
                "request_id": "req-orch-plan",
                "project_id": project_id,
                "game_title": "Practical AAA",
                "content_scale": "vertical_slice",
                "target_engines": ["unreal"],
            },
        )

        asset = await _call(
            app,
            "build_game_ready_asset",
            {
                "request_id": "req-orch-asset",
                "project_id": project_id,
                "plan_id": plan["plan_id"],
                "asset_name": "Runtime Rifle",
                "asset_type": "weapon",
                "target_engine": "unreal",
                "create_lods": True,
                "lod_levels": 2,
                "create_collision": True,
                "create_socket": True,
                "base_color": [0.18, 0.2, 0.22, 1.0],
            },
        )
        listed = await _call(app, "list_objects", {"request_id": "req-orch-list", "project_id": project_id})

        assert asset["status"] == "success"
        assert asset["primary_object_id"] in asset["render_object_ids"]
        assert asset["brief_id"]
        assert asset["asset_id"]
        assert asset["material_id"]
        assert asset["lod_object_ids"]
        assert asset["collision_object_ids"]
        assert asset["socket_object_id"]
        assert len(asset["steps"]) >= 8
        assert len(listed["objects"]) >= 6
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_build_world_blockout_executes_world_pipeline(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-orch-world-project", "name": "World"})
        project_id = str(project["project_id"])

        world = await _call(
            app,
            "build_world_blockout",
            {
                "request_id": "req-orch-world",
                "project_id": project_id,
                "world_name": "Frontier Valley",
                "theme": "temperate frontier",
                "size": 48.0,
                "road_count": 2,
                "vegetation_count": 8,
                "navigation_marker_count": 4,
                "streaming_cell_size": 24.0,
            },
        )

        assert world["status"] == "success"
        assert world["world_id"]
        assert world["streaming_plan_id"]
        assert world["validation"]["severity_summary"]["error"] == 0
        assert {step["tool_name"] for step in world["steps"]} >= {
            "create_world",
            "generate_roads",
            "scatter_vegetation",
            "plan_level_streaming",
            "validate_world_composition",
        }
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shipping_readiness_writes_manifests_after_asset_pipeline(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-orch-ship-project", "name": "Ship"})
        project_id = str(project["project_id"])
        plan = await _call(
            app,
            "create_game_production_plan",
            {
                "request_id": "req-orch-ship-plan",
                "project_id": project_id,
                "game_title": "Ship It",
                "content_scale": "vertical_slice",
                "target_engines": ["unreal"],
                "world_scope": "arena",
            },
        )
        await _call(
            app,
            "build_game_ready_asset",
            {
                "request_id": "req-orch-ship-asset",
                "project_id": project_id,
                "plan_id": plan["plan_id"],
                "asset_name": "Shipping Crate",
                "asset_type": "prop",
                "create_lods": True,
                "create_collision": True,
            },
        )

        readiness = await _call(
            app,
            "run_shipping_readiness_pass",
            {
                "request_id": "req-orch-ship-ready",
                "project_id": project_id,
                "plan_id": plan["plan_id"],
                "target_engine": "unreal",
                "package_name": "ship-it-package",
                "require_asset_library": True,
                "require_aaa_gates": True,
                "write_manifests": True,
            },
        )

        assert readiness["status"] == "success"
        assert readiness["file_paths"]
        assert all(Path(path).exists() for path in readiness["file_paths"])
        assert {step["tool_name"] for step in readiness["steps"]} >= {
            "set_engine_export_profile",
            "validate_production_readiness",
            "validate_engine_export_package",
            "write_game_export_manifest",
            "write_game_production_package",
        }
    finally:
        await app.stop()
