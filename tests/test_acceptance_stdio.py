from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.port_utils import find_free_port


class StdioMCPClient:
    def __init__(self, process: subprocess.Popen[str]):
        self.process = process
        self.next_id = 1

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        request_id = self.next_id
        self.next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        raw = self.process.stdout.readline()
        assert raw, "server closed stdout unexpectedly"
        response = json.loads(raw)
        assert response.get("id") == request_id
        return response

    def notify(self, method: str, params: dict[str, object]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()


@pytest.mark.integration
def test_phase_zero_acceptance_flow_over_stdio(tmp_path: Path) -> None:
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_WORKSPACE_ROOTS": str(tmp_path / "workspace"),
        "BLENDER_MCP_CONTROLLER_MODE": "mock",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
        "BLENDER_MCP_TRANSPORT": "stdio",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.main", "--transport", "stdio"],
        cwd=Path.cwd(),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = StdioMCPClient(process)
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phase-zero-test", "version": "1.0.0"},
            },
        )
        assert initialize["result"]["serverInfo"]["name"] == "blender-mcp"
        assert initialize["result"]["protocolVersion"] == "2024-11-05"

        client.notify("notifications/initialized", {})

        tools = client.request("tools/list", {})
        assert {tool["name"] for tool in tools["result"]["tools"]} >= {
            "create_project",
            "create_primitive",
            "create_material",
            "apply_material",
            "create_camera",
            "create_light",
            "render_preview",
            "save_project",
        }

        create_project = client.request(
            "tools/call",
            {"name": "create_project", "arguments": {"request_id": "phase0-project", "name": "Phase Zero"}},
        )["result"]
        project_id = create_project["project_id"]

        create_cube = client.request(
            "tools/call",
            {
                "name": "create_primitive",
                "arguments": {
                    "request_id": "phase0-cube",
                    "project_id": project_id,
                    "primitive_type": "cube",
                    "name": "Cube",
                },
            },
        )["result"]
        cube_id = create_cube["created_object_ids"][0]

        create_material = client.request(
            "tools/call",
            {
                "name": "create_material",
                "arguments": {
                    "request_id": "phase0-mat",
                    "project_id": project_id,
                    "name": "PreviewMaterial",
                    "preset_name": "metal",
                },
            },
        )["result"]
        material_id = create_material["material"]["material_id"]

        apply_material = client.request(
            "tools/call",
            {
                "name": "apply_material",
                "arguments": {
                    "request_id": "phase0-apply",
                    "project_id": project_id,
                    "material_id": material_id,
                    "target_ids": [cube_id],
                },
            },
        )["result"]
        assert apply_material["status"] == "success"

        create_camera = client.request(
            "tools/call",
            {
                "name": "create_camera",
                "arguments": {"request_id": "phase0-camera", "project_id": project_id, "name": "Camera"},
            },
        )["result"]
        camera_id = create_camera["camera"]["camera_id"]

        create_light = client.request(
            "tools/call",
            {
                "name": "create_light",
                "arguments": {"request_id": "phase0-light", "project_id": project_id, "name": "Light"},
            },
        )["result"]
        assert create_light["status"] == "success"

        frame = client.request(
            "tools/call",
            {
                "name": "frame_object",
                "arguments": {
                    "request_id": "phase0-frame",
                    "project_id": project_id,
                    "camera_id": camera_id,
                    "target_ids": [cube_id],
                },
            },
        )["result"]
        assert frame["status"] == "success"

        render = client.request(
            "tools/call",
            {"name": "render_preview", "arguments": {"request_id": "phase0-render", "project_id": project_id}},
        )["result"]
        render_path = Path(render["image_paths"][0])
        assert render_path.exists()

        save = client.request(
            "tools/call",
            {"name": "save_project", "arguments": {"request_id": "phase0-save", "project_id": project_id}},
        )["result"]
        assert Path(save["blend_file_path"]).exists()
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.terminate()
        process.wait(timeout=10)
        assert process.stdout is not None
        assert process.stdout.read() == ""
        assert process.stderr is not None
        stderr_lines = [line for line in process.stderr.read().splitlines() if line.strip()]
        for line in stderr_lines:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            assert parsed["logger"] in {"mcp_server", "blender_controller"}


@pytest.mark.integration
def test_stdio_failed_result_normalizes_unknown_camera(tmp_path: Path) -> None:
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_WORKSPACE_ROOTS": str(tmp_path / "workspace"),
        "BLENDER_MCP_CONTROLLER_MODE": "mock",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
        "BLENDER_MCP_TRANSPORT": "stdio",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.main", "--transport", "stdio"],
        cwd=Path.cwd(),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = StdioMCPClient(process)
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phase-zero-test", "version": "1.0.0"},
            },
        )
        assert initialize["result"]["serverInfo"]["name"] == "blender-mcp"
        client.notify("notifications/initialized", {})

        create_project = client.request(
            "tools/call",
            {"name": "create_project", "arguments": {"request_id": "phase0-bad-camera-project", "name": "Phase Zero Bad Camera"}},
        )["result"]

        response = client.request(
            "tools/call",
            {
                "name": "render_preview",
                "arguments": {
                    "request_id": "phase0-bad-camera-render",
                    "project_id": create_project["project_id"],
                    "camera_id": "missing-camera",
                },
            },
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert "unknown camera_id" in response["result"]["errors"][0].lower()
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.integration
def test_phase_one_asset_io_and_qa_flow_over_stdio(tmp_path: Path) -> None:
    port = find_free_port()
    env = {
        **os.environ,
        "BLENDER_MCP_WORKSPACE_ROOTS": str(tmp_path / "workspace"),
        "BLENDER_MCP_CONTROLLER_MODE": "mock",
        "BLENDER_MCP_CONTROLLER_PORT": str(port),
        "BLENDER_MCP_TRANSPORT": "stdio",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.main", "--transport", "stdio"],
        cwd=Path.cwd(),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client = StdioMCPClient(process)
    try:
        initialize = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phase-one-test", "version": "1.0.0"},
            },
        )
        assert initialize["result"]["serverInfo"]["name"] == "blender-mcp"
        client.notify("notifications/initialized", {})

        tools = client.request("tools/list", {})
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        assert {"export_scene", "import_asset", "inspect_scene", "generate_qa_report"}.issubset(tool_names)

        create_project = client.request(
            "tools/call",
            {"name": "create_project", "arguments": {"request_id": "phase1-project", "name": "Phase One"}},
        )["result"]
        project_id = create_project["project_id"]

        create_cube = client.request(
            "tools/call",
            {
                "name": "create_primitive",
                "arguments": {
                    "request_id": "phase1-cube",
                    "project_id": project_id,
                    "primitive_type": "cube",
                    "name": "Cube",
                },
            },
        )["result"]
        assert create_cube["status"] == "success"

        inspected = client.request(
            "tools/call",
            {
                "name": "inspect_scene",
                "arguments": {
                    "request_id": "phase1-inspect-scene",
                    "project_id": project_id,
                },
            },
        )["result"]
        assert inspected["status"] == "success"
        assert "severity_summary" in inspected

        qa_report = client.request(
            "tools/call",
            {
                "name": "generate_qa_report",
                "arguments": {
                    "request_id": "phase1-generate-qa",
                    "project_id": project_id,
                    "scope": "scene",
                },
            },
        )["result"]
        assert qa_report["status"] == "success"
        assert qa_report["qa_report_id"]

        exported = client.request(
            "tools/call",
            {
                "name": "export_scene",
                "arguments": {
                    "request_id": "phase1-export-scene",
                    "project_id": project_id,
                    "export_format": "glb",
                },
            },
        )["result"]
        assert exported["status"] == "success"
        export_path = Path(exported["file_paths"][0])
        assert export_path.exists()

        imported = client.request(
            "tools/call",
            {
                "name": "import_asset",
                "arguments": {
                    "request_id": "phase1-import-asset",
                    "project_id": project_id,
                    "input_path": str(export_path),
                    "name_prefix": "phase1",
                },
            },
        )["result"]
        assert imported["status"] == "success"
        assert imported["created_object_ids"]
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.terminate()
        process.wait(timeout=10)