# Epic 02: Asset Generation

## Outcome

The system must allow an LLM to create part-aware assets and revise them locally without collapsing the user’s review loop.

## User Stories

### US-AG-001

As a human director, I want to request an asset in natural language so that I can describe style, colors, symmetry, and intent without authoring Blender scripts myself.

Acceptance criteria:

- The client can pass free-form instruction text plus structured fields such as style, seed, quality, and constraints.
- The system creates an AssetSpec that preserves the request semantics.
- The generated asset is associated with named semantic parts where the category supports decomposition.

### US-AG-002

As an LLM client, I want category-specific generation tools so that I can choose the right modeling strategy for hard-surface assets, furniture, buildings, and natural props.

Acceptance criteria:

- The tool catalog exposes both generic and category-specific generation entry points.
- The controller routes each request to a dedicated module with category-aware defaults.
- Unsupported categories return structured warnings instead of silent degradation.

### US-AG-003

As a human director, I want to revise only selected parts so that I can ask for “thicker legs” or “more detail around the rotors” without rebuilding the whole model.

Acceptance criteria:

- Targeting can resolve by object ID, part ID, collection, tag, or spatial query.
- Local revisions must not modify unrelated parts unless the tool explicitly declares broader impact.
- The response must state which parts were modified and which were intentionally untouched.

### US-AG-004

As a QA reviewer, I want asset outputs to remain editable after generation so that future iterations can still manipulate parts, materials, and modifier stacks.

Acceptance criteria:

- The system prefers non-destructive modifiers and node graphs until a bake or export operation requires collapse.
- Materials, collections, and tags remain attached after revisions.
- The QA report flags destructive baking when it reduces future editability.

### US-AG-005

As an operator, I want polygon budgets and safe-mode limits so that the AI cannot accidentally create unbounded geometry.

Acceptance criteria:

- Each asset request may set a polygon budget.
- The system warns or auto-optimizes when the budget is exceeded.
- Safe mode applies stricter ceilings for polygon count, subdivision depth, scatter density, and texture bake resolution.