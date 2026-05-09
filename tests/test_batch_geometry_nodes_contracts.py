from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

BATCH_TOOLS = {
    "preview_batch_targets",
    "batch_tag_objects",
    "batch_rename_objects",
    "batch_assign_collection",
    "batch_set_visibility",
    "batch_transform_offsets",
    "batch_apply_material",
    "batch_add_modifier",
    "batch_duplicate_objects",
    "batch_export_assets",
    "batch_import_assets",
}

GEOMETRY_NODES_PRESET_TOOLS = {
    "list_geometry_nodes_setups",
    "duplicate_geometry_nodes_setup",
    "add_noise_displace_nodes",
    "add_curve_scatter_nodes",
    "add_instance_collection_nodes",
    "add_lod_switch_nodes",
    "expose_geometry_nodes_parameter",
    "validate_geometry_nodes_setup",
}


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


def _settings(tmp_path: Path) -> ServerSettings:
    port = find_free_port()
    return ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_and_geometry_nodes_preset_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert BATCH_TOOLS.issubset(tools)
        assert GEOMETRY_NODES_PRESET_TOOLS.issubset(tools)
        assert tools["preview_batch_targets"]["annotations"]["family"] == "batch_ops"
        assert tools["preview_batch_targets"]["annotations"]["readOnlyHint"] is True
        assert tools["list_geometry_nodes_setups"]["annotations"]["family"] == "geometry_nodes"
        assert tools["validate_geometry_nodes_setup"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_operations_compose_existing_tools(tmp_path: Path) -> None:
    app = MCPServerApplication(_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-batch-project", "name": "Batch Ops"})
        project_id = str(project["project_id"])
        ids = []
        for index in range(3):
            cube = await _call(
                app,
                "create_primitive",
                {
                    "request_id": f"req-batch-cube-{index}",
                    "project_id": project_id,
                    "primitive_type": "cube",
                    "name": f"BatchCube{index}",
                },
            )
            ids.append(str(cube["created_object_ids"][0]))
        material = await _call(app, "create_material", {"request_id": "req-batch-material", "project_id": project_id, "name": "BatchMat"})

        preview = await _call(app, "preview_batch_targets", {"request_id": "req-batch-preview", "project_id": project_id, "target_ids": ids})
        tagged = await _call(app, "batch_tag_objects", {"request_id": "req-batch-tag", "project_id": project_id, "target_ids": ids, "tags": ["batch_ready"]})
        renamed = await _call(app, "batch_rename_objects", {"request_id": "req-batch-rename", "project_id": project_id, "target_ids": ids, "base_name": "Crate", "prefix": "SM"})
        collected = await _call(app, "batch_assign_collection", {"request_id": "req-batch-collection", "project_id": project_id, "target_ids": ids, "collection_name": "BatchCollection"})
        hidden = await _call(app, "batch_set_visibility", {"request_id": "req-batch-hide", "project_id": project_id, "target_ids": ids, "visible": False})
        moved = await _call(app, "batch_transform_offsets", {"request_id": "req-batch-move", "project_id": project_id, "target_ids": ids, "location_offset": [1.0, 0.0, 0.0]})
        applied = await _call(
            app,
            "batch_apply_material",
            {
                "request_id": "req-batch-apply-material",
                "project_id": project_id,
                "target_ids": ids,
                "material_id": material["material"]["material_id"],
            },
        )
        modified = await _call(app, "batch_add_modifier", {"request_id": "req-batch-modifier", "project_id": project_id, "target_ids": ids, "modifier_type": "BEVEL", "modifier_name": "BatchBevel"})
        duplicated = await _call(
            app,
            "batch_duplicate_objects",
            {
                "request_id": "req-batch-duplicate",
                "project_id": project_id,
                "target_ids": ids[:2],
                "location_step": [2.0, 0.0, 0.0],
                "collection_name": "BatchCopies",
            },
        )
        exported = await _call(
            app,
            "batch_export_assets",
            {
                "request_id": "req-batch-export",
                "project_id": project_id,
                "target_ids": ids[:2],
                "output_prefix": "batch-crates",
                "export_format": "glb",
            },
        )
        import_dir = app.context.settings.workspace_roots[0] / "imports"
        import_dir.mkdir(parents=True, exist_ok=True)
        import_paths = [import_dir / "batch-a.glb", import_dir / "batch-b.glb"]
        for input_path in import_paths:
            input_path.write_text("{}", encoding="utf-8")
        imported = await _call(
            app,
            "batch_import_assets",
            {
                "request_id": "req-batch-import",
                "project_id": project_id,
                "input_paths": [str(input_path) for input_path in import_paths],
                "name_prefix": "imported",
                "collection_name": "BatchImports",
            },
        )

        assert preview["count"] == 3
        assert tagged["modified_object_ids"] == ids
        assert renamed["objects"][0]["name"] == "SM_Crate_01"
        assert collected["objects"][0]["collection"] == "BatchCollection"
        assert {item["visible"] for item in hidden["objects"]} == {False}
        assert moved["objects"][0]["location"][0] == 1.0
        assert set(applied["modified_object_ids"]) == set(ids)
        assert len(modified["modifiers"]) >= 3
        assert len(duplicated["created_object_ids"]) == 2
        assert len(exported["file_paths"]) == 2
        assert all(Path(path).exists() for path in exported["file_paths"])
        assert len(imported["created_object_ids"]) >= 2
        assert {item["collection"] for item in imported["objects"]} == {"BatchImports"}
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_geometry_nodes_presets_extend_and_validate_setups(tmp_path: Path) -> None:
    app = MCPServerApplication(_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-gn-project", "name": "GN Presets"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {"request_id": "req-gn-cube", "project_id": project_id, "primitive_type": "cube", "name": "GNTarget"},
        )
        target_id = str(cube["created_object_ids"][0])
        setup = await _call(
            app,
            "create_geometry_nodes",
            {"request_id": "req-gn-setup", "project_id": project_id, "target_id": target_id, "name": "PresetSetup"},
        )
        setup_id = str(setup["setup_id"])

        noise = await _call(app, "add_noise_displace_nodes", {"request_id": "req-gn-noise", "project_id": project_id, "setup_id": setup_id, "scale": 12.0, "strength": 0.5})
        curve = await _call(app, "add_curve_scatter_nodes", {"request_id": "req-gn-curve", "project_id": project_id, "setup_id": setup_id, "count": 12})
        instancing = await _call(
            app,
            "add_instance_collection_nodes",
            {
                "request_id": "req-gn-instance",
                "project_id": project_id,
                "setup_id": setup_id,
                "collection_name": "Scene Collection",
                "density": 2.0,
            },
        )
        lod = await _call(app, "add_lod_switch_nodes", {"request_id": "req-gn-lod", "project_id": project_id, "setup_id": setup_id, "lod_count": 4})
        exposed = await _call(
            app,
            "expose_geometry_nodes_parameter",
            {
                "request_id": "req-gn-expose",
                "project_id": project_id,
                "setup_id": setup_id,
                "node_id": noise["nodes"][0]["node_id"],
                "param_name": "scale",
                "label": "Noise Scale",
                "default_value": 12.0,
            },
        )
        duplicate = await _call(
            app,
            "duplicate_geometry_nodes_setup",
            {"request_id": "req-gn-duplicate", "project_id": project_id, "setup_id": setup_id, "name": "PresetSetupCopy"},
        )
        listed = await _call(app, "list_geometry_nodes_setups", {"request_id": "req-gn-list", "project_id": project_id, "target_id": target_id})
        validation = await _call(app, "validate_geometry_nodes_setup", {"request_id": "req-gn-validate", "project_id": project_id, "setup_id": setup_id})

        assert curve["status"] == "success"
        assert instancing["setup"]["metadata"]["collection_name"] == "Scene Collection"
        assert lod["setup"]["metadata"]["lod_count"] == 4
        assert exposed["exposed_parameter"]["label"] == "Noise Scale"
        assert duplicate["setup"]["name"] == "PresetSetupCopy"
        assert duplicate["setup"]["exposed_parameters"][0]["node_id"] != noise["nodes"][0]["node_id"]
        assert listed["count"] >= 2
        assert validation["severity_summary"]["error"] == 0
    finally:
        await app.stop()