# Dependency Inventory

| Dependency | Role | License | Security and Maintenance Notes |
| --- | --- | --- | --- |
| Python 3.12 | Primary runtime | PSF | Long-lived stable ecosystem and first-class support for MCP SDK and Blender-adjacent tooling. |
| Blender 5.1 | 3D runtime | GPL-compatible Blender terms | Baseline runtime for bpy, geometry nodes, rendering, and export. |
| mcp | Official MCP protocol SDK | MIT | Active repository, recent releases, supports stdio and Streamable HTTP. |
| pydantic v2 | Input/output validation | MIT | Strong schema generation and validation ergonomics. |
| SQLAlchemy 2 | Persistence abstraction | MIT | Mature Python data-access layer and good fit for future migration away from SQLite. |
| Alembic | Schema migration | MIT | Standard SQLAlchemy migration companion. |
| Pillow | Optional preview and image post-processing helpers | HPND-like PIL license | Mature and widely used for lightweight image operations. |

## Dependency Rules

- Avoid Blender-side dependencies that require complex native packaging unless they deliver substantial value.
- Keep the Blender controller dependency surface smaller than the server dependency surface.
- Pin versions for all protocol-facing and persistence-facing libraries.
- Review dependency updates alongside Blender compatibility testing.