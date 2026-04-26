from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from mcp_server.bridge import ControllerBridgeClient, ControllerBridgeError
from mcp_server.config import ServerSettings
from tests.port_utils import find_free_port


def _detect_blender_binary() -> Path | None:
    candidates: list[Path] = []
    configured = os.environ.get("BLENDER_MCP_BLENDER_BINARY")
    if configured:
        candidates.append(Path(configured))
    discovered = shutil.which("blender")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(Path("/Applications/Blender.app/Contents/MacOS/Blender"))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


BLENDER_BINARY = _detect_blender_binary()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_can_attach_to_existing_runtime(tmp_path):
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
        "BLENDER_MCP_CONTROLLER_BACKEND": "mock",
        "BLENDER_MCP_CONTROLLER_HOST": "127.0.0.1",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "blender_controller.host",
        "--backend",
        "mock",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        cwd=Path.cwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
            "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "2",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        runtime = await bridge.get_runtime_info()
        assert runtime["backend"] == "mock"
        assert bridge._process is None
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_reports_authentication_failure_when_attaching_with_wrong_secret(tmp_path):
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
        "BLENDER_MCP_CONTROLLER_MODE": "mock",
        "BLENDER_MCP_CONTROLLER_HOST": "127.0.0.1",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "blender_controller.host",
        "--backend",
        "mock",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        cwd=Path.cwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "wrong-secret",
            "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "2",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        with pytest.raises(ControllerBridgeError, match="Invalid controller secret") as exc_info:
            await bridge.start()
        assert exc_info.value.code == "authentication_failed"
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_waits_for_delayed_external_runtime_when_secret_is_configured(tmp_path):
    port = find_free_port()
    process: asyncio.subprocess.Process | None = None

    async def start_external_runtime() -> None:
        nonlocal process
        await asyncio.sleep(2.3)
        env = {
            **os.environ,
            "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_HOST": "127.0.0.1",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "blender_controller.host",
            "--backend",
            "mock",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            cwd=Path.cwd(),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    delayed_start = asyncio.create_task(start_external_runtime())
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
            "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "5",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        runtime = await bridge.get_runtime_info()
        assert runtime["backend"] == "mock"
        assert bridge._process is None
    finally:
        delayed_start.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await delayed_start
        if process is not None:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_restarts_managed_runtime_quickly_with_configured_secret(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "managed-secret",
            "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "5",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        process = bridge._process
        assert process is not None

        process.kill()
        process.wait(timeout=10)

        started_at = asyncio.get_running_loop().time()
        runtime = await bridge.get_runtime_info()
        restart_duration = asyncio.get_running_loop().time() - started_at

        assert runtime["backend"] == "mock"
        assert restart_duration < 1.5
        assert bridge.shared_secret == "managed-secret"
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_starts_managed_runtime_immediately_with_configured_secret(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "managed-secret",
            "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "5",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        started_at = asyncio.get_running_loop().time()
        await bridge.start()
        start_duration = asyncio.get_running_loop().time() - started_at
        assert bridge._process is not None
        assert bridge.shared_secret == "managed-secret"
        assert start_duration < 1.5
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_preserves_configured_secret_when_it_starts_managed_runtime(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "managed-secret",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        runtime = await bridge.get_runtime_info()
        assert runtime["backend"] == "mock"
        assert bridge.shared_secret == "managed-secret"

        await bridge.stop()

        await bridge.start()
        restarted_runtime = await bridge.get_runtime_info()
        assert restarted_runtime["backend"] == "mock"
        assert bridge.shared_secret == "managed-secret"
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_rejects_attach_to_runtime_with_wrong_backend(tmp_path):
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
        "BLENDER_MCP_CONTROLLER_BACKEND": "mock",
        "BLENDER_MCP_CONTROLLER_HOST": "127.0.0.1",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "blender_controller.host",
        "--backend",
        "mock",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        cwd=Path.cwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "blender",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "attach-secret",
            "BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS": "1",
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        with pytest.raises(ControllerBridgeError, match="Blender binary is not configured") as exc_info:
            await bridge.start()
        assert exc_info.value.code == "controller_unavailable"
        assert bridge._process is None
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bridge_rotates_generated_secret_when_managed_runtime_restarts(tmp_path):
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
        first_secret = bridge.shared_secret
        assert first_secret

        await bridge.stop()

        await bridge.start()
        second_secret = bridge.shared_secret
        assert second_secret
        assert second_secret != first_secret
    finally:
        await bridge.stop()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(BLENDER_BINARY is None, reason="Blender binary not available")
async def test_bridge_can_start_blender_runtime_and_report_runtime_info(tmp_path):
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "blender",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_CONTROLLER_SECRET": "blender-smoke-secret",
            "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "30",
            "BLENDER_MCP_BLENDER_BINARY": str(BLENDER_BINARY),
        },
        base_dir=tmp_path,
    )
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        runtime = await bridge.get_runtime_info()
        assert runtime["backend"] == "blender"
        assert runtime.get("blender_version")
        assert bridge._process is not None
    finally:
        await bridge.stop()