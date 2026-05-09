from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

PRODUCTION_PIPELINE_TOOLS = {
    "create_game_production_plan",
    "list_game_production_plans",
    "create_asset_brief",
    "list_asset_briefs",
    "update_asset_brief_status",
    "plan_level_streaming",
    "list_level_streaming_plans",
    "validate_production_readiness",
    "plan_game_production_package",
    "write_game_production_package",
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
async def test_production_pipeline_tools_are_registered(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert PRODUCTION_PIPELINE_TOOLS.issubset(tools)
        for tool_name in PRODUCTION_PIPELINE_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "production_pipeline"
        assert tools["list_game_production_plans"]["annotations"]["readOnlyHint"] is True
        assert tools["list_asset_briefs"]["annotations"]["readOnlyHint"] is True
        assert tools["list_level_streaming_plans"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_production_readiness"]["annotations"]["readOnlyHint"] is True
        assert tools["plan_game_production_package"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_production_pipeline_plans_briefs_streaming_and_manifest(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-prod-project", "name": "AAA Production"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-prod-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Hero Crate",
            },
        )
        cube_id = str(cube["created_object_ids"][0])
        material = await _call(
            app,
            "create_pbr_material",
            {
                "request_id": "req-prod-material",
                "project_id": project_id,
                "name": "HeroCratePBR",
                "base_color": [0.6, 0.32, 0.12, 1.0],
            },
        )
        await _call(
            app,
            "apply_material",
            {
                "request_id": "req-prod-apply-material",
                "project_id": project_id,
                "material_id": material["material"]["material_id"],
                "target_id": cube_id,
            },
        )
        await _call(
            app,
            "register_asset_library_item",
            {
                "request_id": "req-prod-asset-register",
                "project_id": project_id,
                "asset_name": "Hero Crate",
                "category": "props",
                "target_id": cube_id,
                "status": "approved",
            },
        )

        plan = await _call(
            app,
            "create_game_production_plan",
            {
                "request_id": "req-prod-plan",
                "project_id": project_id,
                "game_title": "Skyline Zero",
                "genre": "open world action RPG",
                "content_scale": "aaa",
                "target_engines": ["unreal", "unity"],
                "world_scope": "open_world",
                "gameplay_pillars": ["exploration", "tactical combat", "crafting"],
            },
        )
        plan_id = str(plan["plan_id"])
        brief = await _call(
            app,
            "create_asset_brief",
            {
                "request_id": "req-prod-brief",
                "project_id": project_id,
                "plan_id": plan_id,
                "asset_name": "Hero Crate",
                "asset_type": "prop",
                "target_quality": "hero",
                "engine": "unreal",
                "gameplay_tags": ["loot", "cover"],
            },
        )
        brief_id = str(brief["brief_id"])
        approved = await _call(
            app,
            "update_asset_brief_status",
            {
                "request_id": "req-prod-brief-approved",
                "project_id": project_id,
                "brief_id": brief_id,
                "status": "approved",
            },
        )
        streaming = await _call(
            app,
            "plan_level_streaming",
            {
                "request_id": "req-prod-stream",
                "project_id": project_id,
                "plan_id": plan_id,
                "level_name": "Downtown",
                "min_corner": [-512.0, -512.0, 0.0],
                "max_corner": [512.0, 512.0, 128.0],
                "cell_size": 256.0,
                "memory_budget_mb": 512,
            },
        )
        readiness = await _call(
            app,
            "validate_production_readiness",
            {
                "request_id": "req-prod-ready",
                "project_id": project_id,
                "plan_id": plan_id,
                "min_asset_briefs": 1,
                "require_asset_library": True,
                "require_streaming_plan": True,
                "require_approved_briefs": True,
            },
        )
        planned_package = await _call(
            app,
            "plan_game_production_package",
            {
                "request_id": "req-prod-package-plan",
                "project_id": project_id,
                "plan_id": plan_id,
                "package_name": "skyline-zero-production",
                "require_asset_library": True,
                "require_streaming_plan": True,
            },
        )
        written_package = await _call(
            app,
            "write_game_production_package",
            {
                "request_id": "req-prod-package-write",
                "project_id": project_id,
                "plan_id": plan_id,
                "package_name": "skyline-zero-production",
                "require_asset_library": True,
                "require_streaming_plan": True,
            },
        )
        listed_briefs = await _call(
            app,
            "list_asset_briefs",
            {"request_id": "req-prod-list-briefs", "project_id": project_id, "plan_id": plan_id},
        )
        listed_streaming = await _call(
            app,
            "list_level_streaming_plans",
            {"request_id": "req-prod-list-streaming", "project_id": project_id, "plan_id": plan_id},
        )

        assert plan["plan"]["asset_backlog"]
        assert brief["brief"]["budget"]["triangle_budget"] > 0
        assert approved["brief"]["status"] == "approved"
        assert streaming["streaming_plan"]["cell_count"] == 16
        assert readiness["production_ready"] is True
        assert readiness["metrics"]["asset_library_coverage_ratio"] == 1.0
        assert planned_package["package"]["asset_briefs"][0]["brief_id"] == brief_id
        assert Path(written_package["file_paths"][0]).exists()
        assert listed_briefs["count"] == 1
        assert listed_streaming["count"] == 1
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_production_readiness_flags_missing_plan_and_assets(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-prod-empty-project", "name": "Empty"})
        project_id = str(project["project_id"])

        readiness = await _call(
            app,
            "validate_production_readiness",
            {
                "request_id": "req-prod-empty-ready",
                "project_id": project_id,
                "min_asset_briefs": 1,
                "require_asset_library": True,
                "require_streaming_plan": True,
            },
        )

        assert readiness["production_ready"] is False
        assert readiness["severity_summary"]["error"] >= 4
        assert {"missing_production_plan", "not_enough_asset_briefs", "missing_asset_library", "missing_streaming_plan"}.issubset(
            {finding["code"] for finding in readiness["findings"]}
        )
    finally:
        await app.stop()
