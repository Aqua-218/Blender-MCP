# Table: export_records

## Purpose

Stores export attempts and outputs.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| export_id | TEXT | PK, NOT NULL | Stable export identifier |
| project_id | TEXT | FK, NOT NULL | Parent project |
| entity_id | TEXT | FK, NULL | Exported entity if applicable |
| source_operation_id | TEXT | FK, NULL | Operation that requested export |
| format | TEXT | NOT NULL | glb, gltf, fbx, obj, usd, usdz, stl, blend |
| preset | TEXT | NOT NULL | game, web, render, concept, print, archive |
| output_path | TEXT | NOT NULL | Export artifact path |
| success_flag | INTEGER | NOT NULL | 0 false, 1 true |
| warnings_json | TEXT | NOT NULL DEFAULT '[]' | Format-specific warnings |
| exported_at | TEXT | NOT NULL | UTC timestamp |

## Indexes

- INDEX on project_id, exported_at DESC
- INDEX on project_id, format, exported_at DESC
- INDEX on entity_id, exported_at DESC

## Integrity Rules

- output_path must reside under the workspace export root.
- format must be one of the supported export targets.