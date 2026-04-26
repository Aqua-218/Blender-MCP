from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_initialize_tools_list_and_ping(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        initialize = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0.0"},
                },
            }
        )
        tools = await app.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        assert app._started is False
        ping = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "ping_bridge",
                    "arguments": {"request_id": "req-1"},
                },
            }
        )
        assert initialize["result"]["serverInfo"]["name"] == "blender-mcp"
        assert initialize["result"]["protocolVersion"] == "2024-11-05"
        assert {tool["name"] for tool in tools["result"]["tools"]} >= {"ping_bridge", "get_runtime_info"}
        assert ping["result"]["status"] == "success"
        assert app._started is True

        role_override = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ping_bridge",
                    "role": "operator",
                    "arguments": {"request_id": "req-role"},
                },
            }
        )
        assert role_override["result"]["status"] == "failed"
        assert "caller-supplied role" in role_override["result"]["summary"].lower()

        initialized_notification = await app.handle_jsonrpc(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        assert initialized_notification is None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_safe_config_and_server_metrics_tools(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ping_bridge", "arguments": {"request_id": "req-ping"}},
            }
        )
        safe_config = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_safe_config", "arguments": {"request_id": "req-config"}},
            }
        )
        metrics = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_server_metrics", "arguments": {"request_id": "req-metrics"}},
            }
        )

        assert safe_config["result"]["status"] == "success"
        assert safe_config["result"]["config"]["controller_port"] == port
        assert "controller_secret" not in safe_config["result"]["config"]
        assert safe_config["result"]["config"]["http_auth_enabled"] is False
        assert metrics["result"]["status"] == "success"
        assert metrics["result"]["metrics"]["tool_calls"]["total"] >= 2
        assert metrics["result"]["metrics"]["controller"]["available"] is True
        assert "system" in metrics["result"]["metrics"]["latency_ms"]["by_family"]
        assert "percentiles_ms" in metrics["result"]["metrics"]["latency_ms"]["by_family"]["system"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_metrics_track_render_and_export_breakdowns(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "create_project",
                    "arguments": {"request_id": "req-project", "name": "Metrics Project"},
                },
            }
        )
        project_id = str(project["result"]["project_id"])
        await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "create_primitive",
                    "arguments": {
                        "request_id": "req-cube",
                        "project_id": project_id,
                        "primitive_type": "cube",
                        "name": "MetricsCube",
                    },
                },
            }
        )
        await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "render_preview",
                    "arguments": {
                        "request_id": "req-render",
                        "project_id": project_id,
                        "output_path": "metrics/render.png",
                    },
                },
            }
        )
        await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "export_scene",
                    "arguments": {
                        "request_id": "req-export",
                        "project_id": project_id,
                        "export_format": "glb",
                        "output_path": "metrics/export.glb",
                    },
                },
            }
        )
        metrics = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "get_server_metrics", "arguments": {"request_id": "req-metrics"}},
            }
        )

        render_metrics = metrics["result"]["metrics"]["renders"]
        export_metrics = metrics["result"]["metrics"]["exports"]
        assert render_metrics["by_preset"]["preview"]["count"] >= 1
        assert render_metrics["by_preset"]["preview"]["avg_duration_ms"] >= 0.0
        assert export_metrics["by_format"]["glb"]["count"] >= 1
        assert export_metrics["by_format"]["glb"]["success_rate"] == 1.0
        assert metrics["result"]["metrics"]["latency_ms"]["by_family"]["render"]["percentiles_ms"]["p95_ms"] >= 0.0
    finally:
        await app.stop()