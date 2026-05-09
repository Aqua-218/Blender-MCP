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


def _make_settings(tmp_path: Path) -> tuple[ServerSettings, int]:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    return settings, port


MODIFIER_CONVENIENCE_TOOLS = {
    "add_bevel_modifier",
    "add_mirror_modifier",
    "add_array_modifier",
    "add_solidify_modifier",
    "add_subdivision_modifier",
    "add_triangulate_modifier",
    "add_weld_modifier",
    "add_remesh_modifier",
    "add_displace_modifier",
    "add_weighted_normal_modifier",
}


def _modifier_named(modifiers: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(modifier for modifier in modifiers if modifier["name"] == name)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_modifier_convenience_tools_are_registered(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        listed = await app.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert MODIFIER_CONVENIENCE_TOOLS.issubset(tools)
        for tool_name in MODIFIER_CONVENIENCE_TOOLS:
            tool = tools[tool_name]
            assert tool["annotations"]["family"] == "modifiers"
            assert tool["annotations"]["readOnlyHint"] is False
            assert "Non-destructively add" in tool["description"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_and_list_modifiers(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-mod-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-mod-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        add = await _call(
            app,
            "add_modifier",
            {
                "request_id": "req-add-mod",
                "project_id": project_id,
                "target_id": object_id,
                "modifier_type": "SUBSURF",
                "name": "Subdiv",
                "params": {"levels": 2},
            },
        )
        assert add["status"] == "success"
        assert add["modifier_name"] == "Subdiv"
        modifiers = add["modifiers"]
        assert any(m["name"] == "Subdiv" for m in modifiers)

        listed = await _call(
            app,
            "list_modifiers",
            {"request_id": "req-list-mod", "project_id": project_id, "target_id": object_id},
        )
        assert listed["status"] == "success"
        assert any(m["name"] == "Subdiv" for m in listed["modifiers"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_modifier_convenience_tools_add_mock_runtime_params(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app, "create_project", {"request_id": "req-pack-project", "name": "Mod Pack"}
        )
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-pack-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        calls = [
            (
                "add_bevel_modifier",
                {"modifier_name": "RoundEdges", "width": 0.2, "segments": 3},
                "BEVEL",
                {"width": 0.2, "segments": 3, "profile": 0.5, "harden_normals": False},
            ),
            (
                "add_mirror_modifier",
                {"modifier_name": "MirrorYZ", "use_x": False, "use_y": True, "use_z": True},
                "MIRROR",
                {
                    "use_axis": [False, True, True],
                    "use_clip": True,
                    "use_bisect_axis": [False, False, False],
                },
            ),
            (
                "add_array_modifier",
                {
                    "modifier_name": "RepeatX",
                    "count": 4,
                    "relative_offset": [1.25, 0.0, 0.0],
                    "use_constant_offset": True,
                    "constant_offset": [0.0, 0.0, 1.0],
                },
                "ARRAY",
                {
                    "count": 4,
                    "relative_offset_displace": [1.25, 0.0, 0.0],
                    "use_constant_offset": True,
                    "constant_offset_displace": [0.0, 0.0, 1.0],
                },
            ),
            (
                "add_solidify_modifier",
                {"modifier_name": "Shell", "thickness": 0.15, "offset": 1.0},
                "SOLIDIFY",
                {"thickness": 0.15, "offset": 1.0, "use_even_offset": True},
            ),
            (
                "add_subdivision_modifier",
                {
                    "modifier_name": "Smooth",
                    "levels": 2,
                    "render_levels": 3,
                    "subdivision_type": "SIMPLE",
                },
                "SUBSURF",
                {"levels": 2, "render_levels": 3, "subdivision_type": "SIMPLE"},
            ),
            (
                "add_triangulate_modifier",
                {
                    "modifier_name": "Triangles",
                    "quad_method": "FIXED",
                    "ngon_method": "CLIP",
                    "min_vertices": 5,
                },
                "TRIANGULATE",
                {"quad_method": "FIXED", "ngon_method": "CLIP", "min_vertices": 5},
            ),
            (
                "add_weld_modifier",
                {"modifier_name": "CloseGaps", "merge_threshold": 0.002, "mode": "ALL"},
                "WELD",
                {"merge_threshold": 0.002, "mode": "ALL"},
            ),
            (
                "add_remesh_modifier",
                {
                    "modifier_name": "Voxelize",
                    "mode": "VOXEL",
                    "octree_depth": 5,
                    "scale": 0.8,
                    "voxel_size": 0.25,
                    "use_remove_disconnected": False,
                },
                "REMESH",
                {
                    "mode": "VOXEL",
                    "octree_depth": 5,
                    "scale": 0.8,
                    "voxel_size": 0.25,
                    "use_remove_disconnected": False,
                },
            ),
            (
                "add_displace_modifier",
                {
                    "modifier_name": "OffsetZ",
                    "strength": -0.15,
                    "mid_level": 0.25,
                    "direction": "Z",
                },
                "DISPLACE",
                {"strength": -0.15, "mid_level": 0.25, "direction": "Z"},
            ),
            (
                "add_weighted_normal_modifier",
                {
                    "modifier_name": "FaceWeighted",
                    "keep_sharp": False,
                    "weight": 75,
                    "mode": "FACE_AREA",
                    "thresh": 0.02,
                },
                "WEIGHTED_NORMAL",
                {"keep_sharp": False, "weight": 75, "mode": "FACE_AREA", "thresh": 0.02},
            ),
        ]

        for tool_name, arguments, expected_type, expected_params in calls:
            result = await _call(
                app,
                tool_name,
                {
                    "request_id": f"req-{tool_name}",
                    "project_id": project_id,
                    "target_id": object_id,
                    **arguments,
                },
            )
            assert result["status"] == "success"
            assert result["tool_name"] == tool_name
            modifier = _modifier_named(result["modifiers"], str(arguments["modifier_name"]))
            assert modifier["type"] == expected_type
            for key, value in expected_params.items():
                assert modifier["params"][key] == value

        listed = await _call(
            app,
            "list_modifiers",
            {"request_id": "req-pack-list", "project_id": project_id, "target_id": object_id},
        )
        assert listed["status"] == "success"
        listed_by_name = {modifier["name"]: modifier for modifier in listed["modifiers"]}
        assert {str(arguments["modifier_name"]) for _, arguments, _, _ in calls}.issubset(
            listed_by_name
        )
        assert listed_by_name["RoundEdges"]["type"] == "BEVEL"
        assert listed_by_name["RoundEdges"]["params"]["width"] == 0.2
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_modifier(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-rm-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-rm-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        await _call(
            app,
            "add_modifier",
            {"request_id": "req-rm-add", "project_id": project_id, "target_id": object_id, "modifier_type": "BEVEL"},
        )
        removed = await _call(
            app,
            "remove_modifier",
            {"request_id": "req-rm-del", "project_id": project_id, "target_id": object_id, "modifier_name": "BEVEL"},
        )
        assert removed["status"] == "success"
        assert not any(m["name"] == "BEVEL" for m in removed["modifiers"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_modifier_convenience_duplicate_name_rejected_with_wrapper_tool_name(
    tmp_path: Path,
) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app, "create_project", {"request_id": "req-pack-dup-project", "name": "Mod Pack"}
        )
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-pack-dup-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        first = await _call(
            app,
            "add_bevel_modifier",
            {
                "request_id": "req-pack-dup-1",
                "project_id": project_id,
                "target_id": object_id,
                "modifier_name": "DuplicateBevel",
            },
        )
        duplicate = await _call(
            app,
            "add_bevel_modifier",
            {
                "request_id": "req-pack-dup-2",
                "project_id": project_id,
                "target_id": object_id,
                "modifier_name": "DuplicateBevel",
            },
        )

        assert first["status"] == "success"
        assert duplicate["status"] == "failed"
        assert duplicate["tool_name"] == "add_bevel_modifier"
        assert duplicate["errors"]
        assert "validation_error" in duplicate["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_modifier(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-apply-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-apply-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        await _call(
            app,
            "add_modifier",
            {"request_id": "req-apply-add", "project_id": project_id, "target_id": object_id, "modifier_type": "SOLIDIFY", "name": "Shell"},
        )
        applied = await _call(
            app,
            "apply_modifier",
            {"request_id": "req-apply-apply", "project_id": project_id, "target_id": object_id, "modifier_name": "Shell"},
        )
        assert applied["status"] == "success"
        assert not any(m["name"] == "Shell" for m in applied["modifiers"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_modifier_name_rejected(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-dup-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-dup-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        await _call(
            app,
            "add_modifier",
            {"request_id": "req-dup-add1", "project_id": project_id, "target_id": object_id, "modifier_type": "BEVEL", "name": "MyBevel"},
        )
        dup = await _call(
            app,
            "add_modifier",
            {"request_id": "req-dup-add2", "project_id": project_id, "target_id": object_id, "modifier_type": "BEVEL", "name": "MyBevel"},
        )
        assert dup["status"] == "failed"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_modifier_convenience_history_records_wrapper_tool_name(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app, "create_project", {"request_id": "req-pack-history-project", "name": "Mod Pack"}
        )
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-pack-history-prim",
                "project_id": project_id,
                "primitive_type": "cube",
            },
        )
        object_id = str(prim["created_object_ids"][0])

        added = await _call(
            app,
            "add_subdivision_modifier",
            {
                "request_id": "req-pack-history-subdiv",
                "project_id": project_id,
                "target_id": object_id,
                "modifier_name": "HistorySubdiv",
            },
        )
        history = await _call(
            app,
            "list_operations",
            {"request_id": "req-pack-history-list", "project_id": project_id, "limit": 10},
        )

        assert added["status"] == "success"
        assert added["tool_name"] == "add_subdivision_modifier"
        tool_names = [operation["tool_name"] for operation in history["operations"]]
        assert "add_subdivision_modifier" in tool_names
        assert "add_modifier" not in tool_names
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_modifier_updates_params(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-set-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        prim = await _call(
            app,
            "create_primitive",
            {"request_id": "req-set-prim", "project_id": project_id, "primitive_type": "cube"},
        )
        object_id = str(prim["created_object_ids"][0])

        await _call(
            app,
            "add_modifier",
            {"request_id": "req-set-add", "project_id": project_id, "target_id": object_id, "modifier_type": "BEVEL", "name": "MyBevel", "params": {"width": 0.1}},
        )
        updated = await _call(
            app,
            "set_modifier",
            {"request_id": "req-set-run", "project_id": project_id, "target_id": object_id, "modifier_name": "MyBevel", "params": {"width": 0.25}},
        )

        assert updated["status"] == "success"
        bevel = next(modifier for modifier in updated["modifiers"] if modifier["name"] == "MyBevel")
        assert bevel["params"]["width"] == 0.25
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_decimate_and_boolean_helpers_succeed(tmp_path: Path) -> None:
    settings, _ = _make_settings(tmp_path)
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-helper-project", "name": "Mod Demo"})
        project_id = str(project["project_id"])
        cube_a = await _call(
            app,
            "create_primitive",
            {"request_id": "req-helper-a", "project_id": project_id, "primitive_type": "cube", "name": "A"},
        )
        cube_b = await _call(
            app,
            "create_primitive",
            {"request_id": "req-helper-b", "project_id": project_id, "primitive_type": "cube", "name": "B"},
        )
        object_id = str(cube_a["created_object_ids"][0])
        operand_id = str(cube_b["created_object_ids"][0])

        decimated = await _call(
            app,
            "apply_decimate",
            {"request_id": "req-helper-decimate", "project_id": project_id, "target_id": object_id, "ratio": 0.35},
        )
        booleaned = await _call(
            app,
            "apply_boolean",
            {
                "request_id": "req-helper-boolean",
                "project_id": project_id,
                "target_id": object_id,
                "operand_id": operand_id,
                "operation": "UNION",
            },
        )

        assert decimated["status"] == "success"
        assert decimated["ratio"] == 0.35
        assert booleaned["status"] == "success"
        assert booleaned["operand_id"] == operand_id
        assert booleaned["operation"] == "UNION"
    finally:
        await app.stop()
