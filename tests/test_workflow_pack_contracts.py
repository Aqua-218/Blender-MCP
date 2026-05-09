from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

TRANSFORM_TOOLS = {
    "reset_object_transforms",
    "offset_object_transforms",
    "match_object_transform",
    "align_objects",
    "distribute_objects",
    "snap_objects_to_grid",
    "place_objects_on_ground",
    "arrange_objects_in_grid",
    "mirror_object_transforms",
}

SELECTION_SET_TOOLS = {
    "save_selection_set",
    "list_selection_sets",
    "select_selection_set",
    "update_selection_set",
    "add_to_selection_set",
    "remove_from_selection_set",
    "rename_selection_set",
}

MATERIAL_NODE_TOOLS = {
    "add_material_node",
    "set_material_node_param",
    "connect_material_nodes",
    "list_material_nodes",
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


async def _create_cube(
    app: MCPServerApplication,
    project_id: str,
    request_id: str,
    name: str,
    location: list[float] | None = None,
) -> str:
    result = await _call(
        app,
        "create_primitive",
        {
            "request_id": request_id,
            "project_id": project_id,
            "primitive_type": "cube",
            "name": name,
            "location": location or [0.0, 0.0, 0.0],
        },
    )
    return str(result["created_object_ids"][0])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workflow_pack_tools_are_registered_with_families(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert TRANSFORM_TOOLS.issubset(tools)
        assert SELECTION_SET_TOOLS.issubset(tools)
        assert MATERIAL_NODE_TOOLS.issubset(tools)
        for tool_name in TRANSFORM_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "transforms"
            assert tools[tool_name]["annotations"]["readOnlyHint"] is False
        for tool_name in SELECTION_SET_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "selection_sets"
        assert tools["list_selection_sets"]["annotations"]["readOnlyHint"] is True
        assert tools["list_material_nodes"]["annotations"]["family"] == "material"
        assert tools["list_material_nodes"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transform_pack_updates_mock_runtime_transforms(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-transform-project", "name": "Transforms"})
        project_id = str(project["project_id"])
        object_ids = [
            await _create_cube(app, project_id, "req-transform-a", "A", [0.25, 0.0, 4.0]),
            await _create_cube(app, project_id, "req-transform-b", "B", [3.25, 0.0, 1.0]),
            await _create_cube(app, project_id, "req-transform-c", "C", [8.25, 0.0, -2.0]),
        ]

        arranged = await _call(
            app,
            "arrange_objects_in_grid",
            {
                "request_id": "req-transform-arrange",
                "project_id": project_id,
                "target_ids": object_ids,
                "columns": 2,
                "origin": [10.0, 0.0, 0.0],
                "spacing": [2.0, 3.0, 0.0],
            },
        )
        assert [item["location"] for item in arranged["objects"]] == [
            [10.0, 0.0, 0.0],
            [12.0, 0.0, 0.0],
            [10.0, 3.0, 0.0],
        ]

        aligned = await _call(
            app,
            "align_objects",
            {
                "request_id": "req-transform-align",
                "project_id": project_id,
                "target_ids": object_ids,
                "axis": "z",
                "align_to": "min",
                "target_value": 0.0,
            },
        )
        assert {item["location"][2] for item in aligned["objects"]} == {0.5}

        distributed = await _call(
            app,
            "distribute_objects",
            {
                "request_id": "req-transform-distribute",
                "project_id": project_id,
                "target_ids": object_ids,
                "axis": "x",
                "spacing": 2.0,
                "start_value": 0.0,
            },
        )
        assert [item["location"][0] for item in distributed["objects"]] == [0.0, 2.0, 4.0]

        offset = await _call(
            app,
            "offset_object_transforms",
            {
                "request_id": "req-transform-offset",
                "project_id": project_id,
                "target_id": object_ids[0],
                "location_offset": [0.26, 0.0, 0.0],
                "rotation_offset": [0.1, 0.2, 0.3],
                "scale_multiplier": [2.0, 1.0, 1.0],
            },
        )
        assert offset["objects"][0]["location"][0] == 0.26
        assert offset["objects"][0]["rotation"] == [0.1, 0.2, 0.3]
        assert offset["objects"][0]["scale"] == [2.0, 1.0, 1.0]

        snapped = await _call(
            app,
            "snap_objects_to_grid",
            {
                "request_id": "req-transform-snap",
                "project_id": project_id,
                "target_id": object_ids[0],
                "grid_size": 0.5,
                "axes": ["x"],
            },
        )
        assert snapped["objects"][0]["location"][0] == 0.5

        grounded = await _call(
            app,
            "place_objects_on_ground",
            {
                "request_id": "req-transform-ground",
                "project_id": project_id,
                "target_id": object_ids[1],
                "ground_z": 1.0,
            },
        )
        assert grounded["objects"][0]["location"][2] == 1.5

        mirrored = await _call(
            app,
            "mirror_object_transforms",
            {
                "request_id": "req-transform-mirror",
                "project_id": project_id,
                "target_id": object_ids[1],
                "axis": "x",
                "pivot": 1.0,
                "flip_scale": True,
            },
        )
        assert mirrored["objects"][0]["location"][0] == -2.0
        assert mirrored["objects"][0]["scale"] == [-1.0, 1.0, 1.0]

        matched = await _call(
            app,
            "match_object_transform",
            {
                "request_id": "req-transform-match",
                "project_id": project_id,
                "source_id": object_ids[0],
                "target_id": object_ids[1],
            },
        )
        assert matched["objects"][0]["location"] == snapped["objects"][0]["location"]
        assert matched["objects"][0]["rotation"] == [0.1, 0.2, 0.3]

        reset = await _call(
            app,
            "reset_object_transforms",
            {
                "request_id": "req-transform-reset",
                "project_id": project_id,
                "target_ids": object_ids,
            },
        )
        assert {tuple(item["location"]) for item in reset["objects"]} == {(0.0, 0.0, 0.0)}
        assert {tuple(item["rotation"]) for item in reset["objects"]} == {(0.0, 0.0, 0.0)}
        assert {tuple(item["scale"]) for item in reset["objects"]} == {(1.0, 1.0, 1.0)}
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selection_set_pack_manages_membership_without_deleting_objects(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-sel-project", "name": "Selection Sets"})
        project_id = str(project["project_id"])
        hero = await _create_cube(app, project_id, "req-sel-hero", "Hero")
        prop = await _create_cube(app, project_id, "req-sel-prop", "Prop")
        fx = await _create_cube(app, project_id, "req-sel-fx", "FX")

        saved = await _call(
            app,
            "save_selection_set",
            {
                "request_id": "req-sel-save",
                "project_id": project_id,
                "name": "ReviewSet",
                "description": "Objects for review",
                "target_ids": [hero, prop],
            },
        )
        selection_set_id = str(saved["selection_set_id"])
        assert saved["selection_set"]["target_ids"] == [hero, prop]

        added = await _call(
            app,
            "add_to_selection_set",
            {
                "request_id": "req-sel-add",
                "project_id": project_id,
                "name": "ReviewSet",
                "names": ["FX"],
            },
        )
        assert added["selection_set"]["target_ids"] == [hero, prop, fx]

        removed = await _call(
            app,
            "remove_from_selection_set",
            {
                "request_id": "req-sel-remove",
                "project_id": project_id,
                "name": "ReviewSet",
                "target_id": hero,
            },
        )
        assert removed["selection_set"]["target_ids"] == [prop, fx]

        renamed = await _call(
            app,
            "rename_selection_set",
            {
                "request_id": "req-sel-rename",
                "project_id": project_id,
                "selection_set_id": selection_set_id,
                "new_name": "ShotReview",
            },
        )
        assert renamed["selection_set"]["name"] == "ShotReview"

        updated = await _call(
            app,
            "update_selection_set",
            {
                "request_id": "req-sel-update",
                "project_id": project_id,
                "name": "ShotReview",
                "target_ids": [fx],
            },
        )
        assert updated["selection_set"]["target_ids"] == [fx]

        selected = await _call(
            app,
            "select_selection_set",
            {
                "request_id": "req-sel-select",
                "project_id": project_id,
                "name": "ShotReview",
            },
        )
        assert selected["selected_ids"] == [fx]

        listed = await _call(app, "list_selection_sets", {"request_id": "req-sel-list", "project_id": project_id})
        assert listed["count"] == 1
        assert listed["selection_sets"][0]["name"] == "ShotReview"

        objects = await _call(app, "list_objects", {"request_id": "req-sel-objects", "project_id": project_id})
        assert {item["object_id"] for item in objects["objects"]} == {hero, prop, fx}
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_material_node_pack_authors_mock_node_graph(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-node-project", "name": "Material Nodes"})
        project_id = str(project["project_id"])
        material = await _call(
            app,
            "create_pbr_material",
            {
                "request_id": "req-node-material",
                "project_id": project_id,
                "name": "LayeredSurface",
                "base_color": [0.2, 0.3, 0.4, 1.0],
            },
        )
        material_id = str(material["material"]["material_id"])

        noise = await _call(
            app,
            "add_material_node",
            {
                "request_id": "req-node-noise",
                "project_id": project_id,
                "material_id": material_id,
                "node_type": "ShaderNodeTexNoise",
                "node_name": "SurfaceNoise",
                "location": [-300.0, 120.0],
                "params": {"scale": 18.0},
            },
        )
        ramp = await _call(
            app,
            "add_material_node",
            {
                "request_id": "req-node-ramp",
                "project_id": project_id,
                "material_id": material_id,
                "node_type": "ShaderNodeValToRGB",
                "node_name": "PaletteRamp",
            },
        )
        assert noise["status"] == "success"
        assert ramp["status"] == "success"

        updated = await _call(
            app,
            "set_material_node_param",
            {
                "request_id": "req-node-param",
                "project_id": project_id,
                "material_id": material_id,
                "node_id": noise["node"]["node_id"],
                "param_name": "detail",
                "value": 9.0,
            },
        )
        assert updated["node"]["params"] == {"scale": 18.0, "detail": 9.0}

        linked = await _call(
            app,
            "connect_material_nodes",
            {
                "request_id": "req-node-link",
                "project_id": project_id,
                "material_id": material_id,
                "from_node_id": noise["node"]["node_id"],
                "from_socket": "Fac",
                "to_node_id": ramp["node"]["node_id"],
                "to_socket": "Fac",
            },
        )
        assert linked["link"]["from_node_id"] == noise["node"]["node_id"]

        listed = await _call(
            app,
            "list_material_nodes",
            {
                "request_id": "req-node-list",
                "project_id": project_id,
                "material_id": material_id,
            },
        )
        assert {node["node_name"] for node in listed["nodes"]} == {"SurfaceNoise", "PaletteRamp"}
        assert listed["links"] == [linked["link"]]
    finally:
        await app.stop()