from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from mcp_server.models.common import (
    CommonToolRequest,
    CommonToolResult,
    failed_result,
    success_result,
)
from mcp_server.tools.advanced_helpers import load_entity_spec, retag_result, save_metadata_entity
from mcp_server.tools.geometry import CreateCurveRequest, create_curve
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.tools.modifiers import AddModifierRequest, add_modifier, list_modifiers
from mcp_server.tools.object import TransformObjectRequest, transform_object
from mcp_server.tools.render import SetActiveCameraRequest, set_active_camera
from mcp_server.utils import new_id


class KeyframeSpec(BaseModel):
    frame: int = Field(ge=1)
    location: list[float] | None = None
    rotation: list[float] | None = None
    scale: list[float] | None = None


class CreateKeyframeAnimationRequest(CommonToolRequest):
    project_id: str
    target_id: str
    name: str = "Animation"
    keyframes: list[KeyframeSpec] = Field(default_factory=list)
    apply_last_frame: bool = True


class CreateCameraAnimationRequest(CommonToolRequest):
    project_id: str
    camera_id: str
    name: str = "CameraAnimation"
    frame_count: int = Field(default=48, ge=2, le=512)
    radius: float = Field(default=6.0, gt=0.0)
    height: float = Field(default=3.0)


class CreateArmatureRequest(CommonToolRequest):
    project_id: str
    name: str
    root_location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])


class AddBoneRequest(CommonToolRequest):
    project_id: str
    armature_id: str
    name: str
    head: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    tail: list[float] = Field(default_factory=lambda: [0.0, 0.0, 1.0])
    parent_bone_id: str | None = None
    roll: float = 0.0


class SetBoneTransformRequest(CommonToolRequest):
    project_id: str
    armature_id: str
    bone_id: str
    head: list[float] | None = None
    tail: list[float] | None = None
    rotation: list[float] | None = None


class CreateSimpleRigRequest(CommonToolRequest):
    project_id: str
    name: str = "SimpleRig"
    root_location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    target_ids: list[str] = Field(default_factory=list)
    auto_bind: bool = True


class AutoWeightLimitedRequest(CommonToolRequest):
    project_id: str
    armature_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    max_influences: int = Field(default=4, ge=1, le=8)


def _load_armature(context, request_id: str, armature_id: str, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    armature = load_entity_spec(context, armature_id, expected_type="armature")
    if armature is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Armature '{armature_id}' was not found.",
            errors=[f"target_not_found: armature '{armature_id}' does not exist"],
        )
    return armature


def _load_bone(context, request_id: str, bone_id: str, tool_name: str) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    bone = load_entity_spec(context, bone_id, expected_type="bone")
    if bone is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Bone '{bone_id}' was not found.",
            errors=[f"target_not_found: bone '{bone_id}' does not exist"],
        )
    return bone


def _save_armature(context, project_id: str, armature: dict[str, Any]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return save_metadata_entity(
        context,
        project_id=project_id,
        entity_id=str(armature["armature_id"]),
        entity_type="armature",
        name=str(armature["name"]),
        spec=armature,
    )


async def create_armature(context, request: CreateArmatureRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    guide = await create_curve(
        context,
        CreateCurveRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=f"{request.name}_Guide",
            curve_type="polyline",
            points=[
                list(request.root_location),
                [request.root_location[0], request.root_location[1], request.root_location[2] + 1.0],
            ],
            collection_name="Rig Guides",
            tags=["armature_guide"],
        ),
    )
    if guide.status != "success":
        return retag_result(guide, "create_armature")
    armature_id = new_id("armature")
    armature = {
        "armature_id": armature_id,
        "name": request.name,
        "root_location": request.root_location,
        "guide_object_id": str(guide.created_object_ids[0]),
        "bone_ids": [],
    }
    _save_armature(context, project.project_id, armature)
    return success_result(
        request_id=request.request_id,
        tool_name="create_armature",
        summary=f"Created armature '{request.name}'.",
        project_id=project.project_id,
        armature_id=armature_id,
        armature=armature,
        created_object_ids=list(guide.created_object_ids),
        objects=guide.model_dump().get("objects", []),
    )


async def add_bone(context, request: AddBoneRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    armature = _load_armature(context, request.request_id, request.armature_id, "add_bone")
    if isinstance(armature, CommonToolResult):
        return armature
    if request.parent_bone_id is not None and load_entity_spec(context, request.parent_bone_id, expected_type="bone") is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="add_bone",
            summary=f"Parent bone '{request.parent_bone_id}' was not found.",
            errors=[f"target_not_found: parent bone '{request.parent_bone_id}' does not exist"],
        )
    bone_id = new_id("bone")
    bone = {
        "bone_id": bone_id,
        "armature_id": request.armature_id,
        "name": request.name,
        "head": request.head,
        "tail": request.tail,
        "parent_bone_id": request.parent_bone_id,
        "roll": request.roll,
        "rotation": [0.0, 0.0, 0.0],
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=bone_id,
        entity_type="bone",
        name=request.name,
        spec=bone,
    )
    armature["bone_ids"] = [*armature.get("bone_ids", []), bone_id]
    _save_armature(context, project.project_id, armature)
    return success_result(
        request_id=request.request_id,
        tool_name="add_bone",
        summary=f"Added bone '{request.name}'.",
        project_id=project.project_id,
        armature_id=request.armature_id,
        bone_id=bone_id,
        bone=bone,
    )


async def set_bone_transform(context, request: SetBoneTransformRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    armature = _load_armature(context, request.request_id, request.armature_id, "set_bone_transform")
    if isinstance(armature, CommonToolResult):
        return armature
    bone = _load_bone(context, request.request_id, request.bone_id, "set_bone_transform")
    if isinstance(bone, CommonToolResult):
        return bone
    if bone.get("armature_id") != request.armature_id:
        return failed_result(
            request_id=request.request_id,
            tool_name="set_bone_transform",
            summary="Bone does not belong to the requested armature.",
            errors=["validation_error: bone does not belong to the requested armature"],
        )
    if request.head is not None:
        bone["head"] = request.head
    if request.tail is not None:
        bone["tail"] = request.tail
    if request.rotation is not None:
        bone["rotation"] = request.rotation
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=request.bone_id,
        entity_type="bone",
        name=bone["name"],
        spec=bone,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="set_bone_transform",
        summary=f"Updated bone '{bone['name']}'.",
        project_id=project.project_id,
        armature_id=request.armature_id,
        bone=bone,
    )


async def auto_weight_limited(context, request: AutoWeightLimitedRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    armature = _load_armature(context, request.request_id, request.armature_id, "auto_weight_limited")
    if isinstance(armature, CommonToolResult):
        return armature
    target_ids = await resolve_target_ids(
        context,
        project_id=request.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
    )
    modified_object_ids: list[str] = []
    for target_id in target_ids:
        modifier_name = f"{armature['name']}_Weights"
        existing = await list_modifiers(
            context,
            type("ListRequest", (), {"request_id": request.request_id, "project_id": request.project_id, "target_id": target_id})(),
        )
        if existing.status == "success" and any(modifier["name"] == modifier_name for modifier in existing.model_dump().get("modifiers", [])):
            modified_object_ids.append(str(target_id))
            continue
        added = await add_modifier(
            context,
            AddModifierRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=str(target_id),
                modifier_type="ARMATURE",
                name=modifier_name,
                params={},
            ),
        )
        if added.status != "success":
            return retag_result(added, "auto_weight_limited")
        modified_object_ids.append(str(target_id))
    binding_id = new_id("binding")
    binding = {
        "binding_id": binding_id,
        "armature_id": request.armature_id,
        "target_ids": target_ids,
        "max_influences": request.max_influences,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=binding_id,
        entity_type="rig_binding",
        name=f"{armature['name']} Binding",
        spec=binding,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="auto_weight_limited",
        summary=f"Bound {len(target_ids)} target objects to armature '{armature['name']}'.",
        project_id=project.project_id,
        armature_id=request.armature_id,
        binding_id=binding_id,
        binding=binding,
        modified_object_ids=modified_object_ids,
    )


async def create_simple_rig(context, request: CreateSimpleRigRequest):  # type: ignore[no-untyped-def]
    armature = await create_armature(
        context,
        CreateArmatureRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            name=request.name,
            root_location=request.root_location,
        ),
    )
    if armature.status != "success":
        return retag_result(armature, "create_simple_rig")
    armature_id = str(armature.model_dump()["armature_id"])
    root_bone = await add_bone(
        context,
        AddBoneRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            armature_id=armature_id,
            name="root",
            head=request.root_location,
            tail=[request.root_location[0], request.root_location[1], request.root_location[2] + 1.0],
        ),
    )
    if root_bone.status != "success":
        return retag_result(root_bone, "create_simple_rig")
    spine_bone = await add_bone(
        context,
        AddBoneRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            armature_id=armature_id,
            name="spine",
            head=[request.root_location[0], request.root_location[1], request.root_location[2] + 1.0],
            tail=[request.root_location[0], request.root_location[1], request.root_location[2] + 2.1],
            parent_bone_id=root_bone.model_dump()["bone_id"],
        ),
    )
    if spine_bone.status != "success":
        return retag_result(spine_bone, "create_simple_rig")
    head_bone = await add_bone(
        context,
        AddBoneRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            armature_id=armature_id,
            name="head",
            head=[request.root_location[0], request.root_location[1], request.root_location[2] + 2.1],
            tail=[request.root_location[0], request.root_location[1], request.root_location[2] + 2.8],
            parent_bone_id=spine_bone.model_dump()["bone_id"],
        ),
    )
    if head_bone.status != "success":
        return retag_result(head_bone, "create_simple_rig")

    binding = None
    if request.auto_bind and request.target_ids:
        bound = await auto_weight_limited(
            context,
            AutoWeightLimitedRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                armature_id=armature_id,
                target_ids=request.target_ids,
            ),
        )
        if bound.status != "success":
            return retag_result(bound, "create_simple_rig")
        binding = bound.model_dump().get("binding")
    final_armature = load_entity_spec(context, armature_id, expected_type="armature")
    return success_result(
        request_id=request.request_id,
        tool_name="create_simple_rig",
        summary=f"Created simple rig '{request.name}'.",
        project_id=request.project_id,
        armature_id=armature_id,
        armature=final_armature,
        bone_ids=final_armature.get("bone_ids", []) if final_armature else [],
        binding=binding,
        created_object_ids=armature.created_object_ids,
        objects=armature.model_dump().get("objects", []),
    )


async def create_keyframe_animation(context, request: CreateKeyframeAnimationRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target = load_entity_spec(context, request.target_id)
    if target is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_keyframe_animation",
            summary=f"Target '{request.target_id}' was not found.",
            errors=[f"target_not_found: target '{request.target_id}' does not exist"],
        )
    keyframes = [frame.model_dump(exclude_none=True) for frame in request.keyframes]
    if not keyframes:
        keyframes = [
            {"frame": 1, "location": target.get("location", [0.0, 0.0, 0.0])},
            {"frame": 24, "location": [target.get("location", [0.0, 0.0, 0.0])[0] + 2.0, *target.get("location", [0.0, 0.0, 0.0])[1:]]},
        ]
    animation_id = new_id("anim")
    animation = {
        "animation_id": animation_id,
        "name": request.name,
        "target_id": request.target_id,
        "keyframes": keyframes,
    }
    save_metadata_entity(
        context,
        project_id=project.project_id,
        entity_id=animation_id,
        entity_type="animation_track",
        name=request.name,
        spec=animation,
    )
    modified_object_ids: list[str] = []
    if request.apply_last_frame:
        last_keyframe = keyframes[-1]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=request.request_id,
                project_id=request.project_id,
                target_id=request.target_id,
                location=last_keyframe.get("location"),
                rotation=last_keyframe.get("rotation"),
                scale=last_keyframe.get("scale"),
            ),
        )
        if transformed.status != "success":
            return retag_result(transformed, "create_keyframe_animation")
        modified_object_ids = [request.target_id]
    return success_result(
        request_id=request.request_id,
        tool_name="create_keyframe_animation",
        summary=f"Created animation '{request.name}'.",
        project_id=project.project_id,
        animation_id=animation_id,
        animation=animation,
        modified_object_ids=modified_object_ids,
    )


async def create_camera_animation(context, request: CreateCameraAnimationRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    camera = load_entity_spec(context, request.camera_id, expected_type="camera")
    if camera is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_camera_animation",
            summary=f"Camera '{request.camera_id}' was not found.",
            errors=[f"target_not_found: camera '{request.camera_id}' does not exist"],
        )
    keyframes = [
        {
            "frame": 1,
            "location": [request.radius, -request.radius, request.height],
            "rotation": [1.0, 0.0, math.pi / 4.0],
        },
        {
            "frame": max(2, request.frame_count // 2),
            "location": [-request.radius, 0.0, request.height + 0.5],
            "rotation": [1.05, 0.0, math.pi],
        },
        {
            "frame": request.frame_count,
            "location": [0.0, request.radius, request.height],
            "rotation": [1.0, 0.0, math.pi * 1.5],
        },
    ]
    animation = await create_keyframe_animation(
        context,
        CreateKeyframeAnimationRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            target_id=request.camera_id,
            name=request.name,
            keyframes=[KeyframeSpec.model_validate(frame) for frame in keyframes],
            apply_last_frame=True,
        ),
    )
    if animation.status != "success":
        return retag_result(animation, "create_camera_animation")
    active_camera = await set_active_camera(
        context,
        SetActiveCameraRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            camera_id=request.camera_id,
        ),
    )
    if active_camera.status != "success":
        return retag_result(active_camera, "create_camera_animation")
    payload = animation.model_dump()
    payload["tool_name"] = "create_camera_animation"
    payload["summary"] = f"Created camera animation '{request.name}'."
    payload["camera_id"] = request.camera_id
    payload["active_camera_id"] = active_camera.model_dump()["active_camera_id"]
    return type(animation).model_validate(payload)


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    specs: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("create_keyframe_animation", "Create managed animation keyframes for a target object.", CreateKeyframeAnimationRequest, create_keyframe_animation, False),
        ("create_camera_animation", "Create a managed orbit-style camera animation.", CreateCameraAnimationRequest, create_camera_animation, False),
        ("create_simple_rig", "Create a simple managed rig with three default bones.", CreateSimpleRigRequest, create_simple_rig, False),
        ("create_armature", "Create a managed armature guide and metadata record.", CreateArmatureRequest, create_armature, False),
        ("add_bone", "Add a managed bone to an existing armature.", AddBoneRequest, add_bone, False),
        ("set_bone_transform", "Update a managed bone transform.", SetBoneTransformRequest, set_bone_transform, False),
        ("auto_weight_limited", "Bind mesh targets to a managed rig with an ARMATURE modifier.", AutoWeightLimitedRequest, auto_weight_limited, False),
    ]
    for name, description, input_model, handler, read_only in specs:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="animation_rigging",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )