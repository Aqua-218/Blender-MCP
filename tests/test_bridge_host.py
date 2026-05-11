from __future__ import annotations

import asyncio
import json

import pytest
from blender_controller.config import ControllerSettings
from blender_controller.host import ControllerBridgeServer
from blender_controller.protocol import BridgeCancel, BridgeRequest
from blender_controller.runtime import BaseRuntime
from mcp_server.bridge import ControllerBridgeClient, ControllerBridgeError
from mcp_server.config import ServerSettings
from mcp_server.serialization import json_dumps
from tests.port_utils import find_free_port


class SleepRuntime(BaseRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def cmd_sleep(self, _payload: dict[str, object]) -> dict[str, object]:
        self.started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return {"status": "completed"}


class CoordinatedRuntime(BaseRuntime):
    supports_concurrent_reads = True

    def __init__(self) -> None:
        super().__init__()
        self.read_started = asyncio.Event()
        self.release_read = asyncio.Event()
        self.mutation_started = asyncio.Event()

    async def cmd_probe_read(self, _payload: dict[str, object]) -> dict[str, object]:
        self.read_started.set()
        await self.release_read.wait()
        return {"status": "read_complete"}

    async def cmd_probe_mutation(self, _payload: dict[str, object]) -> dict[str, object]:
        self.mutation_started.set()
        return {"status": "mutation_complete"}


class ExplodingRuntime(BaseRuntime):
    async def cmd_explode(self, _payload: dict[str, object]) -> dict[str, object]:
        raise AttributeError("missing runtime helper")


@pytest.mark.asyncio
async def test_host_returns_bridge_error_for_unexpected_runtime_exception(tmp_path):
    port = find_free_port()
    settings = ControllerSettings.model_validate(
        {
            "host": "127.0.0.1",
            "port": port,
            "shared_secret": "host-secret",
            "heartbeat_seconds": 5.0,
            "backend": "mock",
            "repo_root": tmp_path,
        }
    )
    server = ControllerBridgeServer(settings)
    server.runtime = ExplodingRuntime()
    await server.start()
    assert server.server is not None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            (
                json_dumps(
                    BridgeRequest(
                        request_id="explode-test",
                        command="explode",
                        auth_token="host-secret",
                        payload={},
                        read_only=False,
                    ).model_dump()
                )
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()

        assert json.loads((await reader.readline()).decode("utf-8"))["message_type"] == "heartbeat"
        response = json.loads((await asyncio.wait_for(reader.readline(), timeout=1.0)).decode("utf-8"))

        assert response["message_type"] == "error"
        assert response["error_code"] == "internal_error"
        assert "missing runtime helper" in response["message"]
        writer.close()
        await writer.wait_closed()
    finally:
        server.server.close()
        await server.server.wait_closed()


@pytest.mark.asyncio
async def test_host_cancels_cancellable_request_when_client_disconnects(tmp_path):
    port = find_free_port()
    settings = ControllerSettings.model_validate(
        {
            "host": "127.0.0.1",
            "port": port,
            "shared_secret": "host-secret",
            "heartbeat_seconds": 5.0,
            "backend": "mock",
            "repo_root": tmp_path,
        }
    )
    server = ControllerBridgeServer(settings)
    runtime = SleepRuntime()
    server.runtime = runtime
    await server.start()
    assert server.server is not None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            (
                json_dumps(
                    BridgeRequest(
                        request_id="disconnect-test",
                        command="sleep",
                        auth_token="host-secret",
                        payload={},
                        read_only=False,
                    ).model_dump()
                )
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()

        first_message = await reader.readline()
        assert first_message
        await asyncio.wait_for(runtime.started.wait(), timeout=1.0)

        writer.close()
        await writer.wait_closed()

        await asyncio.wait_for(runtime.cancelled.wait(), timeout=1.0)

        async def request_drained() -> bool:
            return server.pending_requests == 0 and server.processed_requests == 1

        deadline = asyncio.get_running_loop().time() + 1.0
        while asyncio.get_running_loop().time() < deadline:
            if await request_drained():
                break
            await asyncio.sleep(0.02)
        assert await request_drained()
    finally:
        server.server.close()
        await server.server.wait_closed()


@pytest.mark.asyncio
async def test_bridge_timeout_sends_cancel_to_host_before_next_heartbeat(tmp_path):
    port = find_free_port()
    controller_settings = ControllerSettings.model_validate(
        {
            "host": "127.0.0.1",
            "port": port,
            "shared_secret": "host-secret",
            "heartbeat_seconds": 5.0,
            "backend": "mock",
            "repo_root": tmp_path,
        }
    )
    server = ControllerBridgeServer(controller_settings)
    runtime = SleepRuntime()
    server.runtime = runtime
    await server.start()
    assert server.server is not None

    bridge_settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": str(tmp_path / "workspace"),
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "host-secret",
            "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "1",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(bridge_settings)
    try:
        baseline_processed = server.processed_requests
        with pytest.raises(ControllerBridgeError, match="Timed out waiting for controller response") as exc_info:
            await bridge.invoke("sleep", {}, read_only=False, request_timeout=0.1)
        assert exc_info.value.code == "controller_timeout"
        await asyncio.wait_for(runtime.cancelled.wait(), timeout=1.0)

        deadline = asyncio.get_running_loop().time() + 1.0
        while asyncio.get_running_loop().time() < deadline:
            if server.pending_requests == 0 and server.processed_requests >= baseline_processed + 1:
                break
            await asyncio.sleep(0.02)
        assert server.pending_requests == 0
        assert server.processed_requests >= baseline_processed + 1
    finally:
        server.server.close()
        await server.server.wait_closed()


@pytest.mark.asyncio
async def test_host_blocks_mutation_until_concurrent_reads_finish(tmp_path):
    port = find_free_port()
    settings = ControllerSettings.model_validate(
        {
            "host": "127.0.0.1",
            "port": port,
            "shared_secret": "host-secret",
            "heartbeat_seconds": 5.0,
            "backend": "mock",
            "repo_root": tmp_path,
        }
    )
    server = ControllerBridgeServer(settings)
    runtime = CoordinatedRuntime()
    server.runtime = runtime

    read_task = asyncio.create_task(
        server._dispatch_request(
            BridgeRequest(
                request_id="read-request",
                command="probe_read",
                auth_token="host-secret",
                payload={},
                read_only=True,
            )
        )
    )
    await asyncio.wait_for(runtime.read_started.wait(), timeout=1.0)

    mutation_task = asyncio.create_task(
        server._dispatch_request(
            BridgeRequest(
                request_id="mutation-request",
                command="probe_mutation",
                auth_token="host-secret",
                payload={},
                read_only=False,
            )
        )
    )

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(runtime.mutation_started.wait(), timeout=0.1)

    runtime.release_read.set()

    assert await read_task == {"status": "read_complete"}
    await asyncio.wait_for(runtime.mutation_started.wait(), timeout=1.0)
    assert await mutation_task == {"status": "mutation_complete"}


@pytest.mark.asyncio
async def test_host_rejects_cancel_with_wrong_secret_without_canceling_request(tmp_path):
    port = find_free_port()
    settings = ControllerSettings.model_validate(
        {
            "host": "127.0.0.1",
            "port": port,
            "shared_secret": "host-secret",
            "heartbeat_seconds": 5.0,
            "backend": "mock",
            "repo_root": tmp_path,
        }
    )
    server = ControllerBridgeServer(settings)
    runtime = SleepRuntime()
    server.runtime = runtime
    await server.start()
    assert server.server is not None
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            (
                json_dumps(
                    BridgeRequest(
                        request_id="wrong-cancel-test",
                        command="sleep",
                        auth_token="host-secret",
                        payload={},
                        read_only=False,
                    ).model_dump()
                )
                + "\n"
            ).encode("utf-8")
        )
        await writer.drain()
        assert await reader.readline()
        await asyncio.wait_for(runtime.started.wait(), timeout=1.0)

        cancel_reader, cancel_writer = await asyncio.open_connection("127.0.0.1", port)
        cancel_writer.write(
            (
                json_dumps(
                    BridgeCancel(
                        request_id="wrong-cancel-test",
                        auth_token="wrong-secret",
                    ).model_dump()
                )
                + "\n"
            ).encode("utf-8")
        )
        await cancel_writer.drain()

        cancel_response = json.loads((await asyncio.wait_for(cancel_reader.readline(), timeout=1.0)).decode("utf-8"))
        assert cancel_response["message_type"] == "error"
        assert cancel_response["error_code"] == "authentication_failed"
        assert not runtime.cancelled.is_set()
        assert server.pending_requests == 1

        cancel_writer.close()
        await cancel_writer.wait_closed()
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(runtime.cancelled.wait(), timeout=1.0)
    finally:
        server.server.close()
        await server.server.wait_closed()
