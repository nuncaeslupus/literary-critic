# Plan: writer install, live Word and updates

**Date**: 2026-10-14
**Specification**: `arsenal/project/install/spec.md` (approved, revision 1)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: approved (2026-10-14, revision 1) — without annotations
**Revision log**:
- r1 — first draft, from the approved spec (Option B; Q-4 and Q-5 take the proposed answers)

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

---

## Technical solution

### Architecture overview

Three independent pieces, then the prompts that use them, then the owner's hand
tests that decide the one-click path:

1. **Version stamp** (`kit.py`): the kit and Skill zips carry a `VERSION` file;
   `lc doctor` reports `version`, `built`, `source`.
2. **Update check** (`kit.py`, `lc doctor --json`): newest release tag over
   HTTPS (stdlib `urllib`, 3 s timeout, once a day), compared with `version`;
   `yes` / `no` / `unknown`, silent on any failure.
3. **Live-first locate** (`word_live.py`): ask doc-control `capabilities` for
   the `live` engine; `live.select` first, then the computer-use steps (today's
   behaviour), then the plain locator. Only `dc.py` talks to doc-control.
4. **Prompts**: `05-setup.md` turns `update_available` into one plain sentence
   at conversation start and resumes from an existing working folder;
   `80-live-word.md` handles `how: live`.
5. **One-click live install**: owned by doc-control (D-3). Here only the wizard
   offers it, on the surfaces the Q-1 result allows.

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "Locate a passage",
 "nodes": [
  {"id": "ask", "text": "writer: take me there"},
  {"id": "word", "text": "lc word locate"},
  {"id": "live", "text": "doc-control live.select"},
  {"id": "cu", "text": "computer-use steps"},
  {"id": "plain", "text": "plain locator"}
 ],
 "edges": [
  {"from": "ask", "to": "word"},
  {"from": "word", "to": "live", "label": "live engine listed"},
  {"from": "live", "to": "cu", "label": "fails"},
  {"from": "word", "to": "cu", "label": "no live engine"},
  {"from": "cu", "to": "plain", "label": "Find cannot reach it"}
 ]}
```

### State changes

| Where | Store | Change | Description |
|-------|-------|--------|-------------|
| kit / Skill zip | `VERSION` | CREATE | `version`, `built` (build date) |
| working folder | `<ws>/.cache/latest.json` | CREATE/UPDATE | latest tag and when it was read; disposable |

### Technology choices

| Choice | Justification |
|--------|--------------|
| stdlib `urllib` for the tag read | runtime is stdlib only (AGENTS.md rule 9) |
| release tags as "latest" (Q-4) | no extra file to keep in sync; tags already mark releases |
| `live` through `dc.py` | only `dc.py` imports doc-control (architecture rule) |

### Out of scope

- Packaging doc-control's live engine or MCP server (doc-control's session, Q-2).
- Any change to the working-folder format.
- Fixing the desktop app's always-on-top window after computer use.

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Version stamp | `src/litcritic/kit.py`, `cli.py` | S | — | `version_source_cases_correct == 4` | `test_doctor_json_in_kit_reports_source_kit` in `tests/test_kit.py` — doctor run from a built kit reports `source: kit` and the stamped version |
| T2 | Update check | `src/litcritic/kit.py` | M | T1 | `update_detected_rate == 1.0` | `test_update_check_older_online_says_yes` in `tests/test_kit.py` — with the tag read mocked newer, `update_available` is `yes`; also offline, current, checkout, dev-newer cases give `unknown`/`no` (`update_false_alarms == 0`) |
| T3 | Live-first locate | `src/litcritic/word_live.py`, `dc.py` | M | — | `live_fallback_correct == 1.0` | `test_locate_live_failure_falls_back_to_steps` in `tests/test_word_live.py` — with `live.select` raising, timing out or returning `selected: false`, the result is the computer-use steps, never an error |
| T4 | Prompts | `prompts/`, `.claude/skills/litcritic/SKILL.md` | S | T2, T3 | `update_notice_words <= 40` | `test_setup_prompt_update_notice_is_short` in `tests/test_prompts.py` — the notice sentence in `05-setup.md` has at most 40 words and no command or file name |
| T5 | Owner hand tests | owner, `status/evidence/` | S | — | `hand_tests_recorded == 2` | `test_install_evidence_names_q1_and_q3` in `tests/test_status.py` — the evidence file exists and answers Q-1 and Q-3 yes or no |
| T6 | One-click offer | `prompts/05-setup.md`, `prompts/80-live-word.md` | S | T4, T5 | `writer_live_install_actions <= 3` | `test_setup_prompt_offers_live_install_once` in `tests/test_prompts.py` — the offer appears once, after a slow locate, only for the surfaces the evidence allows |
| T7 | Walkthrough | owner + Claude, `status/evidence/` | M | T6 | `live_locate_seconds_p50 <= 5` | `test_install_walkthrough_evidence_meets_gates` in `tests/test_status.py` — the walkthrough record lists 20 actions with p50 ≤ 5 s and success ≥ 0.9 |

### Task details

- **T1 Version stamp**: Version stamp: `VERSION` in kit and Skill zips; `lc doctor --json` reports `version`, `built`, `source`; a test keeps `__version__` and `pyproject.toml` equal.
- **T2 Update check**: Update check: newest `vX.Y.Z` tag, 3 s timeout, daily cache, `yes`/`no`/`unknown`; `--no-network`.
- **T3 Live-first locate**: Live-first locate: `live.select` when doc-control lists `live`, else computer-use steps, else plain locator; `how: live` in the result.
- **T4 Prompts**: Prompts: update notice (once, at conversation start, ≤ 40 words, no tool talk) and resume from an existing working folder in `05-setup.md`; `how: live` in `80-live-word.md`; `SKILL.md` "Running the tool" names the check (needs skill-creator loaded).
- **T5 Owner hand tests**: Owner hand tests Q-1 (Cowork calls a host MCP server) and Q-3 (project keeps the folder); results in `status/evidence/install-Q1-Q3.md`; doc-control told the Q-1 result.
- **T6 One-click offer**: Wizard offers the one-click live install on the surfaces Q-1 allows, after the first slow locate; `05-setup.md` states the resume behaviour Q-3 found.
- **T7 Walkthrough**: Walkthrough: 10 located actions on Windows and 10 on a Mac with the live engine; setup and update actions counted.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1, T3, T5 in parallel; T2 after T1; T4 after T2 and T3; T6 after T4 and T5; T7 last.
**Branch pattern**: `install-T<N>-description` from the default branch

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies",
 "nodes": [
  {"id": "T1", "text": "T1\nVersion stamp"},
  {"id": "T2", "text": "T2\nUpdate check"},
  {"id": "T3", "text": "T3\nLive-first locate"},
  {"id": "T4", "text": "T4\nPrompts"},
  {"id": "T5", "text": "T5\nOwner hand tests"},
  {"id": "T6", "text": "T6\nOne-click offer"},
  {"id": "T7", "text": "T7\nWalkthrough"}
 ],
 "edges": [
  {"from": "T1", "to": "T2"},
  {"from": "T2", "to": "T4"},
  {"from": "T3", "to": "T4"},
  {"from": "T4", "to": "T6"},
  {"from": "T5", "to": "T6"},
  {"from": "T6", "to": "T7"}
 ]}
```

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|
| T1 | `version_source_cases_correct == 4` | 4 (kit, skill, checkout, package) | `uv run pytest -q tests/test_kit.py -k doctor_json` | this PR | local | 2026-10-14 |

---

## Sign-off

- [ ] Plan reviewed by the owner
- [ ] Q-1 and Q-3 answered (T5)
- [ ] doc-control session told the Q-1 result
- [ ] Ready for execution
