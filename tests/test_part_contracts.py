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
async def test_generate_parts_creates_entries(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "Parts Demo"})
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "generate_parts",
            {
                "request_id": "req-gen",
                "project_id": project_id,
                "part_hints": ["body", "head"],
            },
        )
        assert result["status"] == "success"
        assert len(result["parts"]) == 2
        names = {p["name"] for p in result["parts"]}
        assert names == {"body", "head"}
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_and_list_parts(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "Parts Demo"})
        project_id = str(project["project_id"])

        add = await _call(
            app,
            "add_part",
            {
                "request_id": "req-add-part",
                "project_id": project_id,
                "name": "wheel",
                "kind": "geometry",
                "tags": ["round", "mechanical"],
                "detail_level": "refined",
            },
        )
        assert add["status"] == "success"
        part_id = add["part"]["part_id"]
        assert add["part"]["detail_level"] == "refined"

        listed = await _call(
            app,
            "list_parts",
            {"request_id": "req-list", "project_id": project_id},
        )
        assert listed["count"] == 1
        assert listed["parts"][0]["part_id"] == part_id
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_part_detail(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "Parts Demo"})
        project_id = str(project["project_id"])

        add = await _call(
            app,
            "add_part",
            {"request_id": "req-add", "project_id": project_id, "name": "engine", "kind": "mechanical"},
        )
        part_id = add["part"]["part_id"]

        updated = await _call(
            app,
            "update_part_detail",
            {"request_id": "req-upd", "project_id": project_id, "part_id": part_id, "detail_level": "hero"},
        )
        assert updated["status"] == "success"
        assert updated["part"]["detail_level"] == "hero"
        assert updated["previous_detail_level"] == "base"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_part(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "Parts Demo"})
        project_id = str(project["project_id"])

        add = await _call(
            app,
            "add_part",
            {"request_id": "req-add", "project_id": project_id, "name": "fin", "kind": "geometry"},
        )
        part_id = add["part"]["part_id"]

        removed = await _call(
            app,
            "remove_part",
            {"request_id": "req-rm", "project_id": project_id, "part_id": part_id},
        )
        assert removed["status"] == "success"
        assert removed["removed_part_id"] == part_id

        listed = await _call(app, "list_parts", {"request_id": "req-list", "project_id": project_id})
        assert listed["count"] == 0
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_nonexistent_part_fails(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-p", "name": "Parts Demo"})
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "remove_part",
            {"request_id": "req-rm", "project_id": project_id, "part_id": "part_nonexistent"},
        )
        assert result["status"] == "failed"
    finally:
        await app.stop()
