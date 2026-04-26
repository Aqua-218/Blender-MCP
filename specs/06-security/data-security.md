# Data Security

## Data Classes

- Public creative outputs: renders and exported assets intended for sharing
- Internal metadata: project paths, logs, QA reports, snapshot lineage
- Sensitive operational data: session tokens, HTTP auth tokens, policy configuration

## Protection Strategy

- Store metadata and artifacts only in approved local directories.
- Rely on workstation disk encryption and operating-system account protection for local-at-rest protection.
- Avoid embedding secrets in project files, exports, or logs.
- Redact sensitive headers and tokens from logs.

## Retention

- Keep recent operation history by default.
- Allow configurable pruning of large snapshot payloads while preserving metadata references.