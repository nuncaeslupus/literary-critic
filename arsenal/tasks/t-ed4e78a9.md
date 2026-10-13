---
id: t-ed4e78a9
title: "T4: convert non-docx to docx"
label: "convert non-docx to docx"
priority: 5
deps: [t-b6a67a3b]
workspace: doccontrol
---

# T4: convert non-docx to docx

From `arsenal/project/doccontrol/plan.md` (service: convert). Spec: `arsenal/project/doccontrol/spec.md` §5.

`litcritic/convert.py`: `.txt`/`.md`/`.odt` → minimal `.docx` (headings, centring, page breaks, blank lines), one function per format

## Acceptance gate
Metric: `converted_layout_fact_mismatches == 0`. Record the measurement in `status/evidence/doccontrol-T4.json` and the plan's evidence log.

```bash
uv run pytest tests/test_convert.py::test_convert_roundtrip_keeps_layout_facts
```

## Tests
`test_convert_roundtrip_keeps_layout_facts` in `tests/test_convert.py` — for both corpus texts in each format, the reader's paragraphs and facts equal those doc-control reads from the converted file
