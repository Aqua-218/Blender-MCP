from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from blender_controller.blender_runtime import BlenderRuntime
from blender_controller.runtime import RuntimeCommandError
from mcp_server.config import ServerSettings
from mcp_server.persistence import EntityRecord
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port


async def _call(app: MCPServerApplication, name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = await _call_raw(app, name, arguments)
    return response["result"]


async def _call_raw(app: MCPServerApplication, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return await app.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_sanitizes_implicit_output_path(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-project", "name": "Render Safety"},
        )
        project_id = str(project["project_id"])

        render = await _call(
            app,
            "render_preview",
            {"request_id": "../../outside", "project_id": project_id},
        )
        image_path = Path(render["image_paths"][0]).resolve()
        expected_root = (tmp_path / "workspace" / "renders" / project_id).resolve()

        assert image_path.parent == expected_root
        assert image_path.name == "outside.png"
        assert image_path.exists()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_relative_output_path_uses_project_render_directory(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-project-rooted", "name": "Render Rooted", "workspace_root": "workspace-b"},
        )
        project_id = str(project["project_id"])

        render = await _call(
            app,
            "render_preview",
            {
                "request_id": "render-relative-rooted",
                "project_id": project_id,
                "output_path": "renders/custom.png",
            },
        )

        assert Path(render["image_paths"][0]).resolve() == (tmp_path / "workspace-b" / "renders" / project_id / "custom.png").resolve()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_material_rejects_unknown_preset(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "material-project", "name": "Material Safety"},
        )
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "create_material",
            {
                "request_id": "unknown-preset",
                "project_id": project_id,
                "name": "UnsafeMaterial",
                "preset_name": "does-not-exist",
            },
        )

        assert result["status"] == "failed"
        assert "unknown material preset" in result["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_material_rejects_targets_without_material_slots(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "material-light-project", "name": "Material Light"},
        )
        project_id = str(project["project_id"])
        material = await _call(
            app,
            "create_material",
            {
                "request_id": "material-light-material",
                "project_id": project_id,
                "name": "Surface",
                "preset_name": "metal",
            },
        )
        light = await _call(
            app,
            "create_light",
            {"request_id": "material-light-light", "project_id": project_id, "name": "KeyLight"},
        )

        result = await _call(
            app,
            "apply_material",
            {
                "request_id": "material-light-apply",
                "project_id": project_id,
                "material_id": material["material"]["material_id"],
                "target_ids": [light["light"]["light_id"]],
            },
        )

        assert result["status"] == "failed"
        assert "support material assignment" in result["errors"][0]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_material_syncs_entity_cache(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "material-cache-project", "name": "Material Cache"},
        )
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "material-cache-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Cube",
            },
        )
        cube_id = cube["created_object_ids"][0]
        material = await _call(
            app,
            "create_material",
            {
                "request_id": "material-cache-material",
                "project_id": project_id,
                "name": "Surface",
                "preset_name": "metal",
            },
        )
        material_id = material["material"]["material_id"]

        applied = await _call(
            app,
            "apply_material",
            {
                "request_id": "material-cache-apply",
                "project_id": project_id,
                "material_id": material_id,
                "target_ids": [cube_id],
            },
        )

        with app.context.db.session() as session:
            entity = session.get(EntityRecord, cube_id)

        assert applied["status"] == "success"
        assert applied["modified_object_ids"] == [cube_id]
        assert entity is not None
        assert material_id in entity.spec_json
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_material_returns_partial_success_for_mixed_targets(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "mixed-material-project", "name": "Mixed Material"},
        )
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "mixed-material-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Cube",
            },
        )
        light = await _call(
            app,
            "create_light",
            {"request_id": "mixed-material-light", "project_id": project_id, "name": "KeyLight"},
        )
        material = await _call(
            app,
            "create_material",
            {
                "request_id": "mixed-material-create",
                "project_id": project_id,
                "name": "Surface",
                "preset_name": "metal",
            },
        )

        result = await _call(
            app,
            "apply_material",
            {
                "request_id": "mixed-material-apply",
                "project_id": project_id,
                "material_id": material["material"]["material_id"],
                "target_ids": [cube["created_object_ids"][0], light["light"]["light_id"]],
            },
        )

        assert result["status"] == "partial_success"
        assert result["modified_object_ids"] == [cube["created_object_ids"][0]]
        assert result["warnings"]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_apply_material_unknown_material_returns_failed_result(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "unknown-material-project", "name": "Unknown Material"},
        )
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "unknown-material-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Cube",
            },
        )

        response = await _call_raw(
            app,
            "apply_material",
            {
                "request_id": "unknown-material-apply",
                "project_id": project_id,
                "material_id": "missing-material",
                "target_ids": cube["created_object_ids"],
            },
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "apply_material"
        assert "unknown material_id" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_unknown_camera_returns_failed_result(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "unknown-camera-project", "name": "Unknown Camera"},
        )

        response = await _call_raw(
            app,
            "render_preview",
            {
                "request_id": "unknown-camera-render",
                "project_id": str(project["project_id"]),
                "camera_id": "missing-camera",
            },
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert response["result"]["tool_name"] == "render_preview"
        assert "unknown camera_id" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_relative_output_path_cannot_escape_project_render_directory(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "root-locked-project", "name": "Root Locked", "workspace_root": "workspace-a"},
        )

        response = await _call_raw(
            app,
            "render_preview",
            {
                "request_id": "root-locked-render",
                "project_id": str(project["project_id"]),
                "output_path": "renders/../../workspace-b/renders/escape.png",
            },
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert "render directory" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_absolute_output_path_cannot_cross_workspace_roots(tmp_path: Path) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace-a,workspace-b",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(
            app,
            "create_project",
            {"request_id": "absolute-root-locked-project", "name": "Absolute Root Locked", "workspace_root": "workspace-a"},
        )

        response = await _call_raw(
            app,
            "render_preview",
            {
                "request_id": "absolute-root-locked-render",
                "project_id": str(project["project_id"]),
                "output_path": str((tmp_path / "workspace-b" / "renders" / "escape.png").resolve()),
            },
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert "render directory" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_entity_cache_keeps_object_shape_for_lights_and_cameras(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-entity-project", "name": "Render Entity Cache"},
        )
        project_id = str(project["project_id"])
        light = await _call(
            app,
            "create_light",
            {"request_id": "render-entity-light", "project_id": project_id, "name": "KeyLight"},
        )
        camera = await _call(
            app,
            "create_camera",
            {"request_id": "render-entity-camera", "project_id": project_id, "name": "ShotCam"},
        )

        await _call(
            app,
            "set_light",
            {"request_id": "render-entity-set-light", "project_id": project_id, "light_id": light["light"]["light_id"], "intensity": 1234.0},
        )
        await _call(
            app,
            "set_camera",
            {"request_id": "render-entity-set-camera", "project_id": project_id, "camera_id": camera["camera"]["camera_id"], "focal_length": 35.0},
        )

        with app.context.db.session() as session:
            light_entity = session.get(EntityRecord, light["light"]["light_id"])
            camera_entity = session.get(EntityRecord, camera["camera"]["camera_id"])

        assert light_entity is not None
        assert camera_entity is not None

        light_spec = json.loads(light_entity.spec_json)
        camera_spec = json.loads(camera_entity.spec_json)

        assert light_entity.entity_type == "light"
        assert camera_entity.entity_type == "camera"
        assert light_spec["object_id"] == light["light"]["light_id"]
        assert camera_spec["object_id"] == camera["camera"]["camera_id"]
        assert light_spec["data"] == {}
        assert camera_spec["data"] == {}
        assert "light_id" not in light_spec
        assert "camera_id" not in camera_spec
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_preview_rejects_unexpected_controller_image_path(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "unexpected-path-project", "name": "Unexpected Path"},
        )
        project_id = str(project["project_id"])
        original_invoke = app.context.bridge.invoke

        async def fake_invoke(command: str, payload: dict[str, object], read_only: bool = False):
            if command == "render_preview":
                return {"image_path": str((tmp_path / "workspace" / "renders" / "unexpected.png").resolve())}
            return await original_invoke(command, payload, read_only=read_only)

        app.context.bridge.invoke = fake_invoke  # type: ignore[assignment]

        response = await _call_raw(
            app,
            "render_preview",
            {"request_id": "unexpected-path-render", "project_id": project_id},
        )

        assert "error" not in response
        assert response["result"]["status"] == "failed"
        assert "unexpected render output path" in response["result"]["errors"][0].lower()
    finally:
        await app.stop()


def test_blender_runtime_set_render_settings_returns_payload_without_transparent_background(monkeypatch) -> None:
    fake_scene = SimpleNamespace(
        render=SimpleNamespace(
            engine="BLENDER_EEVEE",
            resolution_x=1920,
            resolution_y=1080,
            film_transparent=False,
        ),
        cycles=SimpleNamespace(samples=128),
        eevee=SimpleNamespace(taa_render_samples=16),
    )
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=fake_scene),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    result = asyncio.run(
        runtime.cmd_set_render_settings(
            {
                "engine": "CYCLES",
                "resolution_x": 800,
                "resolution_y": 600,
                "samples": 32,
            }
        )
    )

    assert result["render_settings"] == {
        "engine": "CYCLES",
        "resolution_x": 800,
        "resolution_y": 600,
        "samples": 32,
        "transparent_background": False,
    }


def test_blender_runtime_material_payload_tracks_explicit_supported_properties(monkeypatch) -> None:
    class FakeSocket:
        def __init__(self, default_value):
            self.default_value = default_value

    class FakeMaterial(dict):
        def __init__(self, name: str):
            super().__init__()
            self.name = name
            self.use_nodes = True
            self.node_tree = SimpleNamespace(
                nodes={
                    "Principled BSDF": SimpleNamespace(
                        inputs={
                            "Base Color": FakeSocket([0.8, 0.8, 0.8, 1.0]),
                            "Roughness": FakeSocket(0.5),
                            "Metallic": FakeSocket(0.0),
                            "Specular IOR Level": FakeSocket(0.5),
                            "Alpha": FakeSocket(1.0),
                            "Emission Color": FakeSocket([0.0, 0.0, 0.0, 1.0]),
                            "Emission Strength": FakeSocket(0.0),
                        }
                    )
                }
            )

    class FakeMaterials(list):
        def new(self, name: str):
            material = FakeMaterial(name)
            self.append(material)
            return material

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(materials=FakeMaterials()),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    created = asyncio.run(
        runtime.cmd_create_pbr_material(
            {
                "name": "ParityMaterial",
                "base_color": [0.1, 0.2, 0.3, 1.0],
                "roughness": 0.25,
                "metallic": 0.75,
                "specular": 0.4,
                "emission_color": [0.9, 0.8, 0.1, 1.0],
                "emission_strength": 2.5,
            }
        )
    )

    assert created["material"]["properties"] == {
        "base_color": [0.1, 0.2, 0.3, 1.0],
        "roughness": 0.25,
        "metallic": 0.75,
        "specular": 0.4,
        "emission_color": [0.9, 0.8, 0.1, 1.0],
        "emission_strength": 2.5,
    }

    updated = asyncio.run(
        runtime.cmd_set_material_property(
            {
                "material_id": created["material"]["material_id"],
                "property_name": "alpha",
                "value": 0.35,
            }
        )
    )

    assert updated["material"]["properties"] == {
        "base_color": [0.1, 0.2, 0.3, 1.0],
        "roughness": 0.25,
        "metallic": 0.75,
        "specular": 0.4,
        "emission_color": [0.9, 0.8, 0.1, 1.0],
        "emission_strength": 2.5,
        "alpha": 0.35,
    }


def test_blender_runtime_material_properties_fall_back_without_principled_bsdf(monkeypatch) -> None:
    class FakeMaterial(dict):
        def __init__(self, name: str):
            super().__init__()
            self.name = name
            self.use_nodes = True
            self.node_tree = SimpleNamespace(nodes={})
            self.diffuse_color = [1.0, 1.0, 1.0, 1.0]

    class FakeMaterials(list):
        def new(self, name: str):
            material = FakeMaterial(name)
            self.append(material)
            return material

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(materials=FakeMaterials()),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    created = asyncio.run(
        runtime.cmd_create_pbr_material(
            {
                "name": "FallbackMaterial",
                "base_color": [0.2, 0.3, 0.4, 1.0],
                "roughness": 0.8,
                "metallic": 0.1,
            }
        )
    )

    assert created["material"]["properties"] == {
        "base_color": [0.2, 0.3, 0.4, 1.0],
        "roughness": 0.8,
        "metallic": 0.1,
    }
    material = fake_bpy.data.materials[0]
    assert material["base_color"] == [0.2, 0.3, 0.4, 1.0]
    assert material.diffuse_color == [0.2, 0.3, 0.4, 1.0]


def test_blender_runtime_apply_material_filters_unsupported_targets(monkeypatch) -> None:
    class FakeMaterial(dict):
        def __init__(self, material_id: str, name: str):
            super().__init__(mcp_id=material_id)
            self.name = name
            self.use_nodes = False
            self.node_tree = None

    class FakeObject(dict):
        def __init__(self, object_id: str, name: str, object_type: str, pointer: int, materials=None):
            super().__init__(mcp_id=object_id)
            self.name = name
            self.type = object_type
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            if materials is None:
                self.data = SimpleNamespace()
            else:
                self.data = SimpleNamespace(materials=materials, vertices=[], edges=[], polygons=[])
            self._pointer = pointer

        def as_pointer(self) -> int:
            return self._pointer

    material = FakeMaterial("material-surface", "Surface")
    mesh = FakeObject("obj-mesh", "Mesh", "MESH", 101, materials=[])
    light = FakeObject("obj-light", "KeyLight", "LIGHT", 202)
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(objects=[mesh, light], materials=[material]),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()

    mixed_result = asyncio.run(
        runtime.cmd_apply_material(
            {
                "material_id": "material-surface",
                "target_ids": ["obj-mesh", "obj-light"],
            }
        )
    )

    assert mixed_result["objects"] == [runtime._object_payload(mesh)]
    assert mesh.data.materials == [material]

    light_only_result = asyncio.run(
        runtime.cmd_apply_material(
            {
                "material_id": "material-surface",
                "target_ids": ["obj-light"],
            }
        )
    )

    assert light_only_result["objects"] == []


def test_blender_runtime_nodes_modifier_is_virtual_and_does_not_call_blender_modifier_api(monkeypatch) -> None:
    class FakeModifiers(list):
        def __contains__(self, name: object) -> bool:
            return any(modifier.name == name for modifier in self)

        def get(self, name: str):
            return next((modifier for modifier in self if modifier.name == name), None)

        def new(self, *, name: str, type: str):  # noqa: A002
            if type == "NODES":
                raise AssertionError("NODES modifiers should be stored virtually")
            modifier = SimpleNamespace(name=name, type=type)
            self.append(modifier)
            return modifier

    class FakeObject(dict):
        def __init__(self):
            super().__init__(mcp_id="obj-building")
            self.name = "Building"
            self.type = "MESH"
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(materials=[], vertices=[], edges=[], polygons=[])
            self.modifiers = FakeModifiers()

        def as_pointer(self) -> int:
            return 101

    fake_object = FakeObject()
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(objects=[fake_object], materials=[]),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    added = asyncio.run(
        runtime.cmd_add_modifier(
            {
                "target_id": "obj-building",
                "modifier_type": "NODES",
                "name": "ProceduralBuildingNodes",
                "params": {"floors": 6},
            }
        )
    )
    listed = asyncio.run(runtime.cmd_list_modifiers({"target_id": "obj-building"}))

    assert added["modifiers"] == [
        {"type": "NODES", "name": "ProceduralBuildingNodes", "params": {"floors": 6}, "virtual": True}
    ]
    assert listed["modifiers"] == added["modifiers"]


def test_blender_runtime_rejects_wrong_object_types_for_light_and_camera_commands(monkeypatch, tmp_path: Path) -> None:
    class FakeObject(dict):
        def __init__(self, object_id: str, name: str, object_type: str, pointer: int):
            super().__init__(mcp_id=object_id)
            self.name = name
            self.type = object_type
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(materials=[], vertices=[], edges=[], polygons=[])
            self._pointer = pointer

        def as_pointer(self) -> int:
            return self._pointer

    fake_mesh = FakeObject("obj-mesh", "Mesh", "MESH", 313)
    fake_scene = SimpleNamespace(
        collection=SimpleNamespace(objects=SimpleNamespace(link=lambda obj: None)),
        camera=None,
        render=SimpleNamespace(engine="BLENDER_EEVEE", resolution_x=512, resolution_y=512, film_transparent=False, filepath=""),
        cycles=SimpleNamespace(samples=16),
        eevee=SimpleNamespace(taa_render_samples=16),
    )
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=fake_scene),
        data=SimpleNamespace(objects=[fake_mesh], materials=[]),
        ops=SimpleNamespace(render=SimpleNamespace(render=lambda write_still=True: None)),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()

    with pytest.raises(RuntimeCommandError, match="not a light object"):
        asyncio.run(runtime.cmd_set_light({"light_id": "obj-mesh", "intensity": 99.0}))

    with pytest.raises(RuntimeCommandError, match="not a camera object"):
        asyncio.run(runtime.cmd_set_camera({"camera_id": "obj-mesh", "focal_length": 35.0}))

    with pytest.raises(RuntimeCommandError, match="not a camera object"):
        asyncio.run(runtime.cmd_set_active_camera({"camera_id": "obj-mesh"}))

    with pytest.raises(RuntimeCommandError, match="not a camera object"):
        asyncio.run(
            runtime.cmd_render_preview(
                {
                    "camera_id": "obj-mesh",
                    "output_path": str(tmp_path / "preview.png"),
                }
            )
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_render_profile_applies_standard_preset(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-profile-project", "name": "Render Profile"},
        )
        project_id = str(project["project_id"])

        await _call(
            app,
            "set_render_profile",
            {"request_id": "render-profile-set", "project_id": project_id, "preset_name": "standard"},
        )
        settings_result = await _call(
            app,
            "get_render_settings",
            {"request_id": "render-profile-get", "project_id": project_id},
        )

        assert settings_result["render_settings"]["engine"] == "BLENDER_EEVEE"
        assert settings_result["render_settings"]["resolution_x"] == 1280
        assert settings_result["render_settings"]["samples"] == 64
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_standard_and_final_use_named_presets(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-modes-project", "name": "Render Modes"},
        )
        project_id = str(project["project_id"])

        standard = await _call(
            app,
            "render_standard",
            {"request_id": "render-standard-run", "project_id": project_id},
        )
        final = await _call(
            app,
            "render_final",
            {"request_id": "render-final-run", "project_id": project_id},
        )

        assert standard["status"] == "success"
        assert standard["render"]["render_settings"]["resolution_x"] == 1280
        assert final["status"] == "success"
        assert final["render"]["render_settings"]["engine"] == "CYCLES"
        assert Path(str(final["image_paths"][0])).exists()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_final_allows_explicit_resolution_override(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-override-project", "name": "Render Override"},
        )
        project_id = str(project["project_id"])

        final = await _call(
            app,
            "render_final",
            {
                "request_id": "render-final-override",
                "project_id": project_id,
                "resolution_x": 1280,
                "resolution_y": 720,
                "transparent_background": False,
            },
        )

        assert final["status"] == "success"
        assert final["render"]["render_settings"]["engine"] == "CYCLES"
        assert final["render"]["render_settings"]["resolution_x"] == 1280
        assert final["render"]["render_settings"]["resolution_y"] == 720
        assert final["render"]["render_settings"]["transparent_background"] is False
        assert Path(str(final["image_paths"][0])).exists()
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_multiview_outputs_one_image_per_camera(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-multiview-project", "name": "Render Multiview"},
        )
        project_id = str(project["project_id"])
        camera_a = await _call(
            app,
            "create_camera",
            {"request_id": "render-multiview-camera-a", "project_id": project_id, "name": "CamA"},
        )
        camera_b = await _call(
            app,
            "create_camera",
            {
                "request_id": "render-multiview-camera-b",
                "project_id": project_id,
                "name": "CamB",
                "location": [2.0, -4.0, 2.0],
            },
        )

        result = await _call(
            app,
            "render_multiview",
            {
                "request_id": "render-multiview-run",
                "project_id": project_id,
                "camera_ids": [camera_a["camera"]["camera_id"], camera_b["camera"]["camera_id"]],
            },
        )

        assert result["status"] == "success"
        assert len(result["image_paths"]) == 2
        assert all(Path(path).exists() for path in result["image_paths"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_multiview_cameras_creates_requested_count(tmp_path: Path) -> None:
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
        project = await _call(
            app,
            "create_project",
            {"request_id": "render-multiview-helper-project", "name": "Render Multiview Helper"},
        )
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "create_multiview_cameras",
            {
                "request_id": "render-multiview-helper-run",
                "project_id": project_id,
                "count": 3,
                "prefix": "Orbit",
            },
        )

        assert result["status"] == "success"
        assert len(result["cameras"]) == 3
        assert len(result["created_object_ids"]) == 3
        assert all(camera["name"].startswith("Orbit_") for camera in result["cameras"])
    finally:
        await app.stop()
