# Runbook: Export Validation Failed

## Symptoms

- Export tool returns `export_blocked`
- QA report flags naming, transform, material, or topology issues

## Steps

1. Inspect blocking findings in the QA report.
2. Resolve transforms, naming, or geometry issues using repair tools.
3. Re-run export-readiness checks.
4. Export again only after all blockers are cleared.

## Common Causes

- Non-applied transforms
- Unsupported material setup for target format
- Non-manifold or invalid geometry
- Excessive complexity for the chosen export preset