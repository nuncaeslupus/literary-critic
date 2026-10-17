---
id: t-a65ebe58
title: "T6: One-click offer"
label: "T6: One-click offer"
priority: 10
deps: [t-89939b56, t-a5caf3a0]
workspace: install
status: merged
---

## Acceptance gate

`writer_live_install_actions <= 3` (plan: `arsenal/project/install/plan.md` T6; details there under Task details).

```bash
uv run pytest -q tests/test_prompts.py -k live_install
```

## Tests

- `test_setup_prompt_offers_live_install_once` in `tests/test_prompts.py` — the offer appears once, after a slow locate, only on surfaces the evidence allows.
