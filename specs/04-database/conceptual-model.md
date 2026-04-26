# Conceptual Data Model

```mermaid
erDiagram
    PROJECTS ||--o{ ENTITIES : contains
    PROJECTS ||--o{ OPERATIONS : records
    PROJECTS ||--o{ SNAPSHOTS : owns
    PROJECTS ||--o{ EXPORT_RECORDS : produces
    PROJECTS ||--o{ QA_REPORTS : stores
    OPERATIONS ||--o{ QA_REPORTS : generates
    SNAPSHOTS ||--o{ OPERATIONS : precedes
    ENTITIES ||--o{ QA_REPORTS : evaluated_for
    ENTITIES ||--o{ EXPORT_RECORDS : exported_from

    PROJECTS {
        text project_id PK
        text name
        text blend_file_path
        text active_scene_name
        text status
    }
    ENTITIES {
        text entity_id PK
        text project_id FK
        text entity_type
        text name
        text spec_json
    }
    OPERATIONS {
        text operation_id PK
        text project_id FK
        text tool_name
        text status
        text input_json
        text output_json
    }
    SNAPSHOTS {
        text snapshot_id PK
        text project_id FK
        text reason
        text snapshot_path
        text source_operation_id
    }
    QA_REPORTS {
        text qa_report_id PK
        text project_id FK
        text entity_id FK
        text source_operation_id FK
        text severity_summary
    }
    EXPORT_RECORDS {
        text export_id PK
        text project_id FK
        text entity_id FK
        text format
        text output_path
    }
```

## Description

The schema separates project ownership, entity metadata, operation history, reversible snapshots, QA outputs, and export records. This keeps geometry in files while still making revision history queryable.