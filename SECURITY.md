# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` | Yes |
| `0.1.x` | Yes |
| `<0.1.0` | No |

## Reporting A Vulnerability

Do not open a public issue for security vulnerabilities.

Preferred reporting channel:

- GitHub Private Vulnerability Reporting, if it is enabled for this repository

Fallback reporting channel:

- Email: aqua@arivell.com

Please include:

- a clear description of the issue and impact
- affected version, commit, or deployment mode
- reproduction steps or a minimal proof of concept
- whether the issue affects `stdio`, `http`, `mock`, `blender`, or packaging paths
- any proposed remediation details if you already have them

## Response Expectations

- Initial acknowledgement within 3 business days
- Initial triage and severity assessment within 7 business days
- Coordinated remediation timeline communicated after triage

## Disclosure Policy

Blender MCP follows coordinated disclosure.

- Please give maintainers reasonable time to validate and remediate the issue before public disclosure.
- Once a fix is available, release notes and the changelog will document the security impact at an appropriate level of detail.

## Security Practices

Current repository security practices include:

- allowlisted workspace roots for file access
- shared-secret authentication for the controller bridge
- explicit authentication requirements for HTTP mode unless unsafe local debug mode is opted into
- schema validation and typed request and result models
- log redaction for tokens and shared secrets
- automated regression coverage for HTTP authentication, controller authentication, packaging, and workspace safety

## Dependency And Release Hygiene

- Dependency updates are tracked with Dependabot.
- CI is expected to run linting, typing, tests, schema drift checks, packaging smoke validation, and security scanning before release.
- Release artifacts should always include `LICENSE` and `NOTICE`.