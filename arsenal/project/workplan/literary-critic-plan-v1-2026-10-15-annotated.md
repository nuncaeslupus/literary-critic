# Literary Critic — Plan (annotated edition)

> Generated 2026-10-15. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Plan

## Preamble & scope

**Date**: 2026-10-15
**Specification**: `arsenal/project/workplan/spec.md` (approved, revision 1)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: approved (2026-10-15, revision 1) — without annotations
**Revision log**:
- r1: first draft, from the approved spec (Option B). The cards write tracked until doc-control#318 ships; T8 makes the switch to plain writes.

> Review record, kept the way the spec keeps its own. Each round of notes bumps
> **Revision** and adds a log line naming the `<repo>-plan-v<N>-<date>-notes.md`
> export it applied, committed beside this file in the same commit. Approval is
> written `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when
> there were none.

<!-- -->

> **✎ Notes** · `PLAN · intro`
> _(your notes here — replace this line)_

## Technical solution

### Architecture overview

A plan layer sits above rounds. Rounds keep owning actions, and Codex decisions
stay the record of each issue.

1. **`src/litcritic/plan.py`** owns `<ws>/plan/log.jsonl` (append-only, the
   source of truth) and `plan.json` (its replay). It holds a pure transition
   function `apply(state, event) -> state` and the refusal rules. Every command
   appends one event, replays, and writes the snapshot atomically.
2. **`lc plan`** (`cli.py` subcommands): `init`, `add`, `accept`, `start`,
   `skip`, `done`, `reopen`, `move`, `edit`, `next`, `status` and `check`.
   `status` joins the plan events, the change events, `rounds.status` and Codex
   decisions into one timeline.
3. **`rounds.build`** gains `area` and `issues` filters and nothing else, so a
   writer-added aspect part can become a round on just that aspect.
4. **`src/litcritic/change.py`** and **`lc change`** (`propose`, `approve`,
   `dismiss`, `status`). Proposals are stored as `change.proposed` events in the
   same log, with ids `C1…`. `approve` rebuilds the edit from the stored
   proposal only, and writes through `apply_edits`, which is extracted from
   `docx_cli._edits`. That is the same path `lc docx edits` uses, and it stays
   tracked until T8.
5. **MCP** (`mcp.py`): the `plan` tool, the `change_card` tool with its page
   `ui://literary-critic/change`, and the app-only `change_approve` and
   `change_dismiss`. `state()` and `next_step` read the plan. `RUN_ALLOWED`
   gains `plan` and `change`.
6. **Prompts** tell the assistant when to propose a part or a change, that a
   writer move needs the writer's word and reason, and how each surface shows
   the buttons. Prose stays behind `prose_suggestions` (house rule 5).
7. **The switch to plain writes** (T8, after doc-control#318) sets
   `"tracked": False` and puts in the minimum-version check, the `marked`
   reason and the wording changes the spec lists. The live engines follow in T9
   (after doc-control#319).

<!-- -->

> **✎ Notes** · `PLAN › Architecture overview`
> _(your notes here — replace this line)_

### Data flow

```drawspec
{"version": 1, "kind": "flow", "title": "A small change approved in the chat",
 "nodes": [
  {"id": "w", "text": "writer or assistant names X and Y"},
  {"id": "p", "text": "lc change propose"},
  {"id": "r", "text": "refused: prose_off, too_long, not_once"},
  {"id": "c", "text": "card: Replace X with Y?"},
  {"id": "a", "text": "Approve"},
  {"id": "d", "text": "Dismiss"},
  {"id": "e", "text": "apply_edits via doc-control"},
  {"id": "l", "text": "docx locate --go"},
  {"id": "g", "text": "plan/log.jsonl"}
 ],
 "edges": [
  {"from": "w", "to": "p"},
  {"from": "p", "to": "r", "label": "rule fails"},
  {"from": "p", "to": "c", "label": "change.proposed"},
  {"from": "c", "to": "a"},
  {"from": "c", "to": "d"},
  {"from": "a", "to": "e"},
  {"from": "e", "to": "l", "label": "change.applied"},
  {"from": "e", "to": "g"},
  {"from": "d", "to": "g", "label": "change.dismissed"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Data flow`
> _(your notes here — replace this line)_

### State changes

| Where | Store | Change | Description |
|-------|-------|--------|-------------|
| workspace | `<ws>/plan/log.jsonl` | CREATE / APPEND | Plan and change events: `seq`, `at`, `by`, `event`, `part` or `change`, `reason`, `refs` |
| workspace | `<ws>/plan/plan.json` | CREATE / REPLACE | Snapshot rebuilt from the log; `schema_version: 1` |
| workspace | `<ws>/log/edits.jsonl` | APPEND | Unchanged format; approved changes use their `C…` id as the edit id |
| manuscript | the `.docx` | UPDATE | Only on Approve, with a backup, through doc-control: tracked until T8, plain after |
| code | `workspace.SUBDIRS` | UPDATE | Adds `plan` |

<!-- -->

> **✎ Notes** · `PLAN › State changes`
> _(your notes here — replace this line)_

### Technology choices

| Choice | Justification |
|--------|--------------|
| JSON Lines event log plus a replayed snapshot | Any status at any time comes with its reason and date, and `plan_replay_mismatches == 0` can be checked mechanically; stdlib only (rule 9) |
| Proposals stored by id, and approval by id only | A button can never write text the writer was not shown (`writes_without_a_live_proposal == 0`) |
| `apply_edits` extracted from `docx_cli._edits` | One write path; literary-critic rebuilds nothing doc-control owns |
| Its own MCP App page for the card | The places page already shows that the desktop app renders `ui://` pages and lets them call app-only tools |
| `ui/message` only when advertised | Q-1 is unanswered; the result and `plan status` carry the click either way |

<!-- -->

> **✎ Notes** · `PLAN › Technology choices`
> _(your notes here — replace this line)_

### Out of scope

- Any change to how rounds number, score or reuse actions, or to the Codex item types.
- Edits longer than one paragraph, moves of text, or style changes through cards.
- Comments in the manuscript (the existing comment paths stay as they are).
- Adopting history after a move (doc-control#320); it is only cited.
- A plan editor page. The plan is steered in the chat; `plan status` is what the writer sees.

<!-- -->

> **✎ Notes** · `PLAN › Out of scope`
> _(your notes here — replace this line)_

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Plan log, replay and `lc plan` | `src/litcritic/plan.py`, `cli.py`, `workspace.py` | L | — | `invalid_transitions_accepted == 0` | `test_plan_transition_matrix_refuses_every_invalid_move` in `tests/test_plan.py` — every status × command pair outside the allowed table exits 1 and appends nothing; `test_plan_replay_matches_snapshot_after_random_sequence` — 200 random valid command sequences replay to the stored `plan.json` with 0 mismatches; `test_plan_events_carry_required_fields` — each event has seq, at, by, event, part and a reason where one is required |
| T2 | Area and issue filters on round build | `src/litcritic/rounds.py`, `cli.py` | S | — | `legacy_workspace_regressions == 0` | `test_round_build_area_keeps_only_that_area` in `tests/test_rounds.py` — with `--area`, only issues of checks in that area become actions; `test_round_build_without_filters_unchanged` — the existing fixtures produce byte-identical rounds |
| T3 | Plan status, next and legacy seeding | `src/litcritic/plan.py`, `rounds.py` | M | T1, T2 | `resume_names_where_work_stands == 1.0` | `test_plan_status_joins_rounds_and_decisions` in `tests/test_plan.py` — the active round part shows its remaining actions and Codex decisions in the timeline; `test_plan_init_on_legacy_workspace_seeds_rounds` — a workspace with two rounds gets two round parts, the open one active; `test_plan_next_aspect_part_builds_area_round` — `next` on an aspect part returns the `round build --area` command |
| T4 | Change propose, approve and dismiss (tracked) | `src/litcritic/change.py`, `docx_cli.py`, `cli.py` | L | T1 | `writes_without_a_live_proposal == 0` | `test_change_approve_writes_exactly_the_proposed_text` in `tests/test_change.py` — after approve, the paragraph equals the original with X replaced by Y (`approved_change_text_mismatches == 0`); `test_change_propose_refuses_assistant_wording_when_prose_off` — `--by assistant` with `prose_suggestions = false` exits 1 with `prose_off`; `test_change_propose_minor_over_twelve_words_refused` — `too_long`; `test_change_approve_twice_refused` — the second approve answers `not proposed` and writes nothing; `test_change_dismiss_logs_reason` — the dismissal event carries the default reason (`dismissals_logged == 1.0`) |
| T5 | Undo marks a change undone | `src/litcritic/docx_cli.py`, `change.py` | S | T4 | `undo_after_plain_change_mismatches == 0` | `test_docx_undo_of_change_logs_change_undone` in `tests/test_change.py` — undo after an approved change restores the original text and logs `change.undone` for that id |
| T6 | MCP plan tool and change card | `src/litcritic/mcp.py`, `src/litcritic/ui/change.html` | M | T3, T4 | `clicks_per_change == 1` | `test_change_card_result_links_ui_resource` in `tests/test_mcp.py` — `change_card` links `ui://literary-critic/change` and the page holds exactly the Approve and Dismiss buttons; `test_change_approve_tool_is_app_only_and_locates` — `change_approve` is hidden from the model, takes only the id and returns the locate call; `test_state_includes_plan_active_and_next` — `resume` shows the active part and next parts |
| T7 | Prompts for the plan and the cards | `prompts/00-guide.md`, `05-setup.md`, `60-rounds.md`, `80-live-word.md`, `01-chat-guide.md` | M | T6 | `assistant_wording_accepted_when_prose_off == 0` | `test_guide_tells_writer_moves_need_writer_word` in `tests/test_prompts.py` — the guide says a writer move needs the writer's word and reason; `test_cards_prompt_respects_prose_setting` — the prompts say cards with the assistant's wording only under `minor` or on, and name each surface's buttons |
| T8 | Q-1 probe of ui/message | owner, `status/evidence/` | S | T6 | `probes_answered == 1` | `test_workplan_q1_evidence_answers_ui_message` in `tests/test_status.py` — the evidence file says whether the desktop app delivers the page's `ui/message` to the model, yes or no |
| T9 | Plain writes in the file engine | `src/litcritic/docx_cli.py`, `setup.py`, `word_live.py`, `prompts/` | M | T4, T7 | `approved_change_revision_marks == 0` | `test_change_approve_leaves_no_revision_marks` in `tests/test_change.py` — after approve, the document has no `w:ins`/`w:del` from this call; `test_overlap_with_tracked_revision_gives_marked` — the reason is `marked`; `test_old_doc_control_refused_not_tracked` — older doc-control answers `doc_control_too_old`; `test_writer_texts_have_no_tracked_wording` in `tests/test_prompts.py` — `tracked_wording_in_writer_texts == 0` across the listed help and prompt texts |
| T10 | Plain writes in the live engines | `src/litcritic/word_live.py`, `docx_cli.py` | S | T9 | `approved_change_revision_marks == 0` | `test_live_change_approve_sends_untracked_batch` in `tests/test_word_live.py` — with a live session open, approve sends `"tracked": false` to doc-control's live engine and the fake engine records no revisions |
| T11 | Walkthrough | owner + Claude, `status/evidence/` | M | T7, T8, T9 | `clicks_per_change == 1` | `test_workplan_walkthrough_evidence_meets_gates` in `tests/test_status.py` — the record shows one click per change, every skip and add logged with its reason, resume naming where the work stands, and no tracked marks after approve |

<!-- -->

> **✎ Notes** · `PLAN › Implementation tasks`
> _(your notes here — replace this line)_

### Task details

- **T1 Plan log, replay and `lc plan`**: the event schema and the pure `apply`;
  the commands and refusals from spec §5; `init --mode` seeds the parts for
  iterative or report mode, from the profile's mode. The log is appended first,
  then the snapshot is written to a temp file that replaces the old one;
  `check` and `check --repair`. `plan` joins `workspace.SUBDIRS`.
- **T2 Area and issue filters on round build**: `build(..., area=None,
  issues=None)` filters the open problem issues before the level is chosen, and
  the CLI gets `--area` and `--issues`. Nothing else about rounds changes.
- **T3 Plan status, next and legacy seeding**: the read-only join (plan events,
  change events, `rounds.status`, Codex decisions) and the timeline; `next`
  maps a part kind to its command. `init` on a workspace with rounds seeds one
  round part per round. With no `plan/`, `status` answers `no_plan` with the
  proposal.
- **T4 Change propose, approve and dismiss (tracked)**: the card in the work's
  language; the prose rule read from the profile; the size limits (12 changed
  words under `minor`, 1 paragraph under on); the resolve-once and
  one-paragraph checks; the repeat check, with `--again`. `apply_edits` is
  extracted from `_edits`, and `approve` sets the edit id to the change id;
  `--closes` marks the round action done. With `edit_in_place = no` or a
  manuscript that is not `.docx`, approve logs `typed_by: writer` and writes
  nothing. Writes stay tracked here.
- **T5 Undo marks a change undone**: `lc docx undo` looks up the edit id it
  took back and logs `change.undone`; its answer gains `"change"`.
- **T6 MCP plan tool and change card**: the `plan` tool; `change_card` with its
  page; the app-only `change_approve` (which also runs `docx locate --go`) and
  `change_dismiss`. The page sends `ui/message` only when the host advertises
  it. `state()` and `next_step` read the plan, and `RUN_ALLOWED` gains `plan`
  and `change`.
- **T7 Prompts for the plan and the cards**: when to propose parts (by `tool`)
  and when a move is the writer's; the order to follow in iterative and report
  mode; the cards on each surface (desktop page, widget buttons that send
  "Approve C1" / "Dismiss C1", text yes/no). The cards say "Word marks it" until
  T9.
- **T8 Q-1 probe of ui/message**: the owner clicks Approve on a test card in
  the desktop app with a public-domain text from `corpus/`; record whether the
  model sees the message. The spec's Q-1 is updated.
- **T9 Plain writes in the file engine**: once doc-control#318 is released, pin
  its minimum version in `dc.py`. Send `"tracked": False` in `docx_cli` (edits
  and rename); map `UNSUPPORTED_CONTENT` to `marked`; reword the `docx_cli` help,
  `setup.py --edit-in-place` help, `word_live.py`, `prompts/80-live-word.md`
  step 4 and `prompts/05-setup.md` question 3. `lc docx undo` stays the way to
  take a change back.
- **T10 Plain writes in the live engines**: once doc-control#319 is released,
  the same flag through the live path, with its version pin.
- **T11 Walkthrough**: on a `corpus/` text: an iterative plan, one skipped
  part, one added aspect part, five cards (three approved, one dismissed, one
  refused), one undo, then a resume in a new chat. The transcript and the log
  give every §1 criterion.

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1 and T2 in parallel; T3 and T4 after T1 (T3 also after T2);
T5 after T4; T6 after T3 and T4; T7 and T8 after T6; T9 after T4 and T7, and
after doc-control#318 is released; T10 after T9 and doc-control#319; T11 after
T7, T8 and T9.
**Branch pattern**: `workplan-T<N>-description` from the default branch

<!-- -->

> **✎ Notes** · `PLAN › Task details`
> _(your notes here — replace this line)_

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies",
 "nodes": [
  {"id": "T1", "text": "T1\nPlan log, replay and lc plan"},
  {"id": "T2", "text": "T2\nArea and issue filters on round bui…"},
  {"id": "T3", "text": "T3\nPlan status, next and legacy seeding"},
  {"id": "T4", "text": "T4\nChange propose, approve and dismiss…"},
  {"id": "T5", "text": "T5\nUndo marks a change undone"},
  {"id": "T6", "text": "T6\nMCP plan tool and change card"},
  {"id": "T7", "text": "T7\nPrompts for the plan and the cards"},
  {"id": "T8", "text": "T8\nQ-1 probe of ui/message"},
  {"id": "T9", "text": "T9\nPlain writes in the file engine"},
  {"id": "T10", "text": "T10\nPlain writes in the live engines"},
  {"id": "T11", "text": "T11\nWalkthrough"}
 ],
 "edges": [
  {"from": "T1", "to": "T3"},
  {"from": "T2", "to": "T3"},
  {"from": "T1", "to": "T4"},
  {"from": "T4", "to": "T5"},
  {"from": "T3", "to": "T6"},
  {"from": "T4", "to": "T6"},
  {"from": "T6", "to": "T7"},
  {"from": "T6", "to": "T8"},
  {"from": "T4", "to": "T9"},
  {"from": "T7", "to": "T9"},
  {"from": "T9", "to": "T10"},
  {"from": "T7", "to": "T11"},
  {"from": "T8", "to": "T11"},
  {"from": "T9", "to": "T11"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Dependency graph`
> _(your notes here — replace this line)_

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

<!-- -->

> **✎ Notes** · `PLAN › Evidence log`
> _(your notes here — replace this line)_

## Sign-off

- [x] Plan reviewed by the owner
- [ ] Q-1 answered (T8)
- [ ] doc-control#318 released before T9; #319 before T10
- [ ] Ready for execution

<!-- -->

> **✎ Notes** · `PLAN › Sign-off`
> _(your notes here — replace this line)_

