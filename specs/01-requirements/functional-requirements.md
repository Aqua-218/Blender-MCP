# Functional Requirements

## 9.1 Project Management

- FR-001 Create new project: The system shall create a new Blender project from a named template within an allowlisted output directory, set units, persist metadata, and return project_id, blend_file_path, and status.
- FR-002 Open existing project: The system shall load an existing .blend file from an allowlisted path and return the active project context, warnings, and load status.
- FR-003 Save project: The system shall save the current Blender project in place and report completion status, file path, duration, and warnings.
- FR-004 Save project as: The system shall save the active project to a new path after validating overwrite policy, allowed directory, and extension.
- FR-005 Create version snapshot: The system shall create a reversible snapshot before or after major edits and record the snapshot in project history.
- FR-006 Get project metadata: The system shall return project name, file path, unit settings, object counts, current scene, dirty status, and last-save metadata.

## 9.2 Object Management

- FR-010 List objects: The system shall return all scene objects with stable identifiers, names, types, visibility state, collection membership, and transform summary.
- FR-011 Find objects: The system shall search objects by name, type, tag, collection, material, and spatial range and return all matches deterministically.
- FR-012 Select object: The system shall select one or more target objects and report the resulting active selection set.
- FR-013 Delete object: The system shall delete a specified object only when confirmation requirements are satisfied and log the deletion.
- FR-014 Duplicate object: The system shall duplicate an object or object set while preserving links, materials, and collection placement according to tool options.
- FR-015 Transform object: The system shall update object location, rotation, and scale in object space or world space as specified by parameters.
- FR-016 Rename object: The system shall rename objects while enforcing collision handling and naming-rule policies.
- FR-017 Tag object: The system shall attach management tags to objects for later targeting, QA, and grouping.
- FR-018 Manage collections: The system shall create, move, duplicate, and assign objects across collections without breaking object references.

## 9.3 Basic Geometry Creation

- FR-020 Create primitive: The system shall create supported primitive geometry including Cube, UV Sphere, Ico Sphere, Cylinder, Cone, Torus, Plane, Grid, Circle, Curve, and Text.
- FR-021 Create custom mesh: The system shall create a mesh from explicit vertex, edge, and face arrays and validate topology before committing it to the scene.
- FR-022 Create curve: The system shall create Bezier, Path, and Polyline curves with controllable resolution and transform.
- FR-023 Create text object: The system shall create 3D text with configurable font size, extrusion, bevel, position, and rotation.
- FR-024 Create boolean helper shape: The system shall create auxiliary boolean operands and mark them as helper geometry for later edit or cleanup.

## 9.4 High-Level Model Generation

- FR-030 Create standalone model: The system shall generate an asset from category, theme, style, purpose, target_quality, polygon_budget, seed, constraints, and color hints.
- FR-031 Generate semantic parts: The system shall generate assets as named semantic parts when the chosen category supports decomposition.
- FR-032 Add part: The system shall add a new semantic part to an existing asset and record its PartSpec metadata.
- FR-033 Replace part: The system shall replace a target part while preserving unaffected parts and updating part bindings.
- FR-034 Remove part: The system shall delete a target part without deleting unrelated asset structures.
- FR-035 Increase detail: The system shall add geometric or material detail to a target asset or part while honoring polygon and complexity budgets.
- FR-036 Reduce detail: The system shall simplify an asset or part while preserving silhouette and semantic structure as much as practical.
- FR-037 Modify silhouette: The system shall adjust the global or local silhouette according to directional style instructions such as sharper, heavier, lighter, luxurious, or industrial.
- FR-038 Restyle model: The system shall transform an existing asset toward styles such as low-poly, realistic, sci-fi, fantasy, ruined, or miniature while preserving target identity.

## 9.5 Hard-Surface Generation

- FR-040 Create mechanical model: The system shall generate hard-surface assets such as drones, mechs, machines, vehicle concepts, and sci-fi devices.
- FR-041 Generate panel lines: The system shall create panel lines, seams, or grooves on hard-surface geometry with controllable depth and density.
- FR-042 Place bolts, screws, and rivets: The system shall place reusable fastener details at specified points, curves, or procedural distributions.
- FR-043 Create pipes and cables: The system shall generate tubing, wiring, or conduit using curve-based or mesh-based workflows.
- FR-044 Add armor panels: The system shall add external paneling and reinforcement parts while preserving editability.
- FR-045 Add emissive features: The system shall generate emissive strips, sensors, LEDs, or glow components and bind them to materials or lights as needed.

## 9.6 Architectural Generation

- FR-050 Create building exterior: The system shall generate a building shell with coherent facade composition.
- FR-051 Create architectural parts: The system shall generate walls, roofs, windows, doors, columns, stairs, balconies, pipes, signs, and exterior ornamentation.
- FR-052 Set architectural style: The system shall support style directives such as near-future, modern, industrial, ruined, Japanese, Western, fantasy, cyberpunk, and minimal.
- FR-053 Create modular building: The system shall assemble buildings from reusable modules and preserve module-level editability where possible.
- FR-054 Create interior: The system shall generate room interiors including furniture, lighting, and supporting props.

## 9.7 Furniture and Prop Generation

- FR-060 Create furniture: The system shall generate furniture assets such as chairs, desks, shelves, sofas, beds, and lamps.
- FR-061 Create prop: The system shall generate small props such as books, boxes, terminals, vases, tools, or decor pieces.
- FR-062 Add lived-in detail: The system shall place clutter and daily-life props to increase realism or narrative context.
- FR-063 Create display props: The system shall generate display stands, boards, labels, and spotlights for showroom or concept presentation scenes.

## 9.8 Natural and Environmental Generation

- FR-070 Generate terrain: The system shall generate terrain from grids, displacement, curves, or procedural systems using seed-controlled parameters.
- FR-071 Generate rocks: The system shall generate rocks, cliffs, rubble, and stone formations.
- FR-072 Generate trees: The system shall generate simplified, stylized, or low-cost tree assets for scenes and large scatter jobs.
- FR-073 Generate grass and shrubs: The system shall generate grass, shrubs, and vegetation patches suitable for instancing or scattering.
- FR-074 Generate water systems: The system shall generate rivers, lakes, ponds, and puddles with geometry and material setup.
- FR-075 Scatter natural assets: The system shall distribute natural assets according to terrain masks, biome rules, density, and randomness controls.

## 9.9 Scene Generation

- FR-080 Create scene: The system shall create a scene containing multiple assets, lights, cameras, and background elements.
- FR-081 Place asset: The system shall place existing or newly generated assets at requested scene locations with alignment and collision-aware options.
- FR-082 Scatter assets: The system shall scatter one or more assets over target regions using density, rotation, scale, and randomness rules.
- FR-083 Create composition: The system shall create camera-aware composition layouts suitable for review or presentation.
- FR-084 Generate background environment: The system shall generate sky, floor, walls, horizon, and distant background assets for scene context.

## 9.10 World Generation

- FR-090 Create world: The system shall create a world with size, theme, style, biome definitions, and density controls.
- FR-091 Generate biomes: The system shall generate forests, grasslands, wastelands, wetlands, snowfields, urban zones, ruins, mountains, and coastlines.
- FR-092 Generate roads: The system shall generate roads, paths, and bridges between world landmarks or regions.
- FR-093 Generate landmarks: The system shall generate prominent structures or objects that act as anchors in a world.
- FR-094 Detail region: The system shall increase detail in a selected region without rebuilding the entire world.
- FR-095 Manage world hierarchy: The system shall track world entities at World, Region, Area, Location, Asset, and Part levels.

## 9.11 Modifier Control

- FR-100 Add modifier: The system shall add supported modifiers to a target object.
- FR-101 Set modifier parameters: The system shall update modifier parameters for Bevel, Mirror, Array, Boolean, Solidify, Subdivision Surface, Decimate, Displace, Weighted Normal, Geometry Nodes, Curve, Shrinkwrap, Screw, and Skin.
- FR-102 Apply modifier: The system shall apply a modifier to create evaluated mesh output and shall warn when editability is reduced.

## 9.12 Geometry Nodes Control

- FR-110 Create geometry nodes setup: The system shall create a Geometry Nodes modifier and node tree bound to a target object.
- FR-111 Add geometry node: The system shall add supported nodes to a node tree and return stable node identifiers.
- FR-112 Connect geometry nodes: The system shall create links between node sockets with type validation.
- FR-113 Set geometry node parameter: The system shall update exposed inputs and other controllable parameters.
- FR-114 Create scatter node setup: The system shall generate reusable Geometry Nodes graphs for terrain-based scattering.
- FR-115 Create procedural generation node setup: The system shall generate node graphs for buildings, roads, terrain, and decorative systems.

## 9.13 Material and Shader Control

- FR-120 Create material: The system shall create a new material with standardized naming and metadata.
- FR-121 Apply material: The system shall assign a material to objects or faces according to tool scope.
- FR-122 Set PBR parameters: The system shall set Base Color, Roughness, Metallic, Specular, Alpha, Emission Color, Emission Strength, Normal, and Displacement inputs.
- FR-123 Create node-based material: The system shall build node-based materials using supported node patterns.
- FR-124 Apply style material presets: The system shall provide presets for metal, plastic, wood, stone, concrete, glass, water, grass, soil, emissive, cloth, rubber, painted metal, and ruin-dirt looks.
- FR-125 Restyle materials in bulk: The system shall transform materials across a target asset or scene while preserving assignment boundaries.

## 9.14 Texture and UV Control

- FR-130 Unwrap UVs: The system shall perform automatic UV unwrap operations suitable for draft and standard export workflows.
- FR-131 Pack and normalize UVs: The system shall resolve overlap and normalize UV scale according to packing strategy.
- FR-132 Create procedural textures: The system shall generate procedural texture node setups using noise, Voronoi, gradients, and similar primitives.
- FR-133 Apply image texture: The system shall load and bind image textures from allowlisted paths.
- FR-134 Bake textures: The system shall perform texture baking for supported bake targets and report outputs and warnings.

## 9.15 Lighting

- FR-140 Create light: The system shall create Point, Sun, Spot, and Area lights.
- FR-141 Set light properties: The system shall update location, rotation, intensity, color, and size.
- FR-142 Apply lighting preset: The system shall apply presets for product shot, gallery, cinematic, night, daylight exterior, sunset, eerie, luxury, and sci-fi looks.
- FR-143 Auto-light subject: The system shall automatically light a target asset or scene for preview or presentation use.

## 9.16 Camera

- FR-150 Create camera: The system shall create one or more cameras.
- FR-151 Set camera properties: The system shall update focal length, field of view, transform, and depth of field.
- FR-152 Auto-frame object: The system shall place a camera so the target asset fits the frame according to composition rules.
- FR-153 Create multiview cameras: The system shall generate front, three-quarter, side, top, close-up, and bird’s-eye views as requested.
- FR-154 Create camera path: The system shall generate a simple review or presentation camera motion path.

## 9.17 Rendering

- FR-160 Render quick preview: The system shall render a low-resolution fast preview with bounded sampling and time budget.
- FR-161 Render standard preview: The system shall render a review-grade image with higher fidelity than quick preview.
- FR-162 Render final review image: The system shall render a high-quality approval image using the selected engine and quality preset.
- FR-163 Render multiple views: The system shall batch-render multiple cameras and return the generated image paths.
- FR-164 Set render settings: The system shall update resolution, engine, samples, transparent background, color management, ambient occlusion, bloom, and motion blur.
- FR-165 Render thumbnail: The system shall generate thumbnails for lists, history, and asset catalogs.

## 9.18 Inspection and Quality Control

- FR-170 Inspect scene: The system shall report object count, mesh count, camera count, light count, material count, collection count, total vertices, and total faces.
- FR-171 Inspect mesh quality: The system shall inspect vertex count, face count, triangle count, non-manifold elements, duplicate vertices, normal issues, internal faces, extreme aspect-ratio faces, and extreme scale.
- FR-172 Inspect materials: The system shall detect missing, duplicate, and unused materials.
- FR-173 Inspect scale: The system shall flag objects whose scale is implausible for the stated use case.
- FR-174 Inspect naming: The system shall detect naming-rule violations.
- FR-175 Check export readiness: The system shall identify issues that would block or degrade export to a chosen target format.
- FR-176 Generate AI review report: The system shall return a machine-readable QA report that can be used by an LLM for review and repair planning.

## 9.19 Automated Repair and Optimization

- FR-180 Remove duplicate vertices: The system shall merge duplicate or near-duplicate vertices under configured thresholds.
- FR-181 Recalculate normals: The system shall recompute normals according to consistent outside-facing rules or a specified mode.
- FR-182 Clean unused data: The system shall remove unused materials, meshes, and images after validation.
- FR-183 Optimize polygon count: The system shall reduce polygon count using decimation or equivalent methods with controllable fidelity.
- FR-184 Generate LODs: The system shall generate multiple LOD levels and attach naming and metadata conventions.
- FR-185 Generate collision mesh: The system shall create simplified collision meshes for game-engine workflows.
- FR-186 Set origin: The system shall place object origins according to center, geometry, bottom-center, cursor, or custom rules.
- FR-187 Apply transforms: The system shall apply location, rotation, and scale transforms when explicitly requested or required for export readiness.

## 9.20 Animation and Rigging

- FR-190 Create simple animation: The system shall create keyframed location, rotation, and scale animation.
- FR-191 Create camera animation: The system shall animate camera motion for turntables, fly-throughs, or reveal shots.
- FR-192 Create simple rig: The system shall generate simple rigs for mechanical assets such as doors, wheels, arms, or hinges.
- FR-193 Create and manage bones: The system shall create armatures and bones and update their placement, naming, and transforms.
- FR-194 Apply limited auto-weighting: The system shall support constrained auto-weighting for supported simple rig cases and report confidence limitations.

## 9.21 Import

- FR-200 Import asset: The system shall import supported formats including .blend, .glb/.gltf, .fbx, .obj, .usd/.usdz, and .stl from allowlisted paths.
- FR-201 Import image: The system shall load images for textures, reference images, and backgrounds from allowlisted paths.
- FR-202 Search asset library: The system shall search configured asset-library directories and return matching reusable assets.

## 9.22 Export

- FR-210 Save .blend: The system shall save the project in Blender format and return the final file path.
- FR-211 Export glTF/GLB: The system shall export to glTF or GLB with preset-controlled settings and include format-specific warnings.
- FR-212 Export FBX: The system shall export to FBX with axis, scale, modifier, and animation options.
- FR-213 Export OBJ: The system shall export to OBJ for generic mesh interchange use cases.
- FR-214 Export USD/USDZ: The system shall export to USD or USDZ where Blender support is available in the runtime environment.
- FR-215 Export STL: The system shall export STL for print-evaluation workflows.
- FR-216 Apply use-case export presets: The system shall provide export presets for game, web, render, concept, print, and archive targets.

## 9.23 History and Versioning

- FR-220 Save generation history: The system shall record all significant generation and revision actions in an operation log.
- FR-221 Save preview history: The system shall store preview renders and associate them with projects, requests, and snapshots.
- FR-222 Generate diff summary: The system shall summarize changes relative to a previous state or snapshot.
- FR-223 Roll back to snapshot: The system shall restore a selected snapshot and record the rollback event.
- FR-224 Render comparison views: The system shall generate comparison renders for before-and-after review.

## Cross-Cutting Functional Rules

- Every mutating tool shall return structured output containing status, changed object identifiers, warnings, and next-step suggestions.
- Every tool that can materially alter scene state shall support request correlation and history recording.
- Every tool that targets objects, parts, or regions shall report the final resolved target set before or with execution results.
- Every long-running tool shall provide progress updates when the transport and client support them.