# Table: operations

## Purpose

Stores immutable execution history for all significant tool calls.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| operation_id | TEXT | PK, NOT NULL | Stable operation identifier |
| project_id | TEXT | FK, NOT NULL | Parent project |
| request_id | TEXT | NOT NULL | Correlation identifier from MCP request |
| tool_name | TEXT | NOT NULL | Invoked tool |
| target_entity_id | TEXT | NULL | Optional related entity |
| status | TEXT | NOT NULL | success, partial_success, failed, cancelled |
| user_instruction | TEXT | NULL | Natural-language instruction summary |
| input_json | TEXT | NOT NULL | Validated input envelope |
| output_json | TEXT | NOT NULL | Structured result envelope |
| warnings_json | TEXT | NOT NULL DEFAULT '[]' | Warning list |
| errors_json | TEXT | NOT NULL DEFAULT '[]' | Error list |
| started_at | TEXT | NOT NULL | UTC timestamp |
| completed_at | TEXT | NULL | UTC timestamp |
| duration_ms | INTEGER | NULL | Duration in milliseconds |

## Indexes

- INDEX on project_id, started_at DESC
- INDEX on project_id, tool_name, started_at DESC
- INDEX on request_id UNIQUE

## Integrity Rules

- input_json and output_json must be valid JSON.
- completed_at must be greater than or equal to started_at when present.