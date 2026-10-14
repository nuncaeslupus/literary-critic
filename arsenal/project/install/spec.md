# Specification: writer install, live Word and updates

**Date**: 2026-10-14
**Ticket / PR**: workspace `install`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the owner's Cowork run (`status/evidence/W9-walkthrough.md`, "Owner's run in Cowork") and the open items in `arsenal/session/handover.md`

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<project>-spec-notes-<date>-r1.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

---

## 1. Problem statement

The `chat` workspace decided how the tool reaches a writer: Claude fetches it
itself, with the Skill zip upload as the fallback (chat D-7), the main target is
a paid plan with Cowork (chat D-8), and Cowork reaches the open Word through
computer use until a Word-control engine exists (chat D-20, D-21). That engine
now exists: doc-control 0.6 ships a live engine with a Word adapter and an MCP
server. Three gaps remain before a non-technical writer gets the full
experience on their own:

- **Live Word is slow and clumsy.** "Take me there" by computer use worked
  (1 of 1) but took about 30 s and about 15 steps, with windows flickering.
  doc-control's `live_select` does the same in about 2.5 s on the host. But the
  writer has no way to install the live engine without editing a JSON config
  file, and nobody knows yet whether a Cowork conversation can call an MCP
  server running on the writer's computer (Cowork's own commands run in a
  sandbox that cannot reach Word).
- **Nothing tells the writer the tool is out of date.** An uploaded Skill, or a
  copy fetched weeks ago, keeps running old code and old prompts silently.
- **We do not know whether a Cowork project keeps the novel's folder** across
  conversations, so `prompts/05-setup.md` cannot tell the writer what to expect
  when they come back.

This spec decides how a writer installs the tool and the live engine on each
surface, how the tool notices it is out of date and says so plainly, and how a
returning writer resumes. It is a planned improvement; it blocks doc-control's
one-click writer install, which waits on the answer to open question Q-1.

**Success criteria (measurable)**

- [ ] `writer_setup_actions <= 5` on the Cowork main path, unchanged from the
  `chat` spec, counted from "I want to use literary-critic for my novel" to the
  first feedback. The live engine is not part of this count.
- [ ] `writer_live_install_actions <= 3`: the one-time actions (clicks, file
  opens, app restarts) a writer performs to turn on fast "take me there",
  counted on a scripted walkthrough checklist on Windows and on a Mac. Typing
  or editing a config file counts as a failure, not as actions.
- [ ] `live_locate_seconds_p50 <= 5` and `live_locate_writer_visible_steps <= 1`
  (Word comes to the front once, at the passage) when the live engine is
  reachable; measured over 10 located actions on Windows and 10 on a Mac.
- [ ] `live_locate_success >= 0.9` (the `chat` criterion) holds on every path,
  live engine or computer use; on failure the writer gets the plain locator.
- [ ] `live_fallback_correct == 1.0`: with the live engine missing, not
  reachable, or failing, the tool falls back to computer use, then to the plain
  locator, without asking the writer anything technical. Tested by script with
  each failure injected.
- [ ] `update_detected_rate == 1.0` and `update_false_alarms == 0` over the
  scripted cases: kit or Skill older than the latest release (online), current
  (online), older but offline, a source checkout, a development version newer
  than the latest release.
- [ ] `update_notice_plain == 1`: the out-of-date message has no tool talk (no
  version numbers, commands or file names unless the writer asks with
  `[[...]]`), is at most 40 words, appears once per conversation, and never
  interrupts a change being applied. Judged on the scripted walkthrough.
- [ ] `writer_update_actions <= 2` when Claude can fetch the tool itself; when
  the writer must replace an uploaded Skill, the steps are given one at a time
  and counted (target `<= 4`).
- [ ] `resume_setup_actions == 0` when a returning writer opens a new
  conversation in the same Cowork project with the folder still connected;
  otherwise exactly 1 (pick the folder again), and the tool finds the existing
  working folder without re-running setup questions.
- [ ] Owner's hand tests Q-1 and Q-3 are run and recorded in `status/evidence/`
  before any task that depends on their answer is designed.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `prompts/05-setup.md` | Primary | Setup wizard: checks what Claude can do, finds the novel | Yes | Adds the live-engine check, the update check, and the resume path | Med |
| `prompts/80-live-word.md`, `src/litcritic/word_live.py` | Primary | "Take me there" and closing/reopening Word | Yes | `live_select` first; computer-use steps and the plain locator as fallbacks | High |
| `.claude/skills/litcritic/SKILL.md` ("Running the tool") | Primary | How Claude gets and runs the tool | Yes (by its owner, not in this spec's tasks unless approved) | Carries the version and the update rule | Med |
| `src/litcritic/kit.py` | Primary | Builds the kit zip and the Skill zip; `lc doctor` | Yes | Stamps version and build date into the Skill; `lc doctor` reports `update_available` | Med |
| `src/litcritic/dc.py` | Dependent | The only door to doc-control | Validation only | `capabilities` already lists engines; used to tell whether `live` is present | Low |
| doc-control (separate repo) | External dependency | Live engine, Word adapter, MCP server | Yes, in doc-control's own session | Packages the MCP server for one-click install (Q-1 decides how) | High |
| Claude desktop app / Cowork | Host | Runs the conversation, computer use, MCP servers, folder access | No (outside our control) | Whether Cowork can call a host MCP server decides the main path | High |
| GitHub releases / tags of this repo | Shared resource | The source of "latest version" | Yes | Releases must be tagged so the check has something to compare | Low |
| Writer's novel folder (`<novel>/literary-critic/`, chat D-10) | Data | The working folder that holds all state | No | It already holds the state, so resuming needs only the folder | Low |

**Impact dimensions.** Data: none; the working folder format does not change.
API: `lc doctor` gains fields (additive). Performance: locate goes from about
30 s to about 2.5 s where live works. User-facing: fewer clicks, no
flickering, a plain update notice. Operational: tagged releases become part of
shipping. Risk of inaction: writers run stale prompts, and "take me there"
stays slow enough that writers stop using it.

## 3. Options

Every option keeps chat D-7 (Claude fetches the tool; Skill zip fallback) and
chat D-19/D-20 (Cowork does everything; computer use until the live engine is
reachable). They differ in how the live engine reaches the writer, how the
update check works, and what each costs.

**Per surface (common to all options)**

| Surface | Installing the tool | Live Word | Updates |
|---|---|---|---|
| Cowork, paid plan (main) | Claude fetches it from the repository in the conversation (seen working in the owner's run); Skill zip if the network is closed | Depends on Q-1 (below) | Claude re-fetches; uploaded Skill needs a replacement |
| Claude Code on the writer's computer | `uv tool install` / `pip install` from the repository, run by Claude | doc-control's live CLI or MCP server runs on the same machine: works today (2.5 s measured) | Claude runs the upgrade command after asking |
| Plain chat (no Cowork) | Skill zip or kit zip uploaded once | None: basic mode, plain locator and a commented copy (`05-setup.md`) | Writer re-uploads; told in plain words |

**The branch on Q-1** (can a Cowork conversation call an MCP server on the
writer's computer?):

- **Q-1 = yes.** The live engine is installed once on the computer as an MCP
  server; Cowork calls `live_select` and friends directly. The work is making
  that install one-click (Options B and C differ here).
- **Q-1 = no.** Cowork cannot use the live engine at all. Cowork keeps computer
  use for "take me there" (current path, chat D-20), made faster where possible
  (fewer screenshots, Find with the shortest unique phrase). Writers who want
  fast live Word use Claude Code on their computer, where the live engine runs
  locally; the setup wizard offers it only when the writer asks why "take me
  there" is slow. The one-click install is then built for that surface only, or
  deferred.

### Option A: Prompts only (Conservative)

- **Description**: Document the manual MCP config step in the setup prompt for
  writers who want it; keep computer use as the only Cowork path. For updates,
  `lc doctor` prints the version and the prompt asks Claude to compare it with
  the repository's latest tag when the network allows. Resume is a sentence in
  `05-setup.md`.
- **Scope**: `prompts/05-setup.md`, `prompts/80-live-word.md`, `SKILL.md` text.
- **Effort**: Small
- **Tradeoffs**: Almost no code. But a writer would have to edit a JSON file
  (fails `writer_live_install_actions`), and the update check is LLM judgment,
  not a tested script (breaks rule 7, script first).
- **Compatibility**: Fully backwards compatible.

### Option B: Scripted update check plus a packaged live engine, branching on Q-1 (Recommended)

- **Description**:
  1. **Version and update check, by script.** The Skill zip and kit carry the
     version and build date (`kit.py`). `lc doctor` (already run first by the
     wizard) adds `version`, `latest` and `update_available`, reading the
     latest release tag from the repository with a short timeout. Offline, or
     in a source checkout, it reports `unknown` and the tool says nothing. A
     version newer than the latest release (development) is never "out of
     date". The prompt turns `update_available` into one plain sentence
     ("There is a newer version of the tool with fixes. Shall I update it? It
     takes a minute.") at the start of a conversation, never mid-change. If
     Claude fetched the tool, it re-fetches on yes. If the tool came from an
     uploaded Skill, it gives the replacement steps one at a time.
  2. **Live engine first, two fallbacks.** `word_live.call` asks doc-control's
     `capabilities` for the `live` engine, tries `live_select` (or the MCP
     tool when Cowork exposes it), falls back to the computer-use steps, then
     to the plain locator. One adapter (chat D-21), no change elsewhere.
  3. **One-click live install, owned by doc-control.** If Q-1 = yes,
     doc-control ships its MCP server as a desktop extension bundle the writer
     opens once (one double-click and one confirm in the Claude app), and the
     wizard links to it only after the first slow "take me there". If Q-1 =
     no, the bundle targets Claude Code users only and Cowork stays on
     computer use; nothing in literary-critic changes between the two except
     which surfaces the wizard offers it on.
  4. **Resume.** The wizard first looks for an existing `literary-critic/`
     working folder in the connected folder and resumes from it (no setup
     questions). `05-setup.md` says, after Q-3, whether the writer needs to
     pick the folder again in a new conversation.
- **Scope**: `kit.py`, `lc doctor`, `word_live.py`, `prompts/05-setup.md`,
  `prompts/80-live-word.md`, `SKILL.md` "Running the tool"; tests for the
  update check and the fallback chain; doc-control's packaging in its own
  session.
- **Effort**: Medium
- **Tradeoffs**: Meets every criterion on both Q-1 outcomes; the update check
  is a tested script. Costs a network call at start (short timeout, fail
  silent) and a release-tagging habit. The one-click bundle depends on the
  Claude app's extension format and on doc-control's dependencies being
  installable without a terminal (Q-2).
- **Compatibility**: Additive. `lc doctor` gains fields; older Skills simply
  lack the check until replaced (the first update after this ships cannot be
  announced by the old Skill).

### Option C: Our own installer for the writer's computer

- **Description**: A literary-critic installer (Windows and Mac) that installs
  Python, the tool, doc-control's live engine and its MCP config, and updates
  itself in the background.
- **Scope**: New packaging and signing for two operating systems, a background
  updater, uninstall.
- **Effort**: Large
- **Tradeoffs**: Fewest writer actions once installed and works for Claude Code
  too. But it is a second product: code signing, antivirus false positives,
  admin rights, an updater that touches the writer's computer, and it still
  does nothing for Cowork if Q-1 = no. It duplicates what doc-control and the
  Claude app's extension format should own.
- **Compatibility**: New install path; existing ones keep working.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Medium | Large |
| Risk | Low code risk; high usability risk (config editing) | Medium (depends on Q-1, Q-2) | High (signing, admin rights, background updates) |
| Completeness | Update check by judgment; live install manual | All criteria, both Q-1 outcomes | All criteria on the computer; Cowork still gated by Q-1 |
| Compatibility | Full | Additive | New path |
| Maintenance | Low | Medium (release tags, one adapter) | High (two OS installers) |

## 4. Recommendation

**Recommended option**: Option B. It builds on chat D-7, D-20 and D-21 without
reopening them, makes the update check a tested script, gives the fastest
"take me there" wherever the live engine is reachable and degrades cleanly
where it is not, and leaves packaging the live engine to doc-control, which
owns it.

**Immediate next action**: the owner runs the Q-1 test from the handover (add
doc-control's MCP server to the Claude desktop app, restart, ask Cowork for
`live_select` on an open document) and the Q-3 test (a second conversation in
the same Cowork project); record both in `status/evidence/`, tell the
doc-control session the Q-1 result, then `design` the plan. The update check
and the fallback chain do not depend on Q-1 and can be designed first.

**Open questions**:
- [ ] **Q-1 (owner test, pending):** can a Cowork conversation call an MCP
  server on the writer's computer (doc-control's `live_select`)? Yes → one-click
  install for Cowork; no → Cowork stays on computer use and fast live Word is
  offered on Claude Code only.
- [ ] **Q-2:** can doc-control's live engine be packaged so the writer installs
  it with a double-click (no Python or terminal on their side), on both Windows
  and a Mac? doc-control's session answers; if not, `writer_live_install_actions`
  cannot be met and the live engine stays an opt-in for technical users.
- [ ] **Q-3 (owner test):** does a Cowork project keep the novel's folder
  connected across conversations? The answer goes into `05-setup.md`.
- [ ] **Q-4:** where is "latest" read from: GitHub release tags (proposed), or
  a version file on the default branch? Releases need tagging either way.
- [ ] **Q-5:** should Claude update a fetched tool without asking when the
  change is only fixes? Proposed: always ask once, in one sentence.

**Decisions log** (decisions this spec builds on, from `arsenal/project/chat/spec.md`, and the ones it proposes):

| ID | Decision | Status | Date |
|----|----------|--------|------|
| chat D-7 | Install: Claude fetches the tool itself (B); falls back to Skill zip upload (A) | agreed (kept) | 2026-10-11 |
| chat D-8 | Main target paid plan + Cowork; free as basic mode | agreed (kept) | 2026-10-11 |
| chat D-10 | Working files in `<novel>/literary-critic/` | agreed (kept; resume relies on it) | 2026-10-11 |
| chat D-20 | Cowork reaches the open Word through computer use now; Word-control engine later | agreed (kept; the engine now exists as doc-control's live engine) | 2026-10-11 |
| chat D-21 | Word-control is a separate project behind one adapter | agreed (kept; doc-control fills it) | 2026-10-11 |
| D-1 | "Take me there" tries the live engine first, then computer use, then the plain locator | proposed | 2026-10-14 |
| D-2 | The update check is a script (`lc doctor`), silent when offline or unknown; the writer sees one plain sentence, never mid-change | proposed | 2026-10-14 |
| D-3 | Packaging the live engine for writers belongs to doc-control; literary-critic only detects and uses it | proposed | 2026-10-14 |
| D-4 | A returning writer resumes from the existing working folder, without setup questions | proposed | 2026-10-14 |

---

> Sections 5–6 (contracts, risks) are appended by `design`. Risks found so far:
> the Claude app's extension or MCP behaviour changes under us (mitigation: the
> fallback chain and `live_fallback_correct`); a network check slows every
> start (mitigation: short timeout, fail silent); an old uploaded Skill can never
> announce its own replacement (mitigation: the first release with the check
> says so in its notes; the wizard also checks when Claude fetches the tool);
> the computer-use window staying on top is the app's fault and not fixable here.
