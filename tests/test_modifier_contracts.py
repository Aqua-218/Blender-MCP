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
