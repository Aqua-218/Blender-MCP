# Client Config Examples

These example files target desktop MCP clients that launch servers over stdio.

Files in this directory:

- `claude-desktop.mock.json`: deterministic local setup using the mock controller runtime
- `claude-desktop.blender.json`: Blender-backed setup for a local Blender installation

Before using either template:

1. Replace every `/absolute/path/to/blender-mcp` placeholder with the path to your local checkout or virtual environment.
2. Make sure the configured Python executable can import the installed `blender-mcp` package.
3. Set `BLENDER_MCP_WORKSPACE_ROOTS` to a writable workspace path that you trust.

For the Blender-backed template, also set `BLENDER_MCP_BLENDER_BINARY` to a valid Blender executable.

If you install Blender MCP into a dedicated virtual environment, you can point the `command` field at that environment's `blender-mcp-server` entrypoint instead of invoking `python -m mcp_server.main` directly.