# Plan: chat-first literary-critic for non-technical writers

**Date**: 2026-10-11
**Specification**: `arsenal/project/chat/spec.md` (approved, revision 2)
**Author**: imarcos + Claude
**Revision**: 1
**Status**: approved (2026-10-11, revision 1) — without annotations (the owner asked to create the tasks and start implementing overnight)
**Revision log**:
- r1 — first draft

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the plan-notes export it applied,
> committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

---

## Technical solution

### Architecture overview

```text
writer: "I want to use literary-critic for my novel"
   │
   ▼
Skill (litcritic) ── fetch tool (B) / uploaded zip (A)
   │
   ▼
05-setup prompt ── lc setup ── finds manuscript + versions, workspace MyNovel/literary-critic/
   │
   ▼
guided rounds (00-guide, 40, 60) ── Codex, metrics, issues (existing)
   │ writer approves a change
   ▼
lc docx edits / rename ── safe_edit (lock, on-disk change, backup, verify, restore)
   │                         └── docx_edit (tracked revisions, byte-preserving)
   ▼
word_live adapter ── locate / save / close / reopen
   ├── today: instructions for the agent (computer use + Find), manual fallback
   └── later: Word-control extension (separate project, same interface)
```

- `docx_edit.py` knows OOXML: paragraphs, runs and revisions. It writes nothing to disk.
- `safe_edit.py` owns the file on disk: locks, hashes, backups, atomic replace, verify, restore. It calls `docx_edit` and knows nothing about novels.
- `word_live.py` is the one adapter to the open Word.
- `setup.py` handles discovery and the workspace in the novel's folder.

### Data flow

1. **Setup:** `lc setup --folder` scans the folder, groups versions (name stem plus text similarity of the opening paragraphs), takes the newest as the manuscript, creates the workspace, ingests and anchors it.
2. **Round:** the writer approves a change. The agent writes `edits.json` (quote plus context, replacement) and runs `lc docx edits`. `safe_edit` checks, backs up, applies, verifies and logs. The result goes to the writer in one short message.
3. **Live:** `lc docx locate` gives the unique Find string. The agent uses computer use to bring Word to that passage, or gives the writer the plain locator.

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| workspace | `state/documents.json` | CREATE/UPDATE | Hash and modification time of each document at its last read |
| workspace | `backups/` | CREATE | A copy before every write; the last 20 are kept |
| workspace | `log/edits.jsonl` | CREATE | Append-only record of applied edits and renames |
| manuscript | the writer's `.docx` | UPDATE | Tracked revisions only, approved by the writer |
| profile | `analysis/profile.toml` | UPDATE | `prose_suggestions`, `ai_notice_ack` |

### Technology choices

| Choice | Justification |
|--------|--------------|
| OOXML edited as text with stdlib `zipfile` + regex/ElementTree, the same approach as `docx_out.py` | Keeps every untouched byte, runs in chat sandboxes, needs no dependencies (rule 9) |
| Tracked revisions (`w:ins` / `w:del`, author `literary-critic`) | Every Word version shows them and lets the writer reject each one |
| Quote plus prefix/suffix addressing (W3C TextQuoteSelector style, as in `spans.py`) | Survives edits and refuses ambiguous matches |
| Computer use behind an adapter | Works today with no install; the separate extension can replace it later |

### Out of scope

- The Word-control extension itself (separate project; only its interface is defined here).
- The Microsoft 365 side panel, the comment bridge, and Google Docs editing (D-19, D-15).
- Rewriting prose for the writer. Edits apply text the writer approved; wording suggestions only appear when `prose_suggestions` is on.
- `.odt` editing (read-only, as today).

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| W1 | `docx_edit.py`: apply text edits addressed by quote plus context as tracked revisions (split runs at the boundaries, keep `w:rPr`, refuse matches that cross fields or existing revisions); whole-word rename; no disk I/O | lc | L | — | `unintended_docx_changes == 0` | `test_edits_change_only_target_text` in `tests/test_docx_edit.py` — across docgen fixtures, the text after applying equals the expected text, and every part except `document.xml` is byte-identical; `test_edits_are_tracked_revisions` — each edit is a `w:del` plus `w:ins` pair, and rejecting all of them restores the original text |
| W2 | `safe_edit.py`: lock-file and on-disk-change checks, backup, temp write, atomic replace, verify, automatic restore, `state/documents.json`, `log/edits.jsonl` | lc | M | W1 | `restore_on_failure == 1.0` | `test_failure_at_each_step_restores_original` in `tests/test_safe_edit.py` — failures injected after backup, write and verify leave the original byte-identical; `test_locked_or_changed_document_is_refused` — a `~$` lock or a changed hash means nothing is written |
| W3 | CLI `lc docx edits / rename / locate / status` with JSON output; the unique Find string for `locate` | lc | M | W2 | `docx_cli_contract_ok == 1` | `test_docx_cli_contracts` in `tests/test_docx_cli.py` — every command prints the documented JSON keys and exit codes; `test_locate_find_string_is_unique` — on the corpus, every paragraph's Find string matches exactly once and is at most 255 characters |
| W4 | `lc setup`: manuscript and version discovery, environment report, workspace in `<folder>/literary-critic/`, ingest and anchor | lc | M | — | `novel_discovery_accuracy == 1.0` | `test_setup_picks_latest_draft_and_lists_versions` in `tests/test_setup.py` — on a fixture folder with drafts, copies, a backup and an unrelated document, it names the latest draft and lists the versions in date order; `test_setup_reuses_existing_workspace` — a second run changes nothing |
| W5 | Prose-suggestion setting with the AI-text notice (D-22); `AGENTS.md` rule 5 and the prompts reworded | lc, prompts | S | W4 | `prose_suggestions_default_off == 1` | `test_prose_suggestions_off_until_notice_acknowledged` in `tests/test_setup.py` — a new workspace has it off, and turning it on without `--ack-ai-notice` exits 1 and prints the notice |
| W6 | `word_live.py` adapter plus `docs/word-control-interface.md`; `80-live-word` prompt (computer use: bring Word to a passage, save, close, reopen; manual fallback) | lc, docs, prompts | S | W3 | `word_helper_interface_documented == 1` | `test_word_live_adapter_matches_interface_doc` in `tests/test_word_live.py` — every operation in the doc exists in the adapter with the same payload keys, and the default implementation returns manual instructions |
| W7 | Prompts for the guided flow: `05-setup` (wizard: capabilities, what to enable, Pro/Cowork vs basic mode, OS limits), `00-guide` (plan, accept/change/reject, short answers), `60-rounds` (apply approved edits with `lc docx`) | prompts | M | W3, W4, W5, W6 | `prompt_commands_parse == 1` | `test_prompt_commands_parse` in `tests/test_prompts.py` — every `lc` command in the prompts parses, including the new ones |
| W8 | Skill entry and packaging: `SKILL.md` as the entry point (fetch the tool, else upload steps); `lc kit --skill` builds a Skill zip with the kit bundled | skill, lc | M | W7 | `skill_workshop_errors == 0` | `test_skill_zip_builds_and_validates` in `tests/test_kit.py` — the zip has `SKILL.md` at its root and the kit inside, under 30 MB; skill-workshop `validate.py` passes on the repo skill |
| W9 | Scripted usability walkthrough (writer persona, main path, then Word open the whole time) and hand-test checklists for the owner (D-18, D-7 path B, computer-use locate on Mac/Windows) | evidence | M | W8 | `writer_setup_actions <= 5` | Scripted review recorded in `status/evidence/W9-walkthrough.md` — setup actions counted, median writer-facing reply at most 120 words, every instruction located and one step at a time |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: W1 → W2 → W3, with W4 → W5 in parallel; then W6, W7, W8, W9.
**Branch pattern**: the session's designated branch, one PR per task.

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|
| W1 | `unintended_docx_changes == 0` | 0 (8 docgen fixtures × 6 edits; text, other parts and document.xml outside edited paragraphs compared); rejecting all revisions restores the original text | `uv run pytest tests/test_docx_edit.py` | [HERE] | local | 2026-10-12 |
| W2 | `restore_on_failure == 1.0` | 1.0 (7/7: failures injected after backup, temp write, verification and replace, plus two invalid packages and an unexpected change; original byte-identical each time, no temp file left); locked (Word and LibreOffice lock files) and changed-on-disk documents refused | `uv run pytest tests/test_safe_edit.py` | [HERE] | local | 2026-10-12 |
| W3 | `docx_cli_contract_ok == 1` | 1 (21/21 contract checks: `status`, `locate` by anchor and quote, `edits` dry run/apply/refused, locked and stale documents refused, `rename` dry run and apply, unreadable file refused, exit 2 on bad input); Find strings follow Word's Find (any case, `^p ^t ^l ^~ ^s ^^`); Find strings unique and ≤255 chars for 100% of the corpus paragraphs (marianela as .docx, 1000+ paragraphs) | `uv run pytest tests/test_docx_cli.py` | [HERE] | local | 2026-10-12 |
| W4 | `novel_discovery_accuracy == 1.0` | 1.0 (6/6 checks on 5 fixture folders: drafts v1–v3 with copies, a backup, an `.md` export, unrelated notes and a letter, and a Word lock file; drafts with no number; only copies; a newer excerpt, a rewritten opening and a long unrelated book; a newer Markdown draft and a title ending in a number); latest draft named, versions newest first, unrelated documents apart; a second run writes nothing | `uv run pytest tests/test_setup.py` | [HERE] | local | 2026-10-12 |
| W5 | `prose_suggestions_default_off == 1` | 1 (a new workspace reports it off; `--prose-suggestions on` without `--ack-ai-notice` exits 1, prints the notice in the work's language and leaves the profile byte-identical; with it, on plus the acknowledgement time, the rest of the profile kept; off removes the acknowledgement) | `uv run pytest tests/test_setup.py -k prose` | [HERE] | local | 2026-10-12 |
| W6 | `word_helper_interface_documented == 1` | 1 (7/7 operations: request and response keys in `docs/word-control-interface.md` equal the adapter's; each default answer is `manual` with computer-use steps and a writer line); the extension command is used when set and falls back to manual steps when it fails | `uv run pytest tests/test_word_live.py` | [HERE] | local | 2026-10-12 |

### Dependency graph

```text
W1 ─> W2 ─> W3 ─┬─> W6 ─┐
W4 ─> W5 ───────┴───────┴─> W7 ─> W8 ─> W9
```

---

## Sign-off

- [x] Design reviewed (owner pre-approved execution)
- [x] Contracts agreed (spec §5)
- [x] Migration strategy validated (additive only)
- [x] Ready for execution
