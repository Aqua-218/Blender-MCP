# Infrastructure Security

## Local Deployment

- Bind Streamable HTTP to localhost by default.
- Run the MCP server under a non-privileged user account.
- Store artifacts inside a dedicated workspace root.

## Hosted Deployment

- Require TLS termination in front of Streamable HTTP.
- Validate Origin headers for browser-facing endpoints.
- Use token-based authentication.
- Isolate Blender workers from the public internet.

## Controller Bridge

- Bind to localhost only.
- Authenticate every request.
- Use heartbeat and idle-timeout mechanisms to clean up abandoned sessions.