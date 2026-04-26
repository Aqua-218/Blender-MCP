from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic_core import PydanticUndefined

from mcp_server.models.common import CommonToolRequest, CommonToolResult
from mcp_server.models.domain import (
    AssetSpec,
    ExportRecord,
    OperationLog,
    PartSpec,
    QAReport,
    SceneSpec,
    SnapshotMetadata,
    WorldSpec,
)

SCHEMA_MODELS = {
    "common-request.schema.json": CommonToolRequest,
    "common-result.schema.json": CommonToolResult,
    "asset-spec.schema.json": AssetSpec,
    "scene-spec.schema.json": SceneSpec,
    "world-spec.schema.json": WorldSpec,
    "operation-log.schema.json": OperationLog,
    "part-spec.schema.json": PartSpec,
    "qa-report.schema.json": QAReport,
    "snapshot-metadata.schema.json": SnapshotMetadata,
    "export-record.schema.json": ExportRecord,
}

SCHEMA_ID_PREFIX = "urn:blender-mcp:schema:"

PUBLIC_SCHEMA_METADATA = {
    "common-request.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}common-request",
        "title": "CommonToolRequest",
    },
    "common-result.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}common-result",
        "title": "CommonToolResult",
    },
    "asset-spec.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}asset-spec",
        "title": "AssetSpec",
    },
    "scene-spec.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}scene-spec",
        "title": "SceneSpec",
    },
    "world-spec.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}world-spec",
        "title": "WorldSpec",
    },
    "operation-log.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}operation-log",
        "title": "OperationLog",
    },
    "part-spec.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}part-spec",
        "title": "PartSpec",
    },
    "qa-report.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}qa-report",
        "title": "QAReport",
    },
    "snapshot-metadata.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}snapshot-metadata",
        "title": "SnapshotMetadata",
    },
    "export-record.schema.json": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_ID_PREFIX}export-record",
        "title": "ExportRecord",
    },
}

SPEC_SCHEMA_DIR = Path("specs/05-api/schemas")
GENERATED_SCHEMA_DIR = Path("generated_schemas")


def _canonicalize(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _strip_titles(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "title":
                continue
            cleaned[key] = _strip_titles(value)
        return cleaned
    if isinstance(payload, list):
        return [_strip_titles(item) for item in payload]
    return payload


def _strip_nested_additional_properties(payload: Any, *, root: bool = True) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if not root and key == "additionalProperties" and value is True:
                continue
            cleaned[key] = _strip_nested_additional_properties(value, root=False)
        return cleaned
    if isinstance(payload, list):
        return [_strip_nested_additional_properties(item, root=False) for item in payload]
    return payload


def _inject_field_defaults(model: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return payload
    for field_name, field_info in model.model_fields.items():
        property_schema = properties.get(field_name)
        if not isinstance(property_schema, dict):
            continue
        if "default" in property_schema:
            continue
        if field_info.default_factory is not None:
            default_value = field_info.default_factory()
            if isinstance(default_value, (list, dict)):
                property_schema["default"] = default_value
        elif field_info.default not in (None, PydanticUndefined):
            property_schema["default"] = field_info.default
    return payload


def _inject_public_metadata(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    if filename not in PUBLIC_SCHEMA_METADATA:
        return payload
    metadata = PUBLIC_SCHEMA_METADATA[filename]
    merged = dict(metadata)
    merged.update(payload)
    merged["$schema"] = metadata["$schema"]
    merged["$id"] = metadata["$id"]
    merged["title"] = metadata["title"]
    return merged


def _schema_for(filename: str, model: type[Any], base_dir: Path | None = None) -> dict[str, Any]:
    payload = model.model_json_schema()
    payload = _strip_titles(payload)
    payload = _inject_field_defaults(model, payload)
    payload = _strip_nested_additional_properties(payload)
    payload = _inject_public_metadata(filename, payload)
    return payload


def _schema_dir_listing(root: Path, relative_dir: Path) -> set[str]:
    target_dir = root / relative_dir
    if not target_dir.exists():
        return set()
    return {path.name for path in target_dir.glob("*.schema.json") if path.is_file()}


def export_schemas(base_dir: Path | None = None) -> list[Path]:
    root = (base_dir or Path.cwd()).resolve()
    output_dir = root / GENERATED_SCHEMA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        payload = _schema_for(filename, model, root)
        target = output_dir / filename
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(target)
    return written


def check_schema_drift(base_dir: Path | None = None) -> tuple[bool, list[str]]:
    root = (base_dir or Path.cwd()).resolve()
    mismatches: list[str] = []
    expected = set(SCHEMA_MODELS)
    for label, relative_dir in (("spec", SPEC_SCHEMA_DIR), ("generated", GENERATED_SCHEMA_DIR)):
        actual = _schema_dir_listing(root, relative_dir)
        for missing in sorted(expected - actual):
            mismatches.append(f"missing {label} schema: {missing}")
        for unexpected in sorted(actual - expected):
            mismatches.append(f"unexpected {label} schema: {unexpected}")
    for filename, model in SCHEMA_MODELS.items():
        generated = _canonicalize(_schema_for(filename, model, root))
        for label, relative_dir in (("spec", SPEC_SCHEMA_DIR), ("generated", GENERATED_SCHEMA_DIR)):
            schema_path = root / relative_dir / filename
            if not schema_path.exists():
                continue
            schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
            schema = _canonicalize(schema_payload)
            if generated != schema:
                mismatches.append(f"{label}:{filename}")
    return (not mismatches, mismatches)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "export"
    if command == "export":
        written = export_schemas()
        for item in written:
            print(item)
        return 0
    if command == "check":
        ok, mismatches = check_schema_drift()
        if ok:
            print("schema drift check passed")
            return 0
        for mismatch in mismatches:
            print(f"schema drift: {mismatch}")
        return 1
    raise SystemExit(f"Unknown schema command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
