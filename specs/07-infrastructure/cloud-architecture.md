# Runtime Architecture

## MVP Local Topology

- One local MCP server process
- One local Blender runtime process
- One local SQLite metadata file
- One local workspace root for projects, renders, exports, logs, and snapshots

## Hosted Pilot Topology

- One MCP application node
- One or more Blender worker nodes
- Shared object storage for artifacts
- Client/server database for metadata
- Reverse proxy with TLS for Streamable HTTP

## Managed vs Self-Hosted Decision

- MVP: self-contained local deployment
- Hosted pilot: managed TLS and storage where practical, self-managed Blender workers because Blender execution is the specialized component

## Region Strategy

- MVP local: not applicable
- Hosted pilot: single region, single availability zone acceptable for pre-production; multi-zone only after multi-client demand is validated