# Error Handling

## Error Envelope

Tool failures return the normal structured result envelope with:

- `status: failed`
- a human-readable `summary`
- machine-readable `errors`
- optional `warnings`
- optional `next_suggestions`

## Error Categories

| Code | Meaning |
| --- | --- |
| `validation_error` | Input shape or type is invalid |
| `policy_violation` | Request breaks path, budget, or safety rules |
| `target_not_found` | Object, part, or region resolution failed |
| `controller_unavailable` | Blender controller could not be reached |
| `controller_timeout` | Controller job exceeded time budget |
| `blender_execution_error` | Blender-side execution raised an exception |
| `snapshot_required` | Operation requires snapshot or confirmation before proceed |
| `export_blocked` | Export-readiness checks found blocking issues |
| `unsupported_feature` | Requested feature exists conceptually but is not implemented or not stable enough |
| `internal_error` | Unexpected server failure |

## Mapping Rules

- Validation and policy errors are returned before any Blender call.
- Blender exceptions are captured, redacted if needed, and mapped to structured tool errors.
- Partial failures use `partial_success` when some outputs remain usable.
- Long-running cancellations return `failed` with `controller_timeout` or `cancelled` semantics recorded in history.