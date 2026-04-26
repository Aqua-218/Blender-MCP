# Client Config Examples

These examples are ready to copy into a desktop MCP client that supports stdio-launched servers.

Files in this directory:

- `claude-desktop.mock.json`: deterministic local smoke setup using the mock controller runtime
- `claude-desktop.blender.json`: Blender-backed runtime setup for a real local Blender install

Before using either template, replace every `/absolute/path/to/blender-mcp` placeholder with the actual repository path on your machine.

For the Blender-backed template, also make sure the `BLENDER_MCP_BLENDER_BINARY` value points to an installed Blender executable.