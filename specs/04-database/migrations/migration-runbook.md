# Migration Runbook

## Standard Procedure

1. Back up the SQLite database file.
2. Verify no active mutating jobs are running.
3. Run pending Alembic migrations.
4. Run schema verification queries.
5. Start the MCP server and perform a smoke test.

## Rollback Procedure

1. Stop the MCP server.
2. Restore the previous SQLite database backup.
3. Restart the MCP server with the matching application version.

## Smoke Test Checklist

- Open a project
- Create a snapshot
- Run a non-destructive tool
- Persist an operation row
- Generate a QA report
- Export a lightweight artifact