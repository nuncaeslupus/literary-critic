---
id: t-0f1b19db
title: "T7: index prompts"
label: "index prompts"
priority: 10
deps: [t-7598d368]
workspace: index
---

# T7: index prompts

From `arsenal/project/index/plan.md` (service: prompts). Spec: `arsenal/project/doccontrol/spec.md` §5.

Prompts and SKILL.md: packet loop, model tiers, parallel where the surface allows; old item-by-item prompt kept for spot fixes

## Acceptance gate
Metric: `prompts_reference_valid_commands == 1.0`. Record the measurement in `status/evidence/index-T7.json` and the plan's evidence log.

```bash
uv run pytest tests/test_prompts.py::test_prompts_name_only_lc_commands
```

## Tests
`test_prompts_name_only_lc_commands` in `tests/test_prompts.py` — every `lc` command the prompts name exists
