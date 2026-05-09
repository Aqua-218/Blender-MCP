from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.serialization import json_loads
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

ANIMATION_RIGGING_TOOLS = {
    "create_keyframe_animation",
    "create_camera_animation",
    "create_hinge_animation",
    "create_looping_rotation_animation",
    "create_simple_rig",
    "create_mechanical_rig_preset",
    "create_armature",
    "add_bone",
    "set_bone_transform",
    "auto_weight_limited",
    "list_armatures",
    "list_animation_tracks",
    "validate_animation_rigging",
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


def _make_settings(tmp_path: Path) -> ServerSettings:
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
async def test_animation_and_rigging_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        assert ANIMATION_RIGGING_TOOLS.issubset(tools)
        for tool_name in ANIMATION_RIGGING_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "animation_rigging"
        assert tools["list_armatures"]["annotations"]["readOnlyHint"] is True
        assert tools["list_animation_tracks"]["annotations"]["readOnlyHint"] is True
        assert tools["validate_animation_rigging"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_animation_and_rigging_tools_manage_rigs_tracks_and_bindings(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Animation Rigging"})
        project_id = str(project["project_id"])

        mesh = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-mesh",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "RigTarget",
            },
        )
        mesh_id = str(mesh["created_object_ids"][0])

        armature = await _call(
            app,
            "create_armature",
            {
                "request_id": "req-armature",
                "project_id": project_id,
                "name": "HeroRig",
            },
        )
        armature_id = str(armature["armature_id"])
        assert armature["status"] == "success"

        bone = await _call(
            app,
            "add_bone",
            {
                "request_id": "req-bone",
                "project_id": project_id,
                "armature_id": armature_id,
                "name": "root_ctrl",
            },
        )
        assert bone["status"] == "success"

        moved_bone = await _call(
            app,
            "set_bone_transform",
            {
                "request_id": "req-bone-xform",
                "project_id": project_id,
                "armature_id": armature_id,
                "bone_id": bone["bone_id"],
                "tail": [0.0, 0.0, 1.6],
                "rotation": [0.0, 0.0, 0.2],
            },
        )
        assert moved_bone["status"] == "success"
        assert moved_bone["bone"]["tail"][2] == 1.6

        simple_rig = await _call(
            app,
            "create_simple_rig",
            {
                "request_id": "req-simple-rig",
                "project_id": project_id,
                "name": "QuickRig",
                "target_ids": [mesh_id],
            },
        )
        assert simple_rig["status"] == "success"
        assert len(simple_rig["bone_ids"]) == 3
        assert simple_rig["binding"]["target_ids"] == [mesh_id]

        mechanical_rig = await _call(
            app,
            "create_mechanical_rig_preset",
            {
                "request_id": "req-mechanical-rig",
                "project_id": project_id,
                "name": "DoorHingeRig",
                "axis": "z",
                "joint_count": 3,
                "segment_length": 0.75,
                "target_ids": [mesh_id],
            },
        )
        assert mechanical_rig["status"] == "success"
        assert mechanical_rig["armature"]["preset"] == "mechanical_chain"
        assert len(mechanical_rig["bone_ids"]) == 5
        assert mechanical_rig["binding"]["target_ids"] == [mesh_id]

        weighted = await _call(
            app,
            "auto_weight_limited",
            {
                "request_id": "req-weight",
                "project_id": project_id,
                "armature_id": armature_id,
                "target_id": mesh_id,
            },
        )
        assert weighted["status"] == "success"
        assert weighted["modified_object_ids"] == [mesh_id]

        modifiers = await _call(
            app,
            "list_modifiers",
            {
                "request_id": "req-list-modifiers",
                "project_id": project_id,
                "target_id": mesh_id,
            },
        )
        assert any(modifier["type"] == "ARMATURE" for modifier in modifiers["modifiers"])

        animation = await _call(
            app,
            "create_keyframe_animation",
            {
                "request_id": "req-animation",
                "project_id": project_id,
                "target_id": mesh_id,
                "name": "Bounce",
                "keyframes": [
                    {"frame": 1, "location": [0.0, 0.0, 0.0]},
                    {"frame": 20, "location": [2.0, 0.0, 1.0]},
                ],
            },
        )
        assert animation["status"] == "success"
        mesh_spec = json_loads(app.context.entities.get(mesh_id).spec_json)
        assert mesh_spec["location"] == [2.0, 0.0, 1.0]

        hinge_animation = await _call(
            app,
            "create_hinge_animation",
            {
                "request_id": "req-hinge-animation",
                "project_id": project_id,
                "target_id": mesh_id,
                "name": "DoorOpen",
                "axis": "z",
                "angle_degrees": 90.0,
                "start_frame": 1,
                "end_frame": 18,
            },
        )
        looping_animation = await _call(
            app,
            "create_looping_rotation_animation",
            {
                "request_id": "req-looping-animation",
                "project_id": project_id,
                "target_id": mesh_id,
                "name": "Turntable",
                "axis": "y",
                "frame_count": 30,
            },
        )
        assert hinge_animation["status"] == "success"
        assert hinge_animation["animation"]["keyframes"][-1]["rotation"][2] == pytest.approx(1.57079632679)
        assert looping_animation["animation"]["keyframes"][-1]["rotation"][1] == pytest.approx(6.28318530718)

        listed_armatures = await _call(app, "list_armatures", {"request_id": "req-list-armatures", "project_id": project_id})
        listed_tracks = await _call(app, "list_animation_tracks", {"request_id": "req-list-tracks", "project_id": project_id, "target_id": mesh_id})
        validation = await _call(
            app,
            "validate_animation_rigging",
            {"request_id": "req-validate-animation-rigging", "project_id": project_id, "require_bound_targets": True},
        )
        assert listed_armatures["count"] >= 3
        assert any(armature["armature_id"] == mechanical_rig["armature_id"] for armature in listed_armatures["armatures"])
        assert listed_tracks["count"] >= 3
        assert validation["severity_summary"]["error"] == 0
        assert validation["metrics"]["bone_count"] >= 9

        camera = await _call(
            app,
            "create_camera",
            {
                "request_id": "req-camera",
                "project_id": project_id,
                "name": "AnimCam",
            },
        )
        camera_animation = await _call(
            app,
            "create_camera_animation",
            {
                "request_id": "req-camera-animation",
                "project_id": project_id,
                "camera_id": camera["camera"]["camera_id"],
                "frame_count": 36,
            },
        )
        assert camera_animation["status"] == "success"
        assert camera_animation["active_camera_id"] == camera["camera"]["camera_id"]
    finally:
        await app.stop()