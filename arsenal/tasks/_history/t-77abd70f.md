---
id: t-77abd70f
title: "T9: exact anchors for spans"
label: "exact anchors for spans"
priority: 5
deps: [t-570f081a]
workspace: doccontrol
status: merged
---

# T9: exact anchors for spans

From `arsenal/project/doccontrol/plan.md` (service: spans). Spec: `arsenal/project/doccontrol/spec.md` §5.

Codex span relocation via `anchor.resolve` in exact mode (`spans.relocate` keeps its changed/lost outcomes)

## Acceptance gate
Metric: `fuzzy_relocations == 0`. Record the measurement in `status/evidence/doccontrol-T9.json` and the plan's evidence log.

```bash
uv run pytest tests/test_spans.py::test_relocate_exact_only
```

## Tests
`test_relocate_exact_only` in `tests/test_spans.py` — a one-character edit inside a span yields `changed`, never a fuzzy move
