# Backup and Recovery

## Backup Strategy

- Back up the SQLite database daily when the workstation is active.
- Create a metadata backup immediately before schema migrations.
- Store snapshot payloads and export artifacts on the same backup policy as the workspace.

## Recovery Objectives

- Metadata RPO: 24 hours by default for local-only setups
- Metadata RTO: 30 minutes for workstation restoration

## Restore Procedure

1. Restore the workspace root.
2. Restore metadata.sqlite3.
3. Verify that project blend_file_path values resolve correctly.
4. Run a project-open smoke test.