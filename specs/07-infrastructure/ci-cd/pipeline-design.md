# CI/CD Pipeline Design

## Pipeline Stages

1. Format and static checks
2. Unit tests
3. Schema validation tests
4. Blender integration smoke tests
5. Package build
6. Security checks
7. Release artifact publication

## Required Checks

- Python formatting and linting
- JSON schema validation
- Migration smoke test
- FastMCP tool-registration smoke test
- Blender controller launch smoke test in CI-compatible mode

## Release Artifacts

- Python package or installable workspace artifact
- Generated schema bundle
- Release notes with tool catalog changes

## Deployment Rule

- No release is promoted unless the Blender-backed smoke test passes against the supported baseline Blender version.