# Table: qa_reports

## Purpose

Stores machine-readable quality inspection outputs.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| qa_report_id | TEXT | PK, NOT NULL | Stable QA report identifier |
| project_id | TEXT | FK, NOT NULL | Parent project |
| entity_id | TEXT | FK, NULL | Related asset, scene, or world |
| source_operation_id | TEXT | FK, NULL | Operation that produced the report |
| report_type | TEXT | NOT NULL | scene, mesh, material, scale, naming, export_readiness |
| severity_summary | TEXT | NOT NULL | none, info, warning, error, critical |
| findings_json | TEXT | NOT NULL | Structured findings payload |
| generated_at | TEXT | NOT NULL | UTC timestamp |

## Indexes

- INDEX on project_id, generated_at DESC
- INDEX on project_id, report_type, severity_summary
- INDEX on entity_id, generated_at DESC

## Integrity Rules

- findings_json must be valid JSON and include at least one findings array, even if empty.