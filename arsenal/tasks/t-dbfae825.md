---
id: t-dbfae825
title: "C4: sql view"
label: "sql view"
priority: 5
deps: [t-69220b4e]
workspace: codex
---

# C4: `view.py`: in-memory SQL view, `codex_schema = 1`, computed tables (tokens, n-grams, mentions, co-presence) built lazily, read-only guards, budgeted output; `lc codex sql --schema`

## Acceptance gate
Gate: `codex_load_seconds_20k <= 1` (spec: arsenal/project/codex/spec.md, plan: arsenal/project/codex/plan.md)

```bash
uv run pytest tests/test_view.py -q -k "test_view_rejects_writes or test_view_load_time_20k_items"
```

## Tests
`test_view_rejects_writes` in `tests/test_view.py` — INSERT, DELETE and ATTACH are refused; `test_view_load_time_20k_items` — synthetic 20k-item Codex loads within 1 s

## Location
lc
