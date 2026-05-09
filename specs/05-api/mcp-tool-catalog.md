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
| Batch Ops | `preview_batch_targets`, `batch_tag_objects`, `batch_rename_objects`, `batch_assign_collection`, `batch_transform_offsets`, `batch_apply_material`, `batch_add_modifier`, `batch_duplicate_objects`, `batch_export_assets`, `batch_import_assets` | Advanced |
| Collections | `list_collections`, `create_collection`, `rename_collection`, `delete_collection`, `link_objects_to_collection`, `unlink_objects_from_collection`, `set_collection_visibility` | Core |
| Geometry | `create_primitive`, `create_custom_mesh`, `edit_mesh` | Core |
| Model Generation | `create_model`, `generate_parts`, `replace_part`, `increase_detail` | Core |
| Category-Specific Generation | `create_hard_surface_model`, `create_building`, `create_furniture` | Core |
| Scene | `create_scene`, `place_asset`, `scatter_assets`, `create_composition` | Advanced |
| World | `create_world`, `create_world_preset`, `generate_terrain`, `generate_biomes`, `generate_mountain_range`, `create_navigation_markers`, `detail_region`, `validate_world_composition` | Advanced |
| Modifiers | `add_modifier`, `add_bevel_modifier`, `add_mirror_modifier`, `add_array_modifier`, `add_solidify_modifier`, `add_subdivision_modifier`, `add_triangulate_modifier`, `add_weld_modifier`, `add_remesh_modifier`, `add_displace_modifier`, `add_weighted_normal_modifier`, `set_modifier`, `apply_boolean`, `apply_decimate` | Core |
| Geometry Nodes | `create_geometry_nodes`, `create_scatter_node_setup`, `add_noise_displace_nodes`, `add_curve_scatter_nodes`, `add_instance_collection_nodes`, `add_lod_switch_nodes`, `validate_geometry_nodes_setup` | Advanced |
| Materials | `create_material`, `create_pbr_material`, `restyle_materials` | Core |
| Texture and UV | `unwrap_uv`, `list_uv_maps`, `set_uv_density`, `assign_udim_tile`, `create_udim_tile_plan`, `generate_texture_set_manifest`, `plan_texture_bake`, `bake_texture_set`, `create_texture_atlas_manifest`, `create_trim_sheet_manifest`, `validate_uv_layout`, `apply_texture`, `bake_texture` | Advanced |
| Lighting | `create_light`, `create_three_point_lighting`, `create_softbox_lighting`, `create_light_ring`, `aim_lights_at_target` | Core |
| Camera | `create_camera`, `create_shot_camera`, `frame_camera_to_targets`, `create_camera_orbit`, `save_shot_bookmark` | Core |
| Game Prep | `assign_lod_level`, `create_lod_chain`, `create_collision_proxy`, `create_collision_proxy_set`, `create_socket_marker`, `tag_game_export_role`, `validate_game_export_readiness`, `validate_lod_chain`, `plan_game_export_package`, `validate_engine_export_package`, `plan_engine_import_checklist`, `write_game_export_manifest`, `set_engine_export_profile` | Advanced |
| Production Pipeline | `create_game_production_plan`, `create_asset_brief`, `plan_level_streaming`, `validate_production_readiness`, `plan_game_production_package`, `write_game_production_package` | Advanced |
| AAA Orchestrator | `build_game_ready_asset`, `build_environment_kit`, `build_world_blockout`, `run_shipping_readiness_pass` | Advanced |
| AAA Workflows | 520 generated `aaa_*` workflow recipes spanning characters, props, worlds, lighting, materials, VFX, engine integration, QA, release, and localization | Advanced |
| Render | `render_preview`, `render_multiview`, `render_final` | Core |
| Inspection and QA | `inspect_scene`, `inspect_mesh`, `generate_qa_report` | Core |
| Repair and Optimization | `fix_mesh`, `optimize_polycount`, `generate_lod` | Advanced |
| Animation and Rigging | `create_keyframe_animation`, `create_camera_animation`, `create_hinge_animation`, `create_looping_rotation_animation`, `create_simple_rig`, `create_mechanical_rig_preset`, `list_armatures`, `list_animation_tracks`, `validate_animation_rigging` | Experimental |
| Import and Export | `import_asset`, `export_asset`, `export_scene`, `export_world` | Core |
| Asset Library | `register_asset_library_item`, `list_asset_library_items`, `find_asset_library_items`, `create_asset_collection`, `instantiate_asset_library_item`, `validate_asset_library` | Advanced |
| History | `get_generation_history`, `compare_snapshots`, `rollback_to_snapshot` | Advanced |

## Tool Contract Rules

- Every tool must declare its input schema.
- Every mutating tool must declare its output schema.
- Every result must include a human-readable summary string.
- Every mutating tool must return explicit target-change identifiers whenever possible.
- Every tool must set `status` to one of `success`, `partial_success`, or `failed`.
- `delete_collection` deletes only the collection container. Without `force` it requires an empty collection; with `force` it removes collection membership and rehomes child collections without deleting scene objects.

## Prompt and Resource Support

The server may expose MCP prompts and resources in addition to tools:

- Resources: project metadata, current scene summary, recent QA report, tool policy overview
- Prompts: structured planning prompts for asset generation, revision, QA interpretation, and export-prep review

These are helpful but secondary; tools remain the primary contract.
