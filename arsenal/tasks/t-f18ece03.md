---
id: t-f18ece03
title: "T7: Metrics engine (es, en) for the registry in `checklist/metrics.toml`"
label: "metrics engine"
priority: 5
deps: [t-22f7049e]
---

# T7: Metrics engine (es, en) for the registry in `checklist/metrics.toml`

From `status/plan.md` (service: lc).

## Acceptance gate
Metric: `planned_metrics_implemented >= 0.8`. Record the measurement in `status/evidence/T7.json` and the plan's evidence log.

```bash
uv run pytest tests/test_metrics.py::test_readability_es_golden
```

## Tests
`test_readability_es_golden` in `tests/test_metrics.py` — Fernández-Huerta/INFLESZ match hand-computed values
