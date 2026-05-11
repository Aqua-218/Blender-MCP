from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.models.common import failed_result
from mcp_server.serialization import json_loads
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
async def test_scene_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "create_scene",
            "place_asset",
            "scatter_assets",
            "arrange_scene",
            "generate_background",
            "generate_environment",
            "create_composition",
        }.issubset(tool_names)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_scene_keeps_ground_when_ground_material_creation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_ground_material(_context, request):  # type: ignore[no-untyped-def]
        return failed_result(
            request_id=request.request_id,
            tool_name="create_pbr_material",
            summary="Principled BSDF node is unavailable.",
            errors=["blender_execution_error: Principled BSDF node is unavailable."],
        )

    monkeypatch.setattr("mcp_server.tools.scene.create_pbr_material", fail_ground_material)
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Scene Material Fallback"})
        project_id = str(project["project_id"])

        scene = await _call(
            app,
            "create_scene",
            {
                "request_id": "req-scene-material-fallback",
                "project_id": project_id,
                "name": "Fallback Scene",
            },
        )

        assert scene["status"] == "partial_success"
        assert scene["created_object_ids"]
        assert scene["material"] is None
        assert "Ground material was skipped" in scene["warnings"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scene_tools_compose_existing_asset_and_render_workflows(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Scene Tools"})
        project_id = str(project["project_id"])

        furniture = await _call(
            app,
            "create_furniture",
            {
                "request_id": "req-furniture",
                "project_id": project_id,
                "name": "Scatter Chair",
                "furniture_type": "chair",
            },
        )
        asset_id = str(furniture["asset_id"])

        scene = await _call(
            app,
            "create_scene",
            {
                "request_id": "req-scene",
                "project_id": project_id,
                "name": "Review Scene",
                "scene_type": "studio",
            },
        )
        scene_id = str(scene["scene_id"])
        assert scene["status"] == "success"
        assert scene["created_object_ids"]

        placed = await _call(
            app,
            "place_asset",
            {
                "request_id": "req-place",
                "project_id": project_id,
                "scene_id": scene_id,
                "asset_id": asset_id,
                "location": [2.0, 1.5, 0.0],
            },
        )
        assert placed["status"] == "success"
        assert len(placed["created_object_ids"]) >= 4

        scattered = await _call(
            app,
            "scatter_assets",
            {
                "request_id": "req-scatter",
                "project_id": project_id,
                "scene_id": scene_id,
                "asset_ids": [asset_id],
                "count": 3,
                "area_min": [-3.0, -3.0, 0.0],
                "area_max": [3.0, 3.0, 0.0],
                "seed": 17,
            },
        )
        assert scattered["status"] == "success"
        assert len(scattered["placements"]) == 3

        arranged = await _call(
            app,
            "arrange_scene",
            {
                "request_id": "req-arrange",
                "project_id": project_id,
                "target_ids": placed["created_object_ids"][:2],
                "arrangement": "line",
                "origin": [0.0, -2.0, 0.0],
                "spacing": 1.25,
            },
        )
        assert arranged["status"] == "success"
        arranged_first = json_loads(app.context.entities.get(str(placed["created_object_ids"][0])).spec_json)
        arranged_second = json_loads(app.context.entities.get(str(placed["created_object_ids"][1])).spec_json)
        assert arranged_first["location"] == [0.0, -2.0, 0.0]
        assert arranged_second["location"] == [1.25, -2.0, 0.0]

        background = await _call(
            app,
            "generate_background",
            {
                "request_id": "req-background",
                "project_id": project_id,
                "scene_id": scene_id,
                "style": "sunset",
            },
        )
        assert background["status"] == "success"
        assert background["created_object_ids"]

        environment = await _call(
            app,
            "generate_environment",
            {
                "request_id": "req-environment",
                "project_id": project_id,
                "scene_id": scene_id,
                "mood": "clean product shot",
                "render_preset_name": "thumbnail",
            },
        )
        assert environment["status"] == "success"
        assert len(environment["created_object_ids"]) >= 2
        assert environment["render_settings"]["resolution_x"] == 320

        composition = await _call(
            app,
            "create_composition",
            {
                "request_id": "req-composition",
                "project_id": project_id,
                "scene_id": scene_id,
                "name": "Hero Shot",
                "target_id": placed["created_object_ids"][0],
                "preset_name": "preview",
            },
        )
        assert composition["status"] == "success"
        assert composition["camera"]["camera_id"]
        assert composition["active_camera_id"] == composition["camera"]["camera_id"]
        assert composition["render_settings"]["resolution_x"] == 768
    finally:
        await app.stop()
