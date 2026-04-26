from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.persistence import QAReportRecord, decode_json_column
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_scene_returns_quality_metrics(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-scene-project", "name": "QA Scene"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-qa-scene-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "QACube",
            },
        )

        inspected = await _call(
            app,
            "inspect_scene",
            {"request_id": "req-qa-inspect-scene", "project_id": project_id},
        )

        assert inspected["status"] == "success"
        assert inspected["metrics"]["object_count"] >= 1
        assert "objects_by_type" in inspected["metrics"]
        assert "severity_summary" in inspected
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_mesh_rejects_non_mesh_target(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-mesh-project", "name": "QA Mesh"})
        project_id = str(project["project_id"])
        camera = await _call(
            app,
            "create_camera",
            {
                "request_id": "req-qa-mesh-camera",
                "project_id": project_id,
                "name": "QACamera",
            },
        )

        inspected = await _call(
            app,
            "inspect_mesh",
            {
                "request_id": "req-qa-inspect-mesh-invalid",
                "project_id": project_id,
                "target_id": camera["camera"]["camera_id"],
            },
        )

        assert inspected["status"] == "failed"
        assert "not a mesh object" in inspected["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_qa_report_persists_report_record(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-report-project", "name": "QA Report"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-qa-report-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "QAMesh",
            },
        )

        report = await _call(
            app,
            "generate_qa_report",
            {
                "request_id": "req-qa-generate-scene",
                "project_id": project_id,
                "scope": "scene",
            },
        )

        assert report["status"] == "success"
        qa_report_id = str(report["qa_report_id"])
        with app.context.db.session() as session:
            persisted = session.get(QAReportRecord, qa_report_id)
        assert persisted is not None
        report_json = decode_json_column(persisted.report_json)
        assert report_json["scope"] == "scene"
        assert isinstance(report_json["findings"], list)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_scene_allows_viewer_role(tmp_path: Path) -> None:
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
        decision = app.context.policy.authorize(
            tool_name="inspect_scene",
            role="viewer",
            destructive_confirmation=False,
            blast_radius=0,
            overwrite=False,
        )
        assert decision.allowed is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_object_and_naming_return_metrics(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-object-project", "name": "QA Object"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-qa-object-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Prefix_Cube",
            },
        )
        object_id = str(cube["created_object_ids"][0])

        inspected_object = await _call(
            app,
            "inspect_object",
            {
                "request_id": "req-qa-inspect-object",
                "project_id": project_id,
                "target_id": object_id,
            },
        )
        assert inspected_object["status"] == "success"
        assert inspected_object["metrics"]["object_id"] == object_id

        naming = await _call(
            app,
            "inspect_naming",
            {
                "request_id": "req-qa-inspect-naming",
                "project_id": project_id,
                "allowed_prefixes": ["Prefix_"],
            },
        )
        assert naming["status"] == "success"
        assert naming["metrics"]["object_count"] >= 1
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inspect_materials_and_polycount_report_findings(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-mat-poly-project", "name": "QA Mat Poly"})
        project_id = str(project["project_id"])
        await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-qa-mat-poly-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "NoMaterialCube",
            },
        )

        materials = await _call(
            app,
            "inspect_materials",
            {
                "request_id": "req-qa-inspect-materials",
                "project_id": project_id,
            },
        )
        assert materials["status"] == "success"
        assert materials["metrics"]["objects_without_material_count"] >= 1

        polycount = await _call(
            app,
            "check_polycount",
            {
                "request_id": "req-qa-check-polycount",
                "project_id": project_id,
                "max_triangles": 4,
            },
        )
        assert polycount["status"] == "success"
        assert polycount["metrics"]["triangle_count"] >= 1
        assert polycount["severity_summary"]["warning"] >= 1
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_export_readiness_and_generate_export_scope_report(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-qa-export-ready-project", "name": "QA Export Ready"})
        project_id = str(project["project_id"])

        readiness = await _call(
            app,
            "check_export_readiness",
            {
                "request_id": "req-qa-check-export-readiness",
                "project_id": project_id,
            },
        )
        assert readiness["status"] == "success"
        assert "blocked_export_formats" in readiness

        report = await _call(
            app,
            "generate_qa_report",
            {
                "request_id": "req-qa-generate-export-scope",
                "project_id": project_id,
                "scope": "export",
            },
        )
        assert report["status"] == "success"
        assert report["report"]["scope"] == "export"
    finally:
        await app.stop()
