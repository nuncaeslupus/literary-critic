---
id: t-0cf037ae
title: "T8: locators via doc-control"
label: "locators via doc-control"
priority: 10
deps: [t-ebc95c85, t-36595e44]
workspace: doccontrol
status: merged
---

# T8: locators via doc-control

From `arsenal/project/doccontrol/plan.md` (service: locate). Spec: `arsenal/project/doccontrol/spec.md` §5.

Writer locators from `locate`/`page.estimate`; `LocatorBuilder` and `docx_cli.Finder` removed, `locate.describe` keeps the writer wording

## Acceptance gate
Metric: `locators_not_unique == 0`. Record the measurement in `status/evidence/doccontrol-T8.json` and the plan's evidence log.

```bash
uv run pytest tests/test_locate.py::test_locator_phrase_unique_in_document
```

## Tests
`test_locator_phrase_unique_in_document` in `tests/test_locate.py` — every head…tail phrase and Find string returned for the corpus occurs once
