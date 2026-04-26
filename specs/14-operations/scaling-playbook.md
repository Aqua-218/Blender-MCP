# Scaling Playbook

## When to Scale Beyond MVP Local Mode

- More than one active human user per deployment
- Need for remote browser clients
- Need for many concurrent heavy render or world-generation jobs

## First Scaling Steps

1. Move from stdio-only to optional Streamable HTTP.
2. Separate MCP server from Blender worker runtime.
3. Replace SQLite with a client/server database.
4. Introduce shared artifact storage.

## Do Not Scale Prematurely

- Do not introduce microservices before there is evidence of multi-user or hosted demand.
- Do not split the controller into many services while Blender state is still single-runtime.