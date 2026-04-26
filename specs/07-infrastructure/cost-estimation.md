# Cost Estimation

## MVP Local Cost Model

- Software licensing: zero incremental cost for Blender, Python, SQLite, and the official MCP SDK
- Workstation requirement: existing user workstation with at least 32 GB RAM recommended
- Backup storage: optional cloud backup or NAS cost, typically low double-digit USD per month depending on artifact volume

## Hosted Pilot Cost Model

- One small application node for MCP HTTP transport
- One Blender worker node sized for CPU-heavy generation and preview rendering
- Optional GPU cost only if the chosen render path or performance target requires it
- Shared object storage for artifacts and backups

## Cost Controls

- Local-first deployment as the default
- Preview-first workflow to avoid expensive final renders during iteration
- Queue-based heavy job execution
- Snapshot retention policies to limit storage growth