from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.workspace import WorkspaceManager, WorkspaceViolationError


def test_workspace_manager_rejects_path_traversal(tmp_path: Path) -> None:
    settings = ServerSettings.from_env({}, base_dir=tmp_path)
    manager = WorkspaceManager(settings)
    manager.bootstrap()
    outside = tmp_path.parent / "outside.blend"

    with pytest.raises(WorkspaceViolationError):
        manager.canonicalize_output_path(outside, allowed_extensions=settings.allowed_export_extensions)


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks not supported")
def test_workspace_manager_rejects_symlink_escape(tmp_path: Path) -> None:
    settings = ServerSettings.from_env({}, base_dir=tmp_path)
    manager = WorkspaceManager(settings)
    manager.bootstrap()
    real_outside_dir = tmp_path / "external"
    real_outside_dir.mkdir()
    symlink_dir = settings.workspace_roots[0] / settings.artifact_directories.exports / "link"
    symlink_dir.symlink_to(real_outside_dir, target_is_directory=True)

    with pytest.raises(WorkspaceViolationError):
        manager.canonicalize_output_path(
            symlink_dir / "escaped.glb",
            allowed_extensions=settings.allowed_export_extensions,
        )


def test_workspace_manager_rejects_invalid_extension(tmp_path: Path) -> None:
    settings = ServerSettings.from_env({}, base_dir=tmp_path)
    manager = WorkspaceManager(settings)
    manager.bootstrap()

    with pytest.raises(WorkspaceViolationError):
        manager.canonicalize_output_path(
            settings.workspace_roots[0] / "exports" / "bad.exe",
            allowed_extensions=settings.allowed_export_extensions,
        )


def test_workspace_manager_returns_owning_allowlisted_root_for_nested_path(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {"BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b"},
        base_dir=tmp_path,
    )
    manager = WorkspaceManager(settings)
    manager.bootstrap()
    nested_project_path = settings.workspace_roots[1] / "projects" / "demo" / "asset.blend"

    assert manager.choose_workspace_root(nested_project_path) == settings.workspace_roots[1]


def test_workspace_manager_resolves_nested_relative_root_path(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {"BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b"},
        base_dir=tmp_path,
    )
    manager = WorkspaceManager(settings)
    manager.bootstrap()
    nested_project_path = settings.workspace_roots[1] / "projects" / "demo" / "asset.blend"
    nested_project_path.parent.mkdir(parents=True, exist_ok=True)
    nested_project_path.write_text("placeholder", encoding="utf-8")

    resolved = manager.canonicalize_existing_path(
        Path("workspace-b") / "projects" / "demo" / "asset.blend",
        allowed_extensions=[".blend"],
    )

    assert resolved == nested_project_path.resolve()


def test_server_settings_reject_duplicate_workspace_root_basenames(tmp_path: Path) -> None:
    root_a = tmp_path / "one" / "dup-root"
    root_b = tmp_path / "two" / "dup-root"

    with pytest.raises(ValueError, match="unique basenames"):
        ServerSettings.from_env(
            {"BLENDER_MCP_WORKSPACE_ROOTS": f"{root_a},{root_b}"},
            base_dir=tmp_path,
        )
