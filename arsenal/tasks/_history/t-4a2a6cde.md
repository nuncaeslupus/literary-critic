---
id: t-4a2a6cde
title: "T13: `lc pack/unpack` with checksummed manifest; stale-overwrite refusal"
label: "workspace pack/unpack"
priority: 10
deps: [t-d77a64a4]
status: merged
---

# T13: `lc pack/unpack` with checksummed manifest; stale-overwrite refusal

From `status/plan.md` (service: lc).

## Acceptance gate
Metric: `stale_overwrite_blocked == 1.0`. Record the measurement in `status/evidence/T13.json` and the plan's evidence log.

```bash
uv run pytest tests/test_pack.py::test_unpack_refuses_older_zip
```

## Tests
`test_unpack_refuses_older_zip` in `tests/test_pack.py` — older zip cannot overwrite newer workspace
