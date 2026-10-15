---
id: t-fdff2cdf
title: "T3: Plan status, next and legacy seeding"
label: "plan status and next"
priority: 5
deps: [t-5593b8bc, t-778cdc99]
workspace: workplan
---

## Acceptance gate

`resume_names_where_work_stands == 1.0` (plan: `arsenal/project/workplan/plan.md` T3; details there under Task details).

```bash
uv run pytest -q tests/test_plan.py -k "test_plan_status_joins_rounds_and_decisions or test_plan_init_on_legacy_workspace_seeds_rounds or test_plan_next_aspect_part_builds_area_round"
```

## Tests

- `test_plan_status_joins_rounds_and_decisions` in `tests/test_plan.py` — the active round part shows its remaining actions and Codex decisions in the timeline; `test_plan_init_on_legacy_workspace_seeds_rounds` — a workspace with two rounds gets two round parts, the open one active; `test_plan_next_aspect_part_builds_area_round` — `next` on an aspect part returns the `round build --area` command

## Location

`src/litcritic/plan.py`, `rounds.py`
