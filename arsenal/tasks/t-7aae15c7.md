---
id: t-7aae15c7
title: "T8: Annotations"
label: "release Annotations"
priority: 10
deps: [t-b50ea0c6]
workspace: release
---

## Acceptance gate

`tools_annotated == 1.0` (plan: `arsenal/project/release/plan.md` T8; details there under Task details).

```bash
uv run pytest -q tests/test_mcp.py tests/test_prompts.py -k "test_tools_list_declares_annotations or test_guide_names_always_allow"
```

## Tests

- `test_tools_list_declares_annotations` in `tests/test_mcp.py` — every tool has the annotations in §5, and the read-only set is exactly the seven listed
- `test_guide_names_always_allow` in `tests/test_prompts.py` — the setup part tells the writer the answer Q-7 found

## Location

`src/litcritic/mcp.py`, `prompts/01-chat-guide.md`
