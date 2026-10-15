---
id: t-f8a6be89
title: "T5: Undo marks a change undone"
label: "undo marks change undone"
priority: 10
deps: [t-9c184d28]
workspace: workplan
---

## Acceptance gate

`undo_after_plain_change_mismatches == 0` (plan: `arsenal/project/workplan/plan.md` T5; details there under Task details).

```bash
uv run pytest -q tests/test_change.py -k "test_docx_undo_of_change_logs_change_undone"
```

## Tests

- `test_docx_undo_of_change_logs_change_undone` in `tests/test_change.py` — undo after an approved change restores the original text and logs `change.undone` for that id

## Location

`src/litcritic/docx_cli.py`, `change.py`
