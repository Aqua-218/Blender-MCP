# Versioning Strategy

## Principles

- Tool names are stable once released.
- New optional fields are additive.
- Breaking schema changes require a major server version increase.
- Experimental tools are clearly marked and may evolve faster than Core tools.

## Version Surfaces

- Server package version: semantic versioning
- Tool catalog version: published in server metadata and release notes
- Schema version: embedded in generated schema documents
- Blender compatibility version: explicit minimum and tested version range

## Compatibility Rules

- Existing required input fields must not change meaning in minor releases.
- Removed fields require a major version and migration guidance.
- Deprecated tools remain discoverable for at least one minor cycle unless a security issue requires immediate removal.