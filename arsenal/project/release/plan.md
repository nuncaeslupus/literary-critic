# Plan: one extension a writer installs and forgets

**Date**: 2026-10-17
**Specification**: `arsenal/project/release/spec.md` (approved, revision 2)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: approved (2026-10-17, revision 1) — without annotations
**Revision log**:
- r1 — first draft, from the approved spec (Option C, both phases). The first
  chain (T1–T3) packs the bundle in CI, releases it, and runs the clean-PC
  probe on that released bundle

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

---

## Technical solution

### Architecture overview

One `.mcpb` of server type `uv` (D-1). The app installs uv, runs `uv sync`
against the bundled `uv.lock` (D-2), and starts `launch.py`, which starts
`lc mcp`. The work comes in three blocks:

1. **Bundle, release, probe** (T1–T3). This is the spec's first action.
   - CI packs and validates the `.mcpb` on every PR.
   - A version bump that is merged tags the commit, and the tag publishes the
     Release.
   - The owner then installs that released file on a clean PC. That one run
     answers desktop Q-3 and Q-8 and spec Q-5 to Q-8.
   - This replaces `desktop` T8, and runs `desktop` T1 on the real bundle
     (D-9).
2. **Phase 1, Option B** (T4–T10). These tasks are independent of each other
   and can run in parallel.
   - The update check reads Releases, in the background.
   - Working state stays beside the novel, with a fallback where Controlled
     folder access protects the novel's folder.
   - The manuscript is changed only through Word.
   - A standalone doc-control is reported.
   - The tools declare annotations, and the setup guide says which approval
     answer to pick.
   - A daily workflow bumps doc-control.
   - The owner moves from the dev entry to the extension.
3. **Phase 2, self-update** (T11–T13).
   - Releases carry a wheel and hashed requirements.
   - `launch.py` picks the newest healthy runtime, and rolls back.
   - Staging builds new runtimes in the background. The "Update
     automatically" checkbox controls it, and "update now" starts it at once.
   - The phase-2 release is the one manual reinstall into self-update.

The test run on a clean PC (T14, `desktop` T10 on the released bundle) closes
the workspace by measuring every §1 criterion.

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "From a merged fix to the writer's chat",
 "nodes": [
  {"id": "pr", "text": "PR with version bump merged"},
  {"id": "tag", "text": "tag vX.Y.Z"},
  {"id": "rel", "text": "release.yml: lock check, pack,\nvalidate, smoke test"},
  {"id": "gh", "text": "GitHub Release\n.mcpb, SHA256SUMS, wheel,\nrequirements, release.json"},
  {"id": "chk", "text": "server: daily background check\n(releases/latest)"},
  {"id": "auto", "text": "Update automatically on?"},
  {"id": "stage", "text": "stage runtime X.Y.Z\n+ self-test"},
  {"id": "launch", "text": "next app start:\nlaunch.py runs X.Y.Z"},
  {"id": "note", "text": "resume/works: update.available\none plain sentence"},
  {"id": "manual", "text": "writer: click, drag, Install"}
 ],
 "edges": [
  {"from": "pr", "to": "tag"},
  {"from": "tag", "to": "rel"},
  {"from": "rel", "to": "gh", "label": "all green"},
  {"from": "gh", "to": "chk"},
  {"from": "chk", "to": "auto", "label": "newer"},
  {"from": "auto", "to": "stage", "label": "yes, no reinstall flag"},
  {"from": "stage", "to": "launch"},
  {"from": "auto", "to": "note", "label": "no, or reinstall"},
  {"from": "note", "to": "manual"}
 ]}
```

### State changes

| Where | Store | Change | Description |
|-------|-------|--------|-------------|
| Writer's profile | `%APPDATA%\literary-critic\folders.json` | UPDATE | A `state` map for works whose state is in the fallback place (T5) |
| Beside the novel | `<novel>/literary-critic/` | — | Unchanged; still the default place (D-3) |
| Fallback | `%OneDrive%\literary-critic\<work>\` or `%USERPROFILE%\literary-critic\<work>\` | CREATE | Only where Controlled folder access protects the novel's folder (T5) |
| Extension state | `<state folder>\update.json` | CREATE/UPDATE | Cache for the daily check, replacing the tag cache (T4) |
| doc-control | its appdata store | CREATE | File backups move there via `DOC_CONTROL_STORE=appdata` (T6) |
| Phase 2 | `%LOCALAPPDATA%\literary-critic\runtime\<X.Y.Z>\`, `runtime\state.json` | CREATE/DELETE | Staged runtimes; two are kept (T12, T13) |
| Owner's app config | `claude_desktop_config.json` | DELETE | The `literary-critic-dev` entry, once the extension is installed (T10) |

### Technology choices

| Choice | Justification |
|--------|--------------|
| Server type `uv`, manifest 0.4 | D-1: no exe of ours, so nothing to sign; pywin32 arrives through `doc-control[live]` |
| Stdlib `zipfile` pack script plus `npx @anthropic-ai/mcpb validate` in CI | Packing needs no Node; validation uses the official tool |
| GitHub Actions on `windows-latest` for the release | The smoke test must import pywin32 and run uv as the app does |
| uv 0.9.7 in the smoke test | The version the app downloads (§2) |
| `uv export --hashes` for phase-2 requirements | Staging installs exactly the lock, with checked hashes |
| Stdlib `launch.py` | It runs before any environment is chosen, so it can import nothing else |
| PowerShell `Get-MpPreference`, then the registry, for Controlled folder access | Read-only and present on every Windows 11; which one a normal user can read is Q-8 |

### Out of scope

- Signing the `.mcpb` (D-12, Q-4).
- Mac, and listing in the extension directory.
- Blocking a standalone doc-control (D-7: reported only).
- Moving existing working folders. A work stays where its state already is.
- Self-updating the manifest or the launcher: those set `reinstall: true`.
- Any change to doc-control itself.

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Pack and CI check | `extension/`, `scripts/pack_mcpb.py`, `.github/workflows/ci.yml` | M | — | `mcpb_validation_errors == 0` | `test_pack_mcpb_contents_and_manifest` in `tests/test_mcpb.py` — the zip holds the manifest, `launch.py`, `pyproject.toml` and `uv.lock`, with no venv; the manifest is 0.4, type `uv`, with the two settings and the version from `pyproject.toml` |
| T2 | Release on tag | `.github/workflows/release.yml`, `scripts/smoke_mcpb.py` | M | T1 | `release_on_tag == 1` | `test_smoke_versions_differ_from_lock_fails` in `tests/test_mcpb.py` — the smoke check fails when an installed version differs from `uv.lock`, and passes on a match |
| T3 | Clean-PC probe | owner, `status/evidence/` | S | T2 | `probes_answered == 6` | `test_release_probe_evidence_answers_open_questions` in `tests/test_status.py` — the evidence file answers desktop Q-3 and Q-8 and spec Q-5 to Q-8, each yes or no, and records VirusTotal for the first release |
| T4 | Update check | `src/litcritic/kit.py`, `mcp.py` | M | T2 | `update_false_alarms == 0` | `test_update_check_cases_no_false_alarm` in `tests/test_kit.py` — older, equal, newer, offline, checkout and no-`.mcpb` cases give `yes` only for older; `test_update_check_slow_network_adds_under_100ms` in `tests/test_mcp.py` — with a 10 s network, `resume` returns within 100 ms |
| T5 | State place | `src/litcritic/cfa.py` (new), `folders.py`, `workspace.py` | M | T3 | `cfa_fallback_correct == 1.0` | `test_state_place_cfa_on_protected_uses_fallback` in `tests/test_folders.py` — with Controlled folder access faked on, nothing is written under the protected folder, OneDrive's root is used when set and the profile otherwise; `test_state_place_cfa_off_beside_novel` — off, the state is beside the novel in all four layouts |
| T6 | Word-only writes | `src/litcritic/docx_cli.py`, `mcp.py`, `dc.py` | M | — | `manuscript_file_writes_by_server == 0` | `test_apply_closed_document_opens_word_no_file_write` in `tests/test_docx_cli.py` — with a fake that records writes, a change to a closed document opens it through `live` and writes no file beside the manuscript; the server's environment has `DOC_CONTROL_STORE=appdata` |
| T7 | Other doc-control | `src/litcritic/mcp.py`, a detection module | S | — | `standalone_doccontrol_reported == 1.0` | `test_resume_reports_standalone_doccontrol_once` in `tests/test_mcp.py` — enabled extension and config entry are reported once; disabled and none are not |
| T8 | Annotations | `src/litcritic/mcp.py`, `prompts/01-chat-guide.md` | S | T3 | `tools_annotated == 1.0` | `test_tools_list_declares_annotations` in `tests/test_mcp.py` — every tool has the annotations in §5, and the read-only set is exactly the seven listed; `test_guide_names_always_allow` in `tests/test_prompts.py` — the setup part tells the writer the answer Q-7 found |
| T9 | doc-control bump | `.github/workflows/doccontrol-bump.yml`, `scripts/doccontrol_bump.py` | S | T2 | `doccontrol_release_to_bump_pr_days <= 1` | `test_bump_in_range_pr_out_of_range_issue` in `tests/test_mcpb.py` — a newer version inside the range gives a lock upgrade plus a patch bump, and one outside gives an issue |
| T10 | Owner switch | owner, `docs/`, `status/evidence/` | S | T8 | `dev_config_entries == 0` | `test_release_owner_switch_evidence` in `tests/test_status.py` — the evidence shows the extension installed, `literary-critic-dev` gone from the config, and works still found |
| T11 | Staging assets | `release.yml`, `scripts/` | S | T3 | `release_assets_complete == 1` | `test_release_assets_requirements_hashed` in `tests/test_mcpb.py` — the requirements file pins every package and the wheel by hash, and `release.json` carries the version and `reinstall` |
| T12 | Launcher | `extension/launch.py` | M | T11 | `rollback_correct == 1.0` | `test_launch_two_failures_roll_back` in `tests/test_launch.py` — a runtime that fails to start twice is marked bad and the previous one runs; with no staged runtime the bundled one runs; two are kept |
| T13 | Self-update | `src/litcritic/staging.py` (new), `mcp.py`, `prompts/` | L | T4, T12 | `auto_update_applied_restarts <= 1` | `test_staging_ready_after_selftest_applied_next_start` in `tests/test_staging.py` — with fake uv and fake Releases, a newer release is staged, self-tested and run at the next start; `auto_update` off or `reinstall: true` gives the notice instead; `check_update` stages at once |
| T14 | Test run | owner + Claude, `status/evidence/` | M | T5, T6, T7, T10, T13 | `install_actions_clean_pc <= 3` | `test_release_test_run_evidence_meets_gates` in `tests/test_status.py` — the record meets every §1 criterion measured on the test run |

### Task details

- **T1 Pack and CI check** (bundle, pack and CI check) (supersedes `desktop` T8):
  - `extension/` holds the manifest (§5), an icon and `launch.py`. In phase 1,
    `launch.py` only runs `lc mcp` with the granted folders.
  - `scripts/pack_mcpb.py` zips the manifest, `launch.py`, `pyproject.toml`,
    `uv.lock`, `src/` and `prompts/`.
  - The CI job runs `uv lock --check`, the pack and `mcpb validate`, and keeps
    the `.mcpb` as an artifact.
- **T2 Release on tag** (release on tag, with smoke test):
  - Merging a version bump tags `vX.Y.Z`.
  - The tag runs `release.yml` on `windows-latest`. The job:
    - checks that the tag matches `pyproject.toml`;
    - packs and validates the bundle;
    - runs `scripts/smoke_mcpb.py`: unzip, uv 0.9.7 `uv sync` with no system
      Python, JSON-RPC `initialize`, `tools/list` and `works`, the installed
      versions compared with `uv.lock`, and the pywin32 import;
    - publishes the Release with the `.mcpb`, `SHA256SUMS` and plain notes.
  - This task ends by cutting the first release.
- **T3 Clean-PC probe** (clean-PC probe on the released bundle) (`desktop` T1, run on the
  real file):
  - The PC is Windows Sandbox or a fresh account, with Controlled folder
    access on and no Python or uv.
  - The owner downloads the Release's `.mcpb`, drags it onto the app and
    presses Install.
  - Records:
    - each warning, word for word (desktop Q-8);
    - whether the server starts and pywin32 imports (desktop Q-3);
    - whether the server sees `UV` (Q-5);
    - a reinstall of the same file, to see whether the settings are kept
      (Q-6);
    - every approval question the app asks, and whether a group allow exists
      (Q-7);
    - whether a normal user can read the Controlled folder access settings
      (Q-8);
    - the VirusTotal result.
  - Evidence goes to `status/evidence/release-probe.md`, and the spec's open
    questions are updated.
  - If the `uv` type fails, stop and revise the spec (D-1).
- **T4 Update check** (update check via Releases):
  - `kit.update_check` reads `releases/latest` and needs a `.mcpb` asset.
  - It runs in a thread started with the server, at most once a day, and
    writes `update.json`.
  - `resume` and `works` add `update`.
  - `works(check_update=true)` skips the daily limit.
  - The guide keeps install D-2's sentence rules.
- **T5 State place** (working state with a Controlled folder access fallback):
  - `cfa.py` reads whether Controlled folder access is on and which folders
    it protects, from PowerShell or the registry, with a fake for tests.
  - Before the first write for a work, the place is chosen: beside the
    novel, or else the fallback. The choice is recorded in `folders.json`
    and returned once as `state_place`.
  - If the settings cannot be read, the tool tries the novel's folder once
    and falls back if the write is refused (`winblock.kind`).
- **T6 Word-only writes** (manuscript only through Word):
  - When the document is closed, `apply_edits` asks the live engine to open
    it in Word, then applies the change. The file engine is never used on the
    manuscript.
  - Without Word, the result is a card that describes the change.
  - `mcp.py` sets `DOC_CONTROL_STORE=appdata` before doc-control is loaded.
- **T7 Other doc-control** (report a standalone doc-control):
  - Read the app's `extensions-installations.json` (enabled entries only)
    and `claude_desktop_config.json`.
  - `resume` adds `other_doc_control` once per conversation, and the guide
    turns it into one sentence.
- **T8 Annotations** (tool annotations and the setup sentence):
  - The annotations in §5 are added to `Tool` and to `Tool.to_dict`.
  - The guide's setup part says which answer to pick, in the words Q-7
    found.
- **T9 doc-control bump** (daily):
  - A scheduled workflow reads doc-control's PyPI JSON.
  - For a version inside the range, it runs
    `uv lock --upgrade-package doc-control`, bumps the patch version and
    opens a PR. Merging the PR releases.
  - For a version outside the range, it opens an issue.
- **T10 Owner switch** (owner moves to the extension) (D-11):
  - The owner installs the released `.mcpb` on their own PC and removes the
    `literary-critic-dev` entry. The works are found through the shared
    `folders.json`.
  - `docs/` drops the dev-entry instructions and says how a fix reaches the
    owner: a merge, then a release, then an update.
- **T11 Staging assets** (release assets for staging):
  - `release.yml` also builds the wheel, `uv export --hashes` (with the wheel
    pinned by hash) and `release.json`.
  - `reinstall` is true when `extension/` changed since the last release.
- **T12 Launcher** (launcher with rollback):
  - `launch.py` reads `runtime\state.json` and runs the newest ready runtime.
  - It counts failed starts, which are exits within 10 s of start. After two,
    it marks the runtime bad and runs `previous`, or the bundled runtime.
  - It keeps two runtimes and is stdlib only.
- **T13 Self-update** (staging, the checkbox and update now):
  - `staging.py` checks after the update check. It uses `UV`, or a uv it
    downloads with a pinned checksum, as Q-5 decided.
  - It builds `runtime\X.Y.Z\` with `--require-hashes`, self-tests with
    `initialize` and `tools/list`, and marks the runtime ready.
  - `LC_AUTO_UPDATE` turns it off.
  - `works(check_update=true)` stages at once and returns
    `restart_needed`.
  - The first start on a new version returns `update.applied` once.
  - The phase-2 release sets `reinstall: true`, so phase-1 installs are told
    to reinstall once.
- **T14 Test run** (test run on a clean PC) (`desktop` T10, run on the released
  bundle):
  - Install the phase-2 release from its link.
  - Run the scripted session from §1 with the novel in Documents and
    Controlled folder access on.
  - Then publish a patch release and restart the app once.
  - Read Windows Security's protection history.
  - The transcripts and the history give every §1 criterion.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**:
- T1, then T2, then T3. This is the first chain.
- T6 and T7 can start at once, in parallel with that chain.
- After T2: T4 and T9.
- After T3: T5 (which needs Q-8), T8 (which needs Q-7) and T11. T10 after T8.
- Phase 2 in a row after T3: T11, then T12, then T13 (which also waits for
  T4).
- T14 last. T9 is not needed for it and can land any time.

**Branch pattern**: `release-T<N>-description` from the default branch.

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies",
 "nodes": [
  {"id": "T1", "text": "T1\nPack and CI check"},
  {"id": "T2", "text": "T2\nRelease on tag"},
  {"id": "T3", "text": "T3\nClean-PC probe"},
  {"id": "T4", "text": "T4\nUpdate check"},
  {"id": "T5", "text": "T5\nState place"},
  {"id": "T6", "text": "T6\nWord-only writes"},
  {"id": "T7", "text": "T7\nOther doc-control"},
  {"id": "T8", "text": "T8\nAnnotations"},
  {"id": "T9", "text": "T9\ndoc-control bump"},
  {"id": "T10", "text": "T10\nOwner switch"},
  {"id": "T11", "text": "T11\nStaging assets"},
  {"id": "T12", "text": "T12\nLauncher"},
  {"id": "T13", "text": "T13\nSelf-update"},
  {"id": "T14", "text": "T14\nTest run"}
 ],
 "edges": [
  {"from": "T1", "to": "T2"},
  {"from": "T2", "to": "T3"},
  {"from": "T2", "to": "T4"},
  {"from": "T3", "to": "T5"},
  {"from": "T3", "to": "T8"},
  {"from": "T2", "to": "T9"},
  {"from": "T8", "to": "T10"},
  {"from": "T3", "to": "T11"},
  {"from": "T11", "to": "T12"},
  {"from": "T4", "to": "T13"},
  {"from": "T12", "to": "T13"},
  {"from": "T5", "to": "T14"},
  {"from": "T6", "to": "T14"},
  {"from": "T7", "to": "T14"},
  {"from": "T10", "to": "T14"},
  {"from": "T13", "to": "T14"}
 ]}
```

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

---

## Sign-off

- [ ] Plan reviewed by the owner
- [ ] Q-5 to Q-8 answered (T3)
- [ ] Ready for execution
