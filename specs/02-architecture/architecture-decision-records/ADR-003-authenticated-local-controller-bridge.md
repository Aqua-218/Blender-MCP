# ADR-003: Authenticated Local Controller Bridge

## Status

Accepted

## Context

The MCP server and Blender runtime are separate processes. They need a local request/response bridge with progress, cancellation, and structured error handling. The bridge must not be remotely accessible by default.

## Decision

Use a localhost-only bridge with the following properties:

- bind to 127.0.0.1 by default
- random per-session shared secret or bearer token
- newline-delimited JSON messages for simplicity and debuggability
- one request queue per Blender runtime
- explicit message types for request, progress, result, error, cancel, and heartbeat

## Consequences

### Positive

- Human-readable protocol and easy troubleshooting.
- Minimal dependency burden inside Blender.
- Easy progress forwarding into MCP notifications.

### Negative

- Custom bridge protocol maintenance.
- Manual flow control and backpressure handling.

### Risks

- A malformed or stale connection could leave the MCP server believing Blender work is still active.

## Alternatives Considered

### Alternative 1: gRPC

- Description: Use a typed RPC framework between server and controller.
- Pros: Strong contracts and streaming.
- Cons: Higher dependency and packaging burden inside Blender.
- Rejection Reason: The first implementation should minimize Blender-side operational complexity.

### Alternative 2: Local HTTP API

- Description: Run an HTTP server inside Blender.
- Pros: Familiar debugging model.
- Cons: Larger attack surface and heavier HTTP semantics for workstation-local control.
- Rejection Reason: A private local bridge is sufficient and safer by default.