# Literary Critic — Specification (annotated edition)

> Generated 2026-10-11. This is the document with a **note slot** after every section. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Spec

## Preamble & scope

**Date**: 2026-10-11
**Ticket / PR**: workspace `chat`
**Author**: Claude (with the owner)
**Revision**: 2
**Status**: draft
**Revision log**:
- r1 — first draft, from the explore-idea decisions log D-1…D-18
- r2 — owner's decision in conversation (no notes export): the Word 365 side panel leaves the main path; Cowork does everything, reaching the open Word through computer use; a live Word-control extension becomes a separate project, with its interface defined here (D-19…D-21)

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<project>-spec-notes-<date>-r1.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

<!-- -->

> **✎ Notes** · `SPEC · intro`
> _(your notes here — replace this line)_

## §1 Problem statement

Today literary-critic needs someone technical to use it. You need a terminal or a code-running chat, a workspace path, `lc` commands, and, in a chat, uploading the kit and a workspace zip every session. The no-code "reduced mode" loses metrics, the Codex and every check that a script measures. A non-technical writer (or an agency reader) cannot start, and the changes the tool recommends still have to be found and typed by hand in Word. That costs time and creates stray copies of the manuscript.

The tool should start from one sentence in a normal Claude chat: "I want to use literary-critic for my novel".
- A setup wizard checks what the writer's Claude and computer can do, says exactly what to turn on, finds the novel and its versions, and prepares a working folder.
- The tool then guides the writer through a plan in short, targeted messages. The writer accepts, changes or rejects each step.
- Accepted changes land in the writer's own `.docx` as tracked changes, safely, without new copies.
- When the writer needs to work on a passage, Claude brings Word to the front at that exact paragraph, so the writer never has to search for it.

This is a planned improvement. It decides whether the tool is usable by its target users at all.

**Success criteria (measurable)**

- [ ] `writer_setup_actions <= 5` on the main path (Pro plan, Cowork). These are the actions the writer performs between "I want to use literary-critic for my novel" and the first feedback on the novel: toggles, folder picks, uploads and permission clicks. Counted on a scripted walkthrough checklist.
- [ ] `wizard_capability_misreports == 0` over the scripted environment cases: code execution on/off, folder connected or not, computer use on/off, Windows Home or Intel Mac (no Cowork), Free plan.
- [ ] `novel_discovery_accuracy == 1.0` on a fixture folder with drafts, copies, backups and unrelated `.docx` files. The wizard names the latest draft and lists the other versions in date order.
- [ ] `unintended_docx_changes == 0`: across a corpus of fixture manuscripts, the text diff after an approved edit batch equals exactly the approved edits, and styles, comments and other parts are byte-identical outside the edited runs.
- [ ] `edits_as_tracked_revisions == 1.0`: every applied edit is a native Word revision (`w:ins` / `w:del`) that can be rejected one by one. Checked by script, and opening in Word 2016-compatible OOXML is validated.
- [ ] `backup_before_edit == 1.0` and `restore_on_failure == 1.0`, with failures injected at each step of the safe-edit protocol.
- [ ] `open_document_overwrites == 0`: an edit never writes a file that Word holds open (Word's `~$` lock file) or that changed on disk since it was last read.
- [ ] `live_locate_success >= 0.9`: in hand tests with computer use on Mac and Windows, Claude brings Word to the front at the exact paragraph, using Find on its first words, for at least 9 out of 10 located actions. When it fails, it falls back to the plain locator (chapter, page, first and last words) and tells the writer.
- [ ] `word_helper_interface_documented == 1`: the interface the separate Word-control project must provide is written in `docs/` and used by the tool through one adapter, so plugging the extension in later needs no change elsewhere.
- [ ] `prose_suggestions_default_off == 1`: a new workspace never proposes wording until the writer turns the setting on. Tested.
- [ ] `skill_workshop_errors == 0` for the litcritic skill (validate.py and audit_library).
- [ ] Usability, judged by a scripted walkthrough: a fresh assistant plays a non-technical writer persona from the first sentence to an applied round-1 change on the main path, and a second run where Word is open throughout. The reviewer checks that every instruction to the writer is plain, located and one step at a time. Median writer-facing reply is at most 120 words.
- [ ] The hand test D-18 and the D-7 path-B test are run and recorded in `status/evidence/` before any task that depends on their answer is designed.

<!-- -->

> **✎ Notes** · `SPEC §1`
> _(your notes here — replace this line)_

## §2 Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| Setup wizard (new: `lc setup` plus a `05-setup` prompt) | Primary | Detects capabilities, explains what to enable, finds the novel and its versions, creates `MyNovel/literary-critic/` | Yes | New entry point for every writer | High |
| Safe docx editor (new module, stdlib) | Primary | Applies approved edits and renames to the master `.docx` as tracked changes, after the lock-file and on-disk-change checks, with backup, verification and automatic restore | Yes | Writes the writer's manuscript, the highest-risk change the tool has made | High |
| Live Word helper (prompt procedure plus one adapter) | Primary | Brings the open Word to a paragraph and saves, closes or reopens it, using computer use today and the future Word-control extension later | Yes | What makes the work visual: the writer sees the exact place | Med |
| litcritic Skill and packaging (`kit.py`, `.claude/skills/litcritic`) | Primary | Entry instructions for chat and Cowork; builds the Skill zip with the kit bundled | Yes | How the tool is installed and recognised in each surface | Med |
| Prompts (`00-guide`, new `05-setup`, new `80-live-word`) | Dependent | Guided flow, short answers, one change per message, live Word procedure | Yes | What the writer experiences | Med |
| Profile schema and `AGENTS.md` rule 5 | Shared resource | New per-writer setting `prose_suggestions` (default off); rule 5 reworded to match | Yes | Changes a hard rule of the project | Med |
| Codex, rounds, sync (existing) | Dependent | Decisions from comment replies; a new draft is detected when the master file changes | Validation, small changes | Must keep their gates green | Low |
| Claude surfaces (chat, Cowork, computer use, Drive connector) | Infrastructure (external) | Where the tool runs; not ours to change | No (validation) | Their limits shape the design: Cowork needs a paid plan and an Apple Silicon Mac or Windows Pro/Enterprise/Education; computer use is a preview on Pro and Max | High |
| Word-control extension (separate future project) | Dependent (external) | A local extension that controls the open Word directly (COM on Windows, AppleScript on Mac): select a passage, apply tracked edits live, rename, save | No: interface only, defined here | Replaces computer use later without changes elsewhere | Low |
| docx-fixer (separate repo) | Dependent (external) | Existing Word-fixing logic | Validation; reuse decided in design | Kept as a separate repo (earlier decision) | Low |

**Impact dimensions**
- **Data:** the master manuscript is edited in place, and only on explicit approval of each change or batch. Backups in `literary-critic/backups/` are the safety net. *High.*
- **API:** new `lc setup` and `lc docx` commands; nothing removed. *Low.*
- **Performance:** a rename across a 100k-word `.docx` must take seconds, not minutes. *Low.*
- **User-facing:** the whole experience changes from commands to a guided conversation. *High.*
- **Operational:** a Skill zip is released per version, and a computer-use preview may change under us. *Med.*
- **Risk of inaction:** the tool stays usable only by its author.

<!-- -->

> **✎ Notes** · `SPEC §2`
> _(your notes here — replace this line)_

## §3 Options



<!-- -->

> **✎ Notes** · `SPEC §3`
> _(your notes here — replace this line)_

### Option A: Wizard prompt and commented copies (Conservative)

- **Description**: Add a setup prompt and plain-language install docs on top of the current kit. Feedback reaches Word only as a commented **copy** of the manuscript; there are no in-place edits and no live Word.
- **Scope**: `prompts/`, `kit/START_HERE.md`, docs, small `docx_out` changes.
- **Effort**: Small
- **Tradeoffs**: Lowest risk to the manuscript. It contradicts D-19: copies multiply versions, and the writer still searches for and types every change.
- **Compatibility**: Fully backward compatible.

<!-- -->

> **✎ Notes** · `SPEC › Option A: Wizard prompt and commented copies (Conservative)`
> _(your notes here — replace this line)_

### Option B: Cowork does everything; computer use reaches the open Word (Recommended)

- **Description**:
  - The wizard runs in chat or Cowork. Claude fetches the tool itself, or falls back to the Skill zip.
  - In Cowork it finds the novel, prepares `MyNovel/literary-critic/`, and runs the guided rounds.
  - Approved edits and renames are applied to the master `.docx` as tracked changes through the safe-edit protocol.
  - With computer use, Claude saves, closes and reopens Word for the writer, and brings Word to the front at the exact paragraph being discussed.
  - All of this goes through one adapter, whose interface a future Word-control extension will implement.
  - Free plan: basic mode with the existing kit (upload and workspace zip).
- **Scope**: new setup module and prompt, new safe docx editor, live Word helper adapter and procedure, Skill and packaging, prompts, profile setting, rule 5, docs.
- **Effort**: Large
- **Tradeoffs**:
  - Plus: one place where everything happens, with the full Codex, and it works with any Word version.
  - Minus: it writes the writer's own manuscript, which is acceptable only with the safe-edit gates above. Computer use is slower and still a preview, so every step it helps with also works without it.
- **Compatibility**: Backward compatible: existing CLI, Codex and rounds are unchanged; the new commands are additive.

<!-- -->

> **✎ Notes** · `SPEC › Option B: Cowork does everything; computer use reaches the open Word (Recommended)`
> _(your notes here — replace this line)_

### Option C: Build the Word-control extension now

- **Description**: As option B, but reach Word through our own local extension (COM on Windows, AppleScript on Mac) instead of computer use. It edits the open document live with Track Changes, selects passages instantly, and never closes Word.
- **Scope**: option B plus a Windows and Mac extension, its packaging and its install step.
- **Effort**: Large+ (a project in itself)
- **Tradeoffs**: The best live experience on any Word version. But the writer has one more install, and we take on two platform codebases before the core flow is proven.
- **Compatibility**: Additive; the extension implements the same interface option B defines.

<!-- -->

> **✎ Notes** · `SPEC › Option C: Build the Word-control extension now`
> _(your notes here — replace this line)_

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large | Large+ |
| Risk | Low | Medium (manuscript writes, gated; preview tool) | Medium-high (two platform codebases) |
| Completeness | Low: no in-place edits, no live Word | High: every agreed decision; live Word via computer use | Highest: instant live editing |
| Compatibility | Full | Full (additive) | Full (additive) |
| Maintenance | Low | Medium | High |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Recommended option**: Option B. One place where everything happens (Cowork), with the full Codex, the safe in-place editor, and the writer taken to the exact paragraph in Word, on any Word version. The live Word helper is one adapter, so the separate Word-control project (option C's extension) can replace computer use later without changes elsewhere.

**Immediate next action**: `design` the plan, starting with the safe docx editor, since every later task writes through it. In parallel, run the D-18 and D-7 path-B tests.

**Open questions**:
- [ ] **D-18:** are custom Skills available on the Free plan? The help center says yes, the docs say Pro and up. Verify.
- [ ] **D-7 path B:** can Claude in a chat, or in Cowork, download the tool from GitHub itself? Test it; the Skill zip is the fallback either way.
- [ ] **docx-fixer:** reuse its logic as a vendored, stdlib-only module, or reimplement the minimal editor here? Decided in `design`. docx-fixer stays a separate repo.
- [ ] **Windows Home and Intel Macs (no Cowork):** confirm the fallback (web chat with the Skill, or basic mode) is acceptable as documented.
- [ ] **Word-control project (D-21):** a new repository, or grow docx-fixer into it? This is the owner's choice; it does not block this plan.

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
| D-11 | Edit the same manuscript on approval: tracked changes, backup, computer use for live fixes, 365 add-in when available | superseded by D-19 | 2026-10-11 |
| D-12 | Rule 5: prose suggestions are a per-writer setting, off by default; mechanical edits always allowed after approval | agreed | 2026-10-11 |
| D-13 | Safe-edit protocol: lock-file and on-disk-change checks, save before close, backup, verify, auto-restore | agreed | 2026-10-11 |
| D-14 | Free route: Word add-in on free Word for the web | dropped (no 365 path, D-19) | 2026-10-11 |
| D-15 | `.docx` stays the master; Google Docs read-only support | agreed | 2026-10-11 |
| D-16 | Can Skill scripts run inside the Word add-in? | dropped (no 365 path, D-19) | 2026-10-11 |
| D-17 | Cowork↔Word bridge: round actions as tagged comments in the master; decisions back as thread replies | superseded by D-19 | 2026-10-11 |
| D-18 | Skills on the Free plan: sources disagree | open (verify) | 2026-10-11 |
| D-19 | Main path: Cowork does everything. Edits land in the master `.docx` as tracked changes; Claude takes the writer to the exact paragraph in Word; no Microsoft 365 dependency | agreed | 2026-10-11 |
| D-20 | How Cowork reaches the open Word: computer use now (A); our own Word-control extension (B) is built later | agreed | 2026-10-11 |
| D-21 | The Word-control extension is a separate project; this spec defines the interface it must implement (find and select a passage, apply tracked edits live, rename across the document, save, close, reopen) | agreed | 2026-10-11 |


> Sections 5–6 (contracts, risks) are appended by `design`.

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

