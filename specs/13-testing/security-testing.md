# Security Testing

## Required Tests

- Path traversal attempts on import and export
- Controller bridge authentication failure
- Destructive tool call without confirmation
- HTTP request without valid auth token in hosted mode
- Oversized geometry budget request in safe mode

## Expected Outcome

- All unsafe requests fail before unintended side effects occur.
- All failures are logged with structured policy codes.