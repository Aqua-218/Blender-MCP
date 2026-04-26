# Metrics Design

## Core Metrics

- Tool call count by tool_name and status
- Tool latency percentiles by tool family
- Blender controller availability
- Bridge timeout count
- Snapshot creation count and duration
- Render duration by preset
- Export success rate by format
- QA report severity counts

## Heavy-Work Metrics

- Predicted vs actual polygon budget
- Scatter instance count
- Final object count per project
- Render resolution and sample usage

## Alert Conditions

- Controller unavailable for more than 30 seconds
- Tool failure rate above 10% over 15 minutes in hosted mode
- Repeated bridge authentication failures
- Render queue saturation for more than 10 minutes