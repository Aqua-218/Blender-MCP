# SLI and SLO Definitions

## SLIs

- Successful tool call ratio
- p95 latency for lightweight tools
- p95 queue wait for long-running jobs
- Controller uptime
- Export success ratio by format

## SLOs

- Lightweight tool success rate: 99% over rolling 30 days
- Lightweight tool p95 latency: under 2 seconds on the reference workstation
- Controller availability in hosted mode: 99.5% over rolling 30 days
- Export success rate for supported MVP formats: 98% over rolling 30 days

## Error Budget Policy

- If the lightweight tool success SLO is missed, release of new Advanced or Experimental tools pauses until regression causes are fixed.