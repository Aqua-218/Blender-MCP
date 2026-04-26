# Disaster Recovery

## Local-First DR Strategy

- Metadata backup daily
- Snapshot creation before destructive changes
- Artifact directory backup on the operator’s preferred schedule

## Recovery Targets

- Project recovery from snapshot: under 15 minutes for recent projects
- Full workstation metadata recovery: under 30 minutes with a valid backup

## Recovery Procedure

1. Restore workspace root and metadata file.
2. Reinstall the matching application version.
3. Reattach Blender runtime.
4. Open the project and validate scene integrity.
5. Re-run export-readiness QA for critical deliverables.