from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolStatus = Literal["success", "partial_success", "failed"]
QualityName = Literal["draft", "standard", "high", "hero"]


class CommonToolRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str = Field(min_length=1, description="Client-generated correlation identifier.")
    project_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    instruction: str | None = Field(
        default=None,
        description="Natural-language instruction for the tool.",
    )
    style: str | None = None
    quality: QualityName = "standard"
    seed: int = Field(default=0, ge=0)
    safe_mode: bool = True
    preview_after: bool = True


class CommonToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: ToolStatus
    request_id: str
    tool_name: str
    created_object_ids: list[str] = Field(default_factory=list)
    modified_object_ids: list[str] = Field(default_factory=list)
    deleted_object_ids: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    summary: str
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    next_suggestions: list[str] = Field(default_factory=list)


def _result_payload(
    *,
    status: ToolStatus,
    request_id: str,
    tool_name: str,
    summary: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    next_suggestions: list[str] | None = None,
    **extra: Any,
) -> CommonToolResult:
    payload = CommonToolResult(
        status=status,
        request_id=request_id,
        tool_name=tool_name,
        summary=summary,
        warnings=warnings or [],
        errors=errors or [],
        next_suggestions=next_suggestions or [],
        **extra,
    )
    return payload


def success_result(
    *, request_id: str, tool_name: str, summary: str, warnings: list[str] | None = None, **extra: Any
) -> CommonToolResult:
    return _result_payload(
        status="success",
        request_id=request_id,
        tool_name=tool_name,
        summary=summary,
        warnings=warnings,
        **extra,
    )


def partial_success_result(
    *,
    request_id: str,
    tool_name: str,
    summary: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    **extra: Any,
) -> CommonToolResult:
    return _result_payload(
        status="partial_success",
        request_id=request_id,
        tool_name=tool_name,
        summary=summary,
        warnings=warnings,
        errors=errors,
        **extra,
    )


def failed_result(
    *,
    request_id: str,
    tool_name: str,
    summary: str,
    errors: list[str],
    warnings: list[str] | None = None,
    **extra: Any,
) -> CommonToolResult:
    return _result_payload(
        status="failed",
        request_id=request_id,
        tool_name=tool_name,
        summary=summary,
        warnings=warnings,
        errors=errors,
        **extra,
    )
