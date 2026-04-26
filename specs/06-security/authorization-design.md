# Authorization Design

## Model

Use role-based authorization with destructive-operation gates.

## Roles

- Viewer
- Editor
- Destructive Editor
- Operator

## Policy Examples

- `inspect_scene` is allowed to Viewer.
- `create_model` requires Editor.
- `delete_objects` requires Destructive Editor or an explicit confirmation policy outcome.
- `set_allowed_directories` is Operator-only and not exposed as a normal creative tool.

## Enforcement Point

Authorization is enforced in the MCP server before controller dispatch.