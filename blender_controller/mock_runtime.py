from __future__ import annotations

import asyncio
import math
from base64 import b64decode
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp_server.serialization import json_dumps, json_loads
from mcp_server.utils import new_id

from blender_controller.runtime import (
    BaseRuntime,
    RenderSettingsState,
    RuntimeCamera,
    RuntimeCommandError,
    RuntimeLight,
    RuntimeMaterial,
    RuntimeObject,
)

_BLANK_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBAQEA4q0AAAAASUVORK5CYII="
)


class MockRuntime(BaseRuntime):
    supports_concurrent_reads = True

    @staticmethod
    def _edges_from_faces(faces: list[list[int]]) -> list[list[int]]:
        edges: set[tuple[int, int]] = set()
        for face in faces:
            if len(face) < 2:
                continue
            for index, start in enumerate(face):
                end = face[(index + 1) % len(face)]
                if start == end:
                    continue
                edge = tuple(sorted((start, end)))
                edges.add(edge)
        return [list(edge) for edge in sorted(edges)]

    def _primitive_mesh_data(self, primitive_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if primitive_type == "cube":
            vertices = [
                [-0.5, -0.5, -0.5],
                [0.5, -0.5, -0.5],
                [0.5, 0.5, -0.5],
                [-0.5, 0.5, -0.5],
                [-0.5, -0.5, 0.5],
                [0.5, -0.5, 0.5],
                [0.5, 0.5, 0.5],
                [-0.5, 0.5, 0.5],
            ]
            faces = [
                [0, 1, 2, 3],
                [4, 5, 6, 7],
                [0, 1, 5, 4],
                [1, 2, 6, 5],
                [2, 3, 7, 6],
                [3, 0, 4, 7],
            ]
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        if primitive_type == "plane":
            faces = [[0, 1, 2, 3]]
            return {
                "vertices": [[-0.5, -0.5, 0.0], [0.5, -0.5, 0.0], [0.5, 0.5, 0.0], [-0.5, 0.5, 0.0]],
                "edges": self._edges_from_faces(faces),
                "faces": faces,
            }
        if primitive_type == "circle":
            segments = max(3, int(parameters.get("vertices", 32)))
            vertices = [
                [0.5 * math.cos((2.0 * math.pi * index) / segments), 0.5 * math.sin((2.0 * math.pi * index) / segments), 0.0]
                for index in range(segments)
            ]
            edges = [[index, (index + 1) % segments] for index in range(segments)]
            return {"vertices": vertices, "edges": edges, "faces": []}
        if primitive_type == "grid":
            x_subdivisions = max(2, int(parameters.get("x_subdivisions", 10)))
            y_subdivisions = max(2, int(parameters.get("y_subdivisions", 10)))
            vertices = []
            for y_index in range(y_subdivisions):
                for x_index in range(x_subdivisions):
                    x_coord = -0.5 + (x_index / (x_subdivisions - 1))
                    y_coord = -0.5 + (y_index / (y_subdivisions - 1))
                    vertices.append([x_coord, y_coord, 0.0])

            def grid_index(x_index: int, y_index: int) -> int:
                return y_index * x_subdivisions + x_index

            faces = [
                [
                    grid_index(x_index, y_index),
                    grid_index(x_index + 1, y_index),
                    grid_index(x_index + 1, y_index + 1),
                    grid_index(x_index, y_index + 1),
                ]
                for y_index in range(y_subdivisions - 1)
                for x_index in range(x_subdivisions - 1)
            ]
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        if primitive_type in {"cylinder", "cone"}:
            segments = max(3, int(parameters.get("vertices", 32)))
            base_ring = [
                [0.5 * math.cos((2.0 * math.pi * index) / segments), 0.5 * math.sin((2.0 * math.pi * index) / segments), -0.5]
                for index in range(segments)
            ]
            if primitive_type == "cylinder":
                top_ring = [[x_coord, y_coord, 0.5] for x_coord, y_coord, _ in base_ring]
                vertices = [*base_ring, *top_ring]
                faces = [list(range(segments)), list(range(segments, segments * 2))]
                faces.extend(
                    [
                        base_index,
                        (base_index + 1) % segments,
                        segments + ((base_index + 1) % segments),
                        segments + base_index,
                    ]
                    for base_index in range(segments)
                )
                return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
            tip_index = segments
            vertices = [*base_ring, [0.0, 0.0, 0.5]]
            faces = [list(range(segments))]
            faces.extend([tip_index, (base_index + 1) % segments, base_index] for base_index in range(segments))
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        if primitive_type == "uv_sphere":
            segments = max(3, int(parameters.get("segments", 16)))
            ring_count = max(3, int(parameters.get("ring_count", 8)))
            vertices = [[0.0, 0.0, 0.5]]
            for ring_index in range(1, ring_count):
                polar = math.pi * ring_index / ring_count
                ring_radius = 0.5 * math.sin(polar)
                z_coord = 0.5 * math.cos(polar)
                for segment_index in range(segments):
                    azimuth = (2.0 * math.pi * segment_index) / segments
                    vertices.append([ring_radius * math.cos(azimuth), ring_radius * math.sin(azimuth), z_coord])
            vertices.append([0.0, 0.0, -0.5])
            south_pole = len(vertices) - 1

            def sphere_index(ring_index: int, segment_index: int) -> int:
                return 1 + ((ring_index - 1) * segments) + (segment_index % segments)

            faces = []
            for segment_index in range(segments):
                faces.append([0, sphere_index(1, segment_index), sphere_index(1, segment_index + 1)])
            for ring_index in range(1, ring_count - 1):
                for segment_index in range(segments):
                    faces.append(
                        [
                            sphere_index(ring_index, segment_index),
                            sphere_index(ring_index, segment_index + 1),
                            sphere_index(ring_index + 1, segment_index + 1),
                            sphere_index(ring_index + 1, segment_index),
                        ]
                    )
            for segment_index in range(segments):
                faces.append([south_pole, sphere_index(ring_count - 1, segment_index + 1), sphere_index(ring_count - 1, segment_index)])
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        if primitive_type == "ico_sphere":
            golden_ratio = (1.0 + math.sqrt(5.0)) / 2.0
            raw_vertices = [
                (-1, golden_ratio, 0),
                (1, golden_ratio, 0),
                (-1, -golden_ratio, 0),
                (1, -golden_ratio, 0),
                (0, -1, golden_ratio),
                (0, 1, golden_ratio),
                (0, -1, -golden_ratio),
                (0, 1, -golden_ratio),
                (golden_ratio, 0, -1),
                (golden_ratio, 0, 1),
                (-golden_ratio, 0, -1),
                (-golden_ratio, 0, 1),
            ]
            vertices = []
            for x_coord, y_coord, z_coord in raw_vertices:
                length = math.sqrt(x_coord * x_coord + y_coord * y_coord + z_coord * z_coord)
                vertices.append([0.5 * x_coord / length, 0.5 * y_coord / length, 0.5 * z_coord / length])
            faces = [
                [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
                [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
                [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
                [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
            ]
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        if primitive_type == "torus":
            major_segments = max(3, int(parameters.get("major_segments", 12)))
            minor_segments = max(3, int(parameters.get("minor_segments", 8)))
            major_radius = float(parameters.get("major_radius", 0.75))
            minor_radius = float(parameters.get("minor_radius", 0.25))
            vertices = []
            for major_index in range(major_segments):
                major_angle = (2.0 * math.pi * major_index) / major_segments
                cos_major = math.cos(major_angle)
                sin_major = math.sin(major_angle)
                for minor_index in range(minor_segments):
                    minor_angle = (2.0 * math.pi * minor_index) / minor_segments
                    radial = major_radius + minor_radius * math.cos(minor_angle)
                    vertices.append([
                        radial * cos_major,
                        radial * sin_major,
                        minor_radius * math.sin(minor_angle),
                    ])

            def torus_index(major_index: int, minor_index: int) -> int:
                return (major_index % major_segments) * minor_segments + (minor_index % minor_segments)

            faces = [
                [
                    torus_index(major_index, minor_index),
                    torus_index(major_index + 1, minor_index),
                    torus_index(major_index + 1, minor_index + 1),
                    torus_index(major_index, minor_index + 1),
                ]
                for major_index in range(major_segments)
                for minor_index in range(minor_segments)
            ]
            return {"vertices": vertices, "edges": self._edges_from_faces(faces), "faces": faces}
        raise RuntimeCommandError("validation_error", f"Unsupported primitive_type: {primitive_type}")

    async def cmd_sleep(self, payload: dict[str, Any]) -> dict[str, Any]:
        duration = float(payload.get("seconds", payload.get("duration", 1.0)))
        await asyncio.sleep(duration)
        return {"slept_seconds": duration}

    async def cmd_create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        blend_file_path = Path(payload["blend_file_path"])
        blend_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.state.project_id = payload["project_id"]
        self.state.project_name = payload["name"]
        self.state.blend_file_path = str(blend_file_path)
        self.state.active_scene_name = payload.get("active_scene_name", "Scene")
        self.state.template_type = payload.get("template_type", "blank")
        self.state.unit_scale = float(payload.get("unit_scale", 1.0))
        self.state.dirty = False
        self.state.selected_ids = []
        self.state.objects = {}
        self.state.materials = {}
        self.state.lights = {}
        self.state.cameras = {}
        self.state.active_camera_id = None
        self.state.collections = {"Scene Collection": []}
        self.state.collection_parents = {"Scene Collection": None}
        self.state.collection_visibility = {"Scene Collection": {"visible": True, "hide_viewport": False, "hide_render": False}}
        self.state.render_settings = RenderSettingsState()
        blend_file_path.write_text(json_dumps(self._serialize_state(), pretty=True), encoding="utf-8")
        return {
            "project_id": self.state.project_id,
            "project_name": self.state.project_name,
            "blend_file_path": str(blend_file_path),
            "active_scene_name": self.state.active_scene_name,
            "template_type": self.state.template_type,
            "unit_scale": self.state.unit_scale,
            "object_count": 0,
        }

    async def cmd_open_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        blend_file_path = Path(payload["blend_file_path"])
        if not blend_file_path.exists():
            raise RuntimeCommandError("validation_error", f"Blend file does not exist: {blend_file_path}")
        serialized = json_loads(blend_file_path.read_text(encoding="utf-8"))
        self._restore_state(serialized)
        self.state.blend_file_path = str(blend_file_path)
        return {
            "project_id": self.state.project_id,
            "project_name": self.state.project_name,
            "blend_file_path": str(blend_file_path),
            "active_scene_name": self.state.active_scene_name,
            "template_type": self.state.template_type,
            "unit_scale": self.state.unit_scale,
            "object_count": len(self.state.objects),
            "dirty": self.state.dirty,
        }

    async def cmd_save_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("project_id") is not None:
            self.state.project_id = str(payload["project_id"])
        self._require_project()
        path = Path(payload.get("blend_file_path") or self.state.blend_file_path or "")
        if not path:
            raise RuntimeCommandError("validation_error", "No blend file path is available.")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.state.blend_file_path = str(path)
        self.state.dirty = False
        path.write_text(json_dumps(self._serialize_state(), pretty=True), encoding="utf-8")
        return {"blend_file_path": str(path), "active_scene_name": self.state.active_scene_name}

    async def cmd_create_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_project()
        snapshot_path = Path(payload["snapshot_path"])
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json_dumps(self._serialize_state(), pretty=True), encoding="utf-8")
        return {"snapshot_path": str(snapshot_path)}

    async def cmd_restore_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot_path = Path(payload["snapshot_path"])
        if not snapshot_path.exists():
            raise RuntimeCommandError("validation_error", f"Snapshot not found: {snapshot_path}")
        target_path = Path(payload.get("target_blend_file_path") or self.state.blend_file_path or "")
        if not target_path:
            raise RuntimeCommandError("validation_error", "No target .blend filepath is available for restore.")
        serialized = json_loads(snapshot_path.read_text(encoding="utf-8"))
        self._restore_state(serialized)
        await self.cmd_save_project({"blend_file_path": str(target_path)})
        return {
            "blend_file_path": str(target_path),
            "restored_from": str(snapshot_path),
            "active_scene_name": self.state.active_scene_name,
        }

    async def cmd_get_project_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        self._require_project()
        return {
            "project_id": self.state.project_id,
            "name": self.state.project_name,
            "blend_file_path": self.state.blend_file_path,
            "active_scene_name": self.state.active_scene_name,
            "unit_scale": self.state.unit_scale,
            "object_count": len(self.state.objects),
            "dirty": self.state.dirty,
        }

    async def cmd_find_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = [obj for obj in self.state.objects.values() if self._object_matches(obj, payload)]
        return {"objects": [obj.to_payload() for obj in objects]}

    async def cmd_select_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        self.state.selected_ids = target_ids
        return {
            "selected_ids": target_ids,
            "objects": [self.state.objects[target_id].to_payload() for target_id in target_ids],
        }

    async def cmd_delete_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        deleted: list[str] = []
        for target_id in target_ids:
            self._object(target_id)
            deleted.append(target_id)
            self.state.objects.pop(target_id, None)
            self.state.lights.pop(target_id, None)
            self.state.cameras.pop(target_id, None)
            for collection in self.state.collections.values():
                while target_id in collection:
                    collection.remove(target_id)
            if target_id in self.state.selected_ids:
                self.state.selected_ids.remove(target_id)
            if self.state.active_camera_id == target_id:
                self.state.active_camera_id = None
        self.state.dirty = True
        return {"deleted_object_ids": deleted}

    async def cmd_duplicate_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        created_objects: list[dict[str, Any]] = []
        created_ids: list[str] = []
        for target_id in target_ids:
            source = self._object(target_id)
            duplicate_id = self.new_object_id()
            duplicate = RuntimeObject(
                object_id=duplicate_id,
                name=f"{source.name}_copy",
                object_type=source.object_type,
                location=tuple(source.location),
                rotation=tuple(source.rotation),
                scale=tuple(source.scale),
                visible=source.visible,
                collection=source.collection,
                tags=list(source.tags),
                material_ids=list(source.material_ids),
                data=deepcopy(source.data),
            )
            self.state.objects[duplicate_id] = duplicate
            self._ensure_collection(duplicate.collection)
            self.state.collections[duplicate.collection].append(duplicate_id)
            if source.object_type == "LIGHT" and target_id in self.state.lights:
                light = self.state.lights[target_id]
                self.state.lights[duplicate_id] = RuntimeLight(
                    light_id=duplicate_id,
                    name=f"{light.name}_copy",
                    light_type=light.light_type,
                    location=tuple(light.location),
                    rotation=tuple(light.rotation),
                    intensity=light.intensity,
                    color=tuple(light.color),
                    size=light.size,
                )
            if source.object_type == "CAMERA" and target_id in self.state.cameras:
                camera = self.state.cameras[target_id]
                self.state.cameras[duplicate_id] = RuntimeCamera(
                    camera_id=duplicate_id,
                    name=f"{camera.name}_copy",
                    location=tuple(camera.location),
                    rotation=tuple(camera.rotation),
                    focal_length=camera.focal_length,
                    field_of_view=camera.field_of_view,
                )
            created_ids.append(duplicate_id)
            created_objects.append(duplicate.to_payload())
        self.state.dirty = True
        return {"created_object_ids": created_ids, "created_objects": created_objects}

    async def cmd_rename_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object(payload["target_id"])
        obj.name = payload["new_name"]
        if obj.object_type == "LIGHT" and obj.object_id in self.state.lights:
            self.state.lights[obj.object_id].name = payload["new_name"]
        if obj.object_type == "CAMERA" and obj.object_id in self.state.cameras:
            self.state.cameras[obj.object_id].name = payload["new_name"]
        self.state.dirty = True
        return {"object": obj.to_payload()}

    async def cmd_transform_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object(payload["target_id"])
        if payload.get("location") is not None:
            obj.location = tuple(payload["location"])
        if payload.get("rotation") is not None:
            obj.rotation = tuple(payload["rotation"])
        if payload.get("scale") is not None:
            obj.scale = tuple(payload["scale"])
        self._sync_specialized_state(obj)
        self.state.dirty = True
        return {"object": obj.to_payload()}

    async def cmd_apply_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object(payload["target_id"])
        if bool(payload.get("apply_location", False)):
            obj.location = (0.0, 0.0, 0.0)
        if bool(payload.get("apply_rotation", False)):
            obj.rotation = (0.0, 0.0, 0.0)
        if bool(payload.get("apply_scale", True)):
            obj.scale = (1.0, 1.0, 1.0)
        self._sync_specialized_state(obj)
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_set_origin(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._object(payload["target_id"])
        obj.data["origin_mode"] = payload.get("mode", "geometry_center")
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_reset_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        for obj in objects:
            if bool(payload.get("reset_location", True)):
                obj.location = (0.0, 0.0, 0.0)
            if bool(payload.get("reset_rotation", True)):
                obj.rotation = (0.0, 0.0, 0.0)
            if bool(payload.get("reset_scale", True)):
                obj.scale = (1.0, 1.0, 1.0)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_offset_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        location_offset = self._vector3(payload.get("location_offset", [0.0, 0.0, 0.0]))
        rotation_offset = self._vector3(payload.get("rotation_offset", [0.0, 0.0, 0.0]))
        scale_multiplier = self._vector3(payload.get("scale_multiplier", [1.0, 1.0, 1.0]))
        for obj in objects:
            obj.location = tuple(obj.location[index] + location_offset[index] for index in range(3))
            obj.rotation = tuple(obj.rotation[index] + rotation_offset[index] for index in range(3))
            obj.scale = tuple(obj.scale[index] * scale_multiplier[index] for index in range(3))
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_match_object_transform(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._object(str(payload["source_id"]))
        objects = self._target_objects(payload)
        for obj in objects:
            if bool(payload.get("match_location", True)):
                obj.location = tuple(source.location)
            if bool(payload.get("match_rotation", True)):
                obj.rotation = tuple(source.rotation)
            if bool(payload.get("match_scale", True)):
                obj.scale = tuple(source.scale)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_align_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        align_to = str(payload.get("align_to", "origin"))
        points = [self._alignment_point(obj, axis_index, align_to) for obj in objects]
        target_value = float(payload["target_value"]) if payload.get("target_value") is not None else points[0]
        for obj, point in zip(objects, points, strict=False):
            location = list(obj.location)
            location[axis_index] += target_value - point
            obj.location = tuple(location)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_distribute_objects(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        ordered = sorted(objects, key=lambda obj: obj.location[axis_index])
        if len(ordered) <= 1:
            return self._transform_result(ordered)
        spacing = payload.get("spacing")
        if spacing is None:
            start_value = float(payload.get("start_value", ordered[0].location[axis_index]))
            end_value = ordered[-1].location[axis_index]
            step = (end_value - start_value) / float(len(ordered) - 1)
        else:
            start_value = float(payload.get("start_value", ordered[0].location[axis_index]))
            step = float(spacing)
        for index, obj in enumerate(ordered):
            location = list(obj.location)
            location[axis_index] = start_value + (step * index)
            obj.location = tuple(location)
            self._sync_specialized_state(obj)
        return self._transform_result(ordered)

    async def cmd_snap_objects_to_grid(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        grid_size = float(payload.get("grid_size", 1.0))
        if grid_size <= 0:
            raise RuntimeCommandError("validation_error", "grid_size must be greater than zero.")
        axis_indices = [self._axis_index(str(axis)) for axis in payload.get("axes", ["x", "y", "z"])]
        for obj in objects:
            location = list(obj.location)
            for axis_index in axis_indices:
                location[axis_index] = round(location[axis_index] / grid_size) * grid_size
            obj.location = tuple(location)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_place_objects_on_ground(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        ground_z = float(payload.get("ground_z", 0.0))
        for obj in objects:
            minimum, _maximum = self._object_bounds(obj)
            location = list(obj.location)
            location[2] += ground_z - minimum[2]
            obj.location = tuple(location)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_arrange_objects_in_grid(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
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
            obj.location = tuple(location)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_mirror_object_transforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects = self._target_objects(payload)
        axis_index = self._axis_index(str(payload.get("axis", "x")))
        pivot = float(payload.get("pivot", 0.0))
        flip_scale = bool(payload.get("flip_scale", False))
        for obj in objects:
            location = list(obj.location)
            location[axis_index] = (2.0 * pivot) - location[axis_index]
            obj.location = tuple(location)
            if flip_scale:
                scale = list(obj.scale)
                scale[axis_index] *= -1.0
                obj.scale = tuple(scale)
            self._sync_specialized_state(obj)
        return self._transform_result(objects)

    async def cmd_set_object_visibility(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            obj.visible = bool(payload["visible"])
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {"objects": objects}

    async def cmd_assign_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        collection_name = payload["collection_name"]
        self._ensure_collection(collection_name)
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            if obj.collection in self.state.collections and target_id in self.state.collections[obj.collection]:
                self.state.collections[obj.collection].remove(target_id)
            obj.collection = collection_name
            self.state.collections[collection_name].append(target_id)
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {"objects": objects}

    async def cmd_list_collections(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"collections": [self._collection_payload(name) for name in self.state.collections]}

    async def cmd_create_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        parent_name = str(payload.get("parent_collection_name") or "Scene Collection")
        if collection_name in self.state.collections:
            raise RuntimeCommandError("validation_error", f"Collection '{collection_name}' already exists.")
        self._collection(parent_name)
        self.state.collections[collection_name] = []
        self.state.collection_parents[collection_name] = parent_name
        self.state.collection_visibility[collection_name] = {"visible": True, "hide_viewport": False, "hide_render": False}
        self.state.dirty = True
        return {"collection": self._collection_payload(collection_name)}

    async def cmd_rename_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        new_name = str(payload["new_collection_name"])
        object_ids = self._collection(collection_name)
        if collection_name == "Scene Collection":
            raise RuntimeCommandError("validation_error", "Scene Collection cannot be renamed.")
        if new_name in self.state.collections:
            raise RuntimeCommandError("validation_error", f"Collection '{new_name}' already exists.")
        self.state.collections[new_name] = self.state.collections.pop(collection_name)
        self.state.collection_parents[new_name] = self.state.collection_parents.pop(collection_name, "Scene Collection")
        self.state.collection_visibility[new_name] = self.state.collection_visibility.pop(
            collection_name,
            {"visible": True, "hide_viewport": False, "hide_render": False},
        )
        for child_name, parent_name in list(self.state.collection_parents.items()):
            if parent_name == collection_name:
                self.state.collection_parents[child_name] = new_name
        objects: list[dict[str, Any]] = []
        for object_id in object_ids:
            obj = self._object(object_id)
            if obj.collection == collection_name:
                obj.collection = new_name
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {
            "collection": self._collection_payload(new_name),
            "modified_object_ids": list(object_ids),
            "objects": objects,
        }

    async def cmd_delete_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        object_ids = list(self._collection(collection_name))
        if collection_name == "Scene Collection":
            raise RuntimeCommandError("validation_error", "Scene Collection cannot be deleted.")
        child_names = self._collection_children(collection_name)
        force = bool(payload.get("force", False))
        if not force and (object_ids or child_names):
            raise RuntimeCommandError(
                "validation_error",
                f"Collection '{collection_name}' is not empty; pass force=true to remove collection membership without deleting objects.",
            )
        parent_name = self.state.collection_parents.get(collection_name) or "Scene Collection"
        relinked_collection_name = parent_name if parent_name in self.state.collections else "Scene Collection"
        for child_name in child_names:
            self.state.collection_parents[child_name] = relinked_collection_name
        objects: list[dict[str, Any]] = []
        for object_id in object_ids:
            obj = self._object(object_id)
            if obj.collection == collection_name:
                obj.collection = self._first_membership_for_object(object_id, exclude=collection_name) or relinked_collection_name
            if obj.collection not in self.state.collections:
                self._ensure_collection(obj.collection)
            if object_id not in self.state.collections[obj.collection]:
                self.state.collections[obj.collection].append(object_id)
            objects.append(obj.to_payload())
        self.state.collections.pop(collection_name, None)
        self.state.collection_parents.pop(collection_name, None)
        self.state.collection_visibility.pop(collection_name, None)
        self.state.dirty = True
        return {
            "modified_object_ids": object_ids,
            "unlinked_object_ids": object_ids,
            "rehomed_child_collection_names": child_names,
            "relinked_collection_name": relinked_collection_name,
            "objects": objects,
        }

    async def cmd_link_objects_to_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        self._collection(collection_name)
        target_ids = self._resolve_target_ids(payload)
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            if target_id not in self.state.collections[collection_name]:
                self.state.collections[collection_name].append(target_id)
            if obj.collection == "Scene Collection":
                obj.collection = collection_name
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {
            "collection": self._collection_payload(collection_name),
            "modified_object_ids": target_ids,
            "objects": objects,
        }

    async def cmd_unlink_objects_from_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        self._collection(collection_name)
        target_ids = self._resolve_target_ids(payload)
        missing_members = [target_id for target_id in target_ids if target_id not in self.state.collections[collection_name]]
        if missing_members:
            raise RuntimeCommandError(
                "target_not_found",
                f"Object(s) are not linked to collection '{collection_name}': {', '.join(missing_members)}",
            )
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            self.state.collections[collection_name].remove(target_id)
            if obj.collection == collection_name:
                obj.collection = self._first_membership_for_object(target_id, exclude=collection_name) or "Scene Collection"
            if obj.collection not in self.state.collections:
                self._ensure_collection(obj.collection)
            if target_id not in self.state.collections[obj.collection]:
                self.state.collections[obj.collection].append(target_id)
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {
            "collection": self._collection_payload(collection_name),
            "modified_object_ids": target_ids,
            "relinked_collection_name": "Scene Collection",
            "objects": objects,
        }

    async def cmd_set_collection_visibility(self, payload: dict[str, Any]) -> dict[str, Any]:
        collection_name = str(payload["collection_name"])
        self._collection(collection_name)
        visibility = self.state.collection_visibility.setdefault(
            collection_name,
            {"visible": True, "hide_viewport": False, "hide_render": False},
        )
        visible = bool(payload["visible"])
        if bool(payload.get("set_viewport", True)):
            visibility["hide_viewport"] = not visible
        if bool(payload.get("set_render", True)):
            visibility["hide_render"] = not visible
        visibility["visible"] = not visibility.get("hide_viewport", False) and not visibility.get("hide_render", False)
        self.state.dirty = True
        return {"collection": self._collection_payload(collection_name)}

    async def cmd_tag_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        tags = list(payload["tags"])
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            obj.tags = list(dict.fromkeys([*obj.tags, *tags]))
            objects.append(obj.to_payload())
        self.state.dirty = True
        return {"objects": objects}

    async def cmd_create_primitive(self, payload: dict[str, Any]) -> dict[str, Any]:
        object_id = self.new_object_id()
        obj = RuntimeObject(
            object_id=object_id,
            name=payload.get("name") or f"{payload['primitive_type']}_{len(self.state.objects) + 1}",
            object_type="MESH",
            location=tuple(payload.get("location", [0.0, 0.0, 0.0])),
            rotation=tuple(payload.get("rotation", [0.0, 0.0, 0.0])),
            scale=tuple(payload.get("scale", [1.0, 1.0, 1.0])),
            collection=payload.get("collection_name", "Scene Collection"),
            tags=list(payload.get("tags", [])),
            data=self._primitive_mesh_data(payload["primitive_type"], dict(payload.get("parameters", {}))),
        )
        self._add_object(obj)
        return {"created_object_ids": [object_id], "objects": [obj.to_payload()]}

    async def cmd_create_custom_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        object_id = self.new_object_id()
        obj = RuntimeObject(
            object_id=object_id,
            name=payload["name"],
            object_type="MESH",
            collection=payload.get("collection_name", "Scene Collection"),
            tags=list(payload.get("tags", [])),
            data={
                "vertices": payload["vertices"],
                "edges": payload.get("edges", []),
                "faces": payload.get("faces", []),
            },
        )
        self._add_object(obj)
        return {"created_object_ids": [object_id], "objects": [obj.to_payload()]}

    async def cmd_create_curve(self, payload: dict[str, Any]) -> dict[str, Any]:
        resolved_curve_type = "nurbs_path" if payload["curve_type"] == "path" else payload["curve_type"]
        object_id = self.new_object_id()
        obj = RuntimeObject(
            object_id=object_id,
            name=payload["name"],
            object_type="CURVE",
            location=tuple(payload.get("location", [0.0, 0.0, 0.0])),
            rotation=tuple(payload.get("rotation", [0.0, 0.0, 0.0])),
            collection=payload.get("collection_name", "Scene Collection"),
            tags=list(payload.get("tags", [])),
            data={
                "curve_type": payload["curve_type"],
                "resolved_curve_type": resolved_curve_type,
                "points": payload["points"],
                "resolution": payload.get("resolution", 12),
            },
        )
        self._add_object(obj)
        return {"created_object_ids": [object_id], "objects": [obj.to_payload()]}

    async def cmd_create_text(self, payload: dict[str, Any]) -> dict[str, Any]:
        object_id = self.new_object_id()
        obj = RuntimeObject(
            object_id=object_id,
            name=payload["name"],
            object_type="FONT",
            location=tuple(payload.get("location", [0.0, 0.0, 0.0])),
            rotation=tuple(payload.get("rotation", [0.0, 0.0, 0.0])),
            collection=payload.get("collection_name", "Scene Collection"),
            tags=list(payload.get("tags", [])),
            data={
                "text": payload["text"],
                "font_size": payload.get("font_size", 1.0),
                "extrusion": payload.get("extrusion", 0.0),
                "bevel_depth": payload.get("bevel_depth", 0.0),
            },
        )
        self._add_object(obj)
        return {"created_object_ids": [object_id], "objects": [obj.to_payload()]}

    async def cmd_edit_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        obj.data["vertices"] = payload["vertices"]
        obj.data["edges"] = payload.get("edges", [])
        obj.data["faces"] = payload.get("faces", [])
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_extrude_mesh(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        distance = float(payload.get("distance", 0.1))
        vertices = [list(vertex) for vertex in obj.data.get("vertices", [])]
        faces = [list(face) for face in obj.data.get("faces", [])]
        if not vertices or not faces:
            raise RuntimeCommandError("validation_error", f"Target is not a closed mesh object: {payload['target_id']}")
        offset = len(vertices)
        extruded_vertices = [[x_coord, y_coord, z_coord + distance] for x_coord, y_coord, z_coord in vertices]
        extruded_faces = [[vertex_index + offset for vertex_index in face] for face in faces]
        side_faces = [
            [
                start_index,
                end_index,
                end_index + offset,
                start_index + offset,
            ]
            for face in faces
            for start_index, end_index in zip(face, face[1:] + face[:1], strict=False)
        ]
        obj.data["vertices"] = [*vertices, *extruded_vertices]
        obj.data["faces"] = [*faces, *extruded_faces, *side_faces]
        obj.data["edges"] = self._edges_from_faces(obj.data["faces"])
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_bevel_edges(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        obj.data["bevel"] = {"width": payload.get("width", 0.05), "segments": payload.get("segments", 1)}
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_merge_vertices(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        vertices = [list(vertex) for vertex in obj.data.get("vertices", [])]
        edges = [list(edge) for edge in obj.data.get("edges", [])]
        faces = [list(face) for face in obj.data.get("faces", [])]
        threshold = float(payload.get("threshold", 0.0001))
        merged_vertices: list[list[float]] = []
        index_map: dict[int, int] = {}
        for index, vertex in enumerate(vertices):
            mapped_index: int | None = None
            for existing_index, existing in enumerate(merged_vertices):
                distance = sum((a - b) ** 2 for a, b in zip(vertex, existing, strict=False)) ** 0.5
                if distance <= threshold:
                    mapped_index = existing_index
                    break
            if mapped_index is None:
                mapped_index = len(merged_vertices)
                merged_vertices.append(vertex)
            index_map[index] = mapped_index

        def _remap_indices(indices: list[int]) -> list[int]:
            remapped: list[int] = []
            for vertex_index in indices:
                mapped_index = index_map[vertex_index]
                if mapped_index not in remapped:
                    remapped.append(mapped_index)
            return remapped

        remapped_edges = [
            remapped
            for remapped in (_remap_indices(edge) for edge in edges)
            if len(remapped) == 2 and remapped[0] != remapped[1]
        ]
        seen_faces: set[tuple[int, ...]] = set()
        remapped_faces: list[list[int]] = []
        for face in faces:
            remapped = _remap_indices(face)
            if len(remapped) < 3:
                continue
            face_key = tuple(remapped)
            if face_key in seen_faces:
                continue
            seen_faces.add(face_key)
            remapped_faces.append(remapped)

        obj.data["vertices"] = merged_vertices
        obj.data["edges"] = remapped_edges
        obj.data["faces"] = remapped_faces
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_recalculate_normals(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        obj.data["normals_recalculated"] = True
        self.state.dirty = True
        return {"objects": [obj.to_payload()], "modified_object_ids": [obj.object_id]}

    async def cmd_create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material_id = new_id("material")
        material = RuntimeMaterial(material_id=material_id, name=payload["name"], properties=dict(payload.get("properties", {})))
        self.state.materials[material_id] = material
        self.state.dirty = True
        return {"material": asdict(material)}

    async def cmd_apply_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        material_id = payload["material_id"]
        if material_id not in self.state.materials:
            raise RuntimeCommandError("target_not_found", f"Unknown material_id: {material_id}")
        target_ids = self._resolve_target_ids(payload)
        objects: list[dict[str, Any]] = []
        for target_id in target_ids:
            obj = self._object(target_id)
            if obj.object_type not in {"MESH", "CURVE", "FONT"}:
                continue
            obj.material_ids = [material_id]
            objects.append(obj.to_payload())
        if objects:
            self.state.dirty = True
        return {"objects": objects}

    async def cmd_set_material_property(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material(payload["material_id"])
        material.properties[payload["property_name"]] = payload["value"]
        self.state.dirty = True
        return {"material": asdict(material)}

    async def cmd_add_material_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material(payload["material_id"])
        graph = self._material_node_graph(material)
        node = {
            "node_id": new_id("mnode"),
            "node_type": str(payload["node_type"]),
            "node_name": str(payload.get("node_name") or payload["node_type"]),
            "location": list(payload.get("location", [0.0, 0.0])),
            "params": dict(payload.get("params") or {}),
        }
        graph["nodes"].append(node)
        self.state.dirty = True
        return self._material_node_result(material, node=node)

    async def cmd_set_material_node_param(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material(payload["material_id"])
        graph = self._material_node_graph(material)
        node = self._material_node(graph, payload["node_id"])
        params = dict(node.get("params", {}))
        params[str(payload["param_name"])] = payload["value"]
        node["params"] = params
        self.state.dirty = True
        return self._material_node_result(material, node=node)

    async def cmd_connect_material_nodes(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material(payload["material_id"])
        graph = self._material_node_graph(material)
        self._material_node(graph, payload["from_node_id"])
        self._material_node(graph, payload["to_node_id"])
        link = {
            "link_id": new_id("mlink"),
            "from_node_id": payload["from_node_id"],
            "from_socket": payload["from_socket"],
            "to_node_id": payload["to_node_id"],
            "to_socket": payload["to_socket"],
        }
        graph["links"].append(link)
        self.state.dirty = True
        return self._material_node_result(material, link=link)

    async def cmd_list_material_nodes(self, payload: dict[str, Any]) -> dict[str, Any]:
        material = self._material(payload["material_id"])
        return self._material_node_result(material)

    async def cmd_create_pbr_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        properties = {
            key: value
            for key, value in payload.items()
            if key not in {"project_id", "request_id", "name", "safe_mode", "preview_after", "quality", "seed"}
        }
        return await self.cmd_create_material({"name": payload["name"], "properties": properties})

    async def cmd_create_light(self, payload: dict[str, Any]) -> dict[str, Any]:
        light_id = new_id("obj")
        light = RuntimeLight(
            light_id=light_id,
            name=payload["name"],
            light_type=payload.get("light_type", "AREA"),
            location=tuple(payload.get("location", [3.0, -3.0, 4.0])),
            rotation=tuple(payload.get("rotation", [0.9, 0.0, 0.7])),
            intensity=float(payload.get("intensity", 1000.0)),
            color=tuple(payload.get("color", [1.0, 1.0, 1.0])),
            size=float(payload.get("size", 1.0)),
        )
        self.state.lights[light_id] = light
        obj = RuntimeObject(
            object_id=light_id,
            name=payload["name"],
            object_type="LIGHT",
            location=light.location,
            rotation=light.rotation,
            collection="Scene Collection",
            data={},
        )
        self._add_object(obj)
        return {"light": asdict(light), "object": obj.to_payload()}

    async def cmd_set_light(self, payload: dict[str, Any]) -> dict[str, Any]:
        light = self._light(payload["light_id"])
        if payload.get("location") is not None:
            light.location = tuple(payload["location"])
        if payload.get("rotation") is not None:
            light.rotation = tuple(payload["rotation"])
        if payload.get("intensity") is not None:
            light.intensity = float(payload["intensity"])
        if payload.get("color") is not None:
            light.color = tuple(payload["color"])
        if payload.get("size") is not None:
            light.size = float(payload["size"])
        obj = self._object(payload["light_id"])
        obj.location = light.location
        obj.rotation = light.rotation
        self.state.dirty = True
        return {"light": asdict(light), "object": obj.to_payload()}

    async def cmd_apply_lighting_preset(self, payload: dict[str, Any]) -> dict[str, Any]:
        objects: list[dict[str, Any]] = []
        for light_def in payload["lights"]:
            created = await self.cmd_create_light(light_def)
            objects.append(created["object"])
        return {"objects": objects}

    async def cmd_auto_light_subject(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_ids = self._resolve_target_ids(payload)
        if not target_ids:
            raise RuntimeCommandError("target_not_found", "No subject was resolved for auto_light_subject.")
        subject = self._object(target_ids[0])
        base = subject.location
        lights = [
            {
                "name": "AutoKey",
                "location": [base[0] + 3.0, base[1] - 3.0, base[2] + 3.0],
                "rotation": [0.9, 0.0, 0.7],
                "intensity": 1600.0,
                "color": [1.0, 0.97, 0.92],
                "size": 2.0,
            },
            {
                "name": "AutoFill",
                "location": [base[0] - 2.5, base[1] - 2.0, base[2] + 1.5],
                "rotation": [1.0, 0.0, -0.4],
                "intensity": 850.0,
                "color": [0.85, 0.92, 1.0],
                "size": 2.5,
            },
        ]
        return await self.cmd_apply_lighting_preset({"lights": lights})

    async def cmd_create_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera_id = new_id("obj")
        camera = RuntimeCamera(
            camera_id=camera_id,
            name=payload["name"],
            location=tuple(payload.get("location", [0.0, -5.0, 3.0])),
            rotation=tuple(payload.get("rotation", [1.1, 0.0, 0.0])),
            focal_length=float(payload.get("focal_length", 50.0)),
            field_of_view=float(payload.get("field_of_view", 0.9)),
        )
        self.state.cameras[camera_id] = camera
        self.state.active_camera_id = self.state.active_camera_id or camera_id
        obj = RuntimeObject(
            object_id=camera_id,
            name=payload["name"],
            object_type="CAMERA",
            location=camera.location,
            rotation=camera.rotation,
            collection="Scene Collection",
            data={},
        )
        self._add_object(obj)
        return {"camera": asdict(camera), "object": obj.to_payload()}

    async def cmd_set_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera = self._camera(payload["camera_id"])
        if payload.get("location") is not None:
            camera.location = tuple(payload["location"])
        if payload.get("rotation") is not None:
            camera.rotation = tuple(payload["rotation"])
        if payload.get("focal_length") is not None:
            camera.focal_length = float(payload["focal_length"])
        if payload.get("field_of_view") is not None:
            camera.field_of_view = float(payload["field_of_view"])
        obj = self._object(payload["camera_id"])
        obj.location = camera.location
        obj.rotation = camera.rotation
        self.state.dirty = True
        return {"camera": asdict(camera), "object": obj.to_payload()}

    async def cmd_frame_object(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera = self._camera(payload["camera_id"])
        target_ids = self._resolve_target_ids(payload)
        minimum, maximum = self._combined_bounds([self._object(target_id) for target_id in target_ids])
        center = tuple((low + high) / 2.0 for low, high in zip(minimum, maximum, strict=False))
        extent = max(high - low for low, high in zip(minimum, maximum, strict=False))
        distance = max(extent * 2.5, 3.0)
        camera.location = (center[0], center[1] - distance, center[2] + (distance * 0.6))
        obj = self._object(payload["camera_id"])
        obj.location = camera.location
        self.state.dirty = True
        return {"camera": asdict(camera), "object": obj.to_payload()}

    async def cmd_set_active_camera(self, payload: dict[str, Any]) -> dict[str, Any]:
        camera = self._camera(payload["camera_id"])
        self.state.active_camera_id = camera.camera_id
        self.state.dirty = True
        return {"active_camera_id": camera.camera_id}

    async def cmd_set_render_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        for key in ("engine", "resolution_x", "resolution_y", "samples", "transparent_background"):
            if payload.get(key) is not None:
                setattr(self.state.render_settings, key, payload[key])
        self.state.dirty = True
        return {"render_settings": asdict(self.state.render_settings)}

    async def cmd_get_render_settings(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"render_settings": asdict(self.state.render_settings)}

    async def cmd_render_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.cmd_set_render_settings(payload)
        active_camera_id = self.state.active_camera_id
        if payload.get("camera_id") is not None:
            active_camera_id = self._camera(payload["camera_id"]).camera_id
            self.state.active_camera_id = active_camera_id
        image_path = self._write_preview_image(payload["output_path"])
        return {
            "image_path": image_path,
            "render_settings": asdict(self.state.render_settings),
            "active_camera_id": active_camera_id,
        }

    async def cmd_render_thumbnail(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.cmd_render_preview(payload)

    async def cmd_export_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_project()
        output_path = Path(payload["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target_ids = payload.get("target_ids")
        if target_ids:
            object_ids = self._resolve_target_ids({"target_ids": list(target_ids)})
            objects = [self._object(object_id).to_payload() for object_id in object_ids]
        else:
            objects = [obj.to_payload() for obj in self.state.objects.values()]
        export_payload = {
            "project_id": self.state.project_id,
            "export_format": payload.get("export_format", "glb"),
            "object_count": len(objects),
            "objects": objects,
        }
        output_path.write_text(json_dumps(export_payload, pretty=True), encoding="utf-8")
        return {
            "output_path": str(output_path),
            "object_count": len(objects),
            "warnings": [],
        }

    async def cmd_import_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_project()
        input_path = Path(payload["input_path"])
        if not input_path.exists():
            raise RuntimeCommandError("validation_error", f"Import file does not exist: {input_path}")
        prefix = str(payload.get("name_prefix") or "")
        base_name = input_path.stem
        object_name = f"{prefix}_{base_name}" if prefix else base_name
        object_id = self.new_object_id()
        mesh_data = self._primitive_mesh_data("cube", {})
        imported = RuntimeObject(
            object_id=object_id,
            name=object_name,
            object_type="MESH",
            collection="Scene Collection",
            data=mesh_data,
        )
        self._add_object(imported)
        return {"objects": [imported.to_payload()]}

    async def cmd_add_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifiers: list[dict[str, Any]] = list(obj.data.get("modifiers", []))
        modifier_type: str = payload["modifier_type"]
        name: str = str(payload.get("name") or modifier_type)
        params: dict[str, Any] = dict(payload.get("params") or {})
        if any(m["name"] == name for m in modifiers):
            raise RuntimeCommandError("validation_error", f"A modifier named '{name}' already exists.")
        modifiers.append({"type": modifier_type, "name": name, "params": params})
        obj.data["modifiers"] = modifiers
        self.state.dirty = True
        return {"modifier_name": name, "modifiers": modifiers, "objects": [obj.to_payload()]}

    async def cmd_remove_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifiers: list[dict[str, Any]] = list(obj.data.get("modifiers", []))
        modifier_name: str = payload["modifier_name"]
        before = len(modifiers)
        modifiers = [m for m in modifiers if m["name"] != modifier_name]
        if len(modifiers) == before:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        obj.data["modifiers"] = modifiers
        self.state.dirty = True
        return {"modifiers": modifiers, "objects": [obj.to_payload()]}

    async def cmd_set_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifiers: list[dict[str, Any]] = list(obj.data.get("modifiers", []))
        modifier_name: str = payload["modifier_name"]
        params: dict[str, Any] = dict(payload.get("params") or {})
        updated = False
        for modifier in modifiers:
            if modifier["name"] == modifier_name:
                modifier["params"] = {**modifier.get("params", {}), **params}
                updated = True
                break
        if not updated:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        obj.data["modifiers"] = modifiers
        self.state.dirty = True
        return {"modifiers": modifiers, "objects": [obj.to_payload()]}

    async def cmd_apply_modifier(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifiers: list[dict[str, Any]] = list(obj.data.get("modifiers", []))
        modifier_name: str = payload["modifier_name"]
        before = len(modifiers)
        modifiers = [m for m in modifiers if m["name"] != modifier_name]
        if len(modifiers) == before:
            raise RuntimeCommandError("target_not_found", f"Modifier '{modifier_name}' not found.")
        obj.data["modifiers"] = modifiers
        self.state.dirty = True
        return {"modifiers": modifiers, "objects": [obj.to_payload()]}

    async def cmd_list_modifiers(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = self._mesh_object(payload["target_id"])
        modifiers: list[dict[str, Any]] = list(obj.data.get("modifiers", []))
        return {"modifiers": modifiers}

    async def cmd_shutdown(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"shutdown": True}

    def _add_object(self, obj: RuntimeObject) -> None:
        self.state.objects[obj.object_id] = obj
        self._ensure_collection(obj.collection)
        self.state.collections[obj.collection].append(obj.object_id)
        self.state.dirty = True

    def _ensure_collection(self, name: str) -> None:
        self.state.collections.setdefault(name, [])
        self.state.collection_parents.setdefault(name, None if name == "Scene Collection" else "Scene Collection")
        self.state.collection_visibility.setdefault(name, {"visible": True, "hide_viewport": False, "hide_render": False})

    def _collection(self, name: str) -> list[str]:
        if name not in self.state.collections:
            raise RuntimeCommandError("target_not_found", f"Unknown collection_name: {name}")
        self._ensure_collection(name)
        return self.state.collections[name]

    def _collection_children(self, name: str) -> list[str]:
        return [child_name for child_name, parent_name in self.state.collection_parents.items() if parent_name == name]

    def _first_membership_for_object(self, object_id: str, *, exclude: str) -> str | None:
        for collection_name, object_ids in self.state.collections.items():
            if collection_name != exclude and object_id in object_ids:
                return collection_name
        return None

    def _collection_payload(self, name: str) -> dict[str, Any]:
        self._ensure_collection(name)
        visibility = self.state.collection_visibility[name]
        object_ids = list(dict.fromkeys(self.state.collections[name]))
        return {
            "name": name,
            "parent_name": self.state.collection_parents.get(name),
            "children": self._collection_children(name),
            "object_ids": object_ids,
            "object_count": len(object_ids),
            "visible": visibility.get("visible", True),
            "hide_viewport": visibility.get("hide_viewport", False),
            "hide_render": visibility.get("hide_render", False),
        }

    def _object(self, object_id: str) -> RuntimeObject:
        if object_id not in self.state.objects:
            raise RuntimeCommandError("target_not_found", f"Unknown object_id: {object_id}")
        return self.state.objects[object_id]

    def _mesh_object(self, object_id: str) -> RuntimeObject:
        obj = self._object(object_id)
        if obj.object_type != "MESH":
            raise RuntimeCommandError("validation_error", f"Target is not a mesh object: {object_id}")
        return obj

    def _material(self, material_id: str) -> RuntimeMaterial:
        if material_id not in self.state.materials:
            raise RuntimeCommandError("target_not_found", f"Unknown material_id: {material_id}")
        return self.state.materials[material_id]

    @staticmethod
    def _material_node_graph(material: RuntimeMaterial) -> dict[str, Any]:
        graph = material.properties.setdefault("node_graph", {"nodes": [], "links": []})
        graph.setdefault("nodes", [])
        graph.setdefault("links", [])
        return graph

    @staticmethod
    def _material_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
        for node in graph.get("nodes", []):
            if node.get("node_id") == node_id:
                return node
        raise RuntimeCommandError("target_not_found", f"Unknown material node_id: {node_id}")

    def _material_node_result(
        self,
        material: RuntimeMaterial,
        *,
        node: dict[str, Any] | None = None,
        link: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        graph = self._material_node_graph(material)
        result = {
            "material": asdict(material),
            "nodes": list(graph.get("nodes", [])),
            "links": list(graph.get("links", [])),
        }
        if node is not None:
            result["node"] = node
        if link is not None:
            result["link"] = link
        return result

    def _light(self, light_id: str) -> RuntimeLight:
        if light_id not in self.state.lights:
            raise RuntimeCommandError("target_not_found", f"Unknown light_id: {light_id}")
        return self.state.lights[light_id]

    def _camera(self, camera_id: str) -> RuntimeCamera:
        if camera_id not in self.state.cameras:
            raise RuntimeCommandError("target_not_found", f"Unknown camera_id: {camera_id}")
        return self.state.cameras[camera_id]

    def _resolve_target_ids(self, payload: dict[str, Any]) -> list[str]:
        target_ids = list(payload.get("target_ids", []))
        if payload.get("target_id"):
            target_ids.append(payload["target_id"])
        if payload.get("names"):
            wanted = {name.lower() for name in payload["names"]}
            target_ids.extend(
                obj.object_id for obj in self.state.objects.values() if obj.name.lower() in wanted
            )
        resolved = list(dict.fromkeys(target_ids))
        if not resolved:
            raise RuntimeCommandError("target_not_found", "No targets were resolved.")
        for target_id in resolved:
            self._object(target_id)
        return resolved

    def _target_objects(self, payload: dict[str, Any]) -> list[RuntimeObject]:
        return [self._object(target_id) for target_id in self._resolve_target_ids(payload)]

    def _transform_result(self, objects: list[RuntimeObject]) -> dict[str, Any]:
        self.state.dirty = True
        return {
            "modified_object_ids": [obj.object_id for obj in objects],
            "objects": [obj.to_payload() for obj in objects],
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

    def _alignment_point(self, obj: RuntimeObject, axis_index: int, align_to: str) -> float:
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

    def _object_matches(self, obj: RuntimeObject, payload: dict[str, Any]) -> bool:
        if payload.get("names"):
            names = {name.lower() for name in payload["names"]}
            if obj.name.lower() not in names:
                return False
        if payload.get("object_type") and obj.object_type.lower() != str(payload["object_type"]).lower():
            return False
        if payload.get("tag") and payload["tag"] not in obj.tags:
            return False
        if payload.get("collection_name") and obj.collection != payload["collection_name"]:
            return False
        if payload.get("material_id") and payload["material_id"] not in obj.material_ids:
            return False
        if payload.get("spatial_range"):
            minimum = payload["spatial_range"].get("min", [-1e9, -1e9, -1e9])
            maximum = payload["spatial_range"].get("max", [1e9, 1e9, 1e9])
            if any(coord < lower or coord > upper for coord, lower, upper in zip(obj.location, minimum, maximum, strict=False)):
                return False
        return True

    def _combined_bounds(self, objects: list[RuntimeObject]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        for obj in objects:
            obj_min, obj_max = self._object_bounds(obj)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], obj_min[axis])
                maximum[axis] = max(maximum[axis], obj_max[axis])
        return (minimum[0], minimum[1], minimum[2]), (maximum[0], maximum[1], maximum[2])

    def _object_bounds(self, obj: RuntimeObject) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        vertices = obj.data.get("vertices")
        if vertices:
            transformed_vertices = [
                [
                    obj.location[axis] + (vertex[axis] * obj.scale[axis])
                    for axis in range(3)
                ]
                for vertex in vertices
            ]
            minimum = tuple(min(vertex[axis] for vertex in transformed_vertices) for axis in range(3))
            maximum = tuple(max(vertex[axis] for vertex in transformed_vertices) for axis in range(3))
            return minimum, maximum
        half_extents = [max(abs(scale_component), 0.5) * 0.5 for scale_component in obj.scale]
        minimum = tuple(obj.location[axis] - half_extents[axis] for axis in range(3))
        maximum = tuple(obj.location[axis] + half_extents[axis] for axis in range(3))
        return minimum, maximum

    def _sync_specialized_state(self, obj: RuntimeObject) -> None:
        if obj.object_type == "LIGHT" and obj.object_id in self.state.lights:
            light = self.state.lights[obj.object_id]
            light.location = obj.location
            light.rotation = obj.rotation
        if obj.object_type == "CAMERA" and obj.object_id in self.state.cameras:
            camera = self.state.cameras[obj.object_id]
            camera.location = obj.location
            camera.rotation = obj.rotation

    def _serialize_state(self) -> dict[str, Any]:
        return {
            "project": {
                "project_id": self.state.project_id,
                "project_name": self.state.project_name,
                "blend_file_path": self.state.blend_file_path,
                "active_scene_name": self.state.active_scene_name,
                "template_type": self.state.template_type,
                "unit_scale": self.state.unit_scale,
                "dirty": self.state.dirty,
                "selected_ids": self.state.selected_ids,
                "active_camera_id": self.state.active_camera_id,
            },
            "objects": [asdict(item) for item in self.state.objects.values()],
            "materials": [asdict(item) for item in self.state.materials.values()],
            "lights": [asdict(item) for item in self.state.lights.values()],
            "cameras": [asdict(item) for item in self.state.cameras.values()],
            "collections": self.state.collections,
            "collection_parents": self.state.collection_parents,
            "collection_visibility": self.state.collection_visibility,
            "render_settings": asdict(self.state.render_settings),
        }

    def _restore_state(self, payload: dict[str, Any]) -> None:
        project = payload["project"]
        self.state.project_id = project["project_id"]
        self.state.project_name = project["project_name"]
        self.state.blend_file_path = project["blend_file_path"]
        self.state.active_scene_name = project["active_scene_name"]
        self.state.template_type = project["template_type"]
        self.state.unit_scale = project["unit_scale"]
        self.state.dirty = project["dirty"]
        self.state.selected_ids = list(project["selected_ids"])
        self.state.active_camera_id = project["active_camera_id"]
        self.state.objects = {
            item["object_id"]: RuntimeObject(**item) for item in payload.get("objects", [])
        }
        self.state.materials = {
            item["material_id"]: RuntimeMaterial(**item) for item in payload.get("materials", [])
        }
        self.state.lights = {item["light_id"]: RuntimeLight(**item) for item in payload.get("lights", [])}
        self.state.cameras = {
            item["camera_id"]: RuntimeCamera(**item) for item in payload.get("cameras", [])
        }
        self.state.collections = {
            name: list(object_ids) for name, object_ids in payload.get("collections", {}).items()
        }
        if "Scene Collection" not in self.state.collections:
            self.state.collections["Scene Collection"] = []
        self.state.collection_parents = {
            name: parent_name for name, parent_name in payload.get("collection_parents", {}).items()
        }
        self.state.collection_visibility = {
            name: dict(visibility) for name, visibility in payload.get("collection_visibility", {}).items()
        }
        for name in list(self.state.collections):
            self._ensure_collection(name)
        self.state.render_settings = RenderSettingsState(**payload.get("render_settings", {}))

    def _write_preview_image(self, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_BLANK_PNG)
        return str(path)
