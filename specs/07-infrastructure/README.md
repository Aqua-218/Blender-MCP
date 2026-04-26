# Infrastructure Overview

## Deployment Model

The product is local-first.

Primary deployment:

- MCP server running on the user workstation
- Blender runtime running on the same workstation
- SQLite and artifact files stored locally

Optional later deployment:

- Hosted MCP server
- Dedicated Blender worker node(s)
- Shared artifact storage
- Client/server metadata store

## Design Priorities

- Simple local setup for MVP
- Safe defaults for desktop use
- Explicit growth path to hosted operation

## Documents

- [cloud-architecture.md](cloud-architecture.md)
- [ci-cd/pipeline-design.md](ci-cd/pipeline-design.md)
- [ci-cd/environments.md](ci-cd/environments.md)
- [ci-cd/deployment-strategy.md](ci-cd/deployment-strategy.md)
- [observability/metrics.md](observability/metrics.md)
- [observability/logging.md](observability/logging.md)
- [observability/sli-slo.md](observability/sli-slo.md)
- [cost-estimation.md](cost-estimation.md)
- [disaster-recovery.md](disaster-recovery.md)