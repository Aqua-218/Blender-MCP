from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.tools.helpers import require_project


class ExecuteBlenderPythonRequest(CommonToolRequest):
    project_id: str
    code: str = Field(min_length=1, max_length=20_000)
    mode: Literal["read_only"] = "read_only"
    dry_run: bool = False
    retry_once: bool = True
    include_diff: bool = True


def _object_diff(before_objects: list[dict[str, Any]], after_objects: list[dict[str, Any]]) -> dict[str, Any]:
    before_by_id = {str(item["object_id"]): item for item in before_objects if "object_id" in item}
    after_by_id = {str(item["object_id"]): item for item in after_objects if "object_id" in item}
    added = [object_id for object_id in after_by_id if object_id not in before_by_id]
    removed = [object_id for object_id in before_by_id if object_id not in after_by_id]
    modified = [
        object_id
        for object_id in before_by_id
        if object_id in after_by_id and before_by_id[object_id] != after_by_id[object_id]
    ]
    return {
        "added_object_ids": added,
        "removed_object_ids": removed,
        "modified_object_ids": modified,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
    }


async def _list_objects(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    result = await context.bridge.invoke("list_objects", {"project_id": project_id}, read_only=True)
    return list(result.get("objects", []))


def _failure_classification(exc: ControllerBridgeError) -> dict[str, Any]:
    message = exc.message.lower()
    if exc.code == "controller_timeout":
        category = "transient_controller_timeout"
        retryable = True
    elif exc.code == "controller_unavailable":
        category = "controller_unavailable"
        retryable = True
    elif exc.code == "validation_error" and "safe blender python rejected" in message:
        category = "security_violation"
        retryable = False
    elif exc.code == "validation_error" and "syntax error" in message:
        category = "script_syntax"
        retryable = False
    elif exc.code == "validation_error" and "runtime error" in message:
        category = "script_runtime"
        retryable = False
    elif exc.code == "validation_error":
        category = "user_input"
        retryable = False
    else:
        category = "controller_error"
        retryable = False
    return {
        "category": category,
        "retryable": retryable,
        "error_code": exc.code,
    }


async def execute_blender_python(context, request: ExecuteBlenderPythonRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    before_objects = await _list_objects(context, project.project_id) if request.include_diff else []
    attempts = 0
    last_error: ControllerBridgeError | None = None
    max_attempts = 2 if request.retry_once else 1
    while attempts < max_attempts:
        attempts += 1
        try:
            execution = await context.bridge.invoke(
                "execute_python",
                {
                    "project_id": project.project_id,
                    "code": request.code,
                    "mode": request.mode,
                    "validate_only": request.dry_run,
                    "max_code_chars": 20_000,
                },
                read_only=True,
            )
            after_objects = before_objects if request.dry_run or not request.include_diff else await _list_objects(context, project.project_id)
            diff = _object_diff(before_objects, after_objects) if request.include_diff else None
            return success_result(
                request_id=request.request_id,
                tool_name="execute_blender_python",
                summary="Safe Blender Python dry-run completed." if request.dry_run else "Safe Blender Python executed.",
                project_id=project.project_id,
                dry_run=request.dry_run,
                attempts=attempts,
                execution=execution,
                diff=diff,
                failure_classification=None,
                warnings=[
                    "Execution uses a read-only scene snapshot context; bpy, imports, file I/O, dynamic calls, and mutation of context objects are not exposed."
                ],
            )
        except ControllerBridgeError as exc:
            classification = _failure_classification(exc)
            last_error = exc
            if attempts >= max_attempts or not classification["retryable"]:
                after_objects = before_objects if not request.include_diff else await _list_objects(context, project.project_id)
                return failed_result(
                    request_id=request.request_id,
                    tool_name="execute_blender_python",
                    summary="Safe Blender Python execution failed.",
                    errors=[f"{exc.code}: {exc.message}"],
                    project_id=project.project_id,
                    dry_run=request.dry_run,
                    attempts=attempts,
                    diff=_object_diff(before_objects, after_objects) if request.include_diff else None,
                    failure_classification=classification,
                )
    assert last_error is not None
    classification = _failure_classification(last_error)
    return failed_result(
        request_id=request.request_id,
        tool_name="execute_blender_python",
        summary="Safe Blender Python execution failed.",
        errors=[f"{last_error.code}: {last_error.message}"],
        project_id=project.project_id,
        dry_run=request.dry_run,
        attempts=attempts,
        failure_classification=classification,
    )



def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    app.register_tool(
        app.tool_definition(
            name="execute_blender_python",
            description="Execute constrained read-only Blender Python against a safe scene snapshot context with diff and failure classification.",
            family="foundation",
            input_model=ExecuteBlenderPythonRequest,
            handler=execute_blender_python,
            read_only=True,
        )
    )
