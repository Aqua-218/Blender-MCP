from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from blender_controller.blender_runtime import BlenderRuntime
from blender_controller.runtime import RuntimeCommandError
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
async def test_single_object_tools_enforce_cardinality_and_resolve_by_tag_or_collection(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Targeting Demo"})
        project_id = str(project["project_id"])

        hero = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-hero",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Hero",
                "collection_name": "Heroes",
                "tags": ["hero"],
            },
        )
        hero_id = hero["created_object_ids"][0]

        enemy = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-enemy",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "Enemy",
                "location": [10.0, 0.0, 0.0],
                "collection_name": "Enemies",
                "tags": ["enemy"],
            },
        )
        enemy_id = enemy["created_object_ids"][0]

        select_by_tag = await _call(
            app,
            "select_object",
            {
                "request_id": "req-select-tag",
                "project_id": project_id,
                "tag": "hero",
            },
        )
        assert select_by_tag["status"] == "success"
        assert select_by_tag["selected_ids"] == [hero_id]

        select_by_spatial_range = await _call(
            app,
            "select_object",
            {
                "request_id": "req-select-spatial",
                "project_id": project_id,
                "spatial_range": {"min": [-1.0, -1.0, -1.0], "max": [1.0, 1.0, 1.0]},
            },
        )
        assert select_by_spatial_range["status"] == "success"
        assert select_by_spatial_range["selected_ids"] == [hero_id]

        tag_by_spatial_range = await _call(
            app,
            "tag_object",
            {
                "request_id": "req-tag-spatial",
                "project_id": project_id,
                "spatial_range": {"min": [-1.0, -1.0, -1.0], "max": [1.0, 1.0, 1.0]},
                "tags": ["close-range"],
            },
        )
        assert tag_by_spatial_range["status"] == "success"
        assert tag_by_spatial_range["modified_object_ids"] == [hero_id]

        missing_target = await _call(
            app,
            "select_object",
            {
                "request_id": "req-select-missing",
                "project_id": project_id,
                "names": ["MissingObject"],
            },
        )
        assert missing_target["status"] == "failed"
        assert "no matching targets" in missing_target["errors"][0].lower()

        stale_rename = await _call(
            app,
            "rename_object",
            {
                "request_id": "req-rename-stale",
                "project_id": project_id,
                "target_id": "stale-object-id",
                "new_name": "Renamed",
            },
        )
        assert stale_rename["status"] == "failed"
        assert "unknown object_id" in stale_rename["errors"][0].lower()

        stale_select = await _call(
            app,
            "select_object",
            {
                "request_id": "req-select-stale",
                "project_id": project_id,
                "target_id": "stale-object-id",
            },
        )
        assert stale_select["status"] == "failed"
        assert stale_select["tool_name"] == "select_object"

        unknown_project_list = await _call(
            app,
            "list_objects",
            {
                "request_id": "req-unknown-project-list",
                "project_id": "missing-project",
            },
        )
        assert unknown_project_list["status"] == "failed"
        assert unknown_project_list["tool_name"] == "list_objects"
        assert "unknown project_id" in unknown_project_list["errors"][0].lower()

        unknown_project_geometry = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-unknown-project-geometry",
                "project_id": "missing-project",
                "name": "GhostMesh",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "faces": [[0, 1, 2]],
            },
        )
        assert unknown_project_geometry["status"] == "failed"
        assert unknown_project_geometry["tool_name"] == "create_custom_mesh"
        assert "unknown project_id" in unknown_project_geometry["errors"][0].lower()

        duplicate_many = await _call(
            app,
            "duplicate_object",
            {
                "request_id": "req-duplicate-many",
                "project_id": project_id,
                "target_ids": [hero_id, enemy_id],
            },
        )
        assert duplicate_many["status"] == "failed"
        assert "exactly one resolved target" in duplicate_many["summary"].lower()

        delete_by_collection = await _call(
            app,
            "delete_object",
            {
                "request_id": "req-delete-collection",
                "project_id": project_id,
                "match_collection_name": "Enemies",
                "destructive_confirmation": True,
            },
        )
        assert delete_by_collection["status"] == "success"
        assert delete_by_collection["deleted_object_ids"] == [enemy_id]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_geometry_validation_and_render_controls_on_mock_runtime(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Geometry Demo"})
        project_id = str(project["project_id"])

        invalid_mesh = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-invalid-mesh",
                "project_id": project_id,
                "name": "BrokenMesh",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "faces": [[0, 1, 99]],
            },
        )
        assert invalid_mesh["status"] == "failed"
        assert any("out-of-range vertex" in error for error in invalid_mesh["errors"])

        invalid_curve = await _call(
            app,
            "create_curve",
            {
                "request_id": "req-invalid-curve",
                "project_id": project_id,
                "name": "BrokenCurve",
                "curve_type": "polyline",
                "points": [[0, 0], [1, 1]],
            },
        )
        assert invalid_curve["status"] == "failed"
        assert "exactly 3 coordinates" in invalid_curve["errors"][0].lower()

        curve = await _call(
            app,
            "create_curve",
            {
                "request_id": "req-curve",
                "project_id": project_id,
                "name": "GuideCurve",
                "curve_type": "path",
                "points": [[0, 0, 0], [0, 0, 2]],
                "collection_name": "Guides",
                "tags": ["guide"],
            },
        )
        assert curve["status"] == "success"
        assert curve["objects"][0]["data"] == {
            "curve_type": "path",
            "points": [[0, 0, 0], [0, 0, 2]],
            "resolution": 12,
        }

        found_curve = await _call(
            app,
            "find_objects",
            {
                "request_id": "req-find-curve",
                "project_id": project_id,
                "tag": "guide",
                "collection_name": "Guides",
            },
        )
        assert len(found_curve["objects"]) == 1
        assert found_curve["objects"][0]["name"] == "GuideCurve"

        mesh = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-mesh",
                "project_id": project_id,
                "name": "EditableMesh",
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "faces": [[0, 1, 2]],
            },
        )
        mesh_id = mesh["created_object_ids"][0]

        invalid_edit = await _call(
            app,
            "edit_mesh",
            {
                "request_id": "req-invalid-edit",
                "project_id": project_id,
                "target_id": mesh_id,
                "faces": [[0, 1, 2]],
            },
        )
        assert invalid_edit["status"] == "failed"
        assert "requires vertices" in invalid_edit["summary"].lower()

        text = await _call(
            app,
            "create_text",
            {
                "request_id": "req-text",
                "project_id": project_id,
                "name": "Label",
                "text": "Hello",
            },
        )
        text_id = text["created_object_ids"][0]

        invalid_extrude = await _call(
            app,
            "extrude_mesh",
            {
                "request_id": "req-invalid-extrude",
                "project_id": project_id,
                "target_id": text_id,
            },
        )
        assert invalid_extrude["status"] == "failed"
        assert "not a mesh object" in invalid_extrude["errors"][0].lower()

        extrude_mesh = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-extrude-mesh",
                "project_id": project_id,
                "name": "ExtrudeMesh",
                "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                "faces": [[0, 1, 2, 3]],
            },
        )
        extrude_mesh_id = extrude_mesh["created_object_ids"][0]

        duplicate_vertices_mesh = await _call(
            app,
            "create_custom_mesh",
            {
                "request_id": "req-duplicates",
                "project_id": project_id,
                "name": "DuplicateMesh",
                "vertices": [[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "faces": [[0, 2, 3], [1, 2, 3]],
            },
        )
        duplicate_mesh_id = duplicate_vertices_mesh["created_object_ids"][0]

        extruded = await _call(
            app,
            "extrude_mesh",
            {
                "request_id": "req-extrude-success",
                "project_id": project_id,
                "target_id": extrude_mesh_id,
            },
        )
        assert set(extruded["objects"][0]["data"].keys()).issuperset({"vertices", "edges", "faces"})
        assert len(extruded["objects"][0]["data"]["vertices"]) > 4
        assert len(extruded["objects"][0]["data"]["faces"]) > 2

        beveled = await _call(
            app,
            "bevel_edges",
            {
                "request_id": "req-bevel-success",
                "project_id": project_id,
                "target_id": extrude_mesh_id,
            },
        )
        assert set(beveled["objects"][0]["data"].keys()).issuperset({"vertices", "edges", "faces"})

        recalculated = await _call(
            app,
            "recalculate_normals",
            {
                "request_id": "req-recalc-success",
                "project_id": project_id,
                "target_id": extrude_mesh_id,
            },
        )
        assert set(recalculated["objects"][0]["data"].keys()).issuperset({"vertices", "edges", "faces"})

        merged = await _call(
            app,
            "merge_vertices",
            {
                "request_id": "req-merge",
                "project_id": project_id,
                "target_id": duplicate_mesh_id,
            },
        )
        merged_data = merged["objects"][0]["data"]
        assert len(merged_data["vertices"]) == 3
        assert all(
            all(vertex_index < len(merged_data["vertices"]) for vertex_index in face)
            for face in merged_data["faces"]
        )

        camera_a = await _call(
            app,
            "create_camera",
            {"request_id": "req-camera-a", "project_id": project_id, "name": "CameraA"},
        )
        camera_a_id = camera_a["camera"]["camera_id"]
        camera_b = await _call(
            app,
            "create_camera",
            {"request_id": "req-camera-b", "project_id": project_id, "name": "CameraB"},
        )
        camera_b_id = camera_b["camera"]["camera_id"]

        render_settings = await _call(
            app,
            "set_render_settings",
            {
                "request_id": "req-render-settings",
                "project_id": project_id,
                "preset_name": "preview",
                "samples": 99,
            },
        )
        assert render_settings["status"] == "success"
        assert render_settings["render_settings"]["samples"] == 99

        invalid_preset = await _call(
            app,
            "set_render_settings",
            {
                "request_id": "req-invalid-preset",
                "project_id": project_id,
                "preset_name": "does-not-exist",
            },
        )
        assert invalid_preset["status"] == "failed"
        assert "unknown render preset" in invalid_preset["errors"][0]

        large_target = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-large",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "LargeCube",
                "scale": [4.0, 4.0, 4.0],
            },
        )
        large_target_id = large_target["created_object_ids"][0]

        framed = await _call(
            app,
            "frame_object",
            {
                "request_id": "req-frame",
                "project_id": project_id,
                "camera_id": camera_a_id,
                "target_id": large_target_id,
            },
        )
        assert framed["status"] == "success"
        assert framed["camera"]["location"][1] < -5.0

        render = await _call(
            app,
            "render_preview",
            {
                "request_id": "req-render",
                "project_id": project_id,
                "camera_id": camera_b_id,
            },
        )
        assert render["status"] == "success"
        assert render["active_camera_id"] == camera_b_id
        assert Path(render["image_paths"][0]).exists()
    finally:
        await app.stop()


def test_blender_runtime_list_and_find_objects_keep_read_only_ids_stable(monkeypatch) -> None:
    class FakeObject(dict):
        def __init__(self, name: str, pointer: int):
            super().__init__()
            self.name = name
            self.type = "MESH"
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(materials=[], vertices=[], edges=[], polygons=[])
            self._pointer = pointer

        def as_pointer(self) -> int:
            return self._pointer

    fake_object = FakeObject("Cube", 101)
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(objects=[fake_object], materials=[]),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    listed = asyncio.run(runtime.cmd_list_objects({}))
    found = asyncio.run(runtime.cmd_find_objects({"names": ["Cube"]}))

    listed_id = listed["objects"][0]["object_id"]
    found_id = found["objects"][0]["object_id"]
    assert listed_id == found_id
    assert "mcp_id" not in fake_object

    resolved = runtime._object_by_id(listed_id)
    assert resolved is fake_object
    assert fake_object["mcp_id"] == listed_id


def test_blender_runtime_open_project_resets_ephemeral_object_ids(monkeypatch, tmp_path: Path) -> None:
    class FakeObject(dict):
        def __init__(self, name: str, pointer: int):
            super().__init__()
            self.name = name
            self.type = "MESH"
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(materials=[], vertices=[], edges=[], polygons=[])
            self._pointer = pointer

        def as_pointer(self) -> int:
            return self._pointer

    old_object = FakeObject("OldCube", 101)
    replacement_object = FakeObject("NewCube", 101)
    fake_data = SimpleNamespace(objects=[old_object], materials=[])

    def open_mainfile(*, filepath: str) -> None:
        fake_data.objects = [replacement_object]

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=fake_data,
        ops=SimpleNamespace(wm=SimpleNamespace(open_mainfile=open_mainfile)),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    blend_path = tmp_path / "reloaded.blend"
    blend_path.write_text("placeholder", encoding="utf-8")

    runtime = BlenderRuntime()
    listed = asyncio.run(runtime.cmd_list_objects({}))
    listed_id = listed["objects"][0]["object_id"]

    asyncio.run(runtime.cmd_open_project({"blend_file_path": str(blend_path)}))

    with pytest.raises(RuntimeCommandError, match="Unknown object_id"):
        runtime._object_by_id(listed_id)


def test_blender_runtime_open_project_returns_persisted_project_id(monkeypatch, tmp_path: Path) -> None:
    class FakeScene(dict):
        def __init__(self):
            super().__init__()
            self.name = "Scene"
            self.unit_settings = SimpleNamespace(scale_length=1.0)

    scene = FakeScene()
    fake_data = SimpleNamespace(filepath="", objects=[], materials=[], is_dirty=False)

    def open_mainfile(*, filepath: str) -> None:
        fake_data.filepath = filepath
        scene[BlenderRuntime._PROJECT_ID_KEY] = "project-persisted"
        scene[BlenderRuntime._PROJECT_NAME_KEY] = "Persisted Project"
        scene[BlenderRuntime._PROJECT_TEMPLATE_KEY] = "blank"

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=scene),
        data=fake_data,
        ops=SimpleNamespace(wm=SimpleNamespace(open_mainfile=open_mainfile)),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    blend_path = tmp_path / "persisted.blend"
    blend_path.write_text("placeholder", encoding="utf-8")

    runtime = BlenderRuntime()
    opened = asyncio.run(runtime.cmd_open_project({"blend_file_path": str(blend_path)}))

    assert opened["project_id"] == "project-persisted"
    assert opened["project_name"] == "Persisted Project"


def test_blender_runtime_save_project_persists_project_id_for_future_reopen(monkeypatch, tmp_path: Path) -> None:
    class FakeScene(dict):
        def __init__(self):
            super().__init__()
            self.name = "Scene"
            self.unit_settings = SimpleNamespace(scale_length=1.0)

    scene = FakeScene()
    saved_metadata: dict[str, dict[str, object]] = {}
    fake_data = SimpleNamespace(filepath="", objects=[], materials=[], is_dirty=False)

    def save_as_mainfile(*, filepath: str, copy: bool = False) -> None:
        fake_data.filepath = filepath
        saved_metadata[filepath] = dict(scene)

    def open_mainfile(*, filepath: str) -> None:
        scene.clear()
        scene.update(saved_metadata.get(filepath, {}))
        fake_data.filepath = filepath

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=scene),
        data=fake_data,
        ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=save_as_mainfile, open_mainfile=open_mainfile)),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    blend_path = tmp_path / "persist-after-save.blend"
    blend_path.write_text("placeholder", encoding="utf-8")

    runtime = BlenderRuntime()
    first_open = asyncio.run(runtime.cmd_open_project({"blend_file_path": str(blend_path)}))
    asyncio.run(runtime.cmd_save_project({"project_id": "project-persisted-on-save", "blend_file_path": str(blend_path)}))
    reopened = asyncio.run(runtime.cmd_open_project({"blend_file_path": str(blend_path)}))

    assert first_open["project_id"] is None
    assert reopened["project_id"] == "project-persisted-on-save"


def test_blender_runtime_structural_mutation_resets_ephemeral_object_ids(monkeypatch) -> None:
    class FakeObjects(list):
        def remove(self, obj, do_unlink: bool = False) -> None:  # type: ignore[override]
            super().remove(obj)

    class FakeObject(dict):
        def __init__(self, name: str, pointer: int):
            super().__init__()
            self.name = name
            self.type = "MESH"
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(materials=[], vertices=[], edges=[], polygons=[])
            self._pointer = pointer

        def as_pointer(self) -> int:
            return self._pointer

    old_object = FakeObject("OldCube", 101)
    replacement_object = FakeObject("NewCube", 101)
    fake_data = SimpleNamespace(objects=FakeObjects([old_object]), materials=[])
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=fake_data,
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    listed = asyncio.run(runtime.cmd_list_objects({}))
    listed_id = listed["objects"][0]["object_id"]

    asyncio.run(runtime.cmd_delete_objects({"target_id": listed_id}))
    fake_data.objects.append(replacement_object)

    with pytest.raises(RuntimeCommandError, match="Unknown object_id"):
        runtime._object_by_id(listed_id)


def test_blender_runtime_object_payload_includes_mesh_data(monkeypatch) -> None:
    class FakeCoord:
        def __init__(self, x: float, y: float, z: float):
            self.x = x
            self.y = y
            self.z = z

    class FakeVertex:
        def __init__(self, coord: tuple[float, float, float]):
            self.co = FakeCoord(*coord)

    class FakeEdge:
        def __init__(self, vertices: tuple[int, int]):
            self.vertices = vertices

    class FakePolygon:
        def __init__(self, vertices: tuple[int, ...]):
            self.vertices = vertices

    class FakeObject(dict):
        def __init__(self):
            super().__init__()
            self.name = "Mesh"
            self.type = "MESH"
            self.location = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.rotation_euler = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.scale = SimpleNamespace(x=1.0, y=1.0, z=1.0)
            self.hide_viewport = False
            self.users_collection = [SimpleNamespace(name="Scene Collection")]
            self.data = SimpleNamespace(
                materials=[],
                vertices=[FakeVertex((0.0, 0.0, 0.0)), FakeVertex((1.0, 0.0, 0.0)), FakeVertex((0.0, 1.0, 0.0))],
                edges=[FakeEdge((0, 1)), FakeEdge((1, 2))],
                polygons=[FakePolygon((0, 1, 2))],
            )
            self._pointer = 404

        def as_pointer(self) -> int:
            return self._pointer

    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(version=(4, 0, 0)),
        context=SimpleNamespace(scene=SimpleNamespace(name="Scene")),
        data=SimpleNamespace(objects=[], materials=[]),
    )
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    runtime = BlenderRuntime()
    payload = runtime._object_payload(FakeObject(), persist_id=False)

    assert payload["data"] == {
        "vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        "edges": [[0, 1], [1, 2]],
        "faces": [[0, 1, 2]],
    }