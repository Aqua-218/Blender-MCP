# Risk Register

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Tool surface becomes too large too early | High | High | Ship Core first, gate Advanced and Experimental tools |
| Incorrect tool choice by LLM | High | High | Strong schemas, clear descriptions, safe defaults, QA loop |
| Blender performance collapse on heavy scenes | Medium | High | Budgets, instancing, Geometry Nodes, preview-first workflow |
| Local revisions affect unintended geometry | Medium | High | Target resolver, locality checks, snapshots |
| Export mismatch with target runtime | Medium | Medium | Export-readiness QA and format-specific warnings |
| Hosted mode complexity arrives too early | Medium | Medium | Keep MVP local-first and modular |