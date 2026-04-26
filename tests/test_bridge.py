from __future__ import annotations

import asyncio
import json
import time

import pytest
from mcp_server.bridge import ControllerBridgeClient, ControllerBridgeError
from mcp_server.config import ServerSettings
from tests.port_utils import find_free_port


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_can_start_mock_runtime_and_ping(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        ping = await bridge.ping()
        runtime_info = await bridge.get_runtime_info()
        listed = await bridge.invoke("list_objects", {}, read_only=True)
        assert ping["pong"] is True
        assert runtime_info["backend"] == "mock"
        assert listed["objects"] == []
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_restarts_managed_runtime_after_unexpected_exit(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        first_process = bridge._process
        assert first_process is not None
        first_pid = first_process.pid
        first_secret = bridge.shared_secret

        first_process.kill()
        first_process.wait(timeout=10)

        runtime_info = await bridge.get_runtime_info()
        assert runtime_info["backend"] == "mock"

        restarted_process = bridge._process
        assert restarted_process is not None
        assert restarted_process.pid != first_pid
        assert bridge.shared_secret != first_secret
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_stop_does_not_respawn_dead_managed_runtime(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    await bridge.start()
    process = bridge._process
    assert process is not None
    secret_before_stop = bridge.shared_secret

    process.kill()
    process.wait(timeout=10)

    await bridge.stop()

    assert bridge._process is None
    assert bridge.shared_secret == secret_before_stop


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_enforces_absolute_request_timeout_even_with_heartbeats(tmp_path):
    port = find_free_port()
    shared_secret = "timeout-secret"

    async def handle_client(reader, writer):
        try:
            raw = await reader.readline()
            if not raw:
                return
            request = json.loads(raw)
            if request["auth_token"] != shared_secret:
                writer.write(
                    json.dumps(
                        {
                            "message_type": "error",
                            "request_id": request["request_id"],
                            "command": request["command"],
                            "error_code": "authentication_failed",
                            "message": "Invalid controller secret.",
                            "details": {},
                        }
                    ).encode("utf-8")
                    + b"\n"
                )
                await writer.drain()
                return
            if request["command"] == "ping":
                writer.write(
                    json.dumps(
                        {
                            "message_type": "result",
                            "request_id": request["request_id"],
                            "command": request["command"],
                            "payload": {"pong": True},
                        }
                    ).encode("utf-8")
                    + b"\n"
                )
                await writer.drain()
                return
            start_time = time.monotonic()
            while time.monotonic() - start_time < 0.3:
                writer.write(
                    json.dumps(
                        {
                            "message_type": "heartbeat",
                            "request_id": request["request_id"],
                            "command": request["command"],
                            "timestamp": "2026-04-24T00:00:00Z",
                        }
                    ).encode("utf-8")
                    + b"\n"
                )
                await writer.drain()
                await asyncio.sleep(0.02)
            writer.write(
                json.dumps(
                    {
                        "message_type": "result",
                        "request_id": request["request_id"],
                        "command": request["command"],
                        "payload": {"objects": []},
                    }
                ).encode("utf-8")
                + b"\n"
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", port)
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": shared_secret,
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        started_at = time.monotonic()
        with pytest.raises(ControllerBridgeError, match="Timed out waiting for controller response") as exc_info:
            await bridge.invoke("list_objects", {}, read_only=True, request_timeout=0.1)
        assert exc_info.value.code == "controller_timeout"
        assert time.monotonic() - started_at < 0.25
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_bridge_serializes_concurrent_starts(monkeypatch, tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "1",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    spawn_count = 0
    connectable = False

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            return None

        def kill(self):
            return None

        def communicate(self, timeout=None):
            return "", ""

    def fake_can_connect(*, require_expected_backend=False):
        return connectable

    def fake_popen(*args, **kwargs):
        nonlocal spawn_count, connectable
        spawn_count += 1
        time.sleep(0.1)
        connectable = True
        return FakeProcess()

    monkeypatch.setattr(bridge, "_can_connect", fake_can_connect)
    monkeypatch.setattr("mcp_server.bridge.subprocess.Popen", fake_popen)

    await asyncio.gather(bridge.start(), bridge.start())

    assert spawn_count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_timeout_cancels_managed_runtime_request_without_restart_when_cancel_succeeds(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        first_process = bridge._process
        assert first_process is not None

        with pytest.raises(ControllerBridgeError, match="Timed out waiting for controller response") as exc_info:
            await bridge.invoke("sleep", {"seconds": 10}, request_timeout=0.1)
        assert exc_info.value.code == "controller_timeout"

        runtime_info = await bridge.get_runtime_info()
        assert runtime_info["backend"] == "mock"
        current_process = bridge._process
        assert current_process is not None
        assert current_process.pid == first_process.pid
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_keeps_managed_runtime_alive_during_concurrent_long_running_request(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        first_process = bridge._process
        assert first_process is not None

        sleep_task = asyncio.create_task(
            bridge.invoke("sleep", {"seconds": 2.0}, read_only=False, request_timeout=5.0)
        )
        await asyncio.sleep(0.2)

        listed = await bridge.invoke("list_objects", {}, read_only=True, request_timeout=5.0)
        assert listed["objects"] == []

        sleep_result = await sleep_task
        assert sleep_result["slept_seconds"] == 2.0

        current_process = bridge._process
        assert current_process is not None
        assert current_process.pid == first_process.pid
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_timeout_preserves_project_state_for_queued_request_when_cancel_succeeds(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        project_result = await bridge.invoke(
            "create_project",
            {
                "project_id": "proj-timeout",
                "name": "Timeout Project",
                "blend_file_path": str(tmp_path / "workspace" / "project.blend"),
            },
            request_timeout=5.0,
        )
        assert project_result["project_id"] == "proj-timeout"
        first_process = bridge._process
        assert first_process is not None

        timed_out_call = asyncio.create_task(
            bridge.invoke("sleep", {"seconds": 2.0}, request_timeout=0.1)
        )
        await asyncio.sleep(0.2)
        queued_info = asyncio.create_task(
            bridge.invoke("get_project_info", {}, read_only=True, request_timeout=5.0)
        )

        with pytest.raises(ControllerBridgeError, match="Timed out waiting for controller response") as exc_info:
            await timed_out_call
        assert exc_info.value.code == "controller_timeout"

        project_info = await queued_info
        assert project_info["project_id"] == "proj-timeout"
        assert project_info["name"] == "Timeout Project"
        current_process = bridge._process
        assert current_process is not None
        assert current_process.pid == first_process.pid
    finally:
        await bridge.stop()
