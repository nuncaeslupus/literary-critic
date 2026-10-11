# Plan: Codex — knowledge base, spans, sync and query layer

**Date**: 2026-10-11
**Specification**: `arsenal/project/codex/spec.md` (approved, revision 3)
**Author**: imarcos + Claude
**Revision**: 1
**Status**: approved (2026-10-11, revision 1) — without annotations
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
draft file ─> ingest ─> text/vNNN.txt ─> kind.detect_structure ─> structure.json
                                                   │
             codex/items/*.jsonl <─ codex.py ─<────┤ spans.py (create, relocate)
                     │                             │
                     ├─> sync ─(diff.py alignment)─┘─> changes.jsonl, reread.jsonl
                     └─> view.py: in-memory SQLite (paragraphs, items, spans, links,
                                   tokens, ngrams, mentions, copresence, v_<type>)
                                   ─> lc codex sql / ask / questions
                                   ─> rounds, report, locate, Word comments, prompts
```

- `spans.py` knows text positions and nothing about items.
- `codex.py` knows items, types and files, and nothing about SQL.
- `view.py` builds the read-only SQL view from `codex.py` and the text. It is the only place the table layout (`codex_schema`) is defined.
- Kinds plug in structure detection, extra item types and a checklist.
- The library finds works by their `work.toml`.

### Data flow

1. **Ingest and anchor** (unchanged): the kind's structure detection replaces the direct call to `structure.py`.
2. **Write knowledge.** The LLM or the writer adds items through `lc codex add/update/retire` with spans given as anchor plus quote. `spans.py` resolves each into a full span; `codex.py` validates the item, writes the type file atomically and appends to `changes.jsonl`.
3. **Ask.** `view.py` loads the items and the current draft and builds the tables. Computed tables (tokens, n-grams, mentions, co-presence) are built lazily. `lc codex sql/ask` runs read-only within a time limit and a token budget.
4. **Sync** (`lc codex sync`):
   - alignment from `diff.py` (synced draft to latest draft);
   - `spans.py` relocates every span;
   - items whose spans are `changed`/`lost`, plus one hop over `depends_on`/`refers_to`/`pays_off`, become `needs_reread`;
   - `reread.jsonl` is rebuilt;
   - `codex.toml` records the synced draft;
   - the output lists, for the LLM: what moved, what changed, and what to re-read.
5. **Check** (`lc codex check`): dead links, orphans, stale spans, duplicate ids, schema failures.

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| work folder | `codex/` | CREATE | `codex.toml`, `items/<type>.jsonl`, `changes.jsonl`, `reread.jsonl` |
| work folder | `work.toml` | UPDATE | `workspace.toml` renamed to `work.toml`; gains `id`, `author`, `kind`, `series`, `tags`. No novel exists yet, so there is no conversion (D-18) |
| work folder | `index/vNNN/` | DELETE | `scene_cards.json`, `chapter_summaries.json`, `registers/` no longer written |
| work folder | `analysis/`, `revisions/` | UPDATE | Findings and round actions become `issue`/`decision` items. Round folders keep only what is sent to the writer (letters, Word copies) |
| repo | `schemas/` | CREATE/DELETE | `item`, `span`, one schema per type and question header added; `scene-card`, `register`, `finding`, `action` removed |

### Technology choices

| Choice | Justification |
|--------|--------------|
| Python `sqlite3` in memory, read-only (`query_only`, authorizer, progress handler) | D-19: SQL the LLM already writes, with no engine to build. Standard library. Never written to disk (D-10) |
| JSON Lines per item type | D-10/D-11: diffable, Drive-safe, small atomic rewrites per type |
| Item types as TOML data files | `new_type_core_changes == 0` |
| SQL files with a TOML header for named questions | Readable and testable, and the LLM can learn from them |
| Kinds as modules behind a registry | D-13 |
| skill-workshop for every skill | Spec r2 note |

### Out of scope

- Writer-facing report (S1), session flow and journal (S2), Claude packaging and local tool server (S3), editing real files, docx-fixer integration.
- Conversion of phase-1 workspace data (D-18).
- Kinds other than `novel` and a minimal `poem`.

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| C1 | Question catalogue: at least 60 writer questions in plain words across all families. Each records the data it needs; this drives the tables and item types | docs/codex | S | — | `catalogue_questions >= 60` | `test_catalogue_loads_and_covers_families` in `tests/test_codex_catalogue.py` — at least 60 entries, every family present, each lists required data |
| C2 | `spans.py`: build spans from anchor plus quote, relocate after alignment (offsets, text check, quote search), states `ok/moved/changed/lost`; scripted-edit test corpus from `corpus/` | lc | M | — | `span_relocation_accuracy >= 0.98` | `test_spans_unchanged_text_relocated_after_edits` in `tests/test_spans.py` — at least 98% found at the right place; `test_spans_changed_text_never_silently_moved` — every changed span is flagged and 0 are misplaced |
| C3 | `codex.py`: envelope, type registry from `codex_types/*.toml`, eight first types, atomic JSONL store, `changes.jsonl`, in-memory indexes, `lc codex init/add/update/retire/show/find/check` | lc | L | C2 | `check_detection_rate == 1.0` | `test_check_finds_every_injected_defect` in `tests/test_codex.py` — dead link, orphan, stale span, duplicate id and schema failure all reported; `test_new_type_needs_no_core_change` — a dummy type file is usable with no code change |
| C4 | `view.py`: in-memory SQL view, `codex_schema = 1`, computed tables (tokens, n-grams, mentions, co-presence) built lazily, read-only guards, budgeted output; `lc codex sql --schema` | lc | M | C3 | `codex_load_seconds_20k <= 1` | `test_view_rejects_writes` in `tests/test_view.py` — INSERT, DELETE and ATTACH are refused; `test_view_load_time_20k_items` — synthetic 20k-item Codex loads within 1 s |
| C5 | Fixture Codex for a corpus text, hand-written items for entities, dialogue speakers, threads and setups; named questions engine and the first 20 questions; `lc codex ask/questions` | lc | M | C1, C4 | `example_questions_answered == 1.0` | `test_example_question_families_on_fixture` in `tests/test_questions.py` — speech per chapter, expression use, relevance between characters and subplot gaps give the expected answers |
| C6 | Catalogue translation: SQL for each catalogue question; untranslatable ones name the missing data; add item types or tables where cheap | lc | M | C5 | `question_catalogue_expressible >= 0.9` | `test_catalogue_sql_runs_on_fixture` in `tests/test_codex_catalogue.py` — at least 90% of entries have SQL that runs and returns the expected shape |
| C7 | Sync: alignment, relocation, flagging with one-hop links, re-read queue, `lc codex sync` report | lc | M | C3 | `sync_touched_ratio <= 1.5` | `test_sync_single_edit_flags_only_reached_items` in `tests/test_sync.py` — flagged/reached at most 1.5; `test_sync_rename_keeps_entity_id`; `test_sync_deleted_paragraph_flags_dependents`; `test_sync_100k_words_under_5s` |
| C8 | Kinds: registry; `novel` kind (structure detection moved from `structure.py`); minimal `poem` kind (stanzas, lines, `stanza_form` and `motif` types) | lc | M | C3 | `new_kind_core_changes == 0` | `test_poem_kind_plugs_in_without_core_change` in `tests/test_kinds.py` — poem fixture anchored and queried with no core edits |
| C9 | Library: `work.toml` with id and metadata, discovery under the home folder (subfolders allowed), `lc library --by …`, ids in every reference | lc | S | C3 | `library_id_collisions == 0` | `test_same_title_two_authors_coexist` in `tests/test_library.py` — both listed and resolvable; `test_moved_folder_keeps_references` |
| C10 | Rewrite rounds, report, locate and Word comments on Codex `issue`/`decision` items and queries | lc | L | C5, C7 | `phase1_round_paths == 0` | `test_round_built_from_issue_items` in `tests/test_rounds.py` — letter, actions and Word comments come from Codex items; decided issues are not re-raised |
| C11 | Remove phase-1 per-type formats, schemas, `index.py` registers and their docs; update `docs/` | lc | M | C10, C8 | `phase1_leftovers == 0` | `test_no_phase1_leftovers` in `tests/test_codex_cleanup.py` — grep finds no old file names, schemas or commands |
| C12 | Checklist: tag `measurable` checks and point each to a named question; `lc codex questions --coverage`; at least 20 named questions | checklist | M | C6 | `measurable_checks_with_query == 1.0` | `test_every_measurable_check_has_a_question` in `tests/test_checklist.py` — coverage 1.0 and `named_questions >= 20` |
| C13 | Prompts and skills (built and checked with skill-workshop) and chat kit rewritten around the Codex; scripted LLM usability review | prompts | M | C11, C12 | `skill_workshop_errors == 0` | `test_prompt_commands_parse` in `tests/test_prompts.py` — every `lc codex` command in prompts parses; skill-workshop validation exits 0 |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**:
1. C1 and C2 in parallel.
2. C3.
3. C4, C7, C8 and C9 in parallel.
4. C5.
5. C6 and C10.
6. C11 and C12.
7. C13.

**Branch pattern**: the session's designated branch, one PR per task.

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|
| C1 | `catalogue_questions >= 60` | 69 (12 families) | `uv run pytest tests/test_codex_catalogue.py` | [HERE] | local | 2026-10-11 |
| C2 | `span_relocation_accuracy >= 0.98` | 1.0 (3386/3386 spans with a known new home, 2 corpus texts, 5 seeds, edit rates 0.05–0.3); `silent_misanchors` = 0 | `uv run pytest tests/test_spans.py -k relocated` (RUNS: 5 seeds, rates 0.05–0.3) | [HERE] | local | 2026-10-11 |
| C3 | `check_detection_rate == 1.0` | 1.0 (5/5 injected defect kinds: dead link, orphan, stale span, duplicate id, schema failure); `new_type_core_changes` = 0 | `uv run pytest tests/test_codex.py` | [HERE] | local | 2026-10-11 |
| C4 | `codex_load_seconds_20k <= 1` | 0.47 s (20,000 items + base tables, best of 3); writes, ATTACH, PRAGMA and DDL refused | `uv run pytest tests/test_view.py` | [HERE] | local | 2026-10-11 |
| C5 | `example_questions_answered == 1.0` | 1.0 (4/4 families exact on the Marianela fixture Codex: speech per chapter, expression per chapter, relevance, storyline gaps); 21 named questions run | `uv run pytest tests/test_questions.py` | [HERE] | local | 2026-10-11 |
| C7 | `sync_touched_ratio <= 1.5` | 1.0 (single-paragraph edit: 1 flagged / 1 reached); `sync_seconds_100k` = 3.17 s (101k words, 20k items, 5% edits); rename keeps id; deletion flags dependents | `uv run pytest tests/test_sync.py` | [HERE] | local | 2026-10-11 |
| C9 | `library_id_collisions == 0` | 0 (same title by two authors; same slug in two folders resolved by id; moved folder keeps references) | `uv run pytest tests/test_library.py` | [HERE] | local | 2026-10-11 |
| C8 | `new_kind_core_changes == 0` | 0 (poem kind: structure, 2 item types and a 1-area checklist plug in; core modules never name it) | `uv run pytest tests/test_kinds.py` | [HERE] | local | 2026-10-11 |
| C6 | `question_catalogue_expressible >= 0.9` | 0.928 (64/69 run on the fixture, 6 checked for exact answers; 5 name missing data: learns-fact items, flashback flag, per-passage POV, syllables in the view, alignment table) | `uv run pytest tests/test_codex_catalogue.py` | [HERE] | local | 2026-10-11 |
| C12 | `measurable_checks_with_query == 1.0` | 1.0 (22/22 measurable checks name a known question that runs without parameters, across all kinds); `named_questions` = 22 | `uv run pytest tests/test_checklist.py -k measurable` | [HERE] | local | 2026-10-11 |
| C10 | `phase1_round_paths == 0` | 0 (rounds, letters, status, Word comments and the reader report read Codex issue/decision items; no findings.json or actions.json in src/) | `uv run pytest tests/test_rounds.py tests/test_docx_out.py tests/test_report.py` | [HERE] | local | 2026-10-11 |
| C11 | `phase1_leftovers == 0` | 0 (index.py, scene-card/register/finding/action schemas, `lc index` and the scene-card and summaries prompts removed; metrics, `lc context` read Codex entity/setup/scene items; no old file name, schema or command in tracked files outside status/ and arsenal/) | `uv run pytest tests/test_codex_cleanup.py` | [HERE] | local | 2026-10-11 |
| C13 | `skill_workshop_errors == 0` | 0 (skill-workshop validate.py litcritic: clean; audit_library: clean; semantic walk of must rules: no findings); every `lc codex` command in prompts, skill and kit parses and every literal SQL runs; scripted usability review 6/6 (status/evidence/C13-usability.md) | `uv run pytest tests/test_prompts.py -k test_prompt_commands_parse` + `validate.py .claude/skills/litcritic` | [HERE] | local | 2026-10-11 |

### Dependency graph

```text
C1 ───────────────────────┐
C2 ─> C3 ─┬─> C4 ─────────┴─> C5 ─┬─> C6 ─> C12 ─┐
          ├─> C7 ─────────────────┴─> C10 ─> C11 ─┴─> C13
          ├─> C8 ───────────────────────────┘
          └─> C9
```

---

## Sign-off

- [x] Design reviewed by owner
- [x] Contracts (spec §5) agreed
- [x] Ready for execution
