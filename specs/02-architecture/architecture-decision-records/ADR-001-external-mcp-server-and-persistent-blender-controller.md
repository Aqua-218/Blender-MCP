# ADR-001: External MCP Server and Persistent Blender Controller

## Status

Accepted

## Context

The product must support iterative editing, previews, local revisions, snapshots, QA, and export from multiple MCP-capable clients. Blender scene state is large, mutable, and expensive to reconstruct for every tool call.

Alternative architectures considered:

- Run the MCP server inside Blender
- Launch Blender in headless mode for every request
- Use Blender as a Python module inside the MCP server process

## Decision

Implement the MCP server as an external Python process and keep Blender control in a persistent Blender runtime with a dedicated controller bridge.

The MCP server will:

- expose MCP tools
- validate inputs
- enforce policy
- manage history, snapshots, and metadata
- orchestrate requests

The Blender controller will:

- execute Blender Python API operations
- maintain live project state
- run domain modules for modeling, rendering, QA, and export

## Consequences

### Positive

- Blender state survives across iterative edits.
- The server can recover, log, and fail independently of Blender.
- Schema validation and safety policy stay outside the DCC runtime.
- Multi-client support is easier because the server boundary is stable.

### Negative

- A controller bridge must be implemented and secured.
- Cross-process coordination adds operational complexity.
- Request cancellation and timeout handling must be propagated across the bridge.

### Risks

- Blender and server state can drift if a bridge response is lost.
- Blender crashes can leave the project session unavailable until restart.

## Alternatives Considered

### Alternative 1: MCP Server Inside Blender

- Description: Run the MCP server as a Blender add-on or embedded script.
- Pros: No cross-process bridge; direct access to bpy.
- Cons: Tighter coupling, harder transport management, harder recovery after Blender instability, and poorer separation of policy from execution.
- Rejection Reason: The failure domain becomes too large and transport support becomes less flexible.

### Alternative 2: Spawn Blender Per Tool Call

- Description: Use background-mode Blender for every request.
- Pros: Simple isolation and no long-lived runtime management.
- Cons: High latency, lost iterative context, costly startup, and poor review loop ergonomics.
- Rejection Reason: The design objective is interactive iterative creation, not stateless batch conversion.

### Alternative 3: Use Blender as a Python Module in the MCP Process

- Description: Import bpy directly in the server runtime.
- Pros: Fewer moving parts and simple in-process calls.
- Cons: Distribution is less portable, command-line capabilities differ, and single-runtime state still limits concurrency.
- Rejection Reason: Useful for niche deployments, but not the most portable default for desktop MCP clients.