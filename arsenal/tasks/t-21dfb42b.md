---
id: t-21dfb42b
title: "T6: index re-index changed"
label: "index re-index changed"
priority: 10
deps: [t-68b65ef7]
workspace: index
---

# T6: index re-index changed

From `arsenal/project/index/plan.md` (service: reindex). Spec: `arsenal/project/doccontrol/spec.md` §5.

Re-index after a new draft: `lc index plan --changed` packs only re-read scenes

## Acceptance gate
Metric: `reindex_input_tokens_ratio <= 0.15`. Record the measurement in `status/evidence/index-T6.json` and the plan's evidence log.

```bash
uv run pytest tests/test_index.py::test_reindex_packs_only_changed_scenes
```

## Tests
`test_reindex_packs_only_changed_scenes` in `tests/test_index.py` — a draft changing 2 of 20 scenes yields packets for those 2 only
