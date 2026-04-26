# Integration Testing

## Scope

Integration tests exercise the real MCP server, the real controller bridge, and a real Blender runtime where feasible.

## Required Scenarios

- Start MCP server and register tools
- Launch or attach Blender controller
- Create project and save project
- Create primitive and apply material
- Render preview and persist result metadata
- Generate QA report
- Export GLB and record export metadata

## Failure Scenarios

- Invalid path rejected before Blender call
- Controller unavailable error returned correctly
- Timeout handling and partial result behavior