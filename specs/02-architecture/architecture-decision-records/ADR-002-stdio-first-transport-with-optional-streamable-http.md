# ADR-002: Stdio-First Transport with Optional Streamable HTTP

## Status

Accepted

## Context

The target clients include desktop MCP consumers that commonly launch servers as local subprocesses. The product also wants a future path for hosted, browser-compatible, or remote operation.

## Decision

Support stdio from day one and make it the default transport for local desktop use. Add Streamable HTTP as an optional second transport for hosted deployments.

## Consequences

### Positive

- Maximum compatibility with desktop MCP clients.
- Straightforward local installation and subprocess launch.
- Clear path to hosted deployments and web clients.

### Negative

- Two transport surfaces must be tested over time.
- HTTP deployments require session, origin, and authentication handling.

### Risks

- Browser-accessible HTTP endpoints can be abused if origin validation is weak.

## Alternatives Considered

### Alternative 1: HTTP Only

- Description: Expose only Streamable HTTP.
- Pros: Better fit for hosted deployments.
- Cons: Worse local client compatibility and more deployment overhead for workstation-first users.
- Rejection Reason: The initial product is local and desktop-centric.

### Alternative 2: Stdio Only

- Description: Expose only stdio.
- Pros: Smallest implementation surface.
- Cons: No clean path for browser or hosted clients.
- Rejection Reason: Future growth would require a transport redesign instead of an additive feature.