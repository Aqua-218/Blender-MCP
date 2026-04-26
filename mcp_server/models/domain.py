from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mcp_server.models.common import QualityName

AssetCategory = Literal[
    "prop",
    "furniture",
    "building",
    "vehicle",
    "mech",
    "environment",
    "character",
    "world",
    "scene",
    "other",
]
AssetPurpose = Literal["game", "render", "concept", "web", "print", "prototype", "other"]
SnapshotReason = Literal["pre_destructive_change", "manual", "milestone", "rollback_target"]


class PartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_id: str
    name: str
    kind: str
    parent_part_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    detail_level: str = "base"
    symmetrical_with: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    name: str
    category: AssetCategory
    theme: str | None = None
    style: str | None = None
    purpose: AssetPurpose
    target_quality: QualityName
    polygon_budget: int | None = Field(default=None, ge=0)
    seed: int | None = Field(default=None, ge=0)
    constraints: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)
    parts: list[PartSpec] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    name: str
    theme: str | None = None
    style: str | None = None
    assets: list[str] = Field(default_factory=list)
    lighting: dict[str, Any] = Field(default_factory=dict)
    cameras: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)
    quality_target: QualityName


class WorldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_id: str
    name: str
    size_meters: list[Annotated[float, Field(ge=0)]] = Field(min_length=2, max_length=2)
    theme: str | None = None
    style: str | None = None
    biomes: list[str] = Field(default_factory=list)
    regions: list[dict[str, Any]] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    roads: list[dict[str, Any]] = Field(default_factory=list)
    water_systems: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    seed: int | None = Field(default=None, ge=0)


class OperationLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    timestamp: str
    tool_name: str
    user_instruction: str | None = None
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_summary: str
    created_object_ids: list[str] = Field(default_factory=list)
    modified_object_ids: list[str] = Field(default_factory=list)
    deleted_object_ids: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class QAReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qa_report_id: str
    project_id: str
    entity_id: str | None = None
    source_operation_id: str | None = None
    created_at: datetime
    severity_summary: dict[str, int] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    blocked_export_formats: list[str] = Field(default_factory=list)
    summary: str


class SnapshotMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    project_id: str
    source_operation_id: str | None = None
    reason: SnapshotReason
    snapshot_path: str
    diff_summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ExportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_id: str
    project_id: str
    entity_id: str | None = None
    format: str
    output_path: str
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
