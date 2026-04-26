# Logging Strategy

## Log Structure

All major logs should be structured JSON with:

- timestamp
- request_id
- project_id
- tool_name
- status
- duration_ms
- warnings_count
- errors_count
- controller_session_id

## Log Streams

- MCP server application log
- Controller bridge log
- Blender execution log summary
- Security and policy violation log

## Retention

- Keep recent logs on the workstation for 30 days by default
- Prune or rotate logs by size and age

## Redaction Rules

- Do not log secrets, auth tokens, or unsafe full external paths when not necessary