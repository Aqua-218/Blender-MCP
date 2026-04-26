# API Design Overview

## API Style Selection

The primary API is MCP tool invocation, not REST.

Why MCP is the correct primary interface:

- The target clients are MCP-capable LLM applications.
- The interaction model is tool-oriented rather than resource-CRUD oriented.
- Progress, structured output, prompts, and resources map naturally to MCP.

## Design Rules

- Tools use flat snake_case names for maximum client compatibility.
- Inputs are strict JSON-serializable objects validated against generated schemas.
- Outputs always include a structured envelope that preserves created, modified, and deleted identifiers plus warnings and errors.
- Long-running tools support progress updates.
- Tool names are stable once released; new fields are added backward-compatibly.

## API Surface Families

- Project tools
- Object tools
- Geometry tools
- Model generation tools
- Category-specific generation tools
- Scene tools
- World tools
- Modifier tools
- Geometry Nodes tools
- Material tools
- Texture and UV tools
- Lighting tools
- Camera tools
- Render tools
- Inspection and QA tools
- Repair and optimization tools
- Animation and rigging tools
- Import and export tools
- History tools

## Supporting Documents

- [mcp-tool-catalog.md](mcp-tool-catalog.md)
- [authentication.md](authentication.md)
- [authorization.md](authorization.md)
- [error-handling.md](error-handling.md)
- [rate-limiting.md](rate-limiting.md)
- [versioning.md](versioning.md)
- [schemas/common-request.schema.json](schemas/common-request.schema.json)
- [schemas/common-result.schema.json](schemas/common-result.schema.json)