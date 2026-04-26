from __future__ import annotations

import asyncio
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
@pytest.mark.soak
@pytest.mark.asyncio
async def test_repeated_render_queue_stays_healthy(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Render Queue"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "QueueCube",
            },
        )

        results = await asyncio.gather(
            *[
                _call(
                    app,
                    "render_preview",
                    {
                        "request_id": f"req-render-{index}",
                        "project_id": project_id,
                        "output_path": f"queue/render-{index}.png",
                    },
                )
                for index in range(6)
            ]
        )
        metrics = await _call(app, "get_server_metrics", {"request_id": "req-metrics"})

        assert all(result["status"] == "success" for result in results)
        assert metrics["metrics"]["renders"]["by_preset"]["preview"]["count"] >= 6
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.soak
@pytest.mark.asyncio
async def test_repeated_snapshot_loop_preserves_recent_history(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Snapshot Loop"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "SnapshotCube",
            },
        )

        created_ids: list[str] = []
        for index in range(8):
            snapshot = await _call(
                app,
                "create_snapshot",
                {"request_id": f"req-snapshot-{index}", "project_id": project_id},
            )
            created_ids.append(str(snapshot["snapshot_id"]))

        listed = await _call(app, "list_snapshots", {"request_id": "req-list", "project_id": project_id})
        listed_ids = {snapshot["snapshot_id"] for snapshot in listed["snapshots"]}

        assert set(created_ids).issubset(listed_ids)
        assert len(listed["snapshots"]) >= 8
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.soak
@pytest.mark.asyncio
async def test_scatter_assets_rejects_overload_above_contract_limit(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Scatter Overload"})
        response = await app.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": "scatter-overload",
                "method": "tools/call",
                "params": {
                    "name": "scatter_assets",
                    "arguments": {
                        "request_id": "req-scatter-overload",
                        "project_id": str(project["project_id"]),
                        "count": 65,
                    },
                },
            }
        )

        assert response["result"]["status"] == "failed"
        assert "less than or equal to 64" in response["result"]["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.soak
@pytest.mark.asyncio
async def test_long_session_controller_stays_available(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Long Session"})
        project_id = str(project["project_id"])
        await _call(app, "ping_bridge", {"request_id": "req-ping-start"})
        first_process = app.context.bridge._process
        assert first_process is not None
        first_pid = first_process.pid

        for index in range(12):
            await _call(app, "list_objects", {"request_id": f"req-list-{index}", "project_id": project_id})
            await _call(app, "get_runtime_info", {"request_id": f"req-runtime-{index}"})
            await _call(app, "create_snapshot", {"request_id": f"req-snapshot-{index}", "project_id": project_id})

        current_process = app.context.bridge._process
        assert current_process is not None
        assert current_process.pid == first_pid
        assert app.context.metrics["controller"]["available"] is True
        assert app.context.metrics["snapshots"]["count"] >= 12
    finally:
        await app.stop()