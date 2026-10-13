---
id: t-ffcc71ff
title: "T1: index prepass"
label: "index prepass"
priority: 5
workspace: index
---

# T1: index prepass

From `arsenal/project/index/plan.md` (service: prepass). Spec: `arsenal/project/doccontrol/spec.md` §5.

`prepass.py` + `lc index prepass`: entity candidates (count, first quote, ≤ 2 KWIC snippets), role titles, speaker tags, per-scene stats; corpus gold lists in `tests/fixtures/gold/`

## Acceptance gate
Metric: `candidate_entity_recall >= 0.92`. Record the measurement in `status/evidence/index-T1.json` and the plan's evidence log.

```bash
uv run pytest tests/test_prepass.py::test_prepass_recall_on_gold tests/test_prepass.py::test_candidate_list_tokens_bounded
```

## Tests
`test_prepass_recall_on_gold` in `tests/test_prepass.py` — every gold entity of both corpus texts but at most 8 % is reached by some candidate; `test_candidate_list_tokens_bounded` — the rendered list is ≤ 12 % of the text's tokens
