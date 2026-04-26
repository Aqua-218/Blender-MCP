# Final Technology Stack

## Runtime and Language

- Python 3.12
- uv for environment and dependency management
- Blender 5.1 runtime baseline

## MCP Layer

- Official MCP Python SDK
- FastMCP for tool registration, structured output, progress, and transport handling
- stdio as the default transport
- Streamable HTTP as optional hosted transport

## Validation and Schemas

- Pydantic v2 models for input/output contracts
- JSON Schema generated from model definitions for shared contract publication

## Persistence

- SQLite database in WAL mode for metadata
- Filesystem artifact store under workspace roots for projects, renders, exports, snapshots, and logs

## Bridge and Messaging

- Localhost-only newline-delimited JSON bridge
- Per-session shared secret
- Correlation IDs, progress messages, heartbeat messages, and explicit cancellation envelopes

## Rendering and Export

- Blender native render engines and exporters
- glTF/GLB as the default real-time export target
- FBX as a secondary integration target with explicit limitations surfaced to the client

## Testing and Tooling

- pytest for server and metadata unit tests
- Blender-backed integration tests for controller workflows
- JSON fixture snapshots for schema contract stability

## Versioning Policy

- Semantic versioning for the MCP server package
- Tool catalog versions tracked in metadata and release notes
- Blender compatibility matrix documented per release line