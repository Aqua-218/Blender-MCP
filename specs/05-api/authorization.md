# Authorization Design

## Model

Authorization combines role-based policy and tool-class restrictions.

## Roles

| Role | Typical Holder | Permissions |
| --- | --- | --- |
| Viewer | Read-only review client | Read metadata, inspect, list, render existing views |
| Editor | Standard AI-assisted creative workflow | Most create, revise, inspect, render, and export tools |
| Destructive Editor | Explicitly trusted editing workflow | Delete, rollback, overwrite, apply destructive optimization |
| Operator | Human maintainer | Configure paths, limits, transport mode, and policies |

## Policy Rules

- Read-only tools are allowed to all authenticated roles.
- Standard mutating tools require Editor or higher.
- Destructive tools require Destructive Editor or an explicit confirmation gate bound to a higher-trust policy context.
- Operator-only configuration changes are never exposed as model-invocable creative tools.

## Authorization Matrix

| Tool Class | Viewer | Editor | Destructive Editor | Operator |
| --- | --- | --- | --- | --- |
| Query | Allow | Allow | Allow | Allow |
| Safe mutation | Deny | Allow | Allow | Allow |
| Destructive mutation | Deny | Deny by default | Allow | Allow |
| Policy and config mutation | Deny | Deny | Deny | Allow |

## Default Behavior

For local stdio sessions, the default role is Editor but destructive operations still require confirmation unless policy explicitly upgrades the session.