# Plan: one plain desktop chat for the whole novel

**Date**: 2026-10-14
**Specification**: `arsenal/project/desktop/spec.md` (approved, revision 5)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the approved spec (Option B); T1 runs the Q-3 and Q-8 probes first

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

---

## Technical solution

### Architecture overview

One desktop extension, `literary-critic.mcpb`, whose server is `lc mcp`:

1. **Probes first** (T1): the owner runs the probe extension on a clean
   Windows (Sandbox or a spare account) to answer Q-3 (does the `uv` type
   work with no uv or Python, and does pywin32 install), and installs a
   self-signed copy to answer Q-8 (which warnings remain). The answers fix
   the server type and the walkthrough's words before anything is built on
   them.
2. **Server core** (`src/litcritic/mcp.py`): a small stdlib JSON-RPC loop
   (D-4), a tool table, one result shape, errors as results.
3. **Folders** (`src/litcritic/folders.py`): granted folders from the
   install argument plus `folders.json`; work lookup one level deep; one
   confinement function every tool calls.
4. **Tools**: `works`, `resume` (with the guide, D-12), `add_folder` (Windows
   picker, UTF-8), `locate`/`places`/`select` through `dc.py` and
   `doc_control.api.run`, `show`/`find`/`ask`, and the allow-listed `run`.
5. **Packaging**: `extension/manifest.json`, icon, `pyproject.toml` for the
   `uv` type, `scripts/pack_mcpb.py` (stdlib zip), and a CI job that
   validates the manifest and builds the `.mcpb`.
6. **Prompts and skill**: the guide text lives in `prompts/` and is what
   `resume` returns; any skill goes through skill-workshop (D-9).
7. **Walkthrough**: the owner installs from the release file on a clean
   machine and works through scripted requests; transcripts measure the §1
   criteria.

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "Work on my novel",
 "nodes": [
  {"id": "w", "text": "writer: let's work on my novel"},
  {"id": "res", "text": "resume"},
  {"id": "lk", "text": "folder lookup"},
  {"id": "nf", "text": "not found: works + hint"},
  {"id": "add", "text": "add_folder picker"},
  {"id": "st", "text": "state + guide"},
  {"id": "loc", "text": "locate / places"},
  {"id": "dc", "text": "doc_control.api.run live.select"}
 ],
 "edges": [
  {"from": "w", "to": "res"},
  {"from": "res", "to": "lk"},
  {"from": "lk", "to": "st", "label": "found"},
  {"from": "lk", "to": "nf", "label": "not found"},
  {"from": "nf", "to": "add", "label": "writer agrees"},
  {"from": "add", "to": "st"},
  {"from": "st", "to": "loc", "label": "take me there"},
  {"from": "loc", "to": "dc"}
 ]}
```

### State changes

| Where | Store | Change | Description |
|-------|-------|--------|-------------|
| writer's profile | `%APPDATA%\literary-critic\folders.json` | CREATE/UPDATE | folders added with `add_folder` |
| working folder | `<work>/literary-critic/.cache/last_used` | CREATE/UPDATE | orders `works`; disposable |
| app | extension install folder | CREATE | written by the app at install; not touched by lc |

### Technology choices

| Choice | Justification |
|--------|--------------|
| own stdlib JSON-RPC server | doc-control's `mcp` module is internal (Q-1, D-4); runtime stays stdlib (AGENTS.md rule 9) |
| `uv` server type, pending T1 | the host builds the environment, so doc-control installs as a dependency; `binary` then a Node launcher if T1 says no |
| PowerShell FolderBrowserDialog with UTF-8 output | tkinter garbled accented paths in the probe |
| doc-control through `dc.py` and `doc_control.api.run` only | stable entry point; only `dc.py` imports doc-control |
| stdlib `zipfile` pack script | no Node on the build machine for the `mcpb` CLI; the CI job can still run `mcpb validate` |

### Out of scope

- Mac support (the live engine and the picker are Windows-only today).
- Publishing the `.mcpb` (Q-4: the owner decides where).
- Changing the working-folder format or any CLI command's behaviour.
- A plugin or skill unless T9's comparison shows the guide in results is weaker (D-8).
- doc-control's own packaging or places page (Q-5 is asked of doc-control).

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Probes Q-3 and Q-8 | owner, `status/evidence/` | S | — | `probes_answered == 2` | `test_desktop_probe_evidence_answers_q3_q8` in `tests/test_status.py` — the evidence file exists and answers Q-3 (uv type on a clean machine, pywin32) and Q-8 (warnings when signed) yes or no |
| T2 | MCP server core | `src/litcritic/mcp.py`, `cli.py` | M | — | `jsonrpc_transcript_pass == 1.0` | `test_mcp_transcript_initialize_list_call_matches` in `tests/test_mcp.py` — a recorded initialize, tools/list, tools/call, ping and unknown-method transcript replays with identical responses |
| T3 | Folders and confinement | `src/litcritic/folders.py` | M | T2 | `paths_outside_novels_folder_refused == 1.0` | `test_confine_outside_paths_refused` in `tests/test_folders.py` — `..`, absolute, junction/symlink and sibling-prefix paths are all refused; paths under a granted folder pass |
| T4 | works and resume with the guide | `src/litcritic/mcp.py`, `prompts/` | M | T3 | `resume_tool_calls <= 2` | `test_resume_named_work_returns_state_and_guide` in `tests/test_mcp.py` — one call returns state, next step and a guide of at most 400 words; an unknown name returns `not_found` with the works and the `add_folder` hint |
| T5 | add_folder picker | `src/litcritic/folders.py` | S | T3 | `accented_folder_roundtrip == 1.0` | `test_add_folder_decodes_utf8_accents` in `tests/test_folders.py` — with the picker mocked to print an accented path in UTF-8, the stored and returned folder equals it; empty output gives `cancelled` |
| T6 | locate, places and select | `src/litcritic/mcp.py`, `dc.py`, `src/litcritic/ui/places.html` | M | T4 | `places_render_as_buttons == 1.0` | `test_places_result_carries_ui_resource` in `tests/test_mcp.py` — the result links `ui://literary-critic/places`, the resource lists one button per target, and `select` calls `doc_control.api.run("live.select", …)` |
| T7 | show, find, ask, run | `src/litcritic/mcp.py` | S | T4 | `run_disallowed_refused == 1.0` | `test_run_refuses_commands_outside_allow_list` in `tests/test_mcp.py` — `guard`, `init`, `kit` and a shell string are refused; `round status` runs |
| T8 | Manifest, pack and CI | `extension/`, `scripts/pack_mcpb.py`, `.github/workflows/` | M | T1, T6, T7 | `mcpb_validation_errors == 0` | `test_pack_mcpb_contents_and_manifest` in `tests/test_pack.py` — the zip holds the manifest, server and `pyproject.toml`, no venv; the manifest has the 0.4 fields, the `directory` `multiple` setting and the server type T1 chose |
| T9 | Guide wording and skill check | `prompts/`, skill-workshop | S | T4 | `skill_workshop_errors == 0` | `test_guide_prompt_names_channels_rules_and_done` in `tests/test_prompts.py` — the guide names both channels, the writer rules and the one-call jump; any skill file passes skill-workshop's validator |
| T10 | Walkthrough | owner + Claude, `status/evidence/` | M | T5, T8, T9 | `writer_setup_actions <= 3` | `test_desktop_walkthrough_evidence_meets_gates` in `tests/test_status.py` — the record shows setup actions ≤ 3, generic requests and novel switches resolved 10 of 10, jumps p50 ≤ 8 s |

### Task details

- **T1 Probes Q-3 and Q-8**: the owner opens Windows Sandbox (or a spare account) with no uv or Python, installs the Claude app, signs in and drags in the probe `.mcpb` with doc-control's live extra added as a dependency; records whether the server starts, whether pywin32 imports, and the time to first start. Then a self-signed probe (`mcpb sign --self-signed` from a machine with Node, or the CI job) is installed on the owner's PC; each warning is written down word for word. Results in `status/evidence/desktop-Q3-Q8.md`; the spec's Q-3 and Q-8 are updated.
- **T2 MCP server core**: `lc mcp` reads newline-delimited JSON-RPC on stdin; tool table with name, description, input schema and handler; `isError` results for faults; echoes the client protocol version; logs to the extension's state folder.
- **T3 Folders and confinement**: granted folders from argv, `folders.json` read/write, work lookup one level deep, `confine(path)` used by every tool.
- **T4 works and resume with the guide**: descriptions phrased for "work on my novel"; `resume` returns state, open round, next step and the guide from `prompts/`.
- **T5 add_folder picker**: PowerShell `-STA` FolderBrowserDialog on a topmost form, UTF-8 console output, 10-minute timeout.
- **T6 locate, places and select**: thin wrappers over the existing `docx locate --go` and `docx places`; the places page adapted from doc-control 0.6.3 with its version pinned in a test; `select` proxies `live.select`.
- **T7 show, find, ask, run**: wrappers over the CLI subcommands; `run` allow-list on the first word, argv never a shell string.
- **T8 Manifest, pack and CI**: manifest, icon, `pyproject.toml` depending on `doc-control[live]`; the pack script; CI builds the `.mcpb` as an artifact and runs `mcpb validate`.
- **T9 Guide wording and skill check**: the guide (≤ 400 words) in `prompts/`; compare a chat with and without a skill on five generic requests; a skill is written only if the guide loses, and then through skill-workshop.
- **T10 Walkthrough**: on a clean machine, install by drag, pick the folder, allow tools; ten generic requests, two novel switches (one via `add_folder` with an accented folder name), ten jumps; the transcripts give every §1 criterion.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1 and T2 in parallel; T3 after T2; T4 and T5 after T3; T6, T7 and T9 after T4; T8 after T1, T6 and T7; T10 last.
**Branch pattern**: `desktop-T<N>-description` from the default branch

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies",
 "nodes": [
  {"id": "T1", "text": "T1\nProbes Q-3 and Q-8"},
  {"id": "T2", "text": "T2\nMCP server core"},
  {"id": "T3", "text": "T3\nFolders and confinement"},
  {"id": "T4", "text": "T4\nworks and resume with the guide"},
  {"id": "T5", "text": "T5\naddfolder picker"},
  {"id": "T6", "text": "T6\nlocate, places and select"},
  {"id": "T7", "text": "T7\nshow, find, ask, run"},
  {"id": "T8", "text": "T8\nManifest, pack and CI"},
  {"id": "T9", "text": "T9\nGuide wording and skill check"},
  {"id": "T10", "text": "T10\nWalkthrough"}
 ],
 "edges": [
  {"from": "T2", "to": "T3"},
  {"from": "T3", "to": "T4"},
  {"from": "T3", "to": "T5"},
  {"from": "T4", "to": "T6"},
  {"from": "T4", "to": "T7"},
  {"from": "T1", "to": "T8"},
  {"from": "T6", "to": "T8"},
  {"from": "T7", "to": "T8"},
  {"from": "T4", "to": "T9"},
  {"from": "T5", "to": "T10"},
  {"from": "T8", "to": "T10"},
  {"from": "T9", "to": "T10"}
 ]}
```

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

---

## Sign-off

- [ ] Plan reviewed by the owner
- [ ] Q-3 and Q-8 answered (T1)
- [ ] doc-control asked about Q-5
- [ ] Ready for execution
