---
id: t-fec4fdd5
title: "T4: works and resume with the guide"
label: "T4: works and resume with"
priority: 5
deps: [t-2fe9d431]
workspace: desktop
---

## Acceptance gate

`resume_tool_calls <= 2` (plan: `arsenal/project/desktop/plan.md` T4; details there under Task details).

```bash
uv run pytest -q tests/test_mcp.py -k resume
```

## Tests

- `test_resume_named_work_returns_state_and_guide` in `tests/test_mcp.py` — one call returns state, next step and a guide of at most 400 words; an unknown name returns `not_found` with the works and the `add_folder` hint

## Location

`src/litcritic/mcp.py`, `prompts/`
