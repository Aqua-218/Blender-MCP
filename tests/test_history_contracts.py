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
async def test_list_operations_returns_recent(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {"request_id": "req-prim", "project_id": project_id, "primitive_type": "cube"},
        )

        result = await _call(
            app,
            "list_operations",
            {"request_id": "req-list-ops", "project_id": project_id, "limit": 10},
        )
        assert result["status"] == "success"
        assert result["count"] >= 1
        tool_names = [op["tool_name"] for op in result["operations"]]
        assert "create_primitive" in tool_names
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_snapshots_returns_created(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])

        snap = await _call(
            app,
            "create_snapshot",
            {"request_id": "req-snap", "project_id": project_id},
        )
        snapshot_id = snap["snapshot_id"]

        result = await _call(
            app,
            "list_snapshots",
            {"request_id": "req-list-snaps", "project_id": project_id},
        )
        assert result["status"] == "success"
        ids = [s["snapshot_id"] for s in result["snapshots"]]
        assert snapshot_id in ids
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_compare_snapshots_detects_added_object(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])

        snap_a = await _call(app, "create_snapshot", {"request_id": "req-snap-a", "project_id": project_id})
        snap_a_id = snap_a["snapshot_id"]

        await _call(
            app,
            "create_primitive",
            {"request_id": "req-prim", "project_id": project_id, "primitive_type": "cube"},
        )

        snap_b = await _call(app, "create_snapshot", {"request_id": "req-snap-b", "project_id": project_id})
        snap_b_id = snap_b["snapshot_id"]

        result = await _call(
            app,
            "compare_snapshots",
            {
                "request_id": "req-compare",
                "project_id": project_id,
                "snapshot_id_a": snap_a_id,
                "snapshot_id_b": snap_b_id,
            },
        )
        assert result["status"] == "success"
        diff = result["diff"]
        assert diff["added_count"] == 1
        assert diff["removed_count"] == 0
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_compare_snapshots_missing_id_returns_failed(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])

        snap = await _call(app, "create_snapshot", {"request_id": "req-snap", "project_id": project_id})
        snap_id = snap["snapshot_id"]

        result = await _call(
            app,
            "compare_snapshots",
            {
                "request_id": "req-compare",
                "project_id": project_id,
                "snapshot_id_a": snap_id,
                "snapshot_id_b": "snapshot_nonexistent",
            },
        )
        assert result["status"] == "failed"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_diff_summary_returns_human_readable_text(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])

        snap_a = await _call(app, "create_snapshot", {"request_id": "req-snap-a", "project_id": project_id})
        await _call(
            app,
            "create_primitive",
            {"request_id": "req-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        snap_b = await _call(app, "create_snapshot", {"request_id": "req-snap-b", "project_id": project_id})

        result = await _call(
            app,
            "generate_diff_summary",
            {
                "request_id": "req-diff-summary",
                "project_id": project_id,
                "snapshot_id_a": snap_a["snapshot_id"],
                "snapshot_id_b": snap_b["snapshot_id"],
            },
        )

        assert result["status"] == "success"
        assert "Added: 1" in result["diff_summary"]
        assert "Modified: 0" in result["diff_summary"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_comparison_views_outputs_two_images_and_restores_state(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])
        camera = await _call(
            app,
            "create_camera",
            {"request_id": "req-camera", "project_id": project_id, "name": "CompareCam"},
        )
        await _call(
            app,
            "set_active_camera",
            {"request_id": "req-camera-active", "project_id": project_id, "camera_id": camera["camera"]["camera_id"]},
        )

        snap_a = await _call(app, "create_snapshot", {"request_id": "req-snap-a", "project_id": project_id})
        await _call(
            app,
            "create_primitive",
            {"request_id": "req-prim", "project_id": project_id, "primitive_type": "cube", "name": "Cube"},
        )
        snap_b = await _call(app, "create_snapshot", {"request_id": "req-snap-b", "project_id": project_id})

        result = await _call(
            app,
            "render_comparison_views",
            {
                "request_id": "req-compare-render",
                "project_id": project_id,
                "snapshot_id_a": snap_a["snapshot_id"],
                "snapshot_id_b": snap_b["snapshot_id"],
                "camera_id": camera["camera"]["camera_id"],
            },
        )
        objects_after = await _call(
            app,
            "list_objects",
            {"request_id": "req-list-after", "project_id": project_id},
        )

        assert result["status"] == "success"
        assert len(result["image_paths"]) == 2
        assert all(Path(path).exists() for path in result["image_paths"])
        assert any(item["name"] == "Cube" for item in objects_after["objects"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_generation_history_alias_returns_operations(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "History Demo"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {"request_id": "req-prim", "project_id": project_id, "primitive_type": "cube"},
        )

        history = await _call(
            app,
            "get_generation_history",
            {"request_id": "req-history", "project_id": project_id, "limit": 5},
        )

        assert history["status"] == "success"
        assert history["tool_name"] == "get_generation_history"
        assert history["count"] >= 1
    finally:
        await app.stop()
