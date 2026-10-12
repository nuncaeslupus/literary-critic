---
id: t-05ab3f1c
title: "W7: prompts for setup wizard and guided flow"
label: "guided flow prompts"
priority: 5
deps: [t-5f533083, t-b04fa655, t-9263f3a9, t-8e787b86]
workspace: chat
status: merged
---

# W7: prompts for setup wizard and guided flow

See `arsenal/project/chat/plan.md` (row W7) and spec `arsenal/project/chat/spec.md` §5.

## Acceptance gate
Gate: `prompt_commands_parse == 1` (spec: arsenal/project/chat/spec.md, plan: arsenal/project/chat/plan.md)

```bash
uv run pytest tests/test_prompts.py -q -k test_prompt_commands_parse
```

## Tests
`test_prompt_commands_parse` in `tests/test_prompts.py`

## Location
prompts
