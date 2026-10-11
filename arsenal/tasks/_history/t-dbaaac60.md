---
id: t-dbaaac60
title: "C6: catalogue to sql"
label: "catalogue to sql"
priority: 5
deps: [t-dfcab048]
workspace: codex
status: merged
---

# C6: Catalogue translation: SQL for each catalogue question; untranslatable ones name the missing data; add item types or tables where cheap

## Acceptance gate
Gate: `question_catalogue_expressible >= 0.9` (spec: arsenal/project/codex/spec.md, plan: arsenal/project/codex/plan.md)

```bash
uv run pytest tests/test_codex_catalogue.py -q -k "test_catalogue_sql_runs_on_fixture"
```

## Tests
`test_catalogue_sql_runs_on_fixture` in `tests/test_codex_catalogue.py` — at least 90% of entries have SQL that runs and returns the expected shape

## Location
lc
