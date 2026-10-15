# Specification: a work plan the writer steers, and small changes approved in the chat

**Date**: 2026-10-15
**Ticket / PR**: workspace `workplan`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: approved (2026-10-15, revision 1) — without annotations
**Revision log**:
- r1 — first draft, from the owner's two requests (steerable plan; small changes
  approved with buttons and written plainly) and the setup wording of PR #192;
  doc-control dependencies cited as doc-control#318, #319 and #320 (D-21, D-22)

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<repo>-spec-v1-<date>-notes.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

---

## 1. Problem statement

The setup now asks the writer whether they want help with specific aspects, one
at a time, or a full report, and promises that "the work follows a plan the
writer steers" (`prompts/05-setup.md` q1, `prompts/00-guide.md` "The plan").
Nothing holds that plan. The only work state a script keeps is the revision
round (`src/litcritic/rounds.py`): the open problem issues of one editorial
level, each an action with a status (`pending`, `accepted`, `rejected`, `done`,
`deferred`) recorded as a Codex `decision`. A round cannot hold what the writer
asks for that is not yet an issue ("look at the dialogue in the first
chapters"), a skipped level, the parts of a reader report the writer wants to
work through, or the order the writer chose. So a later session rebuilds
"where the work stands" from free-text `log/` notes, and a skipped part comes
back. Second, small changes the writer agrees to are applied by hand-writing
`edits.json` and land as Word tracked changes. The owner finds Word's
accept/reject review hard to follow. They want each small change put to them in
the chat ("Replace «X» with «Y»?", Approve / Dismiss), then written plainly
into the `.docx`, with Word taken to the place. Both are planned improvements.
They decide whether a non-technical writer can steer the work and apply
changes without learning Word's review pane.

**Success criteria (measurable)**

Plan (feature 1):

- [ ] `plan_replay_mismatches == 0`: over scripted event sequences (add, accept,
  start, skip, reopen, move, done, changes), the stored `plan.json` equals a
  fresh replay of `log.jsonl`.
- [ ] `invalid_transitions_accepted == 0`: every status transition outside the
  allowed graph (§4, "Plan contract") is refused with exit 1 and writes nothing.
  The test runs the full status × event matrix.
- [ ] `events_missing_fields == 0`: every logged event has `seq`, `at` (UTC),
  `by` (`writer` / `tool`) and `event`, and every `skipped`, `dismissed` and
  `reopened` event also has a non-empty `reason`. The CLI refuses an event
  without them.
- [ ] `resume_names_where_work_stands == 1.0`: after a restart (new process,
  fixture workspace mid-plan), `lc plan status` and the MCP `resume` state give
  the active part, the next part, what remains, and the last five changes with
  their reasons. Checked by test on five fixture states.
- [ ] `legacy_workspace_regressions == 0`: a workspace without `plan/` behaves
  as today. The existing rounds, MCP and prompt tests pass unchanged, and
  `lc plan status` on it proposes a plan seeded from its rounds instead of
  failing.

Small changes (feature 2):

- [ ] `approved_change_text_mismatches == 0`: over the fixture manuscripts, the
  text diff after approving a change equals exactly that change's X → Y, and
  nothing outside the edited runs changes (the existing `lc docx edits`
  guarantees, reached through `lc change approve`).
- [ ] `writes_without_a_live_proposal == 0`: approving an unknown id, an id
  already approved or dismissed, or a proposal whose quote no longer resolves
  exactly once writes nothing and logs the refusal.
- [ ] `assistant_wording_accepted_when_prose_off == 0` and
  `minor_size_violations_accepted == 0`: `lc change propose --by assistant`
  is refused when `prose_suggestions` is `false`, and refused under `minor`
  when Y exceeds the small-fix limit (§4). A Y from the writer is always
  accepted.
- [ ] `dismissals_logged == 1.0`: every Dismiss leaves a `change.dismissed`
  event with a reason (a default reason when the writer gave none) and touches
  no file.
- [ ] `clicks_per_change == 1` on the desktop extension: one click on Approve
  writes the change, takes Word to it and logs it. Judged on a scripted
  walkthrough on the owner's PC: the card shows, one click, Word lands at the
  new text, and `lc plan status` lists the change.
- [ ] After doc-control D-21 ships: `approved_change_revision_marks == 0` (no
  `w:ins` / `w:del` written by an approved change) and
  `undo_after_plain_change_mismatches == 0` (`lc docx undo` returns the
  paragraph byte for byte).
- [ ] `tracked_wording_in_writer_texts == 0`: after the switch, no prompt, help
  text or writer line says an approved change "shows as a tracked change" or
  that "Word also marks it". A grep test lists the files (§2).

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `src/litcritic/plan.py` + `lc plan` (new) | Primary | Owns the plan: parts, statuses, the event log, replay, status view | Yes | New module and CLI with tests | Med |
| `src/litcritic/change.py` + `lc change` (new) | Primary | Stores small-change proposals, validates them (prose rule, size, quote resolves once), approves by calling the `docx edits` path, dismisses, renders the card text | Yes | New module; reuses `docx_cli` internals (`_resolve`, the batch call, `_written`) | Med |
| `src/litcritic/rounds.py` | Primary | Turns issues into actions; records decisions | Yes, small | `build` gains optional `area` and `issues` filters so a plan part can run a round on one aspect or one report part. Statuses, `mark`, `status`, `remaining` and the Codex decisions are unchanged | Low |
| `src/litcritic/docx_cli.py` | Primary | Writes the `.docx` through doc-control | Yes | `"tracked": True` becomes plain (`"tracked": False`) once doc-control D-21 ships. The module docstring and the `docx` / `edits` / `rename` help ("tracked changes") are reworded. `undo` maps the entry it took back to its change id and logs `change.undone` | Med |
| `src/litcritic/mcp.py` + `src/litcritic/ui/change.html` (new) | UI | The desktop extension's tools and MCP App pages | Yes | New `plan` tool; new `change_card` tool rendered by a change page whose buttons call the app-only `change_approve` / `change_dismiss`; `state()` and `next_step` read the plan when there is one | Med |
| `src/litcritic/word_live.py` | Dependent | Manual steps and writer lines for Word | Yes | The `apply_edits` / `rename` step "shows as a tracked change the writer can accept or reject" is reworded | Low |
| `src/litcritic/setup.py` | Dependent | `--edit-in-place` help ("as tracked changes") | Yes | Reworded | Low |
| `src/litcritic/workspace.py` | Dependent | Workspace subfolders | Yes | `plan` is added to `SUBDIRS`; `lc pack` / `unpack` and `lc remove` carry it (check, no code change expected) | Low |
| Codex (`codex/`, `decision` type) | Shared resource | Issues and the writer's decisions on them | No | Stays the record of issue decisions. The plan references issue, action and decision ids and never copies them (§4) | Low |
| `prompts/00-guide.md`, `05-setup.md`, `60-rounds.md`, `80-live-word.md`, `01-chat-guide.md`, litcritic skill | UI (LLM procedure) | How the assistant runs the plan and puts changes to the writer | Yes | "The plan" section uses `lc plan`. Setup q1 seeds the plan. Rounds step 5 uses `lc change` instead of a hand-written `edits.json`. Live-Word step 4 and setup q3 drop the tracked-change wording. The three button surfaces are described once in `80-live-word.md` | Med |
| doc-control (separate repo) | Dependent (external) | `tracked: false` on `batch`, `term.rename`, `restore` (D-21: file engine [doc-control#318](https://github.com/nuncaeslupus/doc-control/issues/318), live engines [doc-control#319](https://github.com/nuncaeslupus/doc-control/issues/319), after #318) | No (theirs) | literary-critic needs a minimum doc-control version with D-21. A range overlapping an unresolved tracked change is refused there (`UNSUPPORTED_CONTENT`), and literary-critic must explain it plainly | Med |
| doc-control `history.adopt` (separate repo) | Dependent (external) | A moved or renamed document takes its old history back; `open` lists `adoptable` candidates (D-22, [doc-control#320](https://github.com/nuncaeslupus/doc-control/issues/320)) | No (theirs) | Not blocking. Until it ships, a novel moved without its `.doc-control/` folder loses `lc docx undo` for earlier changes; the change log still lists them. Once it ships, `lc docx status` can offer the adoption in plain words | Low |
| `tests/` | Dependent | Pytest suite | Yes | New tests for plan, change, the MCP tools and page, the wording grep; existing tests unchanged | Low |

**Impact dimensions**

- **Data** (Med): two new workspace files, `plan/log.jsonl` (append-only, the
  source of truth) and `plan/plan.json` (a snapshot rebuilt from it).
  Change proposals live in the same log. Nothing existing is migrated. A
  workspace with rounds and no plan gets one seeded on first `lc plan` use.
- **API contracts** (Low): additive CLI commands and MCP tools. `rounds.build`
  gains optional keyword arguments only. The `lc docx edits` output keeps its
  shape; `revisions` keeps counting changed spans.
- **User-facing** (High): approved changes stop appearing in Word's review pane.
  This is the owner's decision. A writer who used the tool before keeps their
  earlier tracked changes as they were; the tool says so once.
- **Operational** (Med): the plain-write switch waits on a doc-control release.
  Until then the change cards ship and write tracked, as today, with today's
  wording.
- **Performance** (Low): a plan holds tens of parts and hundreds of events;
  replay is milliseconds.
- **Risk of inaction** (High): setup promises a plan nobody keeps, skipped
  parts come back, sessions lose their place, and every applied change goes
  through a review UI the owner cannot follow.

## 3. Options

### Option A: Extend the rounds only (Conservative)

- **Description**: Keep the round as the only work state. A skipped level, or a
  report part the writer picks, becomes a round flag. A part the writer adds
  becomes an ad-hoc issue in the Codex, then a round action. Small changes stay
  a hand-written `edits.json`, now with an `approved_in_chat` log line. The
  chat shows changes as numbered text everywhere. The tracked flag flips once
  doc-control ships.
- **Scope**: `rounds.py`, `docx_cli.py`, prompts.
- **Effort**: Small
- **Tradeoffs**: Least code. But a round is "the open issues of one level, by
  score": it has no place for the writer's order, for steps that are not issues
  (overview, checks, report, new draft), or for "skip this level and why". Each
  of those becomes a special case inside `build`. Writer-added parts would
  become Codex issues before anyone has read the text for them, which breaks
  "no anchor, no finding". No buttons, so each change costs a typed answer.
- **Compatibility**: Fully backwards compatible.

### Option B: A plan layer above the rounds, with change proposals in its log (Recommended)

- **Description**: A new `plan.py` owns an ordered list of **parts** (overview,
  checks on an aspect, a round, the report, a report part to work through, a
  new draft, or a free aspect the writer named) and an append-only event log of
  every change to them and every small change put to the writer. Rounds stay
  the engine for "work through these issues one at a time": a round part points
  to `round-NN`, and its progress is read live from `rounds.status`, never
  copied. Issue decisions stay Codex `decision` items. `lc change` stores each
  small-change proposal, validates it, and on Approve runs the existing
  `docx edits` path from the stored proposal. On the desktop extension the card
  is an MCP App page with Approve / Dismiss buttons; elsewhere it is a widget
  whose buttons send a chat message, or numbered text.
- **Scope**: new `plan.py`, `change.py`, `ui/change.html`; small changes to
  `rounds.py`, `docx_cli.py`, `mcp.py`, `word_live.py`, `setup.py`,
  `workspace.py`; prompts.
- **Effort**: Medium
- **Tradeoffs**: One more state file, and a join between the plan, the rounds
  and the Codex decisions for the status view. In return each store keeps one
  job. The Codex holds what is known about the text, decisions included, and is
  re-anchored on every new draft. Rounds turn issues into a letter. The plan
  holds what the writer chose to do, in what order, and why. The writer's
  steering never has to pretend to be an issue.
- **Compatibility**: Additive. Workspaces without a plan run as today and get a
  plan seeded from their rounds on first use.

### Option C: The plan as Codex items

- **Description**: New Codex types `step` and `change` (no spans required, like
  `decision`), linked to issues. History comes from the Codex's item revisions
  and retirements; order is a field.
- **Scope**: `codex_types/step.toml`, `change.toml`, `codex_cli` commands,
  `rounds.py`, prompts, MCP.
- **Effort**: Medium
- **Tradeoffs**: One store, and the Codex already has revisions, `by`,
  `retire` and queries. But the Codex is the knowledge base about the novel,
  synced and re-anchored on each draft and checked by `lc codex check`. Process
  state would ride through every sync for nothing. A reorder rewrites many
  items, and "every transition with its reason and time" would have to be
  reconstructed from item revisions instead of read in order. The Codex guard
  and question catalogue grow types no question needs.
- **Compatibility**: Additive, but changes the Codex schema set every consumer
  validates.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Medium | Medium |
| Risk | Low code risk; high risk the plan stays a promise | Medium; one new store, well bounded | Medium; Codex schema and sync touched |
| Completeness | Partial: no writer-added parts, no order, no buttons | Full: both features, every surface | Full plan; changes still need B's card work |
| Compatibility | Full | Full (additive) | Additive, but every Codex consumer sees new types |
| Maintenance | Special cases pile up in `build` | Three stores, one job each | Process state mixed into the knowledge base |

## 4. Recommendation

**Recommended option**: Option B. The plan is a layer above the rounds, and the
small-change proposals live in its log. Rounds are kept and extended only by
two filters. Each store keeps one job: the Codex holds knowledge and the
writer's decisions on issues, rounds work through issues, and the plan holds
the writer's steering and its history. Every requirement the owner named fits
without bending the other two: skip, add, iterative or report, logged with
status, reason and time, read by the next session.

### Plan contract (feature 1)

- **Files**: `<ws>/plan/log.jsonl`, append-only and the source of truth; one
  event per line: `seq`, `at` (UTC ISO), `by` (`writer` | `tool`), `event`,
  `part` or `change`, `reason`, `refs` (round, issue, action, decision, change
  ids). `<ws>/plan/plan.json` is the replayed snapshot, rewritten by every
  command. It is never edited by hand; `lc plan check` verifies it against a
  replay.
- **Mode**: `lc plan init --mode iterative|report` from setup q1 (`iterative` ⇔
  profile `mode = "revision"`, `report` ⇔ `reader-report`; the profile key is
  unchanged). It seeds proposed parts. Iterative: overview, then the aspects
  the writer picks. Report: checks, the report, then one `report-part` per
  weakness section the writer wants to work through.
- **Part kinds**: `overview`, `checks` (a checklist area), `round` (a level, an
  area or an explicit issue list), `report`, `report-part` (the report section
  and its issue ids), `new-draft`, `aspect` (the writer's own words, until
  checks map it to issues). Each part has `id` (`P1`…), `kind`, `title` in the
  writer's language, `status`, `order`, `origin` (`tool` | `writer`), and
  `refs`.
- **Statuses and transitions**: `proposed` → `todo` (the writer agreed) →
  `active` (at most one at a time) → `done`. `proposed`, `todo` and `active`
  can go to `skipped` (reason required). `skipped` and `done` can be
  `reopened` (back to `todo`, reason required). Any part can be `moved` and
  `edited` (title, refs); added parts enter as `proposed` (tool) or `todo`
  (writer). Anything else is refused.
- **The LLM proposes, the script records**: the assistant runs
  `lc plan add|accept|start|skip|done|reopen|move` only on the writer's word,
  with `--by writer` and their reason in their words. The `tool` origin covers
  proposals and automatic facts (a round built, a change applied). `lc plan
  next` returns the next `todo` part and the command that starts it, for
  example `lc round build --area dialogue` for an aspect part.
- **Rounds**: unchanged statuses, `mark`, `status`, `remaining`, letter and
  Codex decisions. `build(level, area=None, issues=None)` adds the two filters.
  The default order (structure, then scenes, then prose) stays the plan's
  default proposal; skipping a level is a `skipped` round part, and the next
  round is built with the level the plan names. A round part shows the round's
  `remaining` inside it, and `lc plan` proposes `done` once the round can
  close. The writer confirms.
- **Where the work stands**: `lc plan status` gives the active part with its
  round's `remaining`, the next parts, counts by status, and a timeline. The
  timeline merges plan events, change events and the Codex decisions of the
  plan's rounds, ordered by `at`, each with its reason. `mcp.state()` includes
  that summary, and `next_step` follows the plan when there is one.
  `00-guide.md` step 4 and "The writer always knows where they are" read it
  instead of `log/` notes. `log/` stays for free-form session notes.

### Change contract (feature 2)

- **Propose**: `lc change propose --workspace <ws> --quote X --prefix … --suffix
  … --replace Y --why "…" --by writer|assistant [--part P3] [--action A7]
  [--closes]`. The script checks that X resolves exactly once in the current
  `.docx` (the same resolver as `docx edits`) and that the change stays inside
  one paragraph. It applies the prose rule and the size limit below, stores the
  proposal as `change.proposed` (`C1`…) with the document's sha256, and prints
  the card: the writer-language line "Replace «X» with «Y»?", the plain locator
  (chapter, page, first and last words), and who wrote Y ("your words" or
  "suggested").
- **House rule 5, who proposes Y**: `prose_suggestions = false` means only the
  writer's own words, and `--by assistant` is refused. The card then serves
  changes the writer dictated ("change *dijo* to *susurró*"). `"minor"` lets
  the assistant propose a small fix: at most 12 changed words (the rounds'
  `MAX_QUOTE_WORDS`), no new sentence. `true` allows suggested wording up to a
  whole paragraph, still one paragraph per card. Longer rewrites are not small
  changes: the writer types them. Every card labels a suggested Y as a
  suggestion.
- **Approve**: `lc change approve C1`. Only a `proposed` change whose document
  still matches can be approved. It builds the edit from the stored proposal,
  so nothing is retyped, and runs the `docx edits` path: backup, `expect.sha256`,
  the refusal rules, verify-and-restore, `log/edits.jsonl`. It logs
  `change.approved`, then `change.applied` or `change.refused` with the plain
  reason. It returns the `docx locate --go` call for the new text, so the chat
  takes Word to it. With `--closes`, it also runs `rounds.mark <action> done`.
  With `edit_in_place = no`, or a non-`.docx` manuscript, Approve writes
  nothing: it logs `change.approved` with `typed_by: writer`, takes the writer
  to the place, and the card says "type it there".
- **Dismiss**: `lc change dismiss C1 [--reason …]` logs `change.dismissed`; the
  default reason is "dismissed in the chat". No file is touched, and the same
  X → Y is not proposed again unless the writer asks.
- **Undo**: `lc docx undo` stays the way to take a change back. It undoes the
  tool's last write, as today, and when that write was a change it logs
  `change.undone` on it. An older change is taken back by proposing the
  reverse change (Y → X), which is a card of its own.
- **One change per message** (house rule 5 of the guide): one card at a time.
  A name changed everywhere is one card over `lc docx rename`, listing the
  number of places.

### Buttons in each surface

1. **Desktop extension (`lc mcp`, MCP Apps)**: a `change_card` tool rendered by
   `ui://literary-critic/change`, built like the places page. Its Approve and
   Dismiss buttons call the server tools `change_approve` / `change_dismiss`
   with the change id only, through the page's `tools/call`. Both tools have
   `visibility: ["app"]`, so on this surface a click is the only way to
   approve. The page shows ✓ with the place, or the plain refusal reason. It
   then sends a `ui/message` ("Approved C1" / "Dismissed C1") so the
   conversation continues, if the host supports it (Q-1). Otherwise the
   assistant reads `lc plan status` at the writer's next message.
2. **A chat that can show a widget whose buttons send a message** (claude.ai,
   Cowork): the card as a small widget whose buttons send "Approve C1" /
   "Dismiss C1". The assistant runs `lc change approve|dismiss` and takes Word
   there the usual way (`80-live-word.md`).
3. **Text only**: "Replace «X» with «Y»? Answer *yes* or *no*." The writer's
   yes or no is the click. Basic mode (no file access) is the same card with
   `typed_by: writer`.

doc-control's `live_places` page is not reused for the card: the extension
serves its own pages (desktop D-6), and approval is literary-critic's decision
record, not a generic document primitive.

### Writing plainly (DECIDED by the owner, depends on doc-control D-21)

Until doc-control ships `tracked: false` ([doc-control#318](https://github.com/nuncaeslupus/doc-control/issues/318)), the cards ship and write
tracked, with today's wording. When it lands, one change in literary-critic:

- Raise the minimum doc-control version. In `docx_cli.py`, `"tracked": True`
  in the `batch` request becomes `"tracked": False`; pass `tracked: False` to
  `term.rename`; `undo` is unchanged (doc-control undoes from the logged
  paragraph bytes).
- Map doc-control's refusal of a range that overlaps an unresolved tracked
  change (`UNSUPPORTED_CONTENT`) to a plain reason: "this sentence still has a
  marked change from before; accept or reject it in Word first".
- Reword the writer-facing texts:
  - the `docx_cli.py` docstring and its `docx`, `edits` and `rename` help;
  - the `setup.py` `--edit-in-place` help;
  - the `word_live.py` `apply_edits` step;
  - `prompts/00-guide.md` house rule 2;
  - `prompts/05-setup.md` q3 ("Word also marks it" becomes "the change is
    written into your file; a copy is kept each time, and you can ask me to
    take it back");
  - `prompts/80-live-word.md` step 4 ("shows as a tracked change …" becomes
    "say what changed and where; to take it back, ask");
  - `prompts/60-rounds.md` step 5.
  A grep test pins the wording.
- When the live engines get plain writes ([doc-control#319](https://github.com/nuncaeslupus/doc-control/issues/319)), Approve can write into
  the open Word without the save-and-close step; until then the card says
  "save and close Word first" when `locked`.

**Immediate next action**: on approval, hand this spec to `design` for the plan.
Suggested order: `plan.py` and `lc plan` with replay tests; the rounds filters;
`change.py` and `lc change` (tracked); the MCP card and page; the prompts. The
plain-write switch is a separate task gated on doc-control's release.

**Open questions**:
- [x] Q-1: Does the Claude desktop app honour MCP Apps `ui/message` from a
  page, so the model sees a click without the writer typing? Yes, after one
  press of Send: the app puts "Approved C1" in the message box under a caution
  banner, and the model sees it once the writer sends it. The click alone has
  already changed the file (`status/evidence/workplan-Q1-ui-message.md`).
- [ ] Q-2: Should a writer who prefers Word's marks be able to keep tracked
  writes (a profile setting), or is plain the only mode? Proposed: plain only,
  as decided. Revisit if a writer asks.
- [ ] Q-3: The small-change limits: 12 changed words under `minor`, one
  paragraph under `on`. Do these match what the owner means by "small"?
- [ ] Q-4: Should the overview the guide gives first be a plan part the writer
  accepts, or always happen before the plan exists? Proposed: a seeded
  `proposed` part, so even it can be skipped.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | An approved small change is written plainly, not as a tracked change; Word's accept/reject review is hard for the owner to follow. Depends on doc-control D-21 (`tracked: false` on `batch`, `term.rename`, `restore`; doc-control#318 file engine, #319 live engines) | agreed (owner) | 2026-10-15 |
| D-2 | `lc docx undo` stays the way to take a change back | agreed (owner) | 2026-10-15 |
| D-3 | The plan is a layer above the rounds (Option B), not an extension of them and not Codex items | proposed | 2026-10-15 |
| D-4 | `plan/log.jsonl` is append-only and the source of truth; `plan.json` is its replay | proposed | 2026-10-15 |
| D-5 | Issue decisions stay Codex `decision` items; the plan references them and never copies them | proposed | 2026-10-15 |
| D-6 | Change proposals are stored by the script and approved by id; Approve rebuilds the edit from the stored proposal | proposed | 2026-10-15 |
| D-7 | On the desktop extension the card is literary-critic's own MCP App page, with app-only approve/dismiss tools; widget-with-message and numbered text elsewhere | proposed | 2026-10-15 |
| D-8 | `prose_suggestions` gates who may supply Y: off = writer only, minor = small fixes, on = up to a paragraph | proposed | 2026-10-15 |
| D-9 | Cards write tracked until doc-control D-21 ships; the plain switch is its own task | proposed | 2026-10-15 |

---

## 5. Contracts

### CLI contracts (`lc`, stdlib only; one JSON object on stdout; exit 0 done, 1 refused, 2 usage)

#### `lc plan init --workspace <ws> --mode iterative|report`

Seeds the proposed parts for the mode. This happens once: a second `init` is
refused. On a workspace that already has rounds, each round becomes a `round`
part with the status its round implies, logged `by: tool`. The latest round with
open actions is `active`; the others are `done`.

```json
{"status": "ok", "mode": "iterative",
 "parts": [{"id": "P1", "kind": "overview", "title": "Overview: what works, the biggest problems",
            "status": "proposed", "origin": "tool", "order": 1, "refs": {}}]}
```

#### `lc plan add|accept|start|skip|done|reopen|move|edit`

```
lc plan add --kind aspect --title "the dialogue in the first chapters" --by writer [--after P2] [--refs-json '{"area": "dialogue"}']
lc plan accept P1 --by writer
lc plan start P1 --by writer|tool
lc plan skip P3 --by writer --reason "the writer's words"
lc plan done P1 --by writer [--reason "..."]
lc plan reopen P3 --by writer --reason "..."
lc plan move P4 --after P1 --by writer
lc plan edit P4 --title "..." [--refs-json '{...}'] --by writer|tool
```

Every command answers with the part it changed and the event it logged:

```json
{"status": "ok", "part": {"id": "P3", "status": "skipped"},
 "event": {"seq": 12, "at": "2026-10-15T10:02:11.120000Z", "by": "writer",
           "event": "skipped", "part": "P3", "reason": "the writer's words", "refs": {}}}
```

A refusal exits 1 and writes nothing:
`{"status": "refused", "reason": "transition" | "missing_reason" | "missing_by" | "unknown_part" | "one_active", "message": "..."}`.

The transitions:

- `proposed→todo` (accept).
- `proposed|todo→active` (start). Refused while another part is active.
- `active→done`.
- `proposed|todo|active→skipped`.
- `skipped|done→todo` (reopen).
- `move` and `edit` work from any status.

#### `lc plan status --workspace <ws> [--timeline N]`, `lc plan next`, `lc plan check`

```json
{"status": "ok", "mode": "iterative",
 "active": {"id": "P2", "kind": "round", "title": "First round", "round": "round-01",
            "remaining": [{"id": "A3", "status": "pending", "severity": "high"}],
            "can_close": false},
 "next": [{"id": "P3", "kind": "aspect", "title": "the dialogue in the first chapters"}],
 "by_status": {"done": 1, "active": 1, "todo": 2, "skipped": 1},
 "timeline": [{"at": "...", "what": "change.applied", "id": "C4", "reason": "approved in the chat", "by": "writer"},
              {"at": "...", "what": "decision", "id": "A2", "verdict": "rejected", "reason": "...", "by": "writer"}]}
```

- **No `plan/` yet.** The answer is `{"status": "no_plan", "proposed": [...]}`:
  the parts `init` would seed, taken from the profile's mode and the existing
  rounds. Nothing is written.
- **`lc plan next`** answers `{"part": {...}, "command": ["round", "build", "--area", "dialogue"]}`.
  For a part the assistant carries out by reading, such as the overview, it
  answers `"command": null`.
- **`lc plan check`** exits 1 when `plan.json` differs from a replay of
  `log.jsonl`, and names the first part that differs. `--repair` rewrites the
  snapshot from the log.

#### `lc round build --workspace <ws> [--level L] [--area A] [--issues id,id]`

The two new filters narrow the open problem issues before the level is chosen:

- `--area` keeps only the issues whose check belongs to that checklist area.
- `--issues` keeps only the listed ids.

Neither changes scoring, numbering, reuse or the output. An empty selection is
refused, as it is today (`no open … issues`).

#### `lc change propose`

```
lc change propose --workspace <ws> --quote X [--prefix P] [--suffix S] --replace Y
                  --why W --by writer|assistant [--part P3] [--action A7] [--closes]
                  [--document D] [--again]
```

```json
{"status": "proposed", "id": "C4", "by": "assistant",
 "card": {"line": "Replace «dijo» with «susurró»?", "label": "suggested",
          "where": "Chapter 3, page 41: «—Ya voy…» … «…cansada.»",
          "approve": "Approve", "dismiss": "Dismiss"},
 "document": "novel.docx", "sha256": "…"}
```

The card's words are in the work's language. A refusal exits 1, with one of
these reasons:

- `prose_off`: `--by assistant` while `prose_suggestions = false`.
- `too_long`: more than 12 changed words under `minor`, or more than one
  paragraph under `on`.
- `not_once`: the quote resolves 0 times or several times. The answer gives the `count`.
- `cross_paragraph`: the quote spans more than one paragraph.
- `repeat`: the same X → Y was dismissed before. Pass `--again` when the writer
  asks for it.

#### `lc change approve C4` / `lc change dismiss C4 [--reason R]` / `lc change status [C4]`

`approve` refuses (exit 1, nothing written) in three cases:

- the id is unknown;
- the change is not `proposed`;
- the document's sha256 changed since the proposal and the quote no longer
  resolves once.

Otherwise it runs the same write as `lc docx edits`, with the edit id set to the
change id, and answers:

```json
{"status": "applied", "id": "C4", "backup": "…", "document": "novel.docx",
 "locate": {"target": "susurró", "prefix": "—Ya voy —", "suffix": " con voz cansada."},
 "closed": "A7"}
```

- **No write.** With `edit_in_place = no`, or a manuscript that is not `.docx`,
  it answers `{"status": "approved", "typed_by": "writer", "locate": {...}}`
  and writes nothing.
- **doc-control refuses.** The answer is
  `{"status": "refused", "reason": "locked" | "changed" | "edit" | "marked" | "doc_control_too_old", "message": "…"}`,
  and the change stays `proposed`. `marked` is the plain reason for
  `UNSUPPORTED_CONTENT` on a range that overlaps an earlier tracked change,
  once writes are plain.
- **`dismiss`** answers `{"status": "dismissed", "id": "C4"}`. The default reason
  is "dismissed in the chat".

#### `lc docx undo`

The output is unchanged. When the entry it takes back is a change (an edit id
`C…` in `log/edits.jsonl`), it also logs `change.undone` for that id and adds
`"change": "C4"` to its answer.

### MCP tools (`lc mcp`)

| Tool | Visibility | Arguments | Result |
|------|-----------|-----------|--------|
| `plan` | model | `work` | `lc plan status` |
| `change_card` | model (renders `ui://literary-critic/change`) | `work`, `change` (an id from `lc change propose`) | `{"card": {...}, "id": "C4", "work": "..."}` |
| `change_approve` | app only | `work`, `change` | the `lc change approve` answer; on `applied`, the tool then runs `docx locate --go` on the new text |
| `change_dismiss` | app only | `work`, `change`, `reason?` | the `lc change dismiss` answer |

Other MCP changes:

- **`RUN_ALLOWED`** gains `plan` and `change`, so the text surfaces work through `run`.
- **`state()`** gains `"plan"`: the `active` and `next` parts and the last five
  timeline rows.
- **`next_step`** follows `lc plan next` when a plan exists.
- **The change page** sends `ui/message` with "Approved C4" or "Dismissed C4"
  after the tool returns, when the host advertises that capability (Q-1).
  Otherwise it only shows the result.

### Inter-service contracts

| Caller | Callee | Protocol | Contract | Failure handling |
|--------|--------|----------|----------|-----------------|
| `change.approve` | `docx_cli` write path | Python call | `apply_edits(root, doc, edits, dry_run=False) -> dict`, extracted from `_edits`; the same answer `lc docx edits` prints | Refusals pass through unchanged and are logged `change.refused` |
| `docx_cli` | doc-control `batch` / `term.rename` | `litcritic.dc.run` | `"tracked": True` today; `"tracked": False` after doc-control#318, behind a minimum-version check | An older doc-control is refused with `doc_control_too_old` rather than silently writing tracked |
| change page | `lc mcp` | MCP Apps `tools/call` | `change_approve` / `change_dismiss` with the id only; the page never sends text to write | The tool error shows on the card. The card stays actionable after a refusal, so the writer can retry once Word is closed |
| `plan status` | `rounds.status`, Codex decisions, `plan/log.jsonl` | Python call | Read-only join | A missing round or a retired decision shows as such; it never fails the status |

### Workspace file changes

| File | Change | Reversible | Forward-compatible |
|------|--------|------------|-------------------|
| `<ws>/plan/log.jsonl` | CREATE, append-only. One event per line: `seq`, `at`, `by`, `event`, `part` or `change`, `reason`, `refs`. A `change.proposed` event also carries the proposal: `quote`, `prefix`, `suffix`, `replace`, `why`, `by`, `document`, `sha256`, `part`, `action`, `closes` | Yes: delete `plan/`; nothing else reads it | Yes: unknown event types are kept and skipped by replay |
| `<ws>/plan/plan.json` | CREATE, rewritten atomically after each command: `schema_version: 1`, `mode`, `parts`, `changes`, `last_seq` | Yes: rebuilt from the log | Yes |
| `<ws>/log/edits.jsonl` | Format UNCHANGED; an edit id may now be a change id `C…` | n/a | Yes |
| `workspace.SUBDIRS` | ADD `plan` | Yes | Yes |

## 6. Risks & Validation

| Risk | Likelihood | Impact | Mitigation | Validation |
|------|-----------|--------|------------|------------|
| The assistant moves plan statuses on its own, so the plan stops being the writer's | Med | High | `--by` is required. The prompts allow a `writer` move only on the writer's word, with the writer's reason; `tool` covers proposals and facts only. The timeline shows who made each move | Unit (the CLI refuses a missing `--by`), prompt pin, walkthrough review |
| `plan.json` drifts from the log after a crash between the append and the snapshot | Low | Med | The log is appended first. The snapshot goes to a temp file that then replaces the old one. Every command replays when `last_seq` differs | Unit: kill between the two writes, then `lc plan check --repair` |
| A card's button approves a change the writer did not see (stale page, double click) | Med | High | Approve takes the id only, and only for a `proposed` change; a second click gets `not proposed`. The document hash is checked again | Unit and MCP transcript test |
| Plain writes make a wrong change harder to spot than a tracked one | Med | Med | Every change is shown before it is written and named after, and Word is taken to it. Every write makes a backup, `lc docx undo` takes it back, and the timeline lists every applied change | Walkthrough and undo round-trip test |
| An earlier tracked change from the tool overlaps a new plain change, and doc-control refuses | Med | Low | The plain `marked` reason tells the writer to accept or reject the earlier mark in Word first | Unit with a fixture that holds a tracked revision |
| The desktop app ignores `ui/message` (Q-1), so the model never learns of a click | Med | Low | The tool result and `plan status` carry the click. The guide says to read pending cards at each writer message | Probe in T8 |
| doc-control#318 slips | Med | Low | The cards ship writing tracked, with today's wording. T9 is its own task, gated on the release | Dependency check in T9 |
| A moved novel loses its undo history before doc-control#320 ships | Low | Low | The change log still lists the changes. Once #320 ships, `docx status` offers adoption | None needed now |
