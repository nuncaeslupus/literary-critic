---
id: t-2c65cf4f
title: "T2: docx edits on doc-control"
label: "docx edits on doc-control"
priority: 1
deps: [t-b6a67a3b]
workspace: doccontrol
---

# T2: docx edits on doc-control

From `arsenal/project/doccontrol/plan.md` (service: edits). Spec: `arsenal/project/doccontrol/spec.md` §5.

`lc docx edits|rename|status` on doc-control: quotes resolved with `anchor.resolve` (exact), applied with one `batch`/`term.rename`; doc-control's `open`, locks, backups, verify and undo replace `safe_edit.py` and `docx_edit.py` (both deleted); `setup`/`ingest` lock and read checks go through the adapter

## Acceptance gate
Metric: `unintended_docx_changes == 0`. Record the measurement in `status/evidence/doccontrol-T2.json` and the plan's evidence log.

```bash
uv run pytest tests/test_docx_cli.py::test_edits_change_only_target_text tests/test_docx_cli.py::test_edits_are_tracked_revisions tests/test_docx_cli.py::test_edit_refused_when_ambiguous_missing_or_overlapping tests/test_docx_cli.py::test_edit_refused_when_word_has_file_open tests/test_docx_cli.py::test_undo_restores_previous_bytes
```

## Tests
`test_edits_change_only_target_text`, `test_edits_are_tracked_revisions`, `test_edit_refused_when_ambiguous_missing_or_overlapping` moved to `tests/test_docx_cli.py` and run through `lc docx`; `test_edit_refused_when_word_has_file_open` — a lock file makes `lc docx edits` refuse and leave the file byte-identical; `test_undo_restores_previous_bytes` — `lc docx undo` returns the document to its pre-edit text
