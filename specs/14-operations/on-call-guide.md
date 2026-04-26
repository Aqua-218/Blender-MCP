# On-Call Guide

## Priority Levels

- P1: Data loss risk, uncontrolled destructive behavior, or persistent inability to open projects
- P2: Controller unavailable, export outages, repeated render failures
- P3: Non-blocking QA false positives, minor regressions, or documentation issues

## First Checks

- Is the controller reachable?
- Is the workspace path configuration valid?
- Did the issue start after a version change?
- Is there a recent safe snapshot?