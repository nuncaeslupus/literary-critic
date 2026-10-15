---
id: t-d1cd252d
title: "T9: Plain writes in the file engine"
label: "plain writes, file engine"
priority: 5
deps: [t-9c184d28, t-d0b8bc39]
workspace: workplan
---

Blocked outside this repo until doc-control ships `tracked: false` in the file engine: https://github.com/nuncaeslupus/doc-control/issues/318

Detecting support (agreed with doc-control): `capabilities` carries a plain-writes feature flag, separate for the file engine and live; an older doc-control rejects `tracked: false` with `SCHEMA_INVALID`, so map that to `doc_control_too_old`; tracked stays the default when `tracked` is absent. doc-control will send the exact flag name and version when #318/#319 merge.

## Acceptance gate

`approved_change_revision_marks == 0` (plan: `arsenal/project/workplan/plan.md` T9; details there under Task details).

```bash
uv run pytest -q tests/test_change.py -k "test_change_approve_leaves_no_revision_marks or test_overlap_with_tracked_revision_gives_marked or test_old_doc_control_refused_not_tracked"
uv run pytest -q tests/test_prompts.py -k "test_writer_texts_have_no_tracked_wording"
```

## Tests

- `test_change_approve_leaves_no_revision_marks` in `tests/test_change.py` — after approve, the document has no `w:ins`/`w:del` from this call; `test_overlap_with_tracked_revision_gives_marked` — the reason is `marked`; `test_old_doc_control_refused_not_tracked` — older doc-control answers `doc_control_too_old`; `test_writer_texts_have_no_tracked_wording` in `tests/test_prompts.py` — `tracked_wording_in_writer_texts == 0` across the listed help and prompt texts

## Location

`src/litcritic/docx_cli.py`, `setup.py`, `word_live.py`, `prompts/`
