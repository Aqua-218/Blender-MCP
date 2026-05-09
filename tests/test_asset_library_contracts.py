from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

ASSET_LIBRARY_TOOLS = {
    "register_asset_library_item",
    "list_asset_library_items",
    "find_asset_library_items",
    "update_asset_library_item",
    "assign_asset_category",
    "add_asset_variant",
    "set_asset_preview",
    "create_asset_collection",
    "instantiate_asset_library_item",
    "validate_asset_library",
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


def _settings(tmp_path: Path) -> ServerSettings:
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
async def test_asset_library_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert ASSET_LIBRARY_TOOLS.issubset(tools)
        for tool_name in ASSET_LIBRARY_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "asset_library"
        assert tools["list_asset_library_items"]["annotations"]["readOnlyHint"] is True
        assert tools["find_asset_library_items"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_asset_library"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_asset_library_workflow_registers_previews_collections_and_instances(tmp_path: Path) -> None:
    app = MCPServerApplication(_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-asset-project", "name": "Asset Library"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {"request_id": "req-asset-cube", "project_id": project_id, "primitive_type": "cube", "name": "HeroCrate"},
        )
        cube_id = str(cube["created_object_ids"][0])

        registered = await _call(
            app,
            "register_asset_library_item",
            {
                "request_id": "req-asset-register",
                "project_id": project_id,
                "asset_name": "Hero Crate",
                "category": "props",
                "tags": ["wood", "crate"],
                "target_id": cube_id,
            },
        )
        asset_id = str(registered["asset_id"])
        listed = await _call(app, "list_asset_library_items", {"request_id": "req-asset-list", "project_id": project_id, "category": "props"})
        found = await _call(app, "find_asset_library_items", {"request_id": "req-asset-find", "project_id": project_id, "query": "crate", "tags": ["wood"]})
        updated = await _call(app, "update_asset_library_item", {"request_id": "req-asset-update", "project_id": project_id, "asset_id": asset_id, "description": "Gameplay crate", "status": "approved"})
        category = await _call(app, "assign_asset_category", {"request_id": "req-asset-category", "project_id": project_id, "asset_id": asset_id, "category": "environment"})
        variant = await _call(app, "add_asset_variant", {"request_id": "req-asset-variant", "project_id": project_id, "asset_id": asset_id, "variant_name": "Damaged"})
        preview = await _call(app, "set_asset_preview", {"request_id": "req-asset-preview", "project_id": project_id, "asset_id": asset_id})
        collection = await _call(app, "create_asset_collection", {"request_id": "req-asset-collection", "project_id": project_id, "asset_id": asset_id})
        instance = await _call(
            app,
            "instantiate_asset_library_item",
            {
                "request_id": "req-asset-instance",
                "project_id": project_id,
                "asset_id": asset_id,
                "location_offset": [3.0, 0.0, 0.0],
                "collection_name": "InstancedAssets",
            },
        )
        validation = await _call(app, "validate_asset_library", {"request_id": "req-asset-validate", "project_id": project_id, "require_preview": True})

        assert registered["asset"]["source_object_ids"] == [cube_id]
        assert listed["count"] == 1
        assert found["assets"][0]["asset_id"] == asset_id
        assert updated["asset"]["status"] == "approved"
        assert category["asset"]["category"] == "environment"
        assert variant["variant"]["target_ids"] == [cube_id]
        assert Path(preview["file_paths"][0]).exists()
        assert collection["collection"]["object_ids"] == [cube_id]
        assert len(instance["created_object_ids"]) == 1
        assert instance["objects"][0]["location"] == [3.0, 0.0, 0.0]
        assert validation["severity_summary"]["error"] == 0
    finally:
        await app.stop()