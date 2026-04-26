# Physical Model

## Engine Configuration

- SQLite 3 in WAL mode
- foreign_keys=ON
- busy_timeout=5000 ms
- synchronous=NORMAL for balanced durability and performance
- journal_size_limit configured to prevent unbounded WAL growth

## File Placement

- Metadata DB path: workspace root plus /.system/metadata.sqlite3
- Snapshot payloads: workspace root plus /snapshots/{project_id}/
- Renders: workspace root plus /renders/{project_id}/
- Exports: workspace root plus /exports/{project_id}/

## Capacity Assumptions

- Fewer than 100 active projects per workstation
- Fewer than 1,000,000 operation rows per workstation before archival
- Low concurrent writer count because the MCP server serializes writes

## Archival Strategy

- Retain full operation history for the latest 90 days by default
- Archive older operation rows to compressed JSONL bundles if local metadata size becomes excessive
- Retain snapshot metadata even if payload pruning removes older payloads