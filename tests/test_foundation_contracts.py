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
    return ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(find_free_port()),
        },
        base_dir=tmp_path,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_blender_python_reads_scene_snapshot_and_reports_diff(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-foundation-project", "name": "Foundation Demo"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-foundation-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "FoundationCube",
            },
        )

        result = await _call(
            app,
            "execute_blender_python",
            {
                "request_id": "req-safe-python",
                "project_id": project_id,
                "code": "result = {'mesh_count': sum(1 for item in objects if item['type'] == 'MESH'), 'names': sorted([item['name'] for item in objects])}",
            },
        )

        assert result["status"] == "success"
        assert result["attempts"] == 1
        assert result["execution"]["executed"] is True
        assert result["execution"]["sandbox"] == "read_only_scene_context"
        assert result["execution"]["result"] == {"mesh_count": 1, "names": ["FoundationCube"]}
        assert result["diff"] == {
            "added_object_ids": [],
            "removed_object_ids": [],
            "modified_object_ids": [],
            "added_count": 0,
            "removed_count": 0,
            "modified_count": 0,
        }
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_blender_python_dry_run_validates_without_executing(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-foundation-dry-project", "name": "Foundation Dry"})
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "execute_blender_python",
            {
                "request_id": "req-safe-python-dry",
                "project_id": project_id,
                "code": "result = len(objects)",
                "dry_run": True,
            },
        )

        assert result["status"] == "success"
        assert result["dry_run"] is True
        assert result["execution"]["validated"] is True
        assert result["execution"]["executed"] is False
        assert result["diff"]["added_count"] == 0
        assert "result" not in result["execution"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_blender_python_rejects_unsafe_code_with_failure_classification(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-foundation-unsafe-project", "name": "Foundation Unsafe"})
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "execute_blender_python",
            {
                "request_id": "req-safe-python-unsafe",
                "project_id": project_id,
                "code": "import os\nresult = os.listdir('.')",
            },
        )

        assert result["status"] == "failed"
        assert result["failure_classification"] == {
            "category": "security_violation",
            "retryable": False,
            "error_code": "validation_error",
        }
        assert result["attempts"] == 1
        assert "Safe Blender Python rejected" in result["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_blender_python_allows_viewer_role(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        decision = app.context.policy.authorize(
            tool_name="execute_blender_python",
            role="viewer",
            destructive_confirmation=False,
            blast_radius=0,
            overwrite=False,
        )
        assert decision.allowed is True
    finally:
        await app.stop()
