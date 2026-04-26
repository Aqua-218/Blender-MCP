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
async def test_texture_uv_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "unwrap_uv",
            "pack_uv",
            "inspect_uv",
            "apply_texture",
            "create_procedural_texture",
            "bake_texture",
        }.issubset(tool_names)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_texture_uv_tools_manage_uv_metadata_and_bake_outputs(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Texture UV"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "TextureCube",
            },
        )
        cube_id = str(cube["created_object_ids"][0])

        unwrapped = await _call(
            app,
            "unwrap_uv",
            {
                "request_id": "req-unwrap",
                "project_id": project_id,
                "target_id": cube_id,
                "method": "smart",
            },
        )
        assert unwrapped["status"] == "success"
        uv_map_id = str(unwrapped["created_uv_map_ids"][0])

        packed = await _call(
            app,
            "pack_uv",
            {
                "request_id": "req-pack",
                "project_id": project_id,
                "uv_map_ids": [uv_map_id],
                "padding": 0.03,
            },
        )
        assert packed["status"] == "success"
        assert packed["uv_maps"][0]["packed"] is True

        inspected = await _call(
            app,
            "inspect_uv",
            {
                "request_id": "req-inspect",
                "project_id": project_id,
                "target_id": cube_id,
            },
        )
        assert inspected["status"] == "success"
        assert inspected["count"] == 1
        assert inspected["uv_maps"][0]["packed"] is True

        texture = await _call(
            app,
            "create_procedural_texture",
            {
                "request_id": "req-texture",
                "project_id": project_id,
                "name": "CheckerSurface",
                "texture_type": "checker",
            },
        )
        assert texture["status"] == "success"

        applied = await _call(
            app,
            "apply_texture",
            {
                "request_id": "req-apply-texture",
                "project_id": project_id,
                "texture_id": texture["texture_id"],
                "target_id": cube_id,
            },
        )
        assert applied["status"] in {"success", "partial_success"}
        assert cube_id in applied["modified_object_ids"]

        baked = await _call(
            app,
            "bake_texture",
            {
                "request_id": "req-bake",
                "project_id": project_id,
                "target_id": cube_id,
                "texture_id": texture["texture_id"],
                "bake_type": "base_color",
            },
        )
        assert baked["status"] == "success"
        output_path = Path(baked["file_paths"][0])
        assert output_path.exists()
        assert output_path.suffix == ".png"
    finally:
        await app.stop()