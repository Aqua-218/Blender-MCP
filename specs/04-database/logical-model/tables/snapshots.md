# Table: snapshots

## Purpose

Stores reversible project checkpoint metadata.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| snapshot_id | TEXT | PK, NOT NULL | Stable snapshot identifier |
| project_id | TEXT | FK, NOT NULL | Parent project |
| source_operation_id | TEXT | FK, NULL | Operation that triggered the snapshot |
| reason | TEXT | NOT NULL | pre_destructive_change, manual, milestone, or rollback_target |
| snapshot_path | TEXT | NOT NULL | Filesystem path for snapshot payload |
| diff_summary_json | TEXT | NOT NULL DEFAULT '{}' | Optional diff summary |
| created_at | TEXT | NOT NULL | UTC timestamp |

## Indexes

- INDEX on project_id, created_at DESC
- INDEX on source_operation_id

## Integrity Rules

- snapshot_path must reside under the project workspace root.