from __future__ import annotations

import asyncio
import secrets
import socket
import subprocess
import sys
import threading
import time
from contextlib import suppress
from typing import Any

from blender_controller.protocol import (
    BridgeCancel,
    BridgeError,
    BridgeHeartbeat,
    BridgeProgress,
    BridgeRequest,
    BridgeResult,
)

from mcp_server.config import ServerSettings
from mcp_server.logger import get_logger
from mcp_server.serialization import json_dumps, json_loads
from mcp_server.utils import new_id


class ControllerBridgeError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ControllerBridgeClient:
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.logger = get_logger(settings.log_level)
        self._process: subprocess.Popen[str] | None = None
        self._shared_secret = settings.controller_secret or secrets.token_urlsafe(24)
        self._state_lock = threading.RLock()

    @property
    def shared_secret(self) -> str:
        return self._shared_secret

    @property
    def backend(self) -> str:
        if self.settings.controller_mode == "auto":
            return "blender" if self.settings.blender_binary is not None else "mock"
        return self.settings.controller_mode

    async def start(self) -> None:
        await asyncio.to_thread(self._ensure_started)

    async def stop(self) -> None:
        await asyncio.to_thread(self._stop_sync)

    async def invoke(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        read_only: bool = False,
        request_timeout: float = 30.0,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._invoke_sync,
            command,
            payload or {},
            read_only,
            request_timeout,
        )

    async def ping(self) -> dict[str, Any]:
        return await self.invoke("ping", {}, read_only=True)

    async def get_runtime_info(self) -> dict[str, Any]:
        return await self.invoke("get_runtime_info", {}, read_only=True)

    def _stop_sync(self) -> None:
        with self._state_lock:
            process = self._process
            if process is None:
                return
            self._process = None
            auth_token = self._shared_secret
            if process.poll() is None:
                with suppress(Exception):
                    self._send_request(
                        "shutdown",
                        {},
                        False,
                        5.0,
                        auth_token=auth_token,
                    )
                self._finalize_process(process, wait_timeout=5.0)
                return
            with suppress(Exception):
                process.wait(timeout=0.1)

    def _ensure_started(self) -> None:
        with self._state_lock:
            if self._process is not None and self._process.poll() is None:
                return
            if self._can_connect(require_expected_backend=True):
                return
            had_managed_process = self._process is not None
            if self._process is not None:
                process = self._process
                self._process = None
                self._finalize_process(process, wait_timeout=1.0)
            if (
                self.settings.controller_secret is not None
                and not had_managed_process
                and self.settings.controller_attach_timeout_seconds > 0
            ):
                deadline = time.monotonic() + self.settings.controller_attach_timeout_seconds
                while time.monotonic() < deadline:
                    try:
                        if self._can_connect(require_expected_backend=True):
                            return
                    except ControllerBridgeError as exc:
                        if exc.code == "authentication_failed":
                            raise
                    time.sleep(0.1)
            if self.settings.controller_secret is not None:
                self._shared_secret = self.settings.controller_secret
            else:
                self._shared_secret = secrets.token_urlsafe(24)
            env = {
                **dict(),
                **{"BLENDER_MCP_CONTROLLER_SECRET": self._shared_secret},
            }
            env.update({key: value for key, value in self._base_env().items() if value is not None})
            if self.backend == "mock":
                command = [
                    sys.executable,
                    "-m",
                    "blender_controller.host",
                    "--backend",
                    "mock",
                    "--host",
                    self.settings.controller_host,
                    "--port",
                    str(self.settings.controller_port),
                ]
            else:
                if self.settings.blender_binary is None:
                    raise ControllerBridgeError(
                        "controller_unavailable",
                        "Blender binary is not configured for blender controller mode.",
                    )
                bootstrap = str((self.settings.repo_root / "blender_controller" / "bootstrap.py").resolve())
                command = [
                    str(self.settings.blender_binary),
                    "--background",
                    "--python",
                    bootstrap,
                    "--",
                    "--backend",
                    "blender",
                    "--host",
                    self.settings.controller_host,
                    "--port",
                    str(self.settings.controller_port),
                ]
            self._process = subprocess.Popen(
                command,
                cwd=self.settings.repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + self.settings.controller_start_timeout_seconds
            while time.monotonic() < deadline:
                assert self._process is not None
                if self._process.poll() is not None:
                    diagnostics = self._collect_process_diagnostics(self._process)
                    self._process = None
                    raise ControllerBridgeError(
                        "controller_unavailable",
                        "Controller process exited during startup.",
                        diagnostics,
                    )
                if self._can_connect(require_expected_backend=True):
                    return
                time.sleep(0.2)
            diagnostics = self._terminate_startup_process()
            raise ControllerBridgeError(
                "controller_timeout",
                "Timed out waiting for controller startup.",
                diagnostics,
            )

    def _base_env(self) -> dict[str, str | None]:
        return {
            "BLENDER_MCP_CONTROLLER_HOST": self.settings.controller_host,
            "BLENDER_MCP_CONTROLLER_PORT": str(self.settings.controller_port),
            "BLENDER_MCP_CONTROLLER_MODE": self.backend,
            "BLENDER_MCP_CONTROLLER_BACKEND": self.backend,
            "BLENDER_MCP_CONTROLLER_HEARTBEAT_SECONDS": str(self.settings.controller_heartbeat_seconds),
            "BLENDER_MCP_LOG_LEVEL": self.settings.log_level,
            "BLENDER_MCP_BLENDER_BINARY": str(self.settings.blender_binary) if self.settings.blender_binary else None,
            "BLENDER_MCP_REPO_ROOT": str(self.settings.repo_root),
        }

    @staticmethod
    def _collect_process_diagnostics(process: subprocess.Popen[str]) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        stdout_excerpt = ""
        stderr_excerpt = ""
        try:
            stdout_excerpt, stderr_excerpt = process.communicate(timeout=0.2)
        except subprocess.TimeoutExpired:
            return diagnostics
        if process.returncode is not None:
            diagnostics["returncode"] = process.returncode
        if stdout_excerpt.strip():
            diagnostics["stdout_excerpt"] = stdout_excerpt.strip().splitlines()[-10:]
        if stderr_excerpt.strip():
            diagnostics["stderr_excerpt"] = stderr_excerpt.strip().splitlines()[-10:]
        return diagnostics

    def _terminate_startup_process(self) -> dict[str, Any]:
        if self._process is None:
            return {}
        process = self._process
        self._process = None
        self._finalize_process(process, wait_timeout=1.0)
        return self._collect_process_diagnostics(process)

    @staticmethod
    def _finalize_process(process: subprocess.Popen[str], *, wait_timeout: float) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                with suppress(Exception):
                    process.wait(timeout=wait_timeout)
            return
        with suppress(Exception):
            process.wait(timeout=0.1)

    def _can_connect(self, *, require_expected_backend: bool = False) -> bool:
        try:
            if require_expected_backend:
                runtime = self._send_request(
                    "get_runtime_info",
                    {},
                    True,
                    1.0,
                    auth_token=self._shared_secret,
                )
                if runtime.get("backend") != self.backend:
                    return False
            else:
                self._send_request("ping", {}, True, 1.0, auth_token=self._shared_secret)
            return True
        except ControllerBridgeError as exc:
            if exc.code == "authentication_failed":
                raise
            return False
        except Exception:
            return False

    def _invoke_sync(
        self,
        command: str,
        payload: dict[str, Any],
        read_only: bool,
        timeout: float,
    ) -> dict[str, Any]:
        with self._state_lock:
            auth_token = self._shared_secret
        try:
            return self._send_request(
                command,
                payload,
                read_only,
                timeout,
                auth_token=auth_token,
            )
        except ControllerBridgeError as exc:
            if command == "ping" or exc.code != "controller_unavailable":
                raise
        self._ensure_started()
        with self._state_lock:
            auth_token = self._shared_secret
        return self._send_request(
            command,
            payload,
            read_only,
            timeout,
            auth_token=auth_token,
        )

    def _send_request(
        self,
        command: str,
        payload: dict[str, Any],
        read_only: bool,
        timeout: float,
        *,
        auth_token: str,
    ) -> dict[str, Any]:
        request = BridgeRequest(
            request_id=new_id("bridge"),
            command=command,
            auth_token=auth_token,
            payload=payload,
            read_only=read_only,
        )
        deadline = time.monotonic() + timeout
        try:
            with socket.create_connection(
                (self.settings.controller_host, self.settings.controller_port),
                timeout=max(min(timeout, deadline - time.monotonic()), 0.001),
            ) as connection:
                connection.settimeout(max(deadline - time.monotonic(), 0.001))
                connection.sendall((json_dumps(request.model_dump()) + "\n").encode("utf-8"))
                file_object = connection.makefile("rb")
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise self._timeout_error(request.request_id, auth_token)
                    connection.settimeout(remaining)
                    line = file_object.readline()
                    if not line:
                        raise ControllerBridgeError(
                            "controller_unavailable",
                            "Controller connection closed without a result.",
                        )
                    payload = json_loads(line)
                    message_type = payload.get("message_type")
                    if message_type == "heartbeat":
                        BridgeHeartbeat.model_validate(payload)
                        continue
                    if message_type == "progress":
                        BridgeProgress.model_validate(payload)
                        continue
                    if message_type == "error":
                        error = BridgeError.model_validate(payload)
                        raise ControllerBridgeError(error.error_code, error.message, error.details)
                    if message_type == "result":
                        result = BridgeResult.model_validate(payload)
                        return result.payload
                    raise ControllerBridgeError(
                        "internal_error",
                        f"Unexpected bridge message: {message_type}",
                    )
        except TimeoutError as exc:
            raise self._timeout_error(request.request_id, auth_token) from exc
        except OSError as exc:
            raise ControllerBridgeError(
                "controller_unavailable",
                "Unable to connect to controller bridge.",
            ) from exc

    def _timeout_error(self, request_id: str, auth_token: str) -> ControllerBridgeError:
        cancel_sent = False
        with suppress(Exception):
            self._send_cancel(request_id, auth_token, timeout=1.0)
            cancel_sent = True
        if self._has_managed_process() and (not cancel_sent or not self._managed_runtime_recovered(auth_token, grace_seconds=0.5)):
            self._abort_managed_runtime()
        return ControllerBridgeError(
            "controller_timeout",
            "Timed out waiting for controller response.",
        )

    def _has_managed_process(self) -> bool:
        with self._state_lock:
            return self._process is not None and self._process.poll() is None

    def _abort_managed_runtime(self) -> None:
        with self._state_lock:
            process = self._process
            self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
            with suppress(Exception):
                process.wait(timeout=1.0)
            return
        with suppress(Exception):
            process.wait(timeout=0.1)

    def _managed_runtime_recovered(self, auth_token: str, *, grace_seconds: float) -> bool:
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                self._send_request(
                    "ping",
                    {},
                    True,
                    max(min(remaining, 0.2), 0.05),
                    auth_token=auth_token,
                )
                return True
            except ControllerBridgeError as exc:
                if exc.code == "authentication_failed":
                    raise
            time.sleep(0.05)
        return False

    def _send_cancel(self, request_id: str, auth_token: str, *, timeout: float) -> None:
        cancel = BridgeCancel(request_id=request_id, auth_token=auth_token)
        with socket.create_connection(
            (self.settings.controller_host, self.settings.controller_port),
            timeout=max(timeout, 0.001),
        ) as connection:
            connection.settimeout(max(timeout, 0.001))
            connection.sendall((json_dumps(cancel.model_dump()) + "\n").encode("utf-8"))
