from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
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
async def test_fix_mesh_and_remove_duplicate_vertices_succeed(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-repair-project", "name": "Repair Demo"})
        project_id = str(project["project_id"])
        mesh = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-repair-mesh",
                "project_id": project_id,
                "name": "DirtyMesh",
                "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]],
                "faces": [[0, 1, 2, 3]],
            },
        )
        object_id = str(mesh["created_object_ids"][0])

        dedup = await _call(
            app,
            "remove_duplicate_vertices",
            {
                "request_id": "req-repair-dedup",
                "project_id": project_id,
                "target_id": object_id,
                "threshold": 0.001,
            },
        )
        assert dedup["status"] == "success"
        assert object_id in dedup["modified_object_ids"]

        fixed = await _call(
            app,
            "fix_mesh",
            {
                "request_id": "req-repair-fix",
                "project_id": project_id,
                "target_id": object_id,
                "threshold": 0.001,
            },
        )
        assert fixed["status"] == "success"
        assert object_id in fixed["modified_object_ids"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_transforms_resets_scale_when_enabled(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-apply-project", "name": "Apply Transform Demo"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-apply-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "ScaledCube",
            },
        )
        object_id = str(cube["created_object_ids"][0])
        await _call(
            app,
            "transform_object",
            {
                "request_id": "req-apply-transform",
                "project_id": project_id,
                "target_id": object_id,
                "scale": [2.0, 3.0, 4.0],
            },
        )

        applied = await _call(
            app,
            "apply_transforms",
            {
                "request_id": "req-apply-run",
                "project_id": project_id,
                "target_id": object_id,
                "apply_scale": True,
                "apply_location": False,
                "apply_rotation": False,
            },
        )

        assert applied["status"] == "success"
        assert applied["objects"][0]["scale"] == [1.0, 1.0, 1.0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_origin_updates_object_payload(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-origin-project", "name": "Origin Demo"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-origin-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "OriginCube",
            },
        )
        object_id = str(cube["created_object_ids"][0])

        updated = await _call(
            app,
            "set_origin",
            {
                "request_id": "req-origin-set",
                "project_id": project_id,
                "target_id": object_id,
                "mode": "origin_center_of_mass",
            },
        )

        assert updated["status"] == "success"
        assert updated["objects"][0]["data"].get("origin_mode") == "origin_center_of_mass"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_optimize_polycount_and_generate_collision_mesh(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-opt-project", "name": "Optimization Demo"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-opt-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "OptimizeCube",
            },
        )
        object_id = str(cube["created_object_ids"][0])

        optimized = await _call(
            app,
            "optimize_polycount",
            {"request_id": "req-opt-run", "project_id": project_id, "target_id": object_id, "ratio": 0.4},
        )
        collision = await _call(
            app,
            "generate_collision_mesh",
            {"request_id": "req-col-run", "project_id": project_id, "target_id": object_id, "ratio": 0.2},
        )

        assert optimized["status"] == "success"
        assert optimized["ratio"] == 0.4
        assert collision["status"] == "success"
        assert collision["created_object_ids"]
        assert collision["collision_object_id"] == collision["created_object_ids"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_lod_creates_requested_number_of_duplicates(tmp_path: Path) -> None:
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
        project = await _call(app, "create_project", {"request_id": "req-lod-project", "name": "LOD Demo"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-lod-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "LodCube",
            },
        )
        object_id = str(cube["created_object_ids"][0])

        lod = await _call(
            app,
            "generate_lod",
            {"request_id": "req-lod-run", "project_id": project_id, "target_id": object_id, "levels": 2, "base_ratio": 0.5},
        )

        assert lod["status"] == "success"
        assert len(lod["created_object_ids"]) == 2
    finally:
        await app.stop()
