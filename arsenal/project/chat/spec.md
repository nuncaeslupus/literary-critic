# Specification: chat-first literary-critic for non-technical writers

**Date**: 2026-10-11
**Ticket / PR**: workspace `chat`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the explore-idea decisions log D-1…D-18

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<project>-spec-notes-<date>-r1.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

---

## 1. Problem statement

Today literary-critic needs someone technical to use it. You need a terminal or a code-running chat, a workspace path, `lc` commands, and, in a chat, uploading the kit and a workspace zip every session. The no-code "reduced mode" loses metrics, the Codex and every check that a script measures. A non-technical writer (or an agency reader) cannot start, and the changes the tool recommends still have to be found and typed by hand in Word. That costs time and creates stray copies of the manuscript.

The tool should start from one sentence in a normal Claude chat: "I want to use literary-critic for my novel".
- A setup wizard checks what the writer's Claude and computer can do, says exactly what to turn on, finds the novel and its versions, and prepares a working folder.
- The tool then guides the writer through a plan in short, targeted messages. The writer accepts, changes or rejects each step.
- Accepted changes land in the writer's own `.docx` as tracked changes, safely, without new copies.
- Writers with Microsoft 365 can work from a Claude side panel inside Word, with the text changing live in front of them.

This is a planned improvement. It decides whether the tool is usable by its target users at all.

**Success criteria (measurable)**

- [ ] `writer_setup_actions <= 5` on the main path (Pro plan, Cowork). These are the actions the writer performs between "I want to use literary-critic for my novel" and the first feedback on the novel: toggles, folder picks, uploads and permission clicks. Counted on a scripted walkthrough checklist.
- [ ] `wizard_capability_misreports == 0` over the scripted environment cases: code execution on/off, folder connected or not, computer use on/off, Word 365 or perpetual Word, Windows Home, Free plan.
- [ ] `novel_discovery_accuracy == 1.0` on a fixture folder with drafts, copies, backups and unrelated `.docx` files. The wizard names the latest draft and lists the other versions in date order.
- [ ] `unintended_docx_changes == 0`: across a corpus of fixture manuscripts, the text diff after an approved edit batch equals exactly the approved edits, and styles, comments and other parts are byte-identical outside the edited runs.
- [ ] `edits_as_tracked_revisions == 1.0`: every applied edit is a native Word revision (`w:ins` / `w:del`) that can be rejected one by one. Checked by script, and opening in Word 2016-compatible OOXML is validated.
- [ ] `backup_before_edit == 1.0` and `restore_on_failure == 1.0`, with failures injected at each step of the safe-edit protocol.
- [ ] `open_document_overwrites == 0`: an edit never writes a file that Word holds open (Word's `~$` lock file) or that changed on disk since it was last read.
- [ ] `bridge_roundtrip_accuracy == 1.0`: round actions written as tagged comments (`[LC A3]`), with decisions written as replies in those threads, are read back into Codex `decision` items exactly, on fixture documents.
- [ ] `prose_suggestions_default_off == 1`: a new workspace never proposes wording until the writer turns the setting on. Tested.
- [ ] `skill_workshop_errors == 0` for the litcritic skill (validate.py and audit_library).
- [ ] Usability, judged by a scripted walkthrough: a fresh assistant plays a non-technical writer persona from the first sentence to an applied round-1 change on the main path, and a second run on the Word-panel path. The reviewer checks that every instruction to the writer is plain, located and one step at a time. Median writer-facing reply is at most 120 words.
- [ ] The hand tests D-14, D-16 and D-18 are run and recorded in `status/evidence/` before any task that depends on their answer is designed.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| Setup wizard (new: `lc setup` plus a `05-setup` prompt) | Primary | Detects capabilities, explains what to enable, finds the novel and its versions, creates `MyNovel/literary-critic/` | Yes | New entry point for every writer | High |
| Safe docx editor (new module, stdlib) | Primary | Applies approved edits and renames to the master `.docx` as tracked changes, after the lock-file and on-disk-change checks, with backup, verification and automatic restore | Yes | Writes the writer's manuscript, the highest-risk change the tool has made | High |
| Comment bridge (`docx_out` + `rounds`) | Primary | Writes round actions as tagged comments into the master, reads reply decisions back into the Codex, removes finished comments | Yes | Links Cowork with the Word side panel | Med |
| litcritic Skill and packaging (`kit.py`, `.claude/skills/litcritic`) | Primary | Entry instructions for chat, Cowork and the Word panel; builds the Skill zip with the kit bundled | Yes | How the tool is installed and recognised in each surface | Med |
| Prompts (`00-guide`, new `05-setup`, new `80-word-panel`) | Dependent | Guided flow, short answers, one change per message, Word-panel procedure | Yes | What the writer experiences | Med |
| Profile schema and `AGENTS.md` rule 5 | Shared resource | New per-writer setting `prose_suggestions` (default off); rule 5 reworded to match | Yes | Changes a hard rule of the project | Med |
| Codex, rounds, sync (existing) | Dependent | Decisions from comment replies; a new draft is detected when the master file changes | Validation, small changes | Must keep their gates green | Low |
| Claude surfaces (chat, Cowork, computer use, Claude for Word, Drive connector) | Infrastructure (external) | Where the tool runs; not ours to change | No (validation) | Their limits shape the design: Cowork needs a paid plan and an Apple Silicon Mac or Windows Pro/Enterprise/Education; the Word panel needs Word 365 or Word on the web | High |
| docx-fixer (separate repo) | Dependent (external) | Existing Word-fixing logic | Validation; reuse decided in design | Kept as a separate repo (earlier decision) | Low |

**Impact dimensions**
- **Data:** the master manuscript is edited in place, and only on explicit approval of each change or batch. Backups in `literary-critic/backups/` are the safety net. *High.*
- **API:** new `lc setup` and `lc docx` commands; nothing removed. *Low.*
- **Performance:** a rename across a 100k-word `.docx` must take seconds, not minutes. *Low.*
- **User-facing:** the whole experience changes from commands to a guided conversation. *High.*
- **Operational:** a Skill zip is released per version, and a computer-use preview may change under us. *Med.*
- **Risk of inaction:** the tool stays usable only by its author.

## 3. Options

### Option A: Wizard prompt and commented copies (Conservative)

- **Description**: Add a setup prompt and plain-language install docs on top of the current kit. Feedback reaches Word only as a commented **copy** of the manuscript; there are no in-place edits and no Word-panel bridge.
- **Scope**: `prompts/`, `kit/START_HERE.md`, docs, small `docx_out` changes.
- **Effort**: Small
- **Tradeoffs**: Lowest risk to the manuscript. It contradicts D-9/D-11: copies multiply versions, the writer still searches and types every change, and the 365 side panel is unused.
- **Compatibility**: Fully backward compatible.

### Option B: Cowork-first wizard, safe in-place editing, Word-panel bridge (Recommended)

- **Description**:
  - The wizard runs in chat or Cowork. Claude fetches the tool itself, or falls back to the Skill zip.
  - In Cowork it finds the novel, prepares `MyNovel/literary-critic/`, and runs the guided rounds.
  - Approved edits and renames are applied to the master `.docx` as tracked changes through the safe-edit protocol. When computer use is on, it saves, closes and reopens Word for the writer.
  - For Word 365 users, round actions travel as tagged comments in the master. The Skill tells the Word panel how to work through them live, and the replies come back into the Codex.
  - Free plan: basic mode with the existing kit (upload and workspace zip).
- **Scope**: new setup module and prompt, new safe docx editor, comment bridge in `docx_out`/`rounds`, Skill and packaging, prompts, profile setting, rule 5, docs.
- **Effort**: Large
- **Tradeoffs**: Meets every agreed decision, and the heavy analysis stays where scripts can run. The cost is the most code, and it writes the writer's own manuscript, which is acceptable only with the safe-edit gates above. Computer use is a preview, so every step it helps with must also work without it.
- **Compatibility**: Backward compatible: existing CLI, Codex and rounds are unchanged; the new commands are additive.

### Option C: Word-panel-first

- **Description**: Make the Word side panel the main surface. All analysis runs inside the add-in, and the state travels inside the document.
- **Scope**: Skill and prompts; the analysis is re-expressed for the add-in.
- **Effort**: Large
- **Tradeoffs**: The best live experience, but it depends on D-16 (scripts may not run in the panel), loses the Codex (the panel cannot read the folder), excludes perpetual Word and Free, and is bounded by the panel's limits (it sees only open documents, its history is per device).
- **Compatibility**: Breaks the script-first rule (`AGENTS.md` rule 7) unless D-16 proves scripts run there.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large | Large |
| Risk | Low | Medium (manuscript writes, gated) | High (unverified platform) |
| Completeness | Low: no in-place edits, no side panel | High: every agreed decision | Partial: 365 only, no Codex |
| Compatibility | Full | Full (additive) | Conflicts with rule 7 unless D-16 passes |
| Maintenance | Low | Medium | High (tracks a moving add-in) |

## 4. Recommendation

**Recommended option**: Option B. It is the only option that delivers the owner's vision on every plan the writer may have, keeps the analysis in scripts (rule 7), and still gives Word 365 users the live side panel the owner cares about most. The bridge works whether or not D-16 passes.

**Immediate next action**: run the three hand tests below and record them in `status/evidence/`. D-16 decides how much the Word panel can do on its own. Then `design` the plan, starting with the safe docx editor, since every later task writes through it.

**Open questions**:
- [ ] **D-14:** does the Claude for Word add-in install and work in free Word on the web with a personal Microsoft account? This is a hand test by the owner.
- [ ] **D-16:** can an uploaded Skill run its scripts inside the Word panel, and can the panel read comment replies and resolved state? This is a hand test.
- [ ] **D-18:** are custom Skills available on the Free plan? The help center says yes, the docs say Pro and up. Verify.
- [ ] **D-7 path B:** can Claude in a chat, or in Cowork, download the tool from GitHub itself? Test it; the Skill zip is the fallback either way.
- [ ] **docx-fixer:** reuse its logic as a vendored, stdlib-only module, or reimplement the minimal editor here? Decided in `design`. docx-fixer stays a separate repo.
- [ ] **Windows Home and Intel Macs (no Cowork):** confirm the fallback (web chat with the Skill, plus the Word panel or basic mode) is acceptable as documented.

**Decisions log** (carried unchanged from `explore-idea`):

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | Split into engine → storage → setup | agreed | 2026-10-11 |
| D-2 | Claude runs the kit's code; prompt-only fallback | agreed | 2026-10-11 |
| D-3 | What each Claude plan offers (research table) | agreed | 2026-10-11 |
| D-4 | Entry point: a normal-chat sentence ("I want to use literary-critic for my novel") | agreed | 2026-10-11 |
| D-5 | Setup wizard: checks plan, OS, Word version and what is enabled; says what to turn on; finds the novel and its versions | agreed | 2026-10-11 |
| D-6 | Guided flow: a plan; the writer accepts, changes or rejects; short, targeted answers | agreed | 2026-10-11 |
| D-7 | Install: Claude fetches the tool itself (B); falls back to Skill zip upload (A) | agreed | 2026-10-11 |
| D-8 | Main target Pro + Cowork; Free as basic mode | agreed | 2026-10-11 |
| D-9 | Commented copies as the main Word channel | superseded by D-11 | 2026-10-11 |
| D-10 | Working files in `MyNovel/literary-critic/` | agreed | 2026-10-11 |
| D-11 | Edit the same manuscript on approval: tracked changes, backup, computer use for live fixes, 365 add-in when available | agreed | 2026-10-11 |
| D-12 | Rule 5: prose suggestions are a per-writer setting, off by default; mechanical edits always allowed after approval | agreed | 2026-10-11 |
| D-13 | Safe-edit protocol: lock-file and on-disk-change checks, save before close, backup, verify, auto-restore | agreed | 2026-10-11 |
| D-14 | Free route: Word add-in on free Word for the web | open (test by hand) | 2026-10-11 |
| D-15 | `.docx` stays the master; Google Docs read-only support | agreed | 2026-10-11 |
| D-16 | Can Skill scripts run inside the Word add-in? | open (test) | 2026-10-11 |
| D-17 | Cowork↔Word bridge: round actions as tagged comments in the master; decisions back as thread replies | agreed (pending spec approval) | 2026-10-11 |
| D-18 | Skills on the Free plan: sources disagree | open (verify) | 2026-10-11 |

---

> Sections 5–6 (contracts, risks) are appended by `design`.
