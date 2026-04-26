# Architecture Overview

## Selected Architecture Style

The selected architecture is a hybrid of:

- Modular monolith for the MCP server
- Persistent single-runtime controller for Blender execution
- Local RPC bridge between the MCP server and Blender runtime
- File-based artifact storage plus SQLite metadata storage

This design is preferred over a microservice split because the product is fundamentally workstation-local, stateful, latency-sensitive, and Blender-bound.

## Architecture Principles

1. Keep Blender state in one place.
2. Keep policy and validation outside Blender.
3. Preserve editability until export or explicit bake.
4. Prefer deterministic tool contracts over prompt-only behavior.
5. Make every high-impact operation observable and reversible.

## Core Runtime Shape

- The MCP server owns tool discovery, schema validation, safety policy, routing, logging, and metadata persistence.
- The Blender controller owns Blender Python API mutations, evaluated scene state, domain modules, rendering, export, and inspection execution.
- The bridge between them is authenticated, local-only, and request-scoped.

## State Ownership

| State | Owner |
| --- | --- |
| MCP tool schemas | MCP server |
| Policy configuration | MCP server |
| Request logs and operation history | MCP server + SQLite |
| Active .blend scene state | Blender runtime |
| Generated artifacts | Workspace filesystem |
| Snapshot index | SQLite |
| Snapshot payloads | Workspace filesystem |
| QA report records | SQLite + artifact files |

## Key Design Consequences

- A crash in Blender should not corrupt MCP tool discovery or metadata history.
- A schema or policy bug in the MCP server should not require modifying Blender execution modules.
- Local revisions can be reasoned about because target resolution, snapshotting, and diffing are outside the opaque mesh-edit operation.

## Source Support

- MCP supports stdio and Streamable HTTP as standard transports.
- The official MCP Python SDK supports typed tools, structured output, progress, lifespan-managed dependencies, stdio, and Streamable HTTP.
- Blender background mode and Python scripting are first-class supported execution models.
- Blender-as-module is possible but not the default portable distribution and still has a single active blend constraint.

For source URLs, see [../README.md](../README.md).