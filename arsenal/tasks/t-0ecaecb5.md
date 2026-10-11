---
id: t-0ecaecb5
title: "C11: remove phase-1 formats"
label: "remove phase-1 formats"
priority: 5
deps: [t-ae1f0186, t-590ae869]
workspace: codex
---

# C11: Remove phase-1 per-type formats, schemas, `index.py` registers and their docs; update `docs/`

## Acceptance gate
Gate: `phase1_leftovers == 0` (spec: arsenal/project/codex/spec.md, plan: arsenal/project/codex/plan.md)

```bash
uv run pytest tests/test_codex_cleanup.py -q -k "test_no_phase1_leftovers"
```

## Tests
`test_no_phase1_leftovers` in `tests/test_codex_cleanup.py` — grep finds no old file names, schemas or commands

## Location
lc
