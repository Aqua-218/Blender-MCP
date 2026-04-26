# Authentication Design

## Overview

Authentication depends on transport mode.

## Stdio Mode

- Trust boundary: the launching desktop application and the local user session
- No separate end-user token exchange is required
- Security depends on local process launch control and workspace allowlists

## Streamable HTTP Mode

- Require authenticated access for non-localhost deployments
- Prefer OAuth-compatible token verification supported by the official MCP Python SDK
- Validate Origin headers for browser-facing deployments
- Bind to localhost by default for local HTTP mode

## Internal Controller Bridge Authentication

- The MCP server generates a short-lived session secret when starting or attaching to a Blender runtime.
- The Blender controller accepts requests only from local connections presenting the active session secret.
- Secrets rotate when the controller restarts.

## Authentication Outcomes

- Unauthenticated requests are rejected before tool dispatch.
- Authentication context is recorded in operation logs for HTTP-based deployments.