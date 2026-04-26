# Epic 03: Scene and World Pipeline

## Outcome

The system must compose multiple assets into coherent scenes and larger world regions with reusable procedural controls.

## User Stories

### US-SW-001

As a human director, I want the AI to assemble a display scene around an asset so that I can review it in context with camera, lighting, and background.

Acceptance criteria:

- The system can create a scene from existing or newly generated assets.
- Lighting, camera framing, and background are assigned according to the requested style.
- Preview renders are produced from one or more recommended views.

### US-SW-002

As an LLM client, I want high-volume placement tools for vegetation, rocks, props, and modular building elements so that I can populate scenes efficiently.

Acceptance criteria:

- Scatter operations support area, density, scale variance, rotation variance, and seed control.
- Large placement jobs prefer instances or Geometry Nodes rather than unique meshes.
- Scatter jobs produce progress updates and surface warnings when density exceeds configured budgets.

### US-SW-003

As a human director, I want to detail only one region of a world so that I can focus quality where the camera or gameplay needs it.

Acceptance criteria:

- Worlds can be addressed hierarchically by region, area, location, asset, and part.
- The detail operation can target one region without reprocessing the full world.
- The response reports budget impact and any changed procedural dependencies.

### US-SW-004

As an integrator, I want consistent units, world scale, and export conventions across scenes and worlds so that downstream engines receive predictable results.

Acceptance criteria:

- Scene and world creation must inherit project unit settings.
- Export presets encode axis, scale, modifier-application, and inclusion rules by target format.
- Export-readiness checks surface unit, transform, and hierarchy issues before export.