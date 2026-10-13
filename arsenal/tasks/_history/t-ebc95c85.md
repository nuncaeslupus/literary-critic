---
id: t-ebc95c85
title: "T5: ingest via doc-control"
label: "ingest via doc-control"
priority: 5
deps: [t-ed4e78a9]
workspace: doccontrol
status: merged
---

# T5: ingest via doc-control

From `arsenal/project/doccontrol/plan.md` (service: ingest). Spec: `arsenal/project/doccontrol/spec.md` §5.

Ingest through doc-control's uncapped bulk read (waits on doc-control's in-process API); `meta.json` schema 2 with `at`; `read_docx`, `_docx_styles` and the odt/md/txt readers' layout code reduced to `convert`

**Waits on doc-control's uncapped in-process read API** (requested 2026-10-13); do not start before it is released.

## Acceptance gate
Metric: `ingest_100k_words_s <= 3`. Record the measurement in `status/evidence/doccontrol-T5.json` and the plan's evidence log.

```bash
uv run pytest tests/test_ingest.py::test_ingest_100k_words_under_budget tests/test_ingest.py::test_meta_paragraphs_carry_addresses
```

## Tests
`test_ingest_100k_words_under_budget` in `tests/test_ingest.py` — a generated 100k-word `.docx` ingests in under 3 s; `test_meta_paragraphs_carry_addresses` — every paragraph in `meta.json` has an `at` that `para.get` resolves
