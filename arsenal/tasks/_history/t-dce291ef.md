---
id: t-dce291ef
title: "T6: Draft alignment: old\u2192new anchor map, changed/moved/new/deleted, stale scenes"
label: "draft alignment"
priority: 5
deps: [t-22f7049e]
status: merged
---

# T6: Draft alignment: old→new anchor map, changed/moved/new/deleted, stale scenes

From `status/plan.md` (service: lc).

## Acceptance gate
Metric: `anchor_stability_after_synthetic_edits >= 0.99`. Record the measurement in `status/evidence/T6.json` and the plan's evidence log.

```bash
uv run pytest tests/test_diff.py::test_alignment_survives_synthetic_edits
```

## Tests
`test_alignment_survives_synthetic_edits` in `tests/test_diff.py` — unchanged paragraphs keep anchors; recall ≥0.98, precision ≥0.95
