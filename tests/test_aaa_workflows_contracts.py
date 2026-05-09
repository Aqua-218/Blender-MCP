from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from mcp_server.tools.aaa_workflows import WORKFLOW_CATALOG
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
async def test_aaa_workflow_pack_registers_more_than_500_tools(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        aaa_tools = {
            name: tool
            for name, tool in tools.items()
            if tool["annotations"]["family"] == "aaa_workflows"
        }

        assert len(WORKFLOW_CATALOG) == 520
        assert len(aaa_tools) == 520
        assert len(tools) >= 500
        assert aaa_tools["aaa_001_hero_character_brief"]["annotations"]["readOnlyHint"] is True
        assert aaa_tools["aaa_520_world_signage_review"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aaa_workflow_recipe_returns_actionable_tool_chain(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        result = await _call(
            app,
            "aaa_337_lod_pass_optimize",
            {
                "request_id": "req-aaa-lod",
                "goal": "Prepare a boss arena kit for Unreal runtime budgets.",
                "target_engine": "unreal",
                "quality_bar": "shipping",
                "constraints": ["60fps", "Nanite fallback", "console memory budget"],
            },
        )
        workflow = result["workflow"]

        assert result["status"] == "success"
        assert workflow["domain"] == "lod_pass"
        assert workflow["phase"] == "optimize"
        assert workflow["target_engine"] == "unreal"
        assert workflow["quality_bar"] == "shipping"
        assert "create_lod_chain" in {
            step["tool_name"] for step in workflow["recommended_tool_chain"]
        }
        assert "validate_game_export_readiness" in {
            step["tool_name"] for step in workflow["recommended_tool_chain"]
        }
        assert workflow["acceptance_criteria"]
        assert workflow["risk_controls"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_aaa_workflow_recipe_can_trim_optional_sections(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        result = await _call(
            app,
            "aaa_200_sky_weather_review",
            {
                "request_id": "req-aaa-trimmed",
                "include_tool_chain": False,
                "include_acceptance_criteria": False,
            },
        )
        workflow = result["workflow"]

        assert result["status"] == "success"
        assert workflow["domain"] == "sky_weather"
        assert workflow["phase"] == "review"
        assert "recommended_tool_chain" not in workflow
        assert "acceptance_criteria" not in workflow
    finally:
        await app.stop()
