# Constraints

## Technical Constraints

- The production editing surface is Blender and the Blender Python API; no alternative DCC runtime is in scope.
- A single Blender runtime can edit only one active blend file at a time.
- Blender background execution supports scripted automation, but argument ordering and evaluated dependency-graph availability must be handled carefully.
- Blender as a Python module exists, but it is not the most portable default deployment model and still carries single-runtime state constraints.
- Blender asset-library operations are constrained by Blender’s current-file write model; external blend files must generally be opened before edit.

## Safety Constraints

- All read and write paths must remain within operator-approved workspace roots.
- Arbitrary shell execution is forbidden.
- Destructive operations require confirmation or a policy flag.
- External file import must be restricted by path and extension allowlists.
- The system must support operator-configurable ceilings for polygon count, object count, render resolution, sample count, scatter density, and job duration.

## Compatibility Constraints

- Desktop MCP clients require stdio support.
- Network-hosted clients may require Streamable HTTP support with origin validation and authentication.
- glTF export must respect Blender’s format limitations, including mesh triangulation and material compatibility constraints.
- FBX export must surface known limitations such as incomplete instancing preservation and exporter-specific material constraints.

## Product Constraints

- The first validated implementation target is MVP asset and small-scene creation, not full autonomous world-building at production game scale.
- Character generation, rigging, cloth, hair, and facial animation are explicitly phased and lower-confidence capabilities.
- The product is optimized for iterative review, not one-shot “perfect generation.”