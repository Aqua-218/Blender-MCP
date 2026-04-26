# MCP Tool Catalog

## Naming Strategy

- Tool names remain flat, for example `create_project` or `inspect_scene`.
- Parameters carry scope and targeting information; the name should describe the action, not every specialization.
- Tool titles may be more human-friendly in MCP metadata, but `name` remains stable and machine-oriented.

## Capability Tiers

| Tier | Description |
| --- | --- |
| Core | Required for MVP and baseline client compatibility |
| Advanced | Required for post-MVP scene, world, and optimization workflows |
| Experimental | Exposed only behind feature flags and lower trust defaults |

## Execution Classes

| Class | Examples | Expectations |
| --- | --- | --- |
| Read-only query | `get_project_info`, `list_objects`, `inspect_scene` | No scene mutation |
| Safe mutation | `transform_object`, `create_material`, `set_camera` | Localized mutation with normal policy checks |
| Destructive mutation | `delete_objects`, `apply_modifier`, `rollback_to_snapshot` | Confirmation or destructive policy required |
| Long-running job | `create_world`, `render_final`, `export_scene` | Progress events, timeout policy, and partial-result handling |

## Tool Families and Tiers

| Family | Representative Tools | Tier |
| --- | --- | --- |
| Project | `create_project`, `open_project`, `save_project`, `create_snapshot` | Core |
| Object | `list_objects`, `find_objects`, `transform_object`, `tag_object` | Core |
| Geometry | `create_primitive`, `create_custom_mesh`, `edit_mesh` | Core |
| Model Generation | `create_model`, `generate_parts`, `replace_part`, `increase_detail` | Core |
| Category-Specific Generation | `create_hard_surface_model`, `create_building`, `create_furniture` | Core |
| Scene | `create_scene`, `place_asset`, `scatter_assets`, `create_composition` | Advanced |
| World | `create_world`, `generate_terrain`, `generate_biomes`, `detail_region` | Advanced |
| Modifiers | `add_modifier`, `set_modifier`, `apply_boolean`, `apply_decimate` | Core |
| Geometry Nodes | `create_geometry_nodes`, `create_scatter_node_setup` | Advanced |
| Materials | `create_material`, `create_pbr_material`, `restyle_materials` | Core |
| Texture and UV | `unwrap_uv`, `apply_texture`, `bake_texture` | Advanced |
| Lighting | `create_light`, `apply_lighting_preset`, `auto_light_subject` | Core |
| Camera | `create_camera`, `frame_object`, `create_multiview_cameras` | Core |
| Render | `render_preview`, `render_multiview`, `render_final` | Core |
| Inspection and QA | `inspect_scene`, `inspect_mesh`, `generate_qa_report` | Core |
| Repair and Optimization | `fix_mesh`, `optimize_polycount`, `generate_lod` | Advanced |
| Animation and Rigging | `create_keyframe_animation`, `create_simple_rig` | Experimental |
| Import and Export | `import_asset`, `export_asset`, `export_scene`, `export_world` | Core |
| History | `get_generation_history`, `compare_snapshots`, `rollback_to_snapshot` | Advanced |

## Tool Contract Rules

- Every tool must declare its input schema.
- Every mutating tool must declare its output schema.
- Every result must include a human-readable summary string.
- Every mutating tool must return explicit target-change identifiers whenever possible.
- Every tool must set `status` to one of `success`, `partial_success`, or `failed`.

## Prompt and Resource Support

The server may expose MCP prompts and resources in addition to tools:

- Resources: project metadata, current scene summary, recent QA report, tool policy overview
- Prompts: structured planning prompts for asset generation, revision, QA interpretation, and export-prep review

These are helpful but secondary; tools remain the primary contract.