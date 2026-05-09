from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from mcp_server.utils import new_id


class RuntimeCommandError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class RuntimeObject:
    object_id: str
    name: str
    object_type: str
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    visible: bool = True
    collection: str = "Scene Collection"
    tags: list[str] = field(default_factory=list)
    material_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["type"] = payload.pop("object_type")
        if payload["type"] == "MESH":
            mesh_data = payload.get("data", {})
            normalized_mesh_data = {
                "vertices": [list(vertex) for vertex in mesh_data.get("vertices", [])],
                "edges": [list(edge) for edge in mesh_data.get("edges", [])],
                "faces": [list(face) for face in mesh_data.get("faces", [])],
            }
            for key, value in mesh_data.items():
                if key not in normalized_mesh_data:
                    normalized_mesh_data[key] = value
            payload["data"] = normalized_mesh_data
        elif payload["type"] == "CURVE":
            curve_data = payload.get("data", {})
            payload["data"] = {
                "curve_type": curve_data.get("curve_type", "polyline"),
                "points": [list(point) for point in curve_data.get("points", [])],
                "resolution": curve_data.get("resolution", 12),
            }
        return payload


@dataclass
class RuntimeMaterial:
    material_id: str
    name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeLight:
    light_id: str
    name: str
    light_type: str
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    intensity: float = 1000.0
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    size: float = 1.0


@dataclass
class RuntimeCamera:
    camera_id: str
    name: str
    location: tuple[float, float, float] = (0.0, -5.0, 3.0)
    rotation: tuple[float, float, float] = (1.1, 0.0, 0.0)
    focal_length: float = 50.0
    field_of_view: float = 0.9


@dataclass
class RenderSettingsState:
    engine: str = "BLENDER_EEVEE"
    resolution_x: int = 1024
    resolution_y: int = 1024
    samples: int = 32
    transparent_background: bool = True


@dataclass
class RuntimeProjectState:
    project_id: str | None = None
    project_name: str | None = None
    blend_file_path: str | None = None
    active_scene_name: str = "Scene"
    template_type: str = "blank"
    unit_scale: float = 1.0
    dirty: bool = False
    selected_ids: list[str] = field(default_factory=list)
    active_camera_id: str | None = None
    objects: dict[str, RuntimeObject] = field(default_factory=dict)
    materials: dict[str, RuntimeMaterial] = field(default_factory=dict)
    lights: dict[str, RuntimeLight] = field(default_factory=dict)
    cameras: dict[str, RuntimeCamera] = field(default_factory=dict)
    collections: dict[str, list[str]] = field(default_factory=lambda: {"Scene Collection": []})
    collection_parents: dict[str, str | None] = field(default_factory=lambda: {"Scene Collection": None})
    collection_visibility: dict[str, dict[str, bool]] = field(
        default_factory=lambda: {"Scene Collection": {"visible": True, "hide_viewport": False, "hide_render": False}}
    )
    render_settings: RenderSettingsState = field(default_factory=RenderSettingsState)


class BaseRuntime:
    supports_concurrent_reads = False

    def __init__(self) -> None:
        self.state = RuntimeProjectState()

    async def dispatch(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"cmd_{command}", None)
        if handler is None:
            raise RuntimeCommandError(
                "unsupported_feature",
                f"Runtime command is not supported: {command}",
            )
        return await handler(payload)

    async def cmd_ping(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"pong": True}

    async def cmd_get_runtime_info(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": self.__class__.__name__.replace("Runtime", "").lower(),
            "supports_concurrent_reads": self.supports_concurrent_reads,
            "capabilities": sorted(
                name[4:]
                for name in dir(self)
                if name.startswith("cmd_") and name not in {"cmd_ping", "cmd_get_runtime_info"}
            ),
        }

    async def cmd_list_objects(self, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"objects": [obj.to_payload() for obj in self.state.objects.values()]}

    def _require_project(self) -> None:
        if self.state.project_id is None:
            raise RuntimeCommandError("validation_error", "No active project is loaded.")

    @staticmethod
    def new_object_id() -> str:
        return new_id("obj")
