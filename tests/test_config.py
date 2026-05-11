from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings


def test_server_settings_from_env_resolves_workspace_roots(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_DEFAULT_ROLE": "editor",
            "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "2.5",
        },
        base_dir=tmp_path,
    )

    assert settings.workspace_roots == [tmp_path / "workspace-a", tmp_path / "workspace-b"]
    assert settings.controller_mode == "mock"
    assert settings.controller_attach_timeout_seconds == 2.5
    assert settings.default_role == "editor"
    assert settings.repo_root == Path(__file__).resolve().parents[1]


def test_server_settings_bootstrap_directories(tmp_path: Path) -> None:
    settings = ServerSettings.from_env({}, base_dir=tmp_path)

    settings.ensure_workspace_directories()

    for root in settings.workspace_roots:
        assert root.exists()
        assert (root / settings.artifact_directories.projects).exists()
        assert (root / settings.artifact_directories.metadata).exists()


def test_http_transport_requires_explicit_unsafe_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="BLENDER_MCP_HTTP_AUTH_TOKEN"):
        ServerSettings.from_env(
            {
                "BLENDER_MCP_TRANSPORT": "http",
            },
            base_dir=tmp_path,
        )


def test_authenticated_http_transport_allows_non_loopback_when_token_is_configured(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_TRANSPORT": "http",
            "BLENDER_MCP_HTTP_HOST": "0.0.0.0",
            "BLENDER_MCP_HTTP_AUTH_TOKEN": "top-secret",
        },
        base_dir=tmp_path,
    )

    assert settings.transport == "http"
    assert settings.http_host == "0.0.0.0"
    assert settings.http_auth_token == "top-secret"


def test_explicit_unsafe_http_transport_allows_non_loopback_without_token(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_TRANSPORT": "http",
            "BLENDER_MCP_HTTP_HOST": "0.0.0.0",
            "BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP": "true",
        },
        base_dir=tmp_path,
    )

    assert settings.transport == "http"
    assert settings.http_host == "0.0.0.0"
    assert settings.unsafe_http_enabled is True
    assert settings.http_auth_token is None


def test_controller_host_must_remain_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        ServerSettings.from_env(
            {
                "BLENDER_MCP_CONTROLLER_HOST": "0.0.0.0",
            },
            base_dir=tmp_path,
        )


def test_controller_attach_timeout_must_be_non_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="attach timeout"):
        ServerSettings.from_env(
            {
                "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "-1",
            },
            base_dir=tmp_path,
        )


def test_controller_start_timeout_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="start timeout"):
        ServerSettings.from_env(
            {
                "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "0",
            },
            base_dir=tmp_path,
        )
