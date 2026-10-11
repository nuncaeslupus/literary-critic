---
id: t-d46f99ac
title: "W8: skill entry point and skill zip packaging"
label: "skill packaging"
priority: 5
deps: [t-05ab3f1c]
workspace: chat
---

# W8: skill entry point and skill zip packaging

See `arsenal/project/chat/plan.md` (row W8) and spec `arsenal/project/chat/spec.md` §5.

## Acceptance gate
Gate: `skill_workshop_errors == 0` (spec: arsenal/project/chat/spec.md, plan: arsenal/project/chat/plan.md)

```bash
uv run pytest tests/test_kit.py -q
```

## Tests
`test_skill_zip_builds_and_validates` in `tests/test_kit.py`

## Location
skill
