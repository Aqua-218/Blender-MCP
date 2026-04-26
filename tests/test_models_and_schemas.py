from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from mcp_server.models.common import (
    CommonToolRequest,
    failed_result,
    partial_success_result,
    success_result,
)
from mcp_server.schema_tools import check_schema_drift, export_schemas


def test_common_tool_request_defaults() -> None:
    payload = CommonToolRequest(request_id="req-1")

    assert payload.quality == "standard"
    assert payload.target_ids == []
    assert payload.safe_mode is True


def test_result_helpers_build_consistent_statuses() -> None:
    success = success_result(request_id="req-1", tool_name="ping", summary="ok")
    partial = partial_success_result(
        request_id="req-2",
        tool_name="render_preview",
        summary="warning",
        warnings=["slow"],
        errors=["retryable"],
    )
    failed = failed_result(
        request_id="req-3",
        tool_name="delete_object",
        summary="blocked",
        errors=["snapshot_required"],
    )

    assert success.status == "success"
    assert partial.status == "partial_success"
    assert partial.errors == ["retryable"]
    assert failed.status == "failed"
    assert failed.errors == ["snapshot_required"]


@pytest.mark.schema
def test_schema_export_writes_generated_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "generated_schemas").mkdir(exist_ok=True)

    written = export_schemas(tmp_path)

    assert written
    assert all(path.exists() for path in written)
    asset_schema = json.loads((tmp_path / "generated_schemas" / "asset-spec.schema.json").read_text())
    assert asset_schema["properties"]["parts"]["items"] == {"$ref": "#/$defs/PartSpec"}


@pytest.mark.schema
def test_schema_drift_check_against_spec_source_of_truth() -> None:
    ok, mismatches = check_schema_drift(Path.cwd())

    assert ok, mismatches


@pytest.mark.schema
def test_schema_drift_fails_when_public_counterpart_is_missing(tmp_path: Path) -> None:
    export_schemas(tmp_path)
    spec_dir = tmp_path / "specs" / "05-api" / "schemas"
    spec_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        tmp_path / "generated_schemas" / "common-request.schema.json",
        spec_dir / "common-request.schema.json",
    )

    ok, mismatches = check_schema_drift(tmp_path)

    assert not ok
    assert "missing spec schema: asset-spec.schema.json" in mismatches
