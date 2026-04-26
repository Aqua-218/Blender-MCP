# Governance

## Model

Blender MCP is a maintainer-led project.

The lead maintainer is responsible for release decisions, security triage, community standards enforcement, and resolving technical disputes when consensus cannot be reached.

## Roles

### Lead Maintainer

The lead maintainer:

- sets release direction and acceptance criteria
- approves breaking API and schema changes
- owns security response and coordinated disclosure decisions
- can delegate review and triage authority to additional maintainers

### Maintainers

Maintainers:

- review pull requests
- triage issues and feature requests
- help keep documentation and release materials current
- enforce the Code of Conduct within the scope of the repository

### Contributors

Contributors improve the repository through issues, pull requests, design discussion, tests, documentation, examples, and review feedback.

## Decision-Making

Consensus is preferred for normal design and implementation work.

Maintainer decision is the fallback when:

- a decision blocks release or security work
- competing proposals cannot be reconciled in a reasonable timeframe
- a change affects public API or schema contracts
- a change alters the safety model, transport boundary, or release process

## Changes Requiring Explicit Review

The following changes should receive explicit maintainer review before merge:

- public tool contract changes
- JSON schema changes
- transport or authentication changes
- workspace safety or destructive-operation policy changes
- release automation or packaging changes
- security-sensitive logging, persistence, or controller bridge changes

## Release Management

Blender MCP uses Semantic Versioning and Conventional Commits.

- `fix` changes map to patch releases
- `feat` changes map to minor releases
- breaking changes require explicit annotation and trigger a major release boundary

Releases are documented in [CHANGELOG.md](CHANGELOG.md) and maintained through repository release automation.

## Conduct And Enforcement

Community standards are defined in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Maintainers may moderate issues, pull requests, discussions, and review comments to keep the project healthy and productive.

## Governance Changes

Changes to this governance document require a pull request reviewed by the lead maintainer.