# Roadmap

## Near Term

- land OSS release automation, security scanning, and release metadata polish
- gather early feedback from desktop MCP client integrations
- stabilize public tool contracts and schema publishing expectations for the first tagged release
- expand the Blender tool surface through small, tested packs rather than one coarse bulk drop

## Tool Surface Expansion

- completed first-pass non-destructive modifier convenience tools for bevel, mirror, array, solidify, subdivision, triangulate, weld, remesh, displace, and weighted normals
- completed first-pass collection management tools for listing, creating, renaming, deleting, linking, unlinking, and visibility control
- completed first-pass transform/alignment tools for reset, offset, match, align, distribute, snap-to-grid, ground placement, grid arrangement, and mirroring
- completed first-pass selection set tools for saving, listing, selecting, replacing, adding, removing, and renaming object sets without deleting scene objects
- completed first-pass material-node authoring helpers for adding nodes, setting tracked node params, connecting node sockets, and listing material graphs
- completed first-pass camera blocking, lighting rig, and game-prep helpers for shot cameras, camera orbits, shot bookmarks, three-point/softbox/ring lighting, LOD assignment, collision proxies, game naming, and export-readiness validation
- completed first-pass UV layout and asset-library helpers for UV listing, naming, density, UDIM planning, texture-set manifests, UV validation, asset registration/search, variants, previews, collections, instancing, and asset-library validation
- completed first-pass geometry-nodes preset and production batch helpers for setup listing/duplication, noise displacement, curve scatter, collection instancing, LOD switches, exposed parameters, setup validation, batch preview, tagging, renaming, collection assignment, visibility, transform offsets, material assignment, modifier assignment, and duplication
- completed first-pass mechanical animation/rigging helpers for managed armature listing, mechanical chain rig presets, hinge and looping rotation tracks, animation-track listing, and rig metadata validation
- completed first-pass game export hardening helpers for collision proxy sets, socket markers, export-role tagging, LOD chain validation, export package planning, manifest writing, and engine-specific export profiles
- completed first-pass production batch import/export jobs for one-to-many target export, combined batch export, multi-file import, optional import collection assignment, and export/import result aggregation
- completed first-pass material baking helpers for bake planning, multi-channel texture-set baking, texture atlas manifests, and trim-sheet manifests
- completed first-pass procedural environment helpers for complete world presets, mountain ranges, navigation/gameplay markers, and world composition validation
- completed first-pass game-engine export validation helpers for engine-specific package checks and import checklists
- next high-value packs: richer procedural environment biomes, animation graph editing, and renderer/post-processing workflow packs
- keep every pack wired through MCP registration, mock runtime, Blender runtime when needed, policy classification, focused contract tests, and catalog documentation

## Next

- publish repeatable tagged releases and distribution artifacts
- expand client configuration examples and troubleshooting guidance
- improve contributor onboarding through automation, documentation, and packaged workflows

## Later

- broaden client integration coverage beyond the current desktop examples
- expand presets and higher-level workflow examples for scene composition and asset iteration
- document hosted and multi-user deployment considerations once the local-first contract is stable

## Not Planned For This Boundary

- automation for non-Blender DCC tools
- arbitrary workstation or shell execution
- autonomous content pipelines that bypass explicit user review and safety gates

Implementation detail and historical planning notes remain available in [TODO.md](TODO.md) and the specification suite under [specs/README.md](specs/README.md).