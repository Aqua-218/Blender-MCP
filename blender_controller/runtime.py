from __future__ import annotations

import ast
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


_SAFE_PYTHON_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.Global,
    ast.Nonlocal,
    ast.Delete,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
)
_SAFE_PYTHON_FORBIDDEN_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "exit",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "quit",
    "setattr",
    "vars",
}
_SAFE_PYTHON_ALLOWED_CALL_NAMES = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "range",
    "round",
    "sorted",
    "str",
    "sum",
    "tuple",
}
_SAFE_PYTHON_ALLOWED_METHODS = {
    "copy",
    "count",
    "endswith",
    "get",
    "index",
    "items",
    "join",
    "keys",
    "lower",
    "replace",
    "split",
    "startswith",
    "strip",
    "upper",
    "values",
}
_SAFE_PYTHON_CONTEXT_NAMES = {"objects", "materials", "lights", "cameras", "project", "selected_ids"}


def _safe_range(*args: int) -> range:
    values = [int(arg) for arg in args]
    result = range(*values)
    if len(result) > 10_000:
        raise ValueError("range is limited to 10000 items in safe Blender Python")
    return result


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items() if not str(key).startswith("__")}
    return str(value)


def _validate_assignment_target(target: ast.expr) -> None:
    if isinstance(target, ast.Name):
        if target.id in _SAFE_PYTHON_CONTEXT_NAMES or target.id in _SAFE_PYTHON_ALLOWED_CALL_NAMES or target.id.startswith("__"):
            raise RuntimeCommandError("validation_error", f"Safe Blender Python cannot assign to protected name: {target.id}")
        return
    if isinstance(target, ast.Tuple | ast.List):
        for item in target.elts:
            _validate_assignment_target(item)
        return
    raise RuntimeCommandError("validation_error", "Safe Blender Python only allows assignment to local names.")


def _validate_safe_python(code: str, *, max_code_chars: int) -> ast.Module:
    if len(code) > max_code_chars:
        raise RuntimeCommandError("validation_error", f"Safe Blender Python code is limited to {max_code_chars} characters.")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise RuntimeCommandError("validation_error", f"Python syntax error: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, _SAFE_PYTHON_FORBIDDEN_NODES):
            raise RuntimeCommandError("validation_error", f"Safe Blender Python rejected unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and (node.id in _SAFE_PYTHON_FORBIDDEN_NAMES or node.id.startswith("__")):
            raise RuntimeCommandError("validation_error", f"Safe Blender Python rejected forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise RuntimeCommandError("validation_error", f"Safe Blender Python rejected private attribute access: {node.attr}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in _SAFE_PYTHON_ALLOWED_CALL_NAMES:
                    raise RuntimeCommandError("validation_error", f"Safe Blender Python rejected call: {node.func.id}")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in _SAFE_PYTHON_ALLOWED_METHODS:
                    raise RuntimeCommandError("validation_error", f"Safe Blender Python rejected method call: {node.func.attr}")
            else:
                raise RuntimeCommandError("validation_error", "Safe Blender Python rejected dynamic calls.")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _validate_assignment_target(target)
        if isinstance(node, ast.AnnAssign | ast.AugAssign):
            _validate_assignment_target(node.target)
        if isinstance(node, ast.For):
            _validate_assignment_target(node.target)
    return tree


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

    async def cmd_execute_python(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("mode", "read_only") != "read_only":
            raise RuntimeCommandError("validation_error", "Safe Blender Python currently supports read_only mode only.")
        code = str(payload.get("code", ""))
        tree = _validate_safe_python(code, max_code_chars=int(payload.get("max_code_chars", 20_000)))
        if bool(payload.get("validate_only", False)):
            return {
                "validated": True,
                "executed": False,
                "mode": "read_only",
                "sandbox": "read_only_scene_context",
                "available_globals": sorted(_SAFE_PYTHON_CONTEXT_NAMES),
            }
        namespace = {
            "__builtins__": {
                "abs": abs,
                "all": all,
                "any": any,
                "bool": bool,
                "dict": dict,
                "enumerate": enumerate,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "max": max,
                "min": min,
                "range": _safe_range,
                "round": round,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
            },
            **self._safe_python_context(),
        }
        try:
            exec(compile(tree, "<safe_blender_python>", "exec"), namespace, namespace)
        except Exception as exc:
            raise RuntimeCommandError("validation_error", f"Safe Blender Python runtime error: {exc}") from exc
        return {
            "validated": True,
            "executed": True,
            "mode": "read_only",
            "sandbox": "read_only_scene_context",
            "available_globals": sorted(_SAFE_PYTHON_CONTEXT_NAMES),
            "result": _json_safe(namespace.get("result")),
        }

    def _safe_python_context(self) -> dict[str, Any]:
        return {
            "project": {
                "project_id": self.state.project_id,
                "project_name": self.state.project_name,
                "blend_file_path": self.state.blend_file_path,
                "active_scene_name": self.state.active_scene_name,
                "template_type": self.state.template_type,
                "unit_scale": self.state.unit_scale,
            },
            "objects": [_json_safe(obj.to_payload()) for obj in self.state.objects.values()],
            "materials": [_json_safe(asdict(material)) for material in self.state.materials.values()],
            "lights": [_json_safe(asdict(light)) for light in self.state.lights.values()],
            "cameras": [_json_safe(asdict(camera)) for camera in self.state.cameras.values()],
            "selected_ids": list(self.state.selected_ids),
        }

    def _require_project(self) -> None:
        if self.state.project_id is None:
            raise RuntimeCommandError("validation_error", "No active project is loaded.")

    @staticmethod
    def new_object_id() -> str:
        return new_id("obj")
