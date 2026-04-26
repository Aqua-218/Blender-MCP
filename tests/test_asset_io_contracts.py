from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.persistence import EntityRecord
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


async def _call_raw(app: MCPServerApplication, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return await app.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_scene_writes_inside_project_export_directory(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-create-project", "name": "Export Demo"},
        )
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-export-create-primitive",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "ExportCube",
            },
        )

        exported = await _call(
            app,
            "export_scene",
            {
                "request_id": "req-export-scene",
                "project_id": project_id,
                "export_format": "glb",
            },
        )

        output_path = Path(str(exported["file_paths"][0]))
        assert exported["status"] == "success"
        assert output_path.exists()
        assert output_path.parent.name == project_id
        assert output_path.parent.parent.name == settings.artifact_directories.exports
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_scene_rejects_relative_escape_outside_project_export_directory(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-escape-create-project", "name": "Export Escape Demo"},
        )
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-export-escape-cube",
                "project_id": project["project_id"],
                "primitive_type": "cube",
                "name": "EscapeCube",
            },
        )

        response = await _call_raw(
            app,
            "export_scene",
            {
                "request_id": "req-export-escape",
                "project_id": project["project_id"],
                "export_format": "glb",
                "output_path": "../escape.glb",
            },
        )

        result = response["result"]
        assert result["status"] == "failed"
        assert "project's export directory" in result["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_scene_rejects_unexpected_controller_output_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-mismatch-create-project", "name": "Export Mismatch Demo"},
        )
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-export-mismatch-cube",
                "project_id": project["project_id"],
                "primitive_type": "cube",
                "name": "MismatchCube",
            },
        )
        original_invoke = app.context.bridge.invoke

        async def mismatched_output_path_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "export_scene":
                expected = Path(str(payload["output_path"]))
                return {
                    "output_path": str(expected.with_name("mismatched-output.glb")),
                    "object_count": 0,
                    "warnings": [],
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", mismatched_output_path_invoke)

        response = await _call_raw(
            app,
            "export_scene",
            {
                "request_id": "req-export-mismatch",
                "project_id": project["project_id"],
                "export_format": "glb",
            },
        )

        result = response["result"]
        assert result["status"] == "failed"
        assert result["tool_name"] == "export_scene"
        assert "unexpected export output path" in result["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_asset_creates_entities_and_marks_project_dirty(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-import-create-project", "name": "Import Demo"},
        )
        workspace_root = settings.workspace_roots[0]
        import_path = workspace_root / "imports" / "sample.glb"
        import_path.parent.mkdir(parents=True, exist_ok=True)
        import_path.write_text("{}", encoding="utf-8")

        imported = await _call(
            app,
            "import_asset",
            {
                "request_id": "req-import-asset",
                "project_id": project["project_id"],
                "input_path": str(import_path),
                "name_prefix": "ws11",
            },
        )

        assert imported["status"] == "success"
        assert imported["created_object_ids"]
        with app.context.db.session() as session:
            entity = session.get(EntityRecord, str(imported["created_object_ids"][0]))
        assert entity is not None
        project_record = app.context.projects.get(str(project["project_id"]))
        assert project_record is not None
        assert project_record.dirty_flag == 1
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_scene_fails_closed_when_readiness_has_blocking_issues(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-blocked-create-project", "name": "Blocked Export"},
        )
        blocked = await _call(
            app,
            "export_scene",
            {
                "request_id": "req-export-blocked",
                "project_id": project["project_id"],
                "export_format": "glb",
            },
        )
        assert blocked["status"] == "failed"
        assert "blocking issues" in blocked["summary"].lower()
        assert "glb" in blocked.get("blocked_export_formats", [])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_export_profile_and_export_scene_uses_profile_default_format(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-profile-project", "name": "Export Profile Demo"},
        )
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-export-profile-primitive",
                "project_id": project_id,
                "primitive_type": "cube",
            },
        )

        profile = await _call(
            app,
            "set_export_profile",
            {
                "request_id": "req-export-profile-set",
                "project_id": project_id,
                "profile_name": "print",
            },
        )
        exported = await _call(
            app,
            "export_scene",
            {
                "request_id": "req-export-profile-run",
                "project_id": project_id,
            },
        )

        assert profile["status"] == "success"
        assert exported["status"] == "success"
        assert exported["export_profile"] == "print"
        assert exported["export_format"] == "stl"
        assert Path(str(exported["file_paths"][0])).suffix == ".stl"
        assert any("STL export drops materials" in warning for warning in exported["warnings"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_export_formats_returns_supported_formats_and_active_profile(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-formats-project", "name": "Export Format Demo"},
        )
        project_id = str(project["project_id"])
        await _call(
            app,
            "set_export_profile",
            {
                "request_id": "req-export-formats-set",
                "project_id": project_id,
                "profile_name": "archive",
            },
        )

        formats = await _call(
            app,
            "get_export_formats",
            {"request_id": "req-export-formats-get", "project_id": project_id},
        )

        assert formats["status"] == "success"
        assert {"glb", "gltf", "fbx", "obj", "usd", "usdz", "stl"}.issubset(set(formats["supported_formats"]))
        assert formats["active_profile"]["profile_name"] == "archive"
        assert formats["active_profile"]["default_format"] == "usd"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_export_world_writes_inside_project_export_directory(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "req-export-world-project", "name": "Export World Demo"},
        )
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-export-world-primitive",
                "project_id": project_id,
                "primitive_type": "cube",
            },
        )

        exported = await _call(
            app,
            "export_world",
            {
                "request_id": "req-export-world-run",
                "project_id": project_id,
                "export_format": "fbx",
            },
        )

        output_path = Path(str(exported["file_paths"][0]))
        assert exported["status"] == "success"
        assert exported["tool_name"] == "export_world"
        assert output_path.exists()
        assert output_path.suffix == ".fbx"
        assert output_path.parent.name == project_id
    finally:
        await app.stop()

