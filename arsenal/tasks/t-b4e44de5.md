---
id: t-b4e44de5
title: "T3: feedback comments on doc-control"
label: "feedback comments on doc-control"
priority: 10
deps: [t-b6a67a3b]
workspace: doccontrol
---

# T3: feedback comments on doc-control

From `arsenal/project/doccontrol/plan.md` (service: comments). Spec: `arsenal/project/doccontrol/spec.md` §5.

Feedback comments (`lc docx-out`/`docx_out.build`) as one `batch` of `comment.add` on a copy, anchored by address; XML code removed

## Acceptance gate
Metric: `comments_on_wrong_paragraph == 0`. Record the measurement in `status/evidence/doccontrol-T3.json` and the plan's evidence log.

```bash
uv run pytest tests/test_docx_out.py::test_comments_land_on_target_paragraph
```

## Tests
`test_comments_land_on_target_paragraph` in `tests/test_docx_out.py` — every action's comment is on the paragraph its locator names, read back with `comments.list`
