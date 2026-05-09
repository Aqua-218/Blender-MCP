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
            "list_uv_maps",
            "rename_uv_map",
            "set_uv_density",
            "assign_udim_tile",
            "create_udim_tile_plan",
            "mirror_uv_layout",
            "generate_texture_set_manifest",
            "plan_texture_bake",
            "bake_texture_set",
            "create_texture_atlas_manifest",
            "create_trim_sheet_manifest",
            "validate_uv_layout",
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_uv_layout_utility_pack_manages_density_udim_and_manifests(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-uv-project", "name": "UV Utilities"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {"request_id": "req-uv-cube", "project_id": project_id, "primitive_type": "cube", "name": "UDIMCrate"},
        )
        cube_id = str(cube["created_object_ids"][0])
        unwrapped = await _call(app, "unwrap_uv", {"request_id": "req-uv-unwrap", "project_id": project_id, "target_id": cube_id})
        uv_map_id = str(unwrapped["created_uv_map_ids"][0])

        renamed = await _call(app, "rename_uv_map", {"request_id": "req-uv-rename", "project_id": project_id, "uv_map_id": uv_map_id, "name": "Crate_Main_UV"})
        density = await _call(app, "set_uv_density", {"request_id": "req-uv-density", "project_id": project_id, "uv_map_ids": [uv_map_id], "texels_per_unit": 1024.0})
        udim = await _call(app, "assign_udim_tile", {"request_id": "req-uv-udim", "project_id": project_id, "uv_map_ids": [uv_map_id], "tile_number": 1002})
        mirrored = await _call(app, "mirror_uv_layout", {"request_id": "req-uv-mirror", "project_id": project_id, "uv_map_ids": [uv_map_id], "axis": "v"})
        plan = await _call(app, "create_udim_tile_plan", {"request_id": "req-uv-plan", "project_id": project_id, "target_id": cube_id, "name": "Crate UDIM"})
        texture = await _call(app, "create_procedural_texture", {"request_id": "req-uv-texture", "project_id": project_id, "name": "CrateNoise"})
        manifest = await _call(
            app,
            "generate_texture_set_manifest",
            {
                "request_id": "req-uv-manifest",
                "project_id": project_id,
                "target_id": cube_id,
                "name": "CrateTextureSet",
                "texture_ids": [texture["texture_id"]],
            },
        )
        bake_plan = await _call(
            app,
            "plan_texture_bake",
            {
                "request_id": "req-uv-bake-plan",
                "project_id": project_id,
                "target_id": cube_id,
                "channels": ["base_color", "normal"],
            },
        )
        baked_set = await _call(
            app,
            "bake_texture_set",
            {
                "request_id": "req-uv-bake-set",
                "project_id": project_id,
                "target_id": cube_id,
                "texture_id": texture["texture_id"],
                "channels": ["base_color", "normal"],
                "output_prefix": "crate-bake",
            },
        )
        atlas = await _call(
            app,
            "create_texture_atlas_manifest",
            {
                "request_id": "req-uv-atlas",
                "project_id": project_id,
                "target_id": cube_id,
                "name": "Crate Atlas",
            },
        )
        trim = await _call(
            app,
            "create_trim_sheet_manifest",
            {
                "request_id": "req-uv-trim",
                "project_id": project_id,
                "target_id": cube_id,
                "name": "Crate Trim",
                "row_count": 2,
                "column_count": 3,
            },
        )
        listed = await _call(app, "list_uv_maps", {"request_id": "req-uv-list", "project_id": project_id, "target_id": cube_id})
        validation = await _call(app, "validate_uv_layout", {"request_id": "req-uv-validate", "project_id": project_id, "target_id": cube_id, "require_udim": True})

        assert renamed["uv_map"]["name"] == "Crate_Main_UV"
        assert density["uv_maps"][0]["texels_per_unit"] == 1024.0
        assert udim["uv_maps"][0]["udim_tile"] == 1002
        assert mirrored["uv_maps"][0]["mirror_axis"] == "v"
        assert plan["udim_plan"]["assignments"][0]["tile_number"] == 1001
        assert manifest["texture_set_manifest"]["texture_ids"] == [texture["texture_id"]]
        assert bake_plan["bake_jobs"][0]["channels"] == ["base_color", "normal"]
        assert len(baked_set["file_paths"]) == 2
        assert all(Path(path).exists() for path in baked_set["file_paths"])
        assert atlas["texture_atlas_manifest"]["uv_map_ids"] == [uv_map_id]
        assert len(trim["trim_sheet_manifest"]["cells"]) == 6
        assert listed["count"] == 1
        assert validation["severity_summary"]["error"] == 0
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_uv_layout_utility_pack_returns_structured_failures(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-uv-fail-project", "name": "UV Failures"})
        project_id = str(project["project_id"])

        failed = await _call(
            app,
            "set_uv_density",
            {
                "request_id": "req-uv-fail-density",
                "project_id": project_id,
                "uv_map_ids": ["uv_missing"],
                "texels_per_unit": 512.0,
            },
        )

        assert failed["status"] == "failed"
        assert failed["tool_name"] == "set_uv_density"
        assert "target_not_found" in failed["errors"][0]
    finally:
        await app.stop()