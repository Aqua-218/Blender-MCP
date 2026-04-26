# Technology Selection Overview

## Selected Stack Summary

- Language: Python 3.12 for the MCP server and controller-side support code
- MCP framework: official MCP Python SDK with FastMCP surface
- Validation: Pydantic v2 models plus generated JSON Schema
- Metadata storage: SQLite with WAL mode
- Migration tooling: Alembic
- Logging: structured JSON logging using standard logging adapters
- Testing: pytest plus integration harnesses that exercise a real Blender runtime

## Why This Stack

- Python matches Blender’s native automation language.
- The official MCP Python SDK already supports typed tools, structured output, progress, lifespan-managed dependencies, stdio, and Streamable HTTP.
- SQLite is a strong fit for application-local metadata.
- Generated JSON Schema reduces ambiguity for LLM-driven tool invocation.

## Evaluation Documents

- [evaluation-matrices/server-runtime-evaluation.md](evaluation-matrices/server-runtime-evaluation.md)
- [evaluation-matrices/blender-execution-model-evaluation.md](evaluation-matrices/blender-execution-model-evaluation.md)
- [evaluation-matrices/metadata-store-evaluation.md](evaluation-matrices/metadata-store-evaluation.md)
- [tech-stack.md](tech-stack.md)
- [dependency-inventory.md](dependency-inventory.md)