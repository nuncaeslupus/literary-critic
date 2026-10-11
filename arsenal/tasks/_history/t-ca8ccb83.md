---
id: t-ca8ccb83
title: "T9: Index build (registers from scene cards) + `lc show/find/context --budget`"
label: "index build and queries"
priority: 5
deps: [t-dce291ef, t-83a5f678]
status: merged
---

# T9: Index build (registers from scene cards) + `lc show/find/context --budget`

From `status/plan.md` (service: lc).

## Acceptance gate
Metric: `index_query_tokens_p95 <= 2500`. Record the measurement in `status/evidence/T9.json` and the plan's evidence log.

```bash
uv run pytest tests/test_query.py::test_context_respects_budget
```

## Tests
`test_context_respects_budget` in `tests/test_query.py` — output never exceeds the budget
