---
id: t-b6a67a3b
title: "T1: doc-control adapter"
label: "doc-control adapter"
priority: 10
workspace: doccontrol
---

# T1: doc-control adapter

From `arsenal/project/doccontrol/plan.md` (service: adapter). Spec: `arsenal/project/doccontrol/spec.md` §5.

Adapter `litcritic/dc.py` (`run`, `check`, `DocError`), dependency pinned in `pyproject.toml`/`uv.lock`, AGENTS.md rule 9 and `test_stdlib_only.py` allow exactly doc-control

## Acceptance gate
Metric: `api_major_mismatch_runs == 0`. Record the measurement in `status/evidence/doccontrol-T1.json` and the plan's evidence log.

```bash
uv run pytest tests/test_dc.py::test_dc_check_rejects_other_major tests/test_stdlib_only.py::test_runtime_deps_only_doc_control
```

## Tests
`test_dc_check_rejects_other_major` in `tests/test_dc.py` — a faked `capabilities.api` of `2.0` makes `lc` exit with the install hint; `test_runtime_deps_only_doc_control` in `tests/test_stdlib_only.py` — the only non-stdlib import under `src/` is `doc_control`, inside `dc.py`
