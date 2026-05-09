from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

CAMERA_TOOLS = {
    "list_cameras",
    "create_shot_camera",
    "frame_camera_to_targets",
    "create_camera_orbit",
    "dolly_camera",
    "set_camera_lens_profile",
    "save_shot_bookmark",
    "apply_shot_bookmark",
}

LIGHTING_TOOLS = {
    "list_lights",
    "create_three_point_lighting",
    "create_softbox_lighting",
    "create_light_ring",
    "aim_lights_at_target",
    "balance_light_intensities",
    "set_light_color_temperature",
}

GAME_PREP_TOOLS = {
    "assign_lod_level",
    "create_lod_chain",
    "create_collision_proxy",
    "create_collision_proxy_set",
    "create_socket_marker",
    "assign_collision_role",
    "tag_game_export_role",
    "normalize_game_asset_names",
    "validate_game_export_readiness",
    "validate_lod_chain",
    "plan_game_export_package",
    "write_game_export_manifest",
    "set_game_export_profile",
    "set_engine_export_profile",
    "validate_engine_export_package",
    "plan_engine_import_checklist",
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


def _build_app(tmp_path: Path) -> MCPServerApplication:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    return MCPServerApplication(settings)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_camera_lighting_game_prep_tools_are_registered(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert CAMERA_TOOLS.issubset(tools)
        assert LIGHTING_TOOLS.issubset(tools)
        assert GAME_PREP_TOOLS.issubset(tools)
        for tool_name in CAMERA_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "camera"
        for tool_name in LIGHTING_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "lighting"
        for tool_name in GAME_PREP_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "game_prep"
        assert tools["list_cameras"]["annotations"]["readOnlyHint"] is True
        assert tools["list_lights"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_game_export_readiness"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_lod_chain"]["annotations"]["readOnlyHint"] is True
        assert tools["plan_game_export_package"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_engine_export_package"]["annotations"]["readOnlyHint"] is True
        assert tools["plan_engine_import_checklist"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_camera_and_lighting_helpers_do_real_scene_work(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-shot-project", "name": "Shots"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-shot-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Hero",
                "scale": [2.0, 1.0, 1.0],
            },
        )
        object_id = str(cube["created_object_ids"][0])

        shot = await _call(
            app,
            "create_shot_camera",
            {
                "request_id": "req-shot-camera",
                "project_id": project_id,
                "target_id": object_id,
                "name": "HeroShot",
                "shot_size": "wide",
                "angle": "isometric",
            },
        )
        camera_id = str(shot["camera"]["camera_id"])
        assert shot["status"] == "success"
        assert shot["created_object_ids"] == [camera_id]

        orbit = await _call(
            app,
            "create_camera_orbit",
            {
                "request_id": "req-shot-orbit",
                "project_id": project_id,
                "target_id": object_id,
                "count": 4,
                "radius": 6.0,
            },
        )
        assert len(orbit["created_object_ids"]) == 4

        framed = await _call(
            app,
            "frame_camera_to_targets",
            {
                "request_id": "req-shot-frame",
                "project_id": project_id,
                "camera_id": camera_id,
                "target_id": object_id,
                "shot_size": "closeup",
            },
        )
        assert framed["modified_object_ids"] == [camera_id]

        lens = await _call(
            app,
            "set_camera_lens_profile",
            {
                "request_id": "req-shot-lens",
                "project_id": project_id,
                "camera_id": camera_id,
                "profile_name": "telephoto",
            },
        )
        assert lens["camera"]["focal_length"] == 120.0

        dollied = await _call(
            app,
            "dolly_camera",
            {
                "request_id": "req-shot-dolly",
                "project_id": project_id,
                "camera_id": camera_id,
                "target_id": object_id,
                "distance_delta": 1.0,
            },
        )
        assert dollied["distance"] > 1.0

        bookmark = await _call(
            app,
            "save_shot_bookmark",
            {
                "request_id": "req-shot-bookmark",
                "project_id": project_id,
                "camera_id": camera_id,
                "target_id": object_id,
                "name": "Hero bookmark",
            },
        )
        applied = await _call(
            app,
            "apply_shot_bookmark",
            {
                "request_id": "req-shot-apply",
                "project_id": project_id,
                "shot_id": bookmark["shot_id"],
            },
        )
        assert applied["active_camera_id"] == camera_id

        three_point = await _call(
            app,
            "create_three_point_lighting",
            {"request_id": "req-light-three", "project_id": project_id, "target_id": object_id},
        )
        assert len(three_point["created_object_ids"]) == 3
        softbox = await _call(
            app,
            "create_softbox_lighting",
            {"request_id": "req-light-softbox", "project_id": project_id, "target_id": object_id},
        )
        ring = await _call(
            app,
            "create_light_ring",
            {"request_id": "req-light-ring", "project_id": project_id, "target_id": object_id, "count": 3},
        )
        light_id = str(softbox["light"]["light_id"])
        aimed = await _call(
            app,
            "aim_lights_at_target",
            {
                "request_id": "req-light-aim",
                "project_id": project_id,
                "light_ids": [light_id],
                "target_id": object_id,
            },
        )
        balanced = await _call(
            app,
            "balance_light_intensities",
            {
                "request_id": "req-light-balance",
                "project_id": project_id,
                "light_ids": [light_id],
                "target_intensity": 750.0,
            },
        )
        temperature = await _call(
            app,
            "set_light_color_temperature",
            {"request_id": "req-light-temp", "project_id": project_id, "light_id": light_id, "kelvin": 3200.0},
        )
        listed_cameras = await _call(app, "list_cameras", {"request_id": "req-list-cameras", "project_id": project_id})
        listed_lights = await _call(app, "list_lights", {"request_id": "req-list-lights", "project_id": project_id})

        assert ring["status"] == "success"
        assert aimed["modified_object_ids"] == [light_id]
        assert balanced["lights"][0]["intensity"] == 750.0
        assert len(temperature["color"]) == 3
        assert listed_cameras["count"] >= 5
        assert listed_lights["count"] >= 7
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_game_prep_helpers_create_lods_collision_and_validation(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-game-project", "name": "Game Prep"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-game-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Crate",
            },
        )
        object_id = str(cube["created_object_ids"][0])

        lod = await _call(
            app,
            "create_lod_chain",
            {
                "request_id": "req-game-lods",
                "project_id": project_id,
                "target_id": object_id,
                "group_name": "Crate",
                "levels": 2,
                "base_ratio": 0.5,
            },
        )
        assert lod["status"] == "success"
        assert len(lod["created_object_ids"]) == 2
        assert object_id in lod["lod_object_ids"]

        collision = await _call(
            app,
            "create_collision_proxy",
            {
                "request_id": "req-game-collision",
                "project_id": project_id,
                "target_id": object_id,
                "proxy_type": "box",
            },
        )
        collision_id = str(collision["collision_object_id"])
        collision_set = await _call(
            app,
            "create_collision_proxy_set",
            {
                "request_id": "req-game-collision-set",
                "project_id": project_id,
                "target_id": object_id,
                "proxy_types": ["box", "sphere"],
                "padding": 0.02,
            },
        )
        socket = await _call(
            app,
            "create_socket_marker",
            {
                "request_id": "req-game-socket",
                "project_id": project_id,
                "target_id": object_id,
                "socket_name": "muzzle",
                "location_offset": [0.0, 0.0, 1.0],
            },
        )
        export_role = await _call(
            app,
            "tag_game_export_role",
            {
                "request_id": "req-game-role",
                "project_id": project_id,
                "target_id": object_id,
                "role": "render",
                "export_name": "crate_render",
            },
        )
        assigned_collision = await _call(
            app,
            "assign_collision_role",
            {
                "request_id": "req-game-collision-role",
                "project_id": project_id,
                "target_id": collision_id,
                "role": "simple",
                "base_name": "Crate",
            },
        )
        normalized = await _call(
            app,
            "normalize_game_asset_names",
            {
                "request_id": "req-game-normalize",
                "project_id": project_id,
                "target_ids": [object_id],
                "base_name": "Crate",
                "prefix": "SM",
                "include_type_suffix": True,
            },
        )
        readiness = await _call(
            app,
            "validate_game_export_readiness",
            {
                "request_id": "req-game-readiness",
                "project_id": project_id,
                "require_collision": True,
                "require_lods": True,
                "require_materials": False,
            },
        )
        lod_validation = await _call(
            app,
            "validate_lod_chain",
            {
                "request_id": "req-game-lod-validation",
                "project_id": project_id,
                "group_name": "Crate",
                "required_levels": 2,
            },
        )
        package_plan = await _call(
            app,
            "plan_game_export_package",
            {
                "request_id": "req-game-package-plan",
                "project_id": project_id,
                "package_name": "crate_package",
                "require_collision": True,
                "require_lods": True,
                "require_materials": False,
            },
        )
        manifest = await _call(
            app,
            "write_game_export_manifest",
            {
                "request_id": "req-game-manifest",
                "project_id": project_id,
                "package_name": "crate_package",
                "require_collision": True,
                "require_lods": True,
                "require_materials": False,
            },
        )
        profile = await _call(
            app,
            "set_game_export_profile",
            {"request_id": "req-game-profile", "project_id": project_id, "default_format": "glb"},
        )
        engine_profile = await _call(
            app,
            "set_engine_export_profile",
            {"request_id": "req-game-engine-profile", "project_id": project_id, "engine": "unreal"},
        )
        engine_validation = await _call(
            app,
            "validate_engine_export_package",
            {
                "request_id": "req-game-engine-validation",
                "project_id": project_id,
                "engine": "unreal",
                "package_name": "crate_package",
                "require_collision": True,
                "require_lods": True,
                "require_materials": False,
            },
        )
        import_checklist = await _call(
            app,
            "plan_engine_import_checklist",
            {
                "request_id": "req-game-engine-checklist",
                "project_id": project_id,
                "engine": "unreal",
                "package_name": "crate_package",
            },
        )

        assert collision["status"] == "success"
        assert len(collision_set["created_object_ids"]) == 2
        assert socket["socket_name"] == "muzzle"
        assert export_role["export_role"] == "render"
        assert assigned_collision["modified_object_ids"] == [collision_id]
        assert normalized["objects"][0]["name"].startswith("sm_crate_00")
        assert readiness["metrics"]["collision_object_count"] >= 1
        assert readiness["metrics"]["lod_object_count"] >= 1
        assert lod_validation["groups"][0]["group_name"] == "Crate"
        assert package_plan["manifest"]["metrics"]["collision_pair_count"] >= 1
        assert package_plan["manifest"]["metrics"]["socket_marker_count"] == 1
        assert Path(str(manifest["file_paths"][0])).exists()
        assert profile["export_profile"]["profile_name"] == "game"
        assert profile["export_profile"]["include_cameras"] is False
        assert profile["export_profile"]["include_lights"] is False
        assert engine_profile["engine"] == "unreal"
        assert engine_profile["export_profile"]["default_format"] == "fbx"
        assert engine_validation["engine_ready"] is True
        assert engine_validation["expected_format"] == "fbx"
        assert engine_validation["active_export_profile"]["default_format"] == "fbx"
        assert any(item["id"] == "unreal_collision_prefix" for item in import_checklist["checklist"])
    finally:
        await app.stop()
