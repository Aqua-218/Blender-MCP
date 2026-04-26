from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp_server.bridge import ControllerBridgeError
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
async def test_phase_zero_tool_families_on_mock_runtime(tmp_path: Path) -> None:
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
        create_project = await _call(
            app,
            "create_project",
            {"request_id": "req-create-project", "name": "Demo Asset"},
        )
        project_id = str(create_project["project_id"])
        assert create_project["status"] == "success"

        create_primitive = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-create-primitive",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "HeroCube",
            },
        )
        object_id = create_primitive["created_object_ids"][0]
        assert create_primitive["status"] == "success"
        assert len(create_primitive["objects"][0]["data"]["vertices"]) == 8
        assert len(create_primitive["objects"][0]["data"]["faces"]) == 6

        create_material = await _call(
            app,
            "create_pbr_material",
            {
                "request_id": "req-material",
                "project_id": project_id,
                "name": "HeroSurface",
                "base_color": [0.8, 0.2, 0.2, 1.0],
                "roughness": 0.35,
                "metallic": 0.1,
            },
        )
        material_id = create_material["material"]["material_id"]

        apply_material = await _call(
            app,
            "apply_material",
            {
                "request_id": "req-apply-material",
                "project_id": project_id,
                "material_id": material_id,
                "target_ids": [object_id],
            },
        )
        assert apply_material["status"] == "success"

        create_camera = await _call(
            app,
            "create_camera",
            {"request_id": "req-camera", "project_id": project_id, "name": "ReviewCam"},
        )
        camera_id = create_camera["camera"]["camera_id"]
        assert camera_id

        create_light = await _call(
            app,
            "create_light",
            {"request_id": "req-light", "project_id": project_id, "name": "KeyLight"},
        )
        assert create_light["status"] == "success"

        frame = await _call(
            app,
            "frame_object",
            {
                "request_id": "req-frame",
                "project_id": project_id,
                "camera_id": camera_id,
                "target_ids": [object_id],
            },
        )
        assert frame["status"] == "success"

        render = await _call(
            app,
            "render_preview",
            {"request_id": "req-render", "project_id": project_id},
        )
        image_path = Path(render["image_paths"][0])
        assert image_path.exists()

        save_project = await _call(
            app,
            "save_project",
            {"request_id": "req-save", "project_id": project_id},
        )
        assert Path(save_project["blend_file_path"]).exists()
        assert save_project["duration_ms"] >= 0

        snapshot = await _call(
            app,
            "create_snapshot",
            {"request_id": "req-snapshot", "project_id": project_id},
        )
        assert Path(snapshot["snapshot_path"]).exists()

        delete_without_confirmation = await _call(
            app,
            "delete_object",
            {"request_id": "req-delete-denied", "project_id": project_id, "target_id": object_id},
        )
        assert delete_without_confirmation["status"] == "failed"

        delete_with_confirmation = await _call(
            app,
            "delete_object",
            {
                "request_id": "req-delete-ok",
                "project_id": project_id,
                "target_id": object_id,
                "destructive_confirmation": True,
            },
        )
        assert delete_with_confirmation["status"] == "success"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_reconciles_actual_workspace_root_from_controller_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        actual_path = tmp_path / "workspace-b" / "projects" / "actual" / "actual.blend"
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        actual_path.write_text("placeholder", encoding="utf-8")
        original_invoke = app.context.bridge.invoke

        async def redirected_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "create_project":
                return {
                    "project_id": payload["project_id"],
                    "blend_file_path": str(actual_path),
                    "active_scene_name": "Scene",
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", redirected_invoke)

        created = await _call(
            app,
            "create_project",
            {
                "request_id": "req-create-actual-root",
                "name": "Actual Root",
                "workspace_root": "workspace-a",
            },
        )
        record = app.context.projects.get(str(created["project_id"]))

        assert Path(created["blend_file_path"]) == actual_path
        assert record is not None
        assert Path(record.workspace_root) == tmp_path / "workspace-b"
        assert Path(created["project"]["workspace_root"]) == tmp_path / "workspace-b"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_fails_if_controller_does_not_materialize_blend_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        original_invoke = app.context.bridge.invoke
        missing_path = tmp_path / "workspace" / "projects" / "missing" / "missing.blend"

        async def missing_file_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "create_project":
                return {
                    "project_id": payload["project_id"],
                    "blend_file_path": str(missing_path),
                    "active_scene_name": "Scene",
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", missing_file_invoke)

        response = await _call_raw(
            app,
            "create_project",
            {"request_id": "req-create-missing-file", "name": "Missing File"},
        )

        assert response["result"]["status"] == "failed"
        assert "does not exist" in response["result"]["errors"][0].lower()
        assert app.context.active_project_id is None
        assert app.context.projects.recent_history() == []
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_rejects_controller_returned_managed_path_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        first = await _call(
            app,
            "create_project",
            {"request_id": "req-create-first-conflict", "name": "First Conflict"},
        )
        original_invoke = app.context.bridge.invoke

        async def conflicting_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "create_project":
                return {
                    "project_id": payload["project_id"],
                    "blend_file_path": first["blend_file_path"],
                    "active_scene_name": "Scene",
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", conflicting_invoke)

        response = await _call_raw(
            app,
            "create_project",
            {"request_id": "req-create-second-conflict", "name": "Second Conflict"},
        )

        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "create_project"
        assert "already owned by another project" in response["result"]["errors"][0]
        assert app.context.projects.get_by_blend_path(str(first["blend_file_path"])) is not None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_invalid_workspace_root_returns_failed_result(tmp_path: Path) -> None:
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
        response = await _call_raw(
            app,
            "create_project",
            {
                "request_id": "req-create-invalid-root",
                "name": "Invalid Root",
                "workspace_root": str(tmp_path / "outside-workspace"),
            },
        )

        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "create_project"
        assert app.context.active_project_id is None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_project_fails_without_starting_controller(tmp_path: Path) -> None:
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
        response = await _call_raw(
            app,
            "list_objects",
            {"request_id": "req-invalid-project", "project_id": "missing-project"},
        )
        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "list_objects"
        assert app._started is False
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_snapshot_provenance_and_rollback_preserve_project_path(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        create_project = await _call(
            app,
            "create_project",
            {"request_id": "req-project", "name": "Rollback Demo"},
        )
        project_id = str(create_project["project_id"])

        create_snapshot = await _call(
            app,
            "create_snapshot",
            {"request_id": "req-snapshot", "project_id": project_id},
        )
        snapshot_record = app.context.snapshots.get(create_snapshot["snapshot_id"])
        assert snapshot_record is not None
        assert snapshot_record.source_operation_id is not None

        save_as = await _call(
            app,
            "save_project_as",
            {
                "request_id": "req-save-as",
                "project_id": project_id,
                "output_path": str(tmp_path / "workspace-b" / "projects" / "moved.blend"),
                "overwrite": True,
                "destructive_confirmation": True,
            },
        )
        moved_path = Path(save_as["blend_file_path"])
        record_after_save_as = app.context.projects.get(project_id)
        assert record_after_save_as is not None
        assert Path(record_after_save_as.workspace_root) == tmp_path / "workspace-b"

        rollback = await _call(
            app,
            "rollback_to_snapshot",
            {
                "request_id": "req-rollback",
                "project_id": project_id,
                "snapshot_id": create_snapshot["snapshot_id"],
                "destructive_confirmation": True,
            },
        )
        rollback_target_snapshot = app.context.snapshots.lookup_by_project(project_id)[0]
        assert rollback_target_snapshot.reason == "rollback_target"
        assert Path(rollback["blend_file_path"]) == moved_path
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_project_uses_requested_named_workspace_root(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        create_project = await _call(
            app,
            "create_project",
            {
                "request_id": "req-project-root",
                "name": "Rooted Demo",
                "workspace_root": "workspace-b",
            },
        )
        project_id = str(create_project["project_id"])
        project_record = app.context.projects.get(project_id)
        assert project_record is not None
        assert Path(project_record.workspace_root) == tmp_path / "workspace-b"
        assert Path(create_project["blend_file_path"]).is_relative_to(tmp_path / "workspace-b")
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_rehydrates_metadata_and_relative_nested_root(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        created = await _call(
            app,
            "create_project",
            {
                "request_id": "req-create-reopen",
                "name": "Friendly Name",
                "template_name": "custom-template",
                "workspace_root": "workspace-b",
                "unit_scale": 2.5,
                "active_scene_name": "MainScene",
            },
        )
        project_id = str(created["project_id"])
        saved_path = Path(created["blend_file_path"])

        app.context.projects.db_path = getattr(app.context.projects, "db_path", None)  # type: ignore[attr-defined]
        app.context.projects.db.initialize()
        app.context.projects.db.engine.dispose()
        app.context.db.db_path.unlink()
        app.context.db.initialize()

        reopened = await _call(
            app,
            "open_project",
            {
                "request_id": "req-open-relative-root",
                "blend_file_path": str(Path("workspace-b") / saved_path.relative_to(tmp_path / "workspace-b")),
            },
        )
        reopened_record = app.context.projects.get(str(reopened["project_id"]))
        assert reopened_record is not None
        assert reopened_record.name == "Friendly Name"
        assert reopened_record.template_type == "custom-template"
        assert reopened_record.unit_scale == pytest.approx(2.5)
        assert reopened_record.active_scene_name == "MainScene"
        assert Path(reopened_record.workspace_root) == tmp_path / "workspace-b"
        assert reopened["project"]["dirty"] is False

        record = app.context.projects.get(project_id)
        assert record is None or record.project_id == reopened_record.project_id
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_resynchronizes_dirty_flag_on_existing_record(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-dirty-reopen", "name": "Dirty Reopen"},
        )
        project_id = str(created["project_id"])
        blend_path = str(created["blend_file_path"])

        app.context.projects.mark_dirty(project_id, "Scene")
        assert app.context.projects.get(project_id).dirty_flag == 1  # type: ignore[union-attr]

        reopened = await _call(
            app,
            "open_project",
            {"request_id": "req-open-dirty-reopen", "blend_file_path": blend_path},
        )
        reopened_record = app.context.projects.get(project_id)

        assert reopened["project"]["dirty"] is False
        assert reopened_record is not None
        assert reopened_record.dirty_flag == 0
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_sets_dirty_flag_when_creating_record_from_untracked_file(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-dirty-import", "name": "Dirty Import"},
        )
        blend_path = Path(created["blend_file_path"])
        serialized = json.loads(blend_path.read_text(encoding="utf-8"))
        serialized["project"]["dirty"] = True
        blend_path.write_text(json.dumps(serialized), encoding="utf-8")

        app.context.projects.db.engine.dispose()
        app.context.db.db_path.unlink()
        app.context.db.initialize()

        reopened = await _call(
            app,
            "open_project",
            {"request_id": "req-open-dirty-import", "blend_file_path": str(blend_path)},
        )
        reopened_record = app.context.projects.get(str(reopened["project_id"]))

        assert reopened["project"]["dirty"] is True
        assert reopened_record is not None
        assert reopened_record.dirty_flag == 1
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_untracked_project_save_and_reopen_persists_server_assigned_project_id(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-untagged-reopen", "name": "Untagged Reopen"},
        )
        blend_path = Path(created["blend_file_path"])
        serialized = json.loads(blend_path.read_text(encoding="utf-8"))
        serialized["project"]["project_id"] = None
        blend_path.write_text(json.dumps(serialized), encoding="utf-8")

        app.context.projects.db.engine.dispose()
        app.context.db.db_path.unlink()
        app.context.db.initialize()

        reopened = await _call(
            app,
            "open_project",
            {"request_id": "req-open-untagged-reopen", "blend_file_path": str(blend_path)},
        )
        reopened_project_id = str(reopened["project_id"])

        saved = await _call(
            app,
            "save_project",
            {"request_id": "req-save-untagged-reopen", "project_id": reopened_project_id},
        )
        assert saved["status"] == "success"

        app.context.projects.db.engine.dispose()
        app.context.db.db_path.unlink()
        app.context.db.initialize()

        reopened_again = await _call(
            app,
            "open_project",
            {"request_id": "req-open-again-untagged-reopen", "blend_file_path": str(blend_path)},
        )

        assert str(reopened_again["project_id"]) == reopened_project_id
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_from_copied_blend_reuses_existing_project_identity(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-copy-open", "name": "Copy Open"},
        )
        project_id = str(created["project_id"])
        original_path = Path(created["blend_file_path"])
        copied_path = tmp_path / "workspace" / "projects" / "copied" / "copy-open.blend"
        copied_path.parent.mkdir(parents=True, exist_ok=True)
        copied_path.write_text(original_path.read_text(encoding="utf-8"), encoding="utf-8")

        reopened = await _call(
            app,
            "open_project",
            {"request_id": "req-open-copy-open", "blend_file_path": str(copied_path)},
        )
        record = app.context.projects.get(project_id)

        assert reopened["status"] == "success"
        assert str(reopened["project_id"]) == project_id
        assert Path(reopened["project"]["blend_file_path"]) == copied_path
        assert record is not None
        assert Path(record.blend_file_path) == copied_path
        assert app.context.projects.get_by_blend_path(str(original_path)) is None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_rejects_managed_path_identity_conflict(tmp_path: Path) -> None:
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
        project_a = await _call(
            app,
            "create_project",
            {"request_id": "req-create-project-a", "name": "Project A"},
        )
        project_b = await _call(
            app,
            "create_project",
            {"request_id": "req-create-project-b", "name": "Project B"},
        )
        path_a = Path(project_a["blend_file_path"])
        path_b = Path(project_b["blend_file_path"])
        path_a.write_text(path_b.read_text(encoding="utf-8"), encoding="utf-8")

        response = await _call_raw(
            app,
            "open_project",
            {"request_id": "req-open-project-conflict", "blend_file_path": str(path_a)},
        )
        follow_up = await _call_raw(
            app,
            "get_project_info",
            {"request_id": "req-follow-up-project-conflict", "project_id": str(project_a["project_id"])},
        )
        record_a = app.context.projects.get(str(project_a["project_id"]))
        record_b = app.context.projects.get(str(project_b["project_id"]))

        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "open_project"
        assert "embedded project identity" in response["result"]["errors"][0]
        assert follow_up["result"]["status"] == "failed"
        assert "open or create the requested project" in follow_up["result"]["errors"][0]
        assert record_a is not None
        assert record_b is not None
        assert record_a.name == "Project A"
        assert record_b.name == "Project B"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_missing_path_clears_active_project_and_returns_failed_result(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-missing-open", "name": "Missing Open"},
        )

        response = await _call_raw(
            app,
            "open_project",
            {"request_id": "req-open-missing-open", "blend_file_path": str(tmp_path / "workspace" / "missing.blend")},
        )
        follow_up = await _call_raw(
            app,
            "get_project_info",
            {"request_id": "req-follow-up-missing-open", "project_id": str(created["project_id"])},
        )

        assert response["result"]["status"] == "failed"
        assert "does not exist" in response["result"]["errors"][0].lower()
        assert follow_up["result"]["status"] == "failed"
        assert app.context.active_project_id is None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_project_bridge_failure_clears_active_project_and_returns_failed_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-bridge-open", "name": "Bridge Open"},
        )
        original_invoke = app.context.bridge.invoke

        async def failing_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "open_project":
                raise ControllerBridgeError("controller_unavailable", "simulated open failure")
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", failing_invoke)

        response = await _call_raw(
            app,
            "open_project",
            {"request_id": "req-open-bridge-open", "blend_file_path": str(created["blend_file_path"])},
        )
        follow_up = await _call_raw(
            app,
            "get_project_info",
            {"request_id": "req-follow-up-bridge-open", "project_id": str(created["project_id"])},
        )

        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "open_project"
        assert "simulated open failure" in response["result"]["errors"][0]
        assert follow_up["result"]["status"] == "failed"
        assert app.context.active_project_id is None
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_project_bridge_failure_returns_failed_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-save-failure", "name": "Save Failure"},
        )
        original_invoke = app.context.bridge.invoke

        async def failing_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "save_project":
                raise ControllerBridgeError("controller_unavailable", "simulated save failure")
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", failing_invoke)

        response = await _call_raw(
            app,
            "save_project",
            {"request_id": "req-save-save-failure", "project_id": str(created["project_id"])},
        )

        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "save_project"
        assert "simulated save failure" in response["result"]["errors"][0]
        assert app.context.active_project_id == str(created["project_id"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_project_returned_missing_path_returns_failed_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-save-missing", "name": "Save Missing"},
        )
        original_invoke = app.context.bridge.invoke
        missing_path = tmp_path / "workspace" / "projects" / "missing" / "save-missing.blend"

        async def missing_path_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "save_project":
                return {
                    "blend_file_path": str(missing_path),
                    "active_scene_name": "Scene",
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", missing_path_invoke)

        response = await _call_raw(
            app,
            "save_project",
            {"request_id": "req-save-save-missing", "project_id": str(created["project_id"])},
        )

        assert response["result"]["status"] == "failed"
        assert "does not exist" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_project_as_rejects_controller_returned_managed_path_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        first = await _call(
            app,
            "create_project",
            {"request_id": "req-create-save-as-conflict-a", "name": "Save As Conflict A"},
        )
        second = await _call(
            app,
            "create_project",
            {"request_id": "req-create-save-as-conflict-b", "name": "Save As Conflict B"},
        )
        original_invoke = app.context.bridge.invoke

        async def conflicting_invoke(command: str, payload: dict[str, object] | None = None, *, read_only: bool = False, request_timeout: float = 30.0) -> dict[str, object]:
            if command == "save_project":
                return {
                    "blend_file_path": first["blend_file_path"],
                    "active_scene_name": "Scene",
                }
            return await original_invoke(command, payload, read_only=read_only, request_timeout=request_timeout)

        monkeypatch.setattr(app.context.bridge, "invoke", conflicting_invoke)

        response = await _call_raw(
            app,
            "save_project_as",
            {
                "request_id": "req-save-as-returned-conflict",
                "project_id": str(second["project_id"]),
                "output_path": str(tmp_path / "workspace" / "projects" / "other" / "other.blend"),
                "overwrite": True,
                "destructive_confirmation": True,
            },
        )

        assert response["result"]["status"] == "failed"
        assert "returned path is already owned" in response["result"]["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_project_as_allows_new_nested_workspace_subdirectory(tmp_path: Path) -> None:
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
        created = await _call(
            app,
            "create_project",
            {"request_id": "req-create-nested-save-as", "name": "Nested Save As"},
        )
        project_id = str(created["project_id"])

        saved = await _call(
            app,
            "save_project_as",
            {
                "request_id": "req-save-nested-save-as",
                "project_id": project_id,
                "output_path": str(Path("workspace") / "projects" / "new" / "subdir" / "demo.blend"),
                "overwrite": True,
                "destructive_confirmation": True,
            },
        )

        saved_path = Path(saved["blend_file_path"])
        record = app.context.projects.get(project_id)
        assert saved["status"] == "success"
        assert saved["duration_ms"] >= 0
        assert saved_path.exists()
        assert saved_path == tmp_path / "workspace" / "projects" / "new" / "subdir" / "demo.blend"
        assert record is not None
        assert Path(record.workspace_root) == tmp_path / "workspace"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_project_as_rejects_managed_path_owned_by_another_project(tmp_path: Path) -> None:
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
        first_project = await _call(
            app,
            "create_project",
            {"request_id": "req-project-a", "name": "Project A"},
        )
        second_project = await _call(
            app,
            "create_project",
            {"request_id": "req-project-b", "name": "Project B"},
        )
        first_blend_path = Path(first_project["blend_file_path"])
        before_contents = first_blend_path.read_text(encoding="utf-8")

        save_as = await _call(
            app,
            "save_project_as",
            {
                "request_id": "req-project-conflict",
                "project_id": str(second_project["project_id"]),
                "output_path": str(first_blend_path),
                "overwrite": True,
                "destructive_confirmation": True,
            },
        )

        assert save_as["status"] == "failed"
        assert "already owned by another project" in save_as["errors"][0]
        assert first_blend_path.read_text(encoding="utf-8") == before_contents
    finally:
        await app.stop()