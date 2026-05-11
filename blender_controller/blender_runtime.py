from __future__ import annotations

import json
import shutil
from contextlib import suppress
from pathlib import Path
from typing import Any

from mcp_server.utils import new_id

from blender_controller.runtime import BaseRuntime, RuntimeCommandError


class BlenderRuntime(BaseRuntime):
    supports_concurrent_reads = False
    _PROJECT_ID_KEY = "mcp_project_id"
    _PROJECT_NAME_KEY = "mcp_project_name"
    _PROJECT_TEMPLATE_KEY = "mcp_template_type"
    _MATERIAL_PROPERTIES_KEY = "mcp_material_properties_json"
    _VIRTUAL_MODIFIERS_KEY = "mcp_virtual_modifiers_json"

    def __init__(self) -> None:
        super().__init__()
        try:
            import bpy  # type: ignore
        except ImportError as exc:  # pragma: no cover - requires Blender runtime
            raise RuntimeCommandError(
                "controller_unavailable",
                "Blender runtime backend requires bpy and must run inside Blender.",
            ) from exc
        self.bpy = bpy
        self._ephemeral_object_ids: dict[int, str] = {}

    def _reset_object_id_cache(self) -> None:
        self._ephemeral_object_ids.clear()

    def _project_metadata(self) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        scene = self.bpy.context.scene
        scene_get = getattr(scene, "get", None)
        lookup = scene_get if callable(scene_get) else (lambda _key, default=None: default)
        data_filepath = getattr(self.bpy.data, "filepath", "")
        unit_settings = getattr(scene, "unit_settings", None)
        return {
            "project_id": lookup(self._PROJECT_ID_KEY),
            "project_name": str(lookup(self._PROJECT_NAME_KEY, Path(data_filepath or scene.name).stem)),
            "template_type": str(lookup(self._PROJECT_TEMPLATE_KEY, "blank")),
            "unit_scale": float(getattr(unit_settings, "scale_length", 1.0)),
            "active_scene_name": scene.name,
        }

    async def cmd_get_runtime_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        info = await super().cmd_get_runtime_info(payload)
        info.update(
            {
                "backend": "blender",
                "blender_version": list(self.bpy.app.version),
                "active_scene_name": self.bpy.context.scene.name,
            }
        )
        return info

    async def cmd_create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.bpy.ops.wm.read_homefile(use_empty=True)
        self._reset_object_id_cache()
        scene = self.bpy.context.scene
        scene.name = payload.get("active_scene_name", "Scene")
        scene.unit_settings.scale_length = float(payload.get("unit_scale", 1.0))
        scene[self._PROJECT_ID_KEY] = payload["project_id"]
        scene[self._PROJECT_NAME_KEY] = payload.get("name", Path(payload["blend_file_path"]).stem)
        scene[self._PROJECT_TEMPLATE_KEY] = payload.get("template_type", "blank")
        blend_file_path = Path(payload["blend_file_path"])
        blend_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.bpy.ops.wm.save_as_mainfile(filepath=str(blend_file_path), copy=False)
        return {
            "project_id": payload["project_id"],
            "blend_file_path": str(blend_file_path),
            **self._project_metadata(),
            "object_count": len(self.bpy.data.objects),
        }

    async def cmd_open_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        blend_file_path = Path(payload["blend_file_path"])
        if not blend_file_path.exists():
            raise RuntimeCommandError("validation_error", f"Blend file does not exist: {blend_file_path}")
        self.bpy.ops.wm.open_mainfile(filepath=str(blend_file_path))
        self._reset_object_id_cache()
        return {
            "blend_file_path": str(blend_file_path),
            **self._project_metadata(),
            "object_count": len(self.bpy.data.objects),
            "dirty": bool(getattr(self.bpy.data, "is_dirty", False)),
        }

    async def cmd_save_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        filepath = str(payload.get("blend_file_path") or self.bpy.data.filepath)
        if not filepath:
            raise RuntimeCommandError("validation_error", "No active .blend filepath is available.")
        scene = self.bpy.context.scene
        if payload.get("project_id"):
            scene[self._PROJECT_ID_KEY] = payload["project_id"]
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        self.bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=False)
        return {"blend_file_path": filepath, "active_scene_name": self.bpy.context.scene.name}

    async def cmd_create_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.bpy.data.filepath:
            raise RuntimeCommandError("validation_error", "Project must be saved before a snapshot can be created.")
        self.bpy.ops.wm.save_mainfile()
        snapshot_path = Path(payload["snapshot_path"])
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.bpy.data.filepath, snapshot_path)
        return {"snapshot_path": str(snapshot_path)}

    async def cmd_restore_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot_path = Path(payload["snapshot_path"])
        if not snapshot_path.exists():
            raise RuntimeCommandError("validation_error", f"Snapshot not found: {snapshot_path}")
        target_path = Path(payload.get("target_blend_file_path") or self.bpy.data.filepath)
        if not target_path:
            raise RuntimeCommandError("validation_error", "No target .blend filepath is available for restore.")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot_path, target_path)
        self.bpy.ops.wm.open_mainfile(filepath=str(target_path))
        self._reset_object_id_cache()
        return {
            "blend_file_path": str(target_path),
            "restored_from": str(snapshot_path),
            "active_scene_name": self.bpy.context.scene.name,
        }

    async def cmd_get_project_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        scene = self.bpy.context.scene
        return {
            "blend_file_path": self.bpy.data.filepath,
            "active_scene_name": scene.name,
            "unit_scale": scene.unit_settings.scale_length,
            "object_count": len(self.bpy.data.objects),
            "dirty": bool(getattr(self.bpy.data, "is_dirty", False)),
        }

    async def cmd_list_objects(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"objects": [self._object_payload(obj, persist_id=False) for obj in self.bpy.data.objects]}

    async def cmd_find_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = [obj for obj in self.bpy.data.objects if self._object_matches(obj, payload)]
        return {"objects": [self._object_payload(obj, persist_id=False) for obj in objects]}

    async def cmd_select_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        self.bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        if objects:
            self.bpy.context.view_layer.objects.active = objects[-1]
        return {
            "selected_ids": [self._ensure_object_id(obj) for obj in objects],
            "objects": [self._object_payload(obj) for obj in objects],
        }

    async def cmd_delete_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        deleted_ids: list[str] = []
        for obj in objects:
            deleted_ids.append(self._ensure_object_id(obj))
            self.bpy.data.objects.remove(obj, do_unlink=True)
        self._reset_object_id_cache()
        return {"deleted_object_ids": deleted_ids}

    async def cmd_duplicate_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        created_objects: list[dict[str, Any]] = []
        created_ids: list[str] = []
        for source in self._resolve_targets(payload):
            duplicate = source.copy()
            if source.data is not None:
                duplicate.data = source.data.copy()
            duplicate.name = f"{source.name}_copy"
            for collection in source.users_collection or [self.bpy.context.scene.collection]:
                collection.objects.link(duplicate)
            duplicate["mcp_id"] = new_id("obj")
            created_ids.append(duplicate["mcp_id"])
            created_objects.append(self._object_payload(duplicate))
        self._reset_object_id_cache()
        return {"created_object_ids": created_ids, "created_objects": created_objects}

    async def cmd_rename_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        obj.name = payload["new_name"]
        return {"object": self._object_payload(obj)}

    async def cmd_transform_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        if payload.get("location") is not None:
            obj.location = payload["location"]
        if payload.get("rotation") is not None:
            obj.rotation_euler = payload["rotation"]
        if payload.get("scale") is not None:
            obj.scale = payload["scale"]
        return {"object": self._object_payload(obj)}

    async def cmd_apply_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        self.bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.bpy.context.view_layer.objects.active = obj
        self.bpy.ops.object.transform_apply(
            location=bool(payload.get("apply_location", False)),
            rotation=bool(payload.get("apply_rotation", False)),
            scale=bool(payload.get("apply_scale", True)),
        )
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_set_origin(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        self.bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.bpy.context.view_layer.objects.active = obj
        mode_map = {
            "geometry_center": "ORIGIN_GEOMETRY",
            "origin_center_of_mass": "ORIGIN_CENTER_OF_MASS",
            "origin_to_3d_cursor": "ORIGIN_CURSOR",
        }
        mode = mode_map.get(str(payload.get("mode", "geometry_center")), "ORIGIN_GEOMETRY")
        self.bpy.ops.object.origin_set(type=mode, center="MEDIAN")
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_reset_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        for obj in objects:
            if bool(payload.get("reset_location", True)):
                obj.location = (0.0, 0.0, 0.0)
            if bool(payload.get("reset_rotation", True)):
                obj.rotation_euler = (0.0, 0.0, 0.0)
            if bool(payload.get("reset_scale", True)):
                obj.scale = (1.0, 1.0, 1.0)
        return self._transform_result(objects)

    async def cmd_offset_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        location_offset = self._vector3(payload.get("location_offset", [0.0, 0.0, 0.0]))
        rotation_offset = self._vector3(payload.get("rotation_offset", [0.0, 0.0, 0.0]))
        scale_multiplier = self._vector3(payload.get("scale_multiplier", [1.0, 1.0, 1.0]))
        for obj in objects:
            obj.location = [obj.location[index] + location_offset[index] for index in range(3)]
            obj.rotation_euler = [obj.rotation_euler[index] + rotation_offset[index] for index in range(3)]
            obj.scale = [obj.scale[index] * scale_multiplier[index] for index in range(3)]
        return self._transform_result(objects)

    async def cmd_match_object_transform(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._object_by_id(str(payload["source_id"]))
        objects = self._resolve_targets(payload)
        for obj in objects:
            if bool(payload.get("match_location", True)):
                obj.location = list(source.location)
            if bool(payload.get("match_rotation", True)):
                obj.rotation_euler = list(source.rotation_euler)
            if bool(payload.get("match_scale", True)):
                obj.scale = list(source.scale)
        return self._transform_result(objects)

    async def cmd_align_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        align_to = str(payload.get("align_to", "origin"))
        points = [self._alignment_point(obj, axis_index, align_to) for obj in objects]
        target_value = float(payload["target_value"]) if payload.get("target_value") is not None else points[0]
        for obj, point in zip(objects, points, strict=False):
            location = list(obj.location)
            location[axis_index] += target_value - point
            obj.location = location
        return self._transform_result(objects)

    async def cmd_distribute_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        ordered = sorted(objects, key=lambda obj: obj.location[axis_index])
        if len(ordered) <= 1:
            return self._transform_result(ordered)
        spacing = payload.get("spacing")
        if spacing is None:
            start_value = float(payload.get("start_value", ordered[0].location[axis_index]))
            end_value = float(ordered[-1].location[axis_index])
            step = (end_value - start_value) / float(len(ordered) - 1)
        else:
            start_value = float(payload.get("start_value", ordered[0].location[axis_index]))
            step = float(spacing)
        for index, obj in enumerate(ordered):
            location = list(obj.location)
            location[axis_index] = start_value + (step * index)
            obj.location = location
        return self._transform_result(ordered)

    async def cmd_snap_objects_to_grid(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        grid_size = float(payload.get("grid_size", 1.0))
        if grid_size <= 0:
            raise RuntimeCommandError("validation_error", "grid_size must be greater than zero.")
        axis_indices = [self._axis_index(str(axis)) for axis in payload.get("axes", ["x", "y", "z"])]
        for obj in objects:
            location = list(obj.location)
            for axis_index in axis_indices:
                location[axis_index] = round(location[axis_index] / grid_size) * grid_size
            obj.location = location
        return self._transform_result(objects)

    async def cmd_place_objects_on_ground(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        ground_z = float(payload.get("ground_z", 0.0))
        for obj in objects:
            minimum, _maximum = self._object_bounds(obj)
            location = list(obj.location)
            location[2] += ground_z - minimum[2]
            obj.location = location
        return self._transform_result(objects)

    async def cmd_arrange_objects_in_grid(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        columns = max(1, int(payload.get("columns", 4)))
        spacing = self._vector3(payload.get("spacing", [2.0, 2.0, 0.0]))
        origin = self._vector3(payload.get("origin", [0.0, 0.0, 0.0]))
        column_axis = self._axis_index(str(payload.get("column_axis", "x")))
        row_axis = self._axis_index(str(payload.get("row_axis", "y")))
        if column_axis == row_axis:
            raise RuntimeCommandError("validation_error", "column_axis and row_axis must be different.")
        for index, obj in enumerate(objects):
            column = index % columns
            row = index // columns
            location = list(origin)
            location[column_axis] += spacing[column_axis] * column
            location[row_axis] += spacing[row_axis] * row
            obj.location = location
        return self._transform_result(objects)

    async def cmd_mirror_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        pivot = float(payload.get("pivot", 0.0))
        flip_scale = bool(payload.get("flip_scale", False))
        for obj in objects:
            location = list(obj.location)
            location[axis_index] = (2.0 * pivot) - location[axis_index]
            obj.location = location
            if flip_scale:
                scale = list(obj.scale)
                scale[axis_index] *= -1.0
                obj.scale = scale
        return self._transform_result(objects)

    async def cmd_set_object_visibility(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        for obj in objects:
            obj.hide_viewport = not payload["visible"]
            obj.hide_render = not payload["visible"]
        return {"objects": [self._object_payload(obj) for obj in objects]}

    async def cmd_assign_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection = self._ensure_collection(payload["collection_name"])
        objects = self._resolve_targets(payload)
        for obj in objects:
            for existing in list(obj.users_collection):
                existing.objects.unlink(obj)
            collection.objects.link(obj)
        return {"objects": [self._object_payload(obj) for obj in objects]}

    async def cmd_list_collections(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"collections": self._collection_payloads()}

    async def cmd_create_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        parent_name = str(payload.get("parent_collection_name") or self._root_collection().name)
        if self._collection_exists(collection_name):
            raise RuntimeCommandError("validation_error", f"Collection '{collection_name}' already exists.")
        parent = self._collection_by_name(parent_name)
        collection = self.bpy.data.collections.new(collection_name)
        parent.children.link(collection)
        return {"collection": self._collection_payload(collection)}

    async def cmd_rename_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        new_name = str(payload["new_collection_name"])
        collection = self._collection_by_name(collection_name)
        if collection == self._root_collection():
            raise RuntimeCommandError("validation_error", "Scene Collection cannot be renamed.")
        if self._collection_exists(new_name):
            raise RuntimeCommandError("validation_error", f"Collection '{new_name}' already exists.")
        object_ids = [self._ensure_object_id(obj) for obj in collection.objects]
        collection.name = new_name
        objects = [self._object_payload(obj) for obj in collection.objects]
        return {"collection": self._collection_payload(collection), "modified_object_ids": object_ids, "objects": objects}

    async def cmd_delete_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        collection = self._collection_by_name(collection_name)
        root = self._root_collection()
        if collection == root:
            raise RuntimeCommandError("validation_error", "Scene Collection cannot be deleted.")
        object_ids = [self._ensure_object_id(obj) for obj in collection.objects]
        child_collections = list(collection.children)
        force = bool(payload.get("force", False))
        if not force and (object_ids or child_collections):
            raise RuntimeCommandError(
                "validation_error",
                f"Collection '{collection_name}' is not empty; pass force=true to remove collection membership without deleting objects.",
            )
        parent = self._collection_parent(collection) or root
        if parent == collection:
            parent = root
        rehomed_child_names: list[str] = []
        for child in child_collections:
            collection.children.unlink(child)
            if parent.children.get(child.name) is None:
                parent.children.link(child)
            rehomed_child_names.append(child.name)
        objects = []
        for obj in list(collection.objects):
            collection.objects.unlink(obj)
            if not obj.users_collection:
                root.objects.link(obj)
            objects.append(self._object_payload(obj))
        for parent_candidate in self._all_collection_parents():
            if parent_candidate.children.get(collection.name) is not None:
                parent_candidate.children.unlink(collection)
        self.bpy.data.collections.remove(collection)
        return {
            "modified_object_ids": object_ids,
            "unlinked_object_ids": object_ids,
            "rehomed_child_collection_names": rehomed_child_names,
            "relinked_collection_name": parent.name,
            "objects": objects,
        }

    async def cmd_link_objects_to_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection = self._collection_by_name(str(payload["collection_name"]))
        objects = self._resolve_targets(payload)
        for obj in objects:
            if collection.objects.get(obj.name) is None:
                collection.objects.link(obj)
        return {
            "collection": self._collection_payload(collection),
            "modified_object_ids": [self._ensure_object_id(obj) for obj in objects],
            "objects": [self._object_payload(obj) for obj in objects],
        }

    async def cmd_unlink_objects_from_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection = self._collection_by_name(str(payload["collection_name"]))
        root = self._root_collection()
        objects = self._resolve_targets(payload)
        missing = [self._ensure_object_id(obj) for obj in objects if collection.objects.get(obj.name) is None]
        if missing:
            raise RuntimeCommandError(
                "target_not_found",
                f"Object(s) are not linked to collection '{collection.name}': {', '.join(missing)}",
            )
        for obj in objects:
            collection.objects.unlink(obj)
            if not obj.users_collection:
                root.objects.link(obj)
        return {
            "collection": self._collection_payload(collection),
            "modified_object_ids": [self._ensure_object_id(obj) for obj in objects],
            "relinked_collection_name": root.name,
            "objects": [self._object_payload(obj) for obj in objects],
        }

    async def cmd_set_collection_visibility(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection = self._collection_by_name(str(payload["collection_name"]))
        visible = bool(payload["visible"])
        if bool(payload.get("set_viewport", True)) and hasattr(collection, "hide_viewport"):
            collection.hide_viewport = not visible
        if bool(payload.get("set_render", True)) and hasattr(collection, "hide_render"):
            collection.hide_render = not visible
        return {"collection": self._collection_payload(collection)}

    async def cmd_tag_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._resolve_targets(payload)
        tags = payload["tags"]
        for obj in objects:
            existing = self._get_tags(obj)
            obj["mcp_tags_json"] = json.dumps(list(dict.fromkeys([*existing, *tags])))
        return {"objects": [self._object_payload(obj) for obj in objects]}

    async def cmd_create_primitive(self, payload: dict[str, Any]) -> dict[str, Any]:
        primitive_type = payload["primitive_type"]
        location = payload.get("location", [0.0, 0.0, 0.0])
        rotation = payload.get("rotation", [0.0, 0.0, 0.0])
        params = payload.get("parameters", {})
        ops = {
            "cube": self.bpy.ops.mesh.primitive_cube_add,
            "uv_sphere": self.bpy.ops.mesh.primitive_uv_sphere_add,
            "ico_sphere": self.bpy.ops.mesh.primitive_ico_sphere_add,
            "cylinder": self.bpy.ops.mesh.primitive_cylinder_add,
            "cone": self.bpy.ops.mesh.primitive_cone_add,
            "torus": self.bpy.ops.mesh.primitive_torus_add,
            "plane": self.bpy.ops.mesh.primitive_plane_add,
            "grid": self.bpy.ops.mesh.primitive_grid_add,
            "circle": self.bpy.ops.mesh.primitive_circle_add,
        }
        if primitive_type not in ops:
            raise RuntimeCommandError("validation_error", f"Unsupported primitive_type: {primitive_type}")
        ops[primitive_type](location=location, rotation=rotation, **params)
        obj = self.bpy.context.active_object
        obj.name = payload.get("name") or obj.name
        obj.scale = payload.get("scale", [1.0, 1.0, 1.0])
        self._ensure_object_id(obj)
        self._set_tags(obj, payload.get("tags", []))
        if payload.get("collection_name"):
            await self.cmd_assign_collection({"target_ids": [obj["mcp_id"]], "collection_name": payload["collection_name"]})
        self._reset_object_id_cache()
        return {"created_object_ids": [obj["mcp_id"]], "objects": [self._object_payload(obj)]}

    async def cmd_create_custom_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        mesh = self.bpy.data.meshes.new(payload["name"])
        mesh.from_pydata(payload["vertices"], payload.get("edges", []), payload.get("faces", []))
        obj = self.bpy.data.objects.new(payload["name"], mesh)
        self._ensure_collection(payload.get("collection_name", "Scene Collection")).objects.link(obj)
        self._ensure_object_id(obj)
        self._set_tags(obj, payload.get("tags", []))
        self._reset_object_id_cache()
        return {"created_object_ids": [obj["mcp_id"]], "objects": [self._object_payload(obj)]}

    async def cmd_create_curve(self, payload: dict[str, Any]) -> dict[str, Any]:
        curve = self.bpy.data.curves.new(payload["name"], type="CURVE")
        curve.dimensions = "3D"
        if payload["curve_type"] == "bezier":
            spline = curve.splines.new("BEZIER")
            spline.bezier_points.add(len(payload["points"]) - 1)
            for point, bezier in zip(payload["points"], spline.bezier_points, strict=False):
                bezier.co = (*point, 1.0)
        elif payload["curve_type"] == "path":
            spline = curve.splines.new("NURBS")
            spline.points.add(len(payload["points"]) - 1)
            for point, nurbs_point in zip(payload["points"], spline.points, strict=False):
                nurbs_point.co = (*point, 1.0)
            curve.use_path = True
        else:
            spline = curve.splines.new("POLY")
            spline.points.add(len(payload["points"]) - 1)
            for point, poly in zip(payload["points"], spline.points, strict=False):
                poly.co = (*point, 1.0)
        curve.resolution_u = int(payload.get("resolution", 12))
        obj = self.bpy.data.objects.new(payload["name"], curve)
        obj.location = payload.get("location", [0.0, 0.0, 0.0])
        obj.rotation_euler = payload.get("rotation", [0.0, 0.0, 0.0])
        self._ensure_collection(payload.get("collection_name", "Scene Collection")).objects.link(obj)
        self._ensure_object_id(obj)
        self._set_tags(obj, payload.get("tags", []))
        self._reset_object_id_cache()
        return {"created_object_ids": [obj["mcp_id"]], "objects": [self._object_payload(obj)]}

    async def cmd_create_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.bpy.ops.object.text_add(location=payload.get("location", [0.0, 0.0, 0.0]), rotation=payload.get("rotation", [0.0, 0.0, 0.0]))
        obj = self.bpy.context.active_object
        obj.name = payload["name"]
        obj.data.body = payload["text"]
        obj.data.size = payload.get("font_size", 1.0)
        obj.data.extrude = payload.get("extrusion", 0.0)
        obj.data.bevel_depth = payload.get("bevel_depth", 0.0)
        self._ensure_object_id(obj)
        self._set_tags(obj, payload.get("tags", []))
        if payload.get("collection_name"):
            await self.cmd_assign_collection({"target_ids": [obj["mcp_id"]], "collection_name": payload["collection_name"]})
        self._reset_object_id_cache()
        return {"created_object_ids": [obj["mcp_id"]], "objects": [self._object_payload(obj)]}

    async def cmd_edit_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        mesh = obj.data
        mesh.clear_geometry()
        mesh.from_pydata(payload["vertices"], payload.get("edges", []), payload.get("faces", []))
        mesh.update()
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_extrude_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        import bmesh  # type: ignore

        obj = self._mesh_object(payload["target_id"])
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        faces = [face for face in bm.faces]
        result = bmesh.ops.extrude_face_region(bm, geom=faces)
        verts = [item for item in result["geom"] if isinstance(item, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts, vec=(0.0, 0.0, float(payload.get("distance", 0.1))))
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_bevel_edges(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifier = obj.modifiers.get("MCPBevel") or obj.modifiers.new("MCPBevel", type="BEVEL")
        modifier.width = float(payload.get("width", 0.05))
        modifier.segments = int(payload.get("segments", 1))
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_merge_vertices(self, payload: dict[str, Any]) -> dict[str, Any]:
        import bmesh  # type: ignore

        obj = self._mesh_object(payload["target_id"])
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=float(payload.get("threshold", 0.0001)))
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_recalculate_normals(self, payload: dict[str, Any]) -> dict[str, Any]:
        import bmesh  # type: ignore

        obj = self._mesh_object(payload["target_id"])
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {"objects": [self._object_payload(obj)], "modified_object_ids": [self._ensure_object_id(obj)]}

    async def cmd_create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self.bpy.data.materials.new(payload["name"])
        material.use_nodes = True
        material["mcp_id"] = new_id("material")
        for key, value in payload.get("properties", {}).items():
            self._set_material_property(material, key, value)
        return {"material": self._material_payload(material)}

    async def cmd_apply_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        objects = self._resolve_targets(payload)
        changed_objects = []
        for obj in objects:
            if getattr(obj.data, "materials", None) is None:
                continue
            if len(obj.data.materials) == 0:
                obj.data.materials.append(material)
            else:
                obj.data.materials[0] = material
            changed_objects.append(obj)
        return {"objects": [self._object_payload(obj) for obj in changed_objects]}

    async def cmd_set_material_property(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        self._set_material_property(material, payload["property_name"], payload["value"])
        return {"material": self._material_payload(material)}

    async def cmd_add_material_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        node_tree = self._ensure_material_node_tree(material)
        try:
            node = node_tree.nodes.new(type=str(payload["node_type"]))
        except Exception as exc:  # pragma: no cover - depends on Blender node registry
            raise RuntimeCommandError("validation_error", f"Unsupported material node_type: {payload['node_type']}") from exc
        node.name = str(payload.get("node_name") or node.name)
        node.label = str(payload.get("node_name") or node.label or node.name)
        location = payload.get("location", [0.0, 0.0])
        node.location = (float(location[0]), float(location[1]))
        self._ensure_material_node_id(node)
        for param_name, value in dict(payload.get("params") or {}).items():
            self._set_material_node_param(node, str(param_name), value)
        return self._material_node_result(material, node=node)

    async def cmd_set_material_node_param(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        node = self._material_node_by_id(material, payload["node_id"])
        self._set_material_node_param(node, str(payload["param_name"]), payload["value"])
        return self._material_node_result(material, node=node)

    async def cmd_connect_material_nodes(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        node_tree = self._ensure_material_node_tree(material)
        from_node = self._material_node_by_id(material, payload["from_node_id"])
        to_node = self._material_node_by_id(material, payload["to_node_id"])
        output_socket = self._node_socket(from_node.outputs, str(payload["from_socket"]))
        input_socket = self._node_socket(to_node.inputs, str(payload["to_socket"]))
        if output_socket is None or input_socket is None:
            raise RuntimeCommandError("validation_error", "Requested material node sockets were not found.")
        blender_link = node_tree.links.new(output_socket, input_socket)
        link = {
            "link_id": f"mlink_{list(node_tree.links).index(blender_link) + 1}",
            "from_node_id": self._ensure_material_node_id(from_node),
            "from_socket": str(payload["from_socket"]),
            "to_node_id": self._ensure_material_node_id(to_node),
            "to_socket": str(payload["to_socket"]),
        }
        return self._material_node_result(material, link=link)

    async def cmd_list_material_nodes(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material_by_id(payload["material_id"])
        return self._material_node_result(material)

    async def cmd_create_pbr_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material_result = await self.cmd_create_material({"name": payload["name"]})
        material = self._material_by_id(material_result["material"]["material_id"])
        for key, value in payload.items():
            if key in {"project_id", "request_id", "name", "safe_mode", "preview_after", "quality", "seed"}:
                continue
            self._set_material_property(material, key, value)
        return {"material": self._material_payload(material)}

    async def cmd_create_light(self, payload: dict[str, Any]) -> dict[str, Any]:
        light_data = self.bpy.data.lights.new(payload["name"], type=payload.get("light_type", "AREA"))
        light_object = self.bpy.data.objects.new(payload["name"], light_data)
        self.bpy.context.scene.collection.objects.link(light_object)
        self._ensure_object_id(light_object)
        self._update_light(light_object, payload)
        self._reset_object_id_cache()
        return {"light": self._light_payload(light_object), "object": self._object_payload(light_object)}

    async def cmd_set_light(self, payload: dict[str, Any]) -> dict[str, Any]:
        light_object = self._light_object(payload["light_id"])
        self._update_light(light_object, payload)
        return {"light": self._light_payload(light_object), "object": self._object_payload(light_object)}

    async def cmd_apply_lighting_preset(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects: list[dict[str, Any]] = []
        for definition in payload["lights"]:
            created = await self.cmd_create_light(definition)
            objects.append(created["object"])
        return {"objects": objects}

    async def cmd_auto_light_subject(self, payload: dict[str, Any]) -> dict[str, Any]:
        targets = self._resolve_targets(payload)
        subject = targets[0]
        base = subject.location
        lights = [
            {"name": "AutoKey", "location": [base.x + 3.0, base.y - 3.0, base.z + 3.0], "intensity": 1600.0, "size": 2.0},
            {"name": "AutoFill", "location": [base.x - 2.5, base.y - 2.0, base.z + 1.5], "intensity": 900.0, "size": 2.5},
        ]
        return await self.cmd_apply_lighting_preset({"lights": lights})

    async def cmd_create_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera_data = self.bpy.data.cameras.new(payload["name"])
        camera_object = self.bpy.data.objects.new(payload["name"], camera_data)
        self.bpy.context.scene.collection.objects.link(camera_object)
        self._ensure_object_id(camera_object)
        self._update_camera(camera_object, payload)
        if self.bpy.context.scene.camera is None:
            self.bpy.context.scene.camera = camera_object
        self._reset_object_id_cache()
        return {"camera": self._camera_payload(camera_object), "object": self._object_payload(camera_object)}

    async def cmd_set_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera_object = self._camera_object(payload["camera_id"])
        self._update_camera(camera_object, payload)
        return {"camera": self._camera_payload(camera_object), "object": self._object_payload(camera_object)}

    async def cmd_frame_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera_object = self._camera_object(payload["camera_id"])
        minimum, maximum = self._combined_bounds(self._resolve_targets(payload))
        center = [(low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False)]
        extent = max(high - low for low, high in zip(minimum, maximum, strict=False))
        distance = max(extent * 2.5, 3.0)
        camera_object.location = (center[0], center[1] - distance, center[2] + (distance * 0.6))
        camera_object.rotation_euler = (1.1, 0.0, 0.0)
        return {"camera": self._camera_payload(camera_object), "object": self._object_payload(camera_object)}

    async def cmd_set_active_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera_object = self._camera_object(payload["camera_id"])
        self.bpy.context.scene.camera = camera_object
        return {"active_camera_id": self._ensure_object_id(camera_object)}

    async def cmd_set_render_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        render = self.bpy.context.scene.render
        if payload.get("engine") is not None:
            render.engine = payload["engine"]
        if payload.get("resolution_x") is not None:
            render.resolution_x = int(payload["resolution_x"])
        if payload.get("resolution_y") is not None:
            render.resolution_y = int(payload["resolution_y"])
        if payload.get("samples") is not None:
            if render.engine == "CYCLES":
                self.bpy.context.scene.cycles.samples = int(payload["samples"])
            else:
                self.bpy.context.scene.eevee.taa_render_samples = int(payload["samples"])
        if payload.get("transparent_background") is not None:
            render.film_transparent = bool(payload["transparent_background"])
        render_settings = await self.cmd_get_render_settings({})
        return {"render_settings": render_settings["render_settings"]}

    async def cmd_get_render_settings(self, _payload: dict[str, Any]) -> dict[str, Any]:
        scene = self.bpy.context.scene
        render = scene.render
        samples = scene.cycles.samples if render.engine == "CYCLES" else scene.eevee.taa_render_samples
        return {
            "render_settings": {
                "engine": render.engine,
                "resolution_x": render.resolution_x,
                "resolution_y": render.resolution_y,
                "samples": samples,
                "transparent_background": render.film_transparent,
            }
        }

    async def cmd_render_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.cmd_set_render_settings(payload)
        if payload.get("camera_id") is not None:
            self.bpy.context.scene.camera = self._camera_object(payload["camera_id"])
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.bpy.context.scene.render.filepath = str(output_path)
        self.bpy.ops.render.render(write_still=True)
        active_camera = self.bpy.context.scene.camera
        return {
            "image_path": str(output_path),
            "render_settings": (await self.cmd_get_render_settings({}))["render_settings"],
            "active_camera_id": self._object_id(active_camera, persist=False) if active_camera is not None else None,
        }

    async def cmd_render_thumbnail(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.cmd_render_preview(payload)

    async def cmd_export_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_format = str(payload.get("export_format", "glb")).lower()
        target_ids = list(payload.get("target_ids", []))
        axis_forward = str(payload.get("axis_forward", "-Z"))
        axis_up = str(payload.get("axis_up", "Y"))
        apply_scale = float(payload.get("apply_scale", 1.0))
        use_selection = bool(target_ids)
        if use_selection:
            self.bpy.ops.object.select_all(action="DESELECT")
            selected = [self._object_by_id(target_id) for target_id in target_ids]
            for obj in selected:
                obj.select_set(True)
            self.bpy.context.view_layer.objects.active = selected[0]
        if export_format == "glb":
            self.bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLB", use_selection=use_selection)
        elif export_format == "gltf":
            self.bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLTF_SEPARATE", use_selection=use_selection)
        elif export_format == "fbx":
            self.bpy.ops.export_scene.fbx(
                filepath=str(output_path),
                use_selection=use_selection,
                axis_forward=axis_forward,
                axis_up=axis_up,
                global_scale=apply_scale,
            )
        elif export_format == "obj":
            if hasattr(self.bpy.ops.wm, "obj_export"):
                self.bpy.ops.wm.obj_export(
                    filepath=str(output_path),
                    export_selected_objects=use_selection,
                    forward_axis=axis_forward,
                    up_axis=axis_up,
                    global_scale=apply_scale,
                )
            elif hasattr(self.bpy.ops.export_scene, "obj"):
                self.bpy.ops.export_scene.obj(
                    filepath=str(output_path),
                    use_selection=use_selection,
                    axis_forward=axis_forward,
                    axis_up=axis_up,
                    global_scale=apply_scale,
                )
            else:
                raise RuntimeCommandError("unsupported_feature", "OBJ export is not available in this Blender runtime.")
        elif export_format == "stl":
            if hasattr(self.bpy.ops.export_mesh, "stl"):
                self.bpy.ops.export_mesh.stl(
                    filepath=str(output_path),
                    use_selection=use_selection,
                    axis_forward=axis_forward,
                    axis_up=axis_up,
                    global_scale=apply_scale,
                )
            else:
                raise RuntimeCommandError("unsupported_feature", "STL export is not available in this Blender runtime.")
        elif export_format in {"usd", "usdz"}:
            if hasattr(self.bpy.ops.wm, "usd_export"):
                self.bpy.ops.wm.usd_export(
                    filepath=str(output_path),
                    selected_objects_only=use_selection,
                )
            else:
                raise RuntimeCommandError("unsupported_feature", "USD export is not available in this Blender runtime.")
        else:
            raise RuntimeCommandError("validation_error", f"Unsupported export_format: {export_format}")
        object_count = len(target_ids) if use_selection else len(self.bpy.data.objects)
        return {"output_path": str(output_path), "object_count": object_count, "warnings": []}

    async def cmd_import_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_path = Path(payload["input_path"])
        if not input_path.exists():
            raise RuntimeCommandError("validation_error", f"Import file does not exist: {input_path}")
        suffix = input_path.suffix.lower()
        before_pointers = {int(obj.as_pointer()) for obj in self.bpy.data.objects}
        if suffix in {".glb", ".gltf"}:
            self.bpy.ops.import_scene.gltf(filepath=str(input_path))
        elif suffix == ".fbx":
            self.bpy.ops.import_scene.fbx(filepath=str(input_path))
        elif suffix == ".obj":
            if hasattr(self.bpy.ops.wm, "obj_import"):
                self.bpy.ops.wm.obj_import(filepath=str(input_path))
            elif hasattr(self.bpy.ops.import_scene, "obj"):
                self.bpy.ops.import_scene.obj(filepath=str(input_path))
            else:
                raise RuntimeCommandError("unsupported_feature", "OBJ import is not available in this Blender runtime.")
        elif suffix in {".usd", ".usdz"}:
            if hasattr(self.bpy.ops.wm, "usd_import"):
                self.bpy.ops.wm.usd_import(filepath=str(input_path))
            else:
                raise RuntimeCommandError("unsupported_feature", "USD import is not available in this Blender runtime.")
        elif suffix == ".stl":
            if hasattr(self.bpy.ops.import_mesh, "stl"):
                self.bpy.ops.import_mesh.stl(filepath=str(input_path))
            else:
                raise RuntimeCommandError("unsupported_feature", "STL import is not available in this Blender runtime.")
        else:
            raise RuntimeCommandError("validation_error", f"Unsupported import extension: {suffix}")
        name_prefix = payload.get("name_prefix")
        imported_objects = []
        for obj in self.bpy.data.objects:
            pointer = int(obj.as_pointer())
            if pointer in before_pointers:
                continue
            if name_prefix:
                obj.name = f"{name_prefix}_{obj.name}"
            self._ensure_object_id(obj)
            imported_objects.append(self._object_payload(obj))
        self._reset_object_id_cache()
        return {"objects": imported_objects}

    def _object_id(self, obj, *, persist: bool) -> str:  # type: ignore[no-untyped-def]
        raw = obj.get("mcp_id")
        if raw:
            return str(raw)
        pointer = int(obj.as_pointer())
        if persist:
            generated = self._ephemeral_object_ids.pop(pointer, None) or new_id("obj")
            obj["mcp_id"] = generated
            return generated
        return self._ephemeral_object_ids.setdefault(pointer, new_id("obj"))

    def _ensure_object_id(self, obj) -> str:  # type: ignore[no-untyped-def]
        return self._object_id(obj, persist=True)

    def _object_by_id(self, object_id: str):  # type: ignore[no-untyped-def]
        for obj in self.bpy.data.objects:
            if (
                str(obj.get("mcp_id", "")) == object_id
                or self._ephemeral_object_ids.get(int(obj.as_pointer())) == object_id
            ):
                self._ensure_object_id(obj)
                return obj
        raise RuntimeCommandError("target_not_found", f"Unknown object_id: {object_id}")

    def _mesh_object(self, object_id: str):  # type: ignore[no-untyped-def]
        obj = self._object_by_id(object_id)
        if obj.type != "MESH":
            raise RuntimeCommandError("validation_error", f"Target is not a mesh object: {object_id}")
        return obj

    def _light_object(self, object_id: str):  # type: ignore[no-untyped-def]
        obj = self._object_by_id(object_id)
        if obj.type != "LIGHT":
            raise RuntimeCommandError("validation_error", f"Target is not a light object: {object_id}")
        return obj

    def _camera_object(self, object_id: str):  # type: ignore[no-untyped-def]
        obj = self._object_by_id(object_id)
        if obj.type != "CAMERA":
            raise RuntimeCommandError("validation_error", f"Target is not a camera object: {object_id}")
        return obj

    def _resolve_targets(self, payload: dict[str, Any]):  # type: ignore[no-untyped-def]
        target_ids = list(payload.get("target_ids", []))
        if payload.get("target_id"):
            target_ids.append(payload["target_id"])
        if payload.get("names"):
            wanted = {name.lower() for name in payload["names"]}
            for obj in self.bpy.data.objects:
                if obj.name.lower() in wanted:
                    self._ensure_object_id(obj)
                    target_ids.append(str(obj["mcp_id"]))
        if not target_ids:
            raise RuntimeCommandError("target_not_found", "No targets were resolved.")
        return [self._object_by_id(target_id) for target_id in dict.fromkeys(target_ids)]

    def _transform_result(self, objects) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        return {
            "modified_object_ids": [self._ensure_object_id(obj) for obj in objects],
            "objects": [self._object_payload(obj) for obj in objects],
        }

    @staticmethod
    def _vector3(value: Any) -> list[float]:
        items = list(value)
        if len(items) != 3:
            raise RuntimeCommandError("validation_error", "Expected exactly 3 coordinates.")
        return [float(component) for component in items]

    @staticmethod
    def _axis_index(axis: str) -> int:
        axis_map = {"x": 0, "y": 1, "z": 2}
        if axis not in axis_map:
            raise RuntimeCommandError("validation_error", f"Unsupported axis: {axis}")
        return axis_map[axis]

    def _alignment_point(self, obj, axis_index: int, align_to: str) -> float:  # type: ignore[no-untyped-def]
        if align_to == "origin":
            return float(obj.location[axis_index])
        minimum, maximum = self._object_bounds(obj)
        if align_to == "min":
            return float(minimum[axis_index])
        if align_to == "max":
            return float(maximum[axis_index])
        if align_to == "center":
            return float((minimum[axis_index] + maximum[axis_index]) / 2.0)
        raise RuntimeCommandError("validation_error", f"Unsupported align_to mode: {align_to}")

    def _object_matches(self, obj, payload: dict[str, Any]) -> bool:  # type: ignore[no-untyped-def]
        if payload.get("names"):
            names = {name.lower() for name in payload["names"]}
            if obj.name.lower() not in names:
                return False
        if payload.get("object_type") and obj.type.lower() != str(payload["object_type"]).lower():
            return False
        if payload.get("tag") and payload["tag"] not in self._get_tags(obj):
            return False
        if payload.get("collection_name"):
            collections = {collection.name for collection in obj.users_collection}
            if payload["collection_name"] not in collections:
                return False
        if payload.get("material_id"):
            material_ids = {str(material.get("mcp_id", material.name)) for material in getattr(obj.data, "materials", []) if material is not None}
            if payload["material_id"] not in material_ids:
                return False
        if payload.get("spatial_range"):
            minimum = payload["spatial_range"].get("min", [-1e9, -1e9, -1e9])
            maximum = payload["spatial_range"].get("max", [1e9, 1e9, 1e9])
            coords = [obj.location.x, obj.location.y, obj.location.z]
            if any(coord < lower or coord > upper for coord, lower, upper in zip(coords, minimum, maximum, strict=False)):
                return False
        return True

    def _get_tags(self, obj) -> list[str]:  # type: ignore[no-untyped-def]
        raw = obj.get("mcp_tags_json")
        if not raw:
            return []
        return list(json.loads(str(raw)))

    def _set_tags(self, obj, tags: list[str]) -> None:  # type: ignore[no-untyped-def]
        obj["mcp_tags_json"] = json.dumps(tags)

    def _object_payload(self, obj, *, persist_id: bool = True) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        object_id = self._object_id(obj, persist=persist_id)
        return {
            "object_id": object_id,
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": not obj.hide_viewport,
            "collection": obj.users_collection[0].name if obj.users_collection else "Scene Collection",
            "tags": self._get_tags(obj),
            "material_ids": [str(material.get("mcp_id", material.name)) for material in getattr(obj.data, "materials", []) if material is not None],
            "data": self._object_data_payload(obj),
        }

    def _object_data_payload(self, obj) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        data = getattr(obj, "data", None)
        if data is None:
            return {}
        if obj.type == "MESH":
            return {
                "vertices": [self._vector_payload(getattr(vertex, "co", vertex)) for vertex in getattr(data, "vertices", [])],
                "edges": [list(getattr(edge, "vertices", edge)) for edge in getattr(data, "edges", [])],
                "faces": [list(getattr(polygon, "vertices", polygon)) for polygon in getattr(data, "polygons", [])],
            }
        if obj.type == "CURVE":
            points: list[list[float]] = []
            curve_type = "polyline"
            for spline in getattr(data, "splines", []):
                spline_type = str(getattr(spline, "type", "POLY")).upper()
                if spline_type == "BEZIER":
                    curve_type = "bezier"
                    points.extend(self._vector_payload(bezier.co) for bezier in getattr(spline, "bezier_points", []))
                else:
                    if spline_type == "NURBS":
                        curve_type = "path"
                    points.extend(self._vector_payload(point.co) for point in getattr(spline, "points", []))
                if points:
                    break
            return {
                "curve_type": curve_type,
                "points": points,
                "resolution": int(getattr(data, "resolution_u", 12)),
            }
        if obj.type == "FONT":
            return {
                "text": str(getattr(data, "body", "")),
                "font_size": float(getattr(data, "size", 1.0)),
                "extrusion": float(getattr(data, "extrude", 0.0)),
                "bevel_depth": float(getattr(data, "bevel_depth", 0.0)),
            }
        return {}

    def _vector_payload(self, value) -> list[float]:  # type: ignore[no-untyped-def]
        if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
            return [float(value.x), float(value.y), float(value.z)]
        return [float(component) for component in list(value)[:3]]

    def _combined_bounds(self, objects) -> tuple[tuple[float, float, float], tuple[float, float, float]]:  # type: ignore[no-untyped-def]
        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        for obj in objects:
            obj_min, obj_max = self._object_bounds(obj)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], obj_min[axis])
                maximum[axis] = max(maximum[axis], obj_max[axis])
        return (minimum[0], minimum[1], minimum[2]), (maximum[0], maximum[1], maximum[2])

    def _object_bounds(self, obj) -> tuple[tuple[float, float, float], tuple[float, float, float]]:  # type: ignore[no-untyped-def]
        from mathutils import Vector  # type: ignore

        if getattr(obj, "bound_box", None):
            corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            minimum = tuple(min(corner[axis] for corner in corners) for axis in range(3))
            maximum = tuple(max(corner[axis] for corner in corners) for axis in range(3))
            return minimum, maximum
        location = obj.matrix_world.translation
        point = (location.x, location.y, location.z)
        return point, point

    def _material_payload(self, material) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        if "mcp_id" not in material:
            material["mcp_id"] = new_id("material")
        return {
            "material_id": str(material["mcp_id"]),
            "name": material.name,
            "properties": self._extract_material_properties(material),
        }

    def _material_by_id(self, material_id: str):  # type: ignore[no-untyped-def]
        for material in self.bpy.data.materials:
            if str(material.get("mcp_id", "")) == material_id or material.name == material_id:
                if "mcp_id" not in material:
                    material["mcp_id"] = new_id("material")
                return material
        raise RuntimeCommandError("target_not_found", f"Unknown material_id: {material_id}")

    def _ensure_material_node_tree(self, material):  # type: ignore[no-untyped-def]
        material.use_nodes = True
        if material.node_tree is None:
            raise RuntimeCommandError("blender_execution_error", "Material node tree is unavailable.")
        return material.node_tree

    @staticmethod
    def _node_custom_get(node, key: str, default: Any = None) -> Any:  # type: ignore[no-untyped-def]
        getter = getattr(node, "get", None)
        if callable(getter):
            return getter(key, default)
        try:
            return node[key]
        except Exception:
            return default

    @staticmethod
    def _node_custom_set(node, key: str, value: Any) -> None:  # type: ignore[no-untyped-def]
        node[key] = value

    def _ensure_material_node_id(self, node) -> str:  # type: ignore[no-untyped-def]
        node_id = self._node_custom_get(node, "mcp_node_id")
        if node_id:
            return str(node_id)
        node_id = new_id("mnode")
        self._node_custom_set(node, "mcp_node_id", node_id)
        return node_id

    def _material_node_by_id(self, material, node_id: str):  # type: ignore[no-untyped-def]
        node_tree = self._ensure_material_node_tree(material)
        for node in node_tree.nodes:
            if self._ensure_material_node_id(node) == node_id or node.name == node_id:
                return node
        raise RuntimeCommandError("target_not_found", f"Unknown material node_id: {node_id}")

    def _set_material_node_param(self, node, param_name: str, value: Any) -> None:  # type: ignore[no-untyped-def]
        params = self._material_node_params(node)
        params[param_name] = json.loads(json.dumps(value))
        self._node_custom_set(node, "mcp_node_params_json", json.dumps(params))
        socket = self._node_socket(node.inputs, param_name)
        if socket is None or not hasattr(socket, "default_value"):
            return
        try:
            socket.default_value = value
        except TypeError:
            socket.default_value = tuple(value) if isinstance(value, list) else value

    def _material_node_params(self, node) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        raw = self._node_custom_get(node, "mcp_node_params_json")
        if not raw:
            return {}
        try:
            params = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return params if isinstance(params, dict) else {}

    @staticmethod
    def _node_socket(sockets, socket_name: str):  # type: ignore[no-untyped-def]
        getter = getattr(sockets, "get", None)
        if callable(getter):
            direct = getter(socket_name)
            if direct is not None:
                return direct
        lowered = socket_name.lower()
        for socket in sockets:
            if str(getattr(socket, "name", "")).lower() == lowered:
                return socket
        return None

    def _material_node_payload(self, node) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        location = getattr(node, "location", None)
        return {
            "node_id": self._ensure_material_node_id(node),
            "node_type": str(getattr(node, "bl_idname", type(node).__name__)),
            "node_name": str(getattr(node, "name", "MaterialNode")),
            "label": str(getattr(node, "label", "")),
            "location": [float(getattr(location, "x", 0.0)), float(getattr(location, "y", 0.0))],
            "params": self._material_node_params(node),
        }

    def _material_links_payload(self, material) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        node_tree = self._ensure_material_node_tree(material)
        links: list[dict[str, Any]] = []
        for index, link in enumerate(node_tree.links, start=1):
            links.append(
                {
                    "link_id": f"mlink_{index}",
                    "from_node_id": self._ensure_material_node_id(link.from_node),
                    "from_socket": str(getattr(link.from_socket, "name", "")),
                    "to_node_id": self._ensure_material_node_id(link.to_node),
                    "to_socket": str(getattr(link.to_socket, "name", "")),
                }
            )
        return links

    def _material_node_result(
        self,
        material,
        *,
        node=None,
        link: dict[str, Any] | None = None,
    ) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        node_tree = self._ensure_material_node_tree(material)
        result = {
            "material": self._material_payload(material),
            "nodes": [self._material_node_payload(existing_node) for existing_node in node_tree.nodes],
            "links": self._material_links_payload(material),
        }
        if node is not None:
            result["node"] = self._material_node_payload(node)
        if link is not None:
            result["link"] = link
        return result

    def _extract_material_properties(self, material) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        tracked = self._tracked_material_properties(material)
        if not tracked:
            return {}
        if not material.use_nodes or material.node_tree is None:
            return tracked
        bsdf = self._principled_bsdf_node(material, create=False)
        if bsdf is None:
            return tracked
        properties: dict[str, Any] = {}
        for property_name, fallback in tracked.items():
            socket = None
            for socket_name in self._material_socket_names(property_name):
                socket = self._node_socket(bsdf.inputs, socket_name)
                if socket is not None:
                    break
            if socket is None or not hasattr(socket, "default_value"):
                properties[property_name] = fallback
                continue
            default_value = socket.default_value
            if isinstance(fallback, list):
                properties[property_name] = list(default_value)
            else:
                properties[property_name] = float(default_value)
        return properties

    def _set_material_property(self, material, property_name: str, value: Any) -> None:  # type: ignore[no-untyped-def]
        self._remember_material_property(material, property_name, value)
        material.use_nodes = True
        bsdf = self._principled_bsdf_node(material)
        if bsdf is None:
            self._apply_material_property_fallback(material, property_name, value)
            return
        for socket_name in self._material_socket_names(property_name):
            socket = self._node_socket(bsdf.inputs, socket_name)
            if socket is None or not hasattr(socket, "default_value"):
                continue
            try:
                socket.default_value = value
            except TypeError:
                socket.default_value = tuple(value) if isinstance(value, list) else value
            return
        self._apply_material_property_fallback(material, property_name, value)

    @classmethod
    def _material_socket_names(cls, property_name: str) -> tuple[str, ...]:
        return {
            "base_color": ("Base Color",),
            "roughness": ("Roughness",),
            "metallic": ("Metallic",),
            "specular": ("Specular IOR Level", "Specular"),
            "alpha": ("Alpha",),
            "emission_color": ("Emission Color", "Emission"),
            "emission_strength": ("Emission Strength",),
        }.get(property_name, ())

    def _principled_bsdf_node(self, material, *, create: bool = True):  # type: ignore[no-untyped-def]
        node_tree = getattr(material, "node_tree", None)
        if node_tree is None:
            return None
        nodes = getattr(node_tree, "nodes", None)
        if nodes is None:
            return None
        getter = getattr(nodes, "get", None)
        if callable(getter):
            named = getter("Principled BSDF")
            if named is not None:
                return named
        for node in nodes:
            if getattr(node, "bl_idname", None) == "ShaderNodeBsdfPrincipled":
                return node
            if getattr(node, "type", None) == "BSDF_PRINCIPLED":
                return node
        if not create:
            return None
        creator = getattr(nodes, "new", None)
        if not callable(creator):
            return None
        with suppress(Exception):
            return creator(type="ShaderNodeBsdfPrincipled")
        return None

    def _apply_material_property_fallback(self, material, property_name: str, value: Any) -> None:  # type: ignore[no-untyped-def]
        material[property_name] = value
        if property_name == "base_color":
            with suppress(Exception):
                material.diffuse_color = value
        elif property_name == "alpha":
            with suppress(Exception):
                color = list(getattr(material, "diffuse_color", [1.0, 1.0, 1.0, 1.0]))
                while len(color) < 4:
                    color.append(1.0)
                color[3] = float(value)
                material.diffuse_color = color
            with suppress(Exception):
                material.blend_method = "BLEND"
        elif property_name == "roughness":
            with suppress(Exception):
                material.roughness = float(value)
        elif property_name == "metallic":
            with suppress(Exception):
                material.metallic = float(value)
        elif property_name == "specular":
            with suppress(Exception):
                material.specular_intensity = float(value)

    def _tracked_material_properties(self, material) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        raw = material.get(self._MATERIAL_PROPERTIES_KEY)
        if not raw:
            return {}
        try:
            properties = json.loads(str(raw))
        except json.JSONDecodeError:
            return {}
        return properties if isinstance(properties, dict) else {}

    def _remember_material_property(self, material, property_name: str, value: Any) -> None:  # type: ignore[no-untyped-def]
        properties = self._tracked_material_properties(material)
        properties[property_name] = json.loads(json.dumps(value))
        material[self._MATERIAL_PROPERTIES_KEY] = json.dumps(properties)

    def _virtual_modifiers(self, obj) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        raw = obj.get(self._VIRTUAL_MODIFIERS_KEY)
        if not raw:
            return []
        try:
            modifiers = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        if not isinstance(modifiers, list):
            return []
        return [modifier for modifier in modifiers if isinstance(modifier, dict)]

    def _save_virtual_modifiers(self, obj, modifiers: list[dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]
        obj[self._VIRTUAL_MODIFIERS_KEY] = json.dumps(modifiers)

    def _modifier_payloads(self, obj) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
        return [{"type": modifier.type, "name": modifier.name} for modifier in obj.modifiers] + [
            {
                "type": str(modifier.get("type", "NODES")),
                "name": str(modifier.get("name", "GeometryNodes")),
                "params": dict(modifier.get("params") or {}),
                "virtual": True,
            }
            for modifier in self._virtual_modifiers(obj)
        ]

    def _light_payload(self, light_object) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        light_data = light_object.data
        return {
            "light_id": self._ensure_object_id(light_object),
            "name": light_object.name,
            "light_type": light_data.type,
            "location": [light_object.location.x, light_object.location.y, light_object.location.z],
            "rotation": [light_object.rotation_euler.x, light_object.rotation_euler.y, light_object.rotation_euler.z],
            "intensity": float(light_data.energy),
            "color": list(light_data.color),
            "size": float(getattr(light_data, "size", 1.0)),
        }

    def _update_light(self, light_object, payload: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        if payload.get("location") is not None:
            light_object.location = payload["location"]
        if payload.get("rotation") is not None:
            light_object.rotation_euler = payload["rotation"]
        if payload.get("intensity") is not None:
            light_object.data.energy = float(payload["intensity"])
        if payload.get("color") is not None:
            light_object.data.color = payload["color"][:3]
        if payload.get("size") is not None and hasattr(light_object.data, "size"):
            light_object.data.size = float(payload["size"])

    def _camera_payload(self, camera_object) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        camera_data = camera_object.data
        return {
            "camera_id": self._ensure_object_id(camera_object),
            "name": camera_object.name,
            "location": [camera_object.location.x, camera_object.location.y, camera_object.location.z],
            "rotation": [camera_object.rotation_euler.x, camera_object.rotation_euler.y, camera_object.rotation_euler.z],
            "focal_length": float(camera_data.lens),
            "field_of_view": float(camera_data.angle),
        }

    def _update_camera(self, camera_object, payload: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        if payload.get("location") is not None:
            camera_object.location = payload["location"]
        if payload.get("rotation") is not None:
            camera_object.rotation_euler = payload["rotation"]
        if payload.get("focal_length") is not None:
            camera_object.data.lens = float(payload["focal_length"])
        if payload.get("field_of_view") is not None:
            camera_object.data.angle = float(payload["field_of_view"])

    def _root_collection(self):  # type: ignore[no-untyped-def]
        return self.bpy.context.scene.collection

    def _collection_exists(self, name: str) -> bool:
        root = self._root_collection()
        return name == root.name or name == "Scene Collection" or self.bpy.data.collections.get(name) is not None

    def _collection_by_name(self, name: str):  # type: ignore[no-untyped-def]
        root = self._root_collection()
        if name in {root.name, "Scene Collection"}:
            return root
        collection = self.bpy.data.collections.get(name)
        if collection is None:
            raise RuntimeCommandError("target_not_found", f"Unknown collection_name: {name}")
        return collection

    def _ensure_collection(self, name: str, parent_name: str | None = None):  # type: ignore[no-untyped-def]
        try:
            return self._collection_by_name(name)
        except RuntimeCommandError:
            parent = self._collection_by_name(parent_name or "Scene Collection")
            collection = self.bpy.data.collections.new(name)
            parent.children.link(collection)
            return collection

    def _all_collection_parents(self):  # type: ignore[no-untyped-def]
        return [self._root_collection(), *list(self.bpy.data.collections)]

    def _collection_parent(self, collection):  # type: ignore[no-untyped-def]
        for parent in self._all_collection_parents():
            if parent != collection and parent.children.get(collection.name) is not None:
                return parent
        return None

    def _collection_payloads(self) -> list[dict[str, Any]]:
        root = self._root_collection()
        payloads: list[dict[str, Any]] = []
        seen: set[int] = set()

        def visit(collection) -> None:  # type: ignore[no-untyped-def]
            pointer = int(collection.as_pointer())
            if pointer in seen:
                return
            seen.add(pointer)
            payloads.append(self._collection_payload(collection))
            for child in collection.children:
                visit(child)

        visit(root)
        for collection in self.bpy.data.collections:
            visit(collection)
        return payloads

    def _collection_payload(self, collection) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        parent = self._collection_parent(collection)
        object_ids = [self._ensure_object_id(obj) for obj in collection.objects]
        hide_viewport = bool(getattr(collection, "hide_viewport", False))
        hide_render = bool(getattr(collection, "hide_render", False))
        return {
            "name": collection.name,
            "parent_name": parent.name if parent is not None else None,
            "children": [child.name for child in collection.children],
            "object_ids": object_ids,
            "object_count": len(object_ids),
            "visible": not hide_viewport and not hide_render,
            "hide_viewport": hide_viewport,
            "hide_render": hide_render,
        }

    async def cmd_add_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        modifier_type: str = payload["modifier_type"]
        name: str = str(payload.get("name") or modifier_type)
        params: dict[str, Any] = dict(payload.get("params") or {})
        if name in obj.modifiers or any(modifier["name"] == name for modifier in self._virtual_modifiers(obj)):
            raise RuntimeCommandError("validation_error", f"A modifier named '{name}' already exists.")
        if modifier_type == "NODES":
            modifiers = [*self._virtual_modifiers(obj), {"type": modifier_type, "name": name, "params": params}]
            self._save_virtual_modifiers(obj, modifiers)
            return {"modifier_name": name, "modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}
        mod = obj.modifiers.new(name=name, type=modifier_type)
        for key, value in params.items():
            if hasattr(mod, key):
                setattr(mod, key, value)
        return {"modifier_name": name, "modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}

    async def cmd_remove_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        modifier_name: str = payload["modifier_name"]
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            virtual_modifiers = self._virtual_modifiers(obj)
            filtered = [modifier for modifier in virtual_modifiers if modifier["name"] != modifier_name]
            if len(filtered) != len(virtual_modifiers):
                self._save_virtual_modifiers(obj, filtered)
                return {"modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}
        if mod is None:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        obj.modifiers.remove(mod)
        return {"modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}

    async def cmd_set_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        modifier_name: str = payload["modifier_name"]
        params: dict[str, Any] = dict(payload.get("params") or {})
        mod = obj.modifiers.get(modifier_name)
        if mod is None:
            virtual_modifiers = self._virtual_modifiers(obj)
            for modifier in virtual_modifiers:
                if modifier["name"] == modifier_name:
                    modifier["params"] = {**dict(modifier.get("params") or {}), **params}
                    self._save_virtual_modifiers(obj, virtual_modifiers)
                    return {"modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}
        if mod is None:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        unsupported = []
        for key, value in params.items():
            if hasattr(mod, key):
                setattr(mod, key, value)
            else:
                unsupported.append(key)
        if unsupported:
            raise RuntimeCommandError("validation_error", f"Unsupported modifier parameter(s): {', '.join(unsupported)}")
        return {"modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}

    async def cmd_apply_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        modifier_name: str = payload["modifier_name"]
        if modifier_name not in obj.modifiers:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        self.bpy.context.view_layer.objects.active = obj
        self.bpy.ops.object.modifier_apply(modifier=modifier_name)
        return {"modifiers": self._modifier_payloads(obj), "objects": [self._object_payload(obj)]}

    async def cmd_list_modifiers(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object_by_id(payload["target_id"])
        return {"modifiers": self._modifier_payloads(obj)}
