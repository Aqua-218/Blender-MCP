from __future__ import annotations

import json
import socket
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.serialization import json_loads
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port


def _make_http_app(tmp_path: Path, **overrides: str) -> tuple[MCPServerApplication, ServerSettings]:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(find_free_port()),
            "BLENDER_MCP_TRANSPORT": "http",
            "BLENDER_MCP_HTTP_HOST": "127.0.0.1",
            "BLENDER_MCP_HTTP_PORT": str(port),
            **overrides,
        },
        base_dir=tmp_path,
    )
    return MCPServerApplication(settings), settings


def _start_http_server(app: MCPServerApplication, settings: ServerSettings) -> threading.Thread:
    thread = threading.Thread(target=app.serve_http, daemon=True)
    thread.start()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection((settings.http_host, settings.http_port), timeout=0.1):
                return thread
        except OSError:
            time.sleep(0.05)
    raise AssertionError("HTTP server did not start in time")


def _post_json(
    settings: ServerSettings,
    payload: dict[str, object],
    *,
    token: str | None = None,
    origin: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    connection = HTTPConnection(settings.http_host, settings.http_port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["Origin"] = origin
    connection.request("POST", "/", body=json.dumps(payload), headers=headers)
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    response_headers = {key: value for key, value in response.getheaders()}
    connection.close()
    return response.status, body, response_headers


def _options(settings: ServerSettings, *, origin: str | None = None) -> tuple[int, dict[str, str]]:
    connection = HTTPConnection(settings.http_host, settings.http_port, timeout=5)
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
        headers["Access-Control-Request-Method"] = "POST"
        headers["Access-Control-Request-Headers"] = "Authorization, Content-Type"
    connection.request("OPTIONS", "/", headers=headers)
    response = connection.getresponse()
    response.read()
    response_headers = {key: value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, response_headers


def _get(settings: ServerSettings) -> tuple[int, str, dict[str, str]]:
    connection = HTTPConnection(settings.http_host, settings.http_port, timeout=5)
    connection.request("GET", "/")
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    response_headers = {key: value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, body, response_headers


def _tool_call_payload(name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": name,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


@pytest.mark.integration
def test_http_transport_rejects_missing_or_invalid_auth_token(tmp_path: Path) -> None:
    app, settings = _make_http_app(
        tmp_path,
        BLENDER_MCP_HTTP_AUTH_TOKEN="secret-token",
    )
    thread = _start_http_server(app, settings)
    try:
        missing_status, _, _ = _post_json(
            settings,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        invalid_status, _, _ = _post_json(
            settings,
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
            token="wrong-token",
        )

        assert missing_status == 401
        assert invalid_status == 401
        assert app.context.metrics["security"]["http_auth_failures"] >= 2
    finally:
        app.shutdown_http_server()
        thread.join(timeout=5)


@pytest.mark.integration
def test_http_transport_accepts_explicit_unauthenticated_remote_binding(tmp_path: Path) -> None:
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(find_free_port()),
            "BLENDER_MCP_TRANSPORT": "http",
            "BLENDER_MCP_HTTP_HOST": "0.0.0.0",
            "BLENDER_MCP_HTTP_PORT": str(find_free_port()),
            "BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP": "true",
        },
        base_dir=tmp_path,
    )

    assert settings.transport == "http"
    assert settings.http_host == "0.0.0.0"
    assert settings.unsafe_http_enabled is True
    assert settings.http_auth_token is None


@pytest.mark.integration
def test_http_transport_unsafe_mode_accepts_requests_without_auth_and_handles_streamable_http_edges(tmp_path: Path) -> None:
    app, settings = _make_http_app(
        tmp_path,
        BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP="true",
    )
    thread = _start_http_server(app, settings)
    try:
        status, body, _ = _post_json(
            settings,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        notification_status, notification_body, _ = _post_json(
            settings,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        get_status, get_body, get_headers = _get(settings)

        assert status == 200
        assert json.loads(body)["result"]["serverInfo"]["name"] == "blender-mcp"
        assert notification_status == 202
        assert notification_body == ""
        assert get_status == 405
        assert get_headers["Allow"] == "POST, OPTIONS"
        assert "SSE streams are not supported" in get_body
    finally:
        app.shutdown_http_server()
        thread.join(timeout=5)


@pytest.mark.integration
def test_http_transport_accepts_valid_token_and_records_auth_context(tmp_path: Path) -> None:
    app, settings = _make_http_app(
        tmp_path,
        BLENDER_MCP_HTTP_AUTH_TOKEN="secret-token",
        BLENDER_MCP_HTTP_ALLOWED_ORIGINS="https://client.example",
        BLENDER_MCP_HTTP_AUTH_ROLE="operator",
    )
    thread = _start_http_server(app, settings)
    try:
        options_status, options_headers = _options(
            settings,
            origin="https://client.example",
        )
        status, body, headers = _post_json(
            settings,
            _tool_call_payload(
                "create_project",
                {"request_id": "req-http-project", "name": "HTTP Project"},
            ),
            token="secret-token",
            origin="https://client.example",
        )

        assert options_status == 204
        assert options_headers["Access-Control-Allow-Origin"] == "https://client.example"
        assert "Authorization" in options_headers["Access-Control-Allow-Headers"]
        assert status == 200
        assert headers["Access-Control-Allow-Origin"] == "https://client.example"
        payload = json.loads(body)
        project_id = str(payload["result"]["project_id"])
        operations = app.context.operations.recent_by_project(project_id, limit=1)
        assert len(operations) == 1
        logged_input = json_loads(operations[0].input_json)
        assert logged_input["_auth_context"]["authenticated"] is True
        assert logged_input["_auth_context"]["role"] == "operator"
        assert logged_input["_auth_context"]["transport"] == "http"
        assert "secret-token" not in operations[0].input_json
    finally:
        app.shutdown_http_server()
        thread.join(timeout=5)


@pytest.mark.integration
def test_http_transport_rejects_oversized_request_body(tmp_path: Path) -> None:
    app, settings = _make_http_app(
        tmp_path,
        BLENDER_MCP_HTTP_AUTH_TOKEN="secret-token",
        BLENDER_MCP_HTTP_MAX_REQUEST_BYTES="96",
    )
    thread = _start_http_server(app, settings)
    try:
        status, _, _ = _post_json(
            settings,
            _tool_call_payload(
                "create_project",
                {
                    "request_id": "req-large",
                    "name": "X" * 256,
                },
            ),
            token="secret-token",
        )

        assert status == 413
        assert app.context.metrics["security"]["oversized_request_rejections"] >= 1
    finally:
        app.shutdown_http_server()
        thread.join(timeout=5)


@pytest.mark.integration
def test_http_transport_rejects_disallowed_origin_and_counts_it(tmp_path: Path) -> None:
    app, settings = _make_http_app(
        tmp_path,
        BLENDER_MCP_HTTP_AUTH_TOKEN="secret-token",
        BLENDER_MCP_HTTP_ALLOWED_ORIGINS="https://client.example",
    )
    thread = _start_http_server(app, settings)
    try:
        status, _, _ = _post_json(
            settings,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            token="secret-token",
            origin="https://evil.example",
        )

        assert status == 403
        assert app.context.metrics["security"]["http_origin_rejections"] >= 1
    finally:
        app.shutdown_http_server()
        thread.join(timeout=5)
