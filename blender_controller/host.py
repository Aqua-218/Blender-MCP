from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress

from mcp_server.serialization import json_dumps, json_loads
from mcp_server.utils import utc_now_iso

from blender_controller.blender_runtime import BlenderRuntime
from blender_controller.config import ControllerSettings
from blender_controller.logger import get_logger
from blender_controller.mock_runtime import MockRuntime
from blender_controller.protocol import (
    BridgeCancel,
    BridgeError,
    BridgeHeartbeat,
    BridgeRequest,
    BridgeResult,
)
from blender_controller.runtime import BaseRuntime, RuntimeCommandError


class ControllerBridgeServer:
    def __init__(self, settings: ControllerSettings):
        self.settings = settings
        self.logger = get_logger(settings.log_level)
        self.runtime = self._build_runtime(settings.backend)
        self.server: asyncio.AbstractServer | None = None
        self.stop_event = asyncio.Event()
        self.dispatch_condition = asyncio.Condition()
        self.read_only_semaphore = asyncio.Semaphore(2)
        self.active_readers = 0
        self.waiting_mutations = 0
        self.active_mutation = False
        self.pending_requests = 0
        self.processed_requests = 0
        self.active_requests: dict[str, asyncio.Task[dict[str, object]]] = {}

    @staticmethod
    def _build_runtime(backend: str) -> BaseRuntime:
        if backend == "mock":
            return MockRuntime()
        return BlenderRuntime()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_connection, self.settings.host, self.settings.port)
        self.logger.info(
            "controller_ready",
            extra={
                "status": "success",
                "warnings_count": 0,
                "errors_count": 0,
            },
        )

    async def run_forever(self) -> None:
        await self.start()
        assert self.server is not None
        async with self.server:
            await self.stop_event.wait()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        send_lock = asyncio.Lock()
        try:
            while not reader.at_eof():
                raw = await reader.readline()
                if not raw:
                    break
                payload = json_loads(raw)
                if payload.get("message_type") == "cancel":
                    cancel = BridgeCancel.model_validate(payload)
                    if cancel.auth_token != self.settings.shared_secret:
                        await self._send(
                            writer,
                            BridgeError(
                                request_id=cancel.request_id,
                                command="cancel",
                                error_code="authentication_failed",
                                message="Invalid controller secret.",
                            ),
                            send_lock,
                        )
                        break
                    task = self.active_requests.get(cancel.request_id)
                    if task is not None:
                        task.cancel()
                    break
                request = BridgeRequest.model_validate(payload)
                if request.auth_token != self.settings.shared_secret:
                    await self._send(
                        writer,
                        BridgeError(
                            request_id=request.request_id,
                            command=request.command,
                            error_code="authentication_failed",
                            message="Invalid controller secret.",
                        ),
                        send_lock,
                    )
                    break
                await self._send(
                    writer,
                    BridgeHeartbeat(
                        request_id=request.request_id,
                        command=request.command,
                        timestamp=utc_now_iso(),
                    ),
                    send_lock,
                )
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(writer, request, send_lock))
                dispatch_task = asyncio.create_task(self._dispatch_request(request))
                disconnect_task = asyncio.create_task(reader.read(1))
                self.active_requests[request.request_id] = dispatch_task
                self.pending_requests += 1
                try:
                    done, _ = await asyncio.wait(
                        {dispatch_task, heartbeat_task, disconnect_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if disconnect_task in done:
                        dispatch_task.cancel()
                        with suppress(asyncio.CancelledError, RuntimeCommandError):
                            await dispatch_task
                        break
                    if heartbeat_task in done:
                        heartbeat_error = heartbeat_task.exception()
                        if heartbeat_error is not None:
                            dispatch_task.cancel()
                            with suppress(asyncio.CancelledError, RuntimeCommandError):
                                await dispatch_task
                            break
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                    result = await dispatch_task
                    await self._send(
                        writer,
                        BridgeResult(
                            request_id=request.request_id,
                            command=request.command,
                            payload=result,
                        ),
                        send_lock,
                    )
                except RuntimeCommandError as exc:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                    await self._send(
                        writer,
                        BridgeError(
                            request_id=request.request_id,
                            command=request.command,
                            error_code=exc.code,
                            message=exc.message,
                            details=exc.details,
                        ),
                        send_lock,
                    )
                except asyncio.CancelledError:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                    break
                except (BrokenPipeError, ConnectionResetError, OSError):
                    dispatch_task.cancel()
                    with suppress(asyncio.CancelledError, RuntimeCommandError):
                        await dispatch_task
                    break
                finally:
                    self.active_requests.pop(request.request_id, None)
                    if not disconnect_task.done():
                        disconnect_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await disconnect_task
                    if not dispatch_task.done():
                        dispatch_task.cancel()
                        with suppress(asyncio.CancelledError, RuntimeCommandError):
                            await dispatch_task
                    if not heartbeat_task.done():
                        heartbeat_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await heartbeat_task
                    self.pending_requests -= 1
                    self.processed_requests += 1
                if request.command == "shutdown":
                    self.stop_event.set()
                break
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def _dispatch_request(self, request: BridgeRequest) -> dict[str, object]:
        if request.command == "get_runtime_info":
            result = await self.runtime.dispatch(request.command, request.payload)
            result["queue_metrics"] = {
                "pending_requests": self.pending_requests,
                "processed_requests": self.processed_requests,
            }
            return result
        if request.read_only and self.runtime.supports_concurrent_reads:
            async with self.dispatch_condition:
                while self.active_mutation or self.waiting_mutations > 0:
                    await self.dispatch_condition.wait()
                self.active_readers += 1
            try:
                async with self.read_only_semaphore:
                    return await self.runtime.dispatch(request.command, request.payload)
            finally:
                async with self.dispatch_condition:
                    self.active_readers -= 1
                    if self.active_readers == 0:
                        self.dispatch_condition.notify_all()
        async with self.dispatch_condition:
            self.waiting_mutations += 1
            try:
                while self.active_mutation or self.active_readers > 0:
                    await self.dispatch_condition.wait()
                self.active_mutation = True
            finally:
                self.waiting_mutations -= 1
        try:
            return await self.runtime.dispatch(request.command, request.payload)
        finally:
            async with self.dispatch_condition:
                self.active_mutation = False
                self.dispatch_condition.notify_all()

    async def _heartbeat_loop(
        self,
        writer: asyncio.StreamWriter,
        request: BridgeRequest,
        send_lock: asyncio.Lock,
    ) -> None:
        while True:
            await asyncio.sleep(self.settings.heartbeat_seconds)
            await self._send(
                writer,
                BridgeHeartbeat(
                    request_id=request.request_id,
                    command=request.command,
                    timestamp=utc_now_iso(),
                ),
                send_lock,
            )

    async def _send(self, writer: asyncio.StreamWriter, payload, send_lock: asyncio.Lock) -> None:  # type: ignore[no-untyped-def]
        async with send_lock:
            writer.write((json_dumps(payload.model_dump()) + "\n").encode("utf-8"))
            await writer.drain()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blender controller host")
    parser.add_argument("--backend", choices=["mock", "blender"], default="mock")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    try:
        settings = ControllerSettings.from_env()
        if args.host is not None or args.port is not None or args.backend != settings.backend:
            settings = ControllerSettings.model_validate(
                {
                    **settings.model_dump(),
                    "backend": args.backend,
                    "host": args.host or settings.host,
                    "port": args.port or settings.port,
                }
            )
    except ValueError as exc:
        parser.error(str(exc))
    asyncio.run(ControllerBridgeServer(settings).run_forever())


if __name__ == "__main__":
    main()
