---
id: t-7a41dbc6
title: "T5: State place"
label: "release State place"
priority: 5
deps: [t-b50ea0c6]
workspace: release
---

## Acceptance gate

`cfa_fallback_correct == 1.0` (plan: `arsenal/project/release/plan.md` T5; details there under Task details).

```bash
uv run pytest -q tests/test_folders.py -k "test_state_place_cfa_on_protected_uses_fallback or test_state_place_cfa_off_beside_novel"
```

## Tests

- `test_state_place_cfa_on_protected_uses_fallback` in `tests/test_folders.py` — with Controlled folder access faked on, nothing is written under the protected folder, OneDrive's root is used when set and the profile otherwise
- `test_state_place_cfa_off_beside_novel` — off, the state is beside the novel in all four layouts

## Location

`src/litcritic/cfa.py` (new), `folders.py`, `workspace.py`
