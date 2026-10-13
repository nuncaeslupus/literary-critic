---
id: t-fbce7af4
title: "T10: workspace upgrade"
label: "workspace upgrade"
priority: 5
deps: [t-36595e44, t-570f081a, t-77abd70f]
workspace: doccontrol
---

# T10: workspace upgrade

From `arsenal/project/doccontrol/plan.md` (service: upgrade). Spec: `arsenal/project/doccontrol/spec.md` §5.

`lc upgrade`: backup, re-ingest every version from `manuscript/`, migrate overrides by text match (D-7), re-anchor Codex spans, write `analysis/upgrade-report.md`; drop `.safe-edit/` state

## Acceptance gate
Metric: `codex_spans_lost_on_upgrade == 0`. Record the measurement in `status/evidence/doccontrol-T10.json` and the plan's evidence log.

```bash
uv run pytest tests/test_upgrade.py::test_upgrade_keeps_every_resolved_span tests/test_upgrade.py::test_upgrade_lists_unmatched_overrides
```

## Tests
`test_upgrade_keeps_every_resolved_span` in `tests/test_upgrade.py` — a fixture workspace built by the current release keeps every span that resolved before; `test_upgrade_lists_unmatched_overrides` — an override whose paragraph text changed is reported, not dropped silently
