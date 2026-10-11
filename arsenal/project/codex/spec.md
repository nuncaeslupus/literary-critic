# Specification: Codex — the structured knowledge base behind every reading, report and edit

**Date**: 2026-10-11
**Ticket / PR**: phase 2, sub-project S0 (from `status/ideas.md`)
**Author**: imarcos + Claude
**Revision**: 3
**Status**: approved (2026-10-11, revision 3)
**Revision log**:
- r1 — first draft, from the explore-idea session approved 2026-10-11 (D-1…D-15)
- r2 — applied `literary-critic-spec-notes-2026-10-11-r1.md`: no migration (phase-1 formats and docs are replaced, not converted); skills built with skill-workshop; the Codex answers questions through a query API, and checks and proactive feedback are named questions (D-16…D-18)
- r3 — conversation note: Q-c chosen, with the table layout derived from a catalogue of writer questions so the LLM's translations have enough to work with (D-19). Approved.

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied, and commit that
> export beside this file in the same commit. On approval set **Status** to
> `approved (YYYY-MM-DD, revision N)`.

---

## 1. Problem statement

Phase 1 gave the tool a map of a draft (anchors, structure), metrics, scene
cards, registers, findings and revision rounds. But each of these is a separate
format, tied to one draft version, at a fixed granularity (scene or paragraph),
with its own code for loading and checking. Nothing carries knowledge from one
draft to the next. A renamed character becomes a new one. A deleted paragraph
leaves references to it elsewhere unflagged. A new plot twist does not mark the
earlier passages it makes obsolete. Edits the writer made between sessions are
noticed only if someone re-ingests and reads everything again. Every view the
writer receives (reports, session agendas, chat advice) and every later editing
tool depends on knowledge that stays correct as the text changes. Without it,
the LLM either re-reads the whole work (slow, costly, forgetful) or works from
stale notes (wrong advice).

The Codex is a single knowledge base per work:
- text spans of any length (D-8);
- items that share one envelope (D-12);
- links between items;
- a sync step that follows each new draft and flags exactly what a change
  touched.

It is stored as plain text behind one module (D-10). It follows strict
maintenance rules (D-11), is modular by kind of text (D-13), and lives in a
library of many works (D-14, D-15).

Above all, the Codex answers questions (D-16). Typical questions:
- "In how many chapters does this character speak?"
- "Am I overusing this expression?"
- "Which character matters most to this other character?"
- "Is every subplot told continuously, or are there gaps?"

The LLM turns such a question into a query in the Codex query API. Every
measurable check in the catalogue is a named question (D-17), so feedback can
be proactive: the tool runs the questions and raises what it finds.

No novel has been analysed yet, so phase-1 per-type formats and their docs are
replaced, not migrated (D-18). The tool is rebuilt on the Codex using the
public corpus as the worked example. Data types a real novel later reveals are
added as new item types.

**Success criteria (measurable)**. Each criterion is measured on the public corpus (`corpus/`) plus scripted edits; no working novel is used.

- [ ] `span_relocation_accuracy >= 0.98`. Spans whose text is unchanged are found again at the right place after scripted edits: moves, insertions and deletions around them, splits and merges of their paragraph.
- [ ] `silent_misanchors == 0`. A span whose text changed, or that cannot be found, is always flagged `needs_reread`; it is never placed at a wrong position.
- [ ] `sync_touched_ratio <= 1.5`. On a single-paragraph edit, items flagged / items whose spans or links actually reach the edited paragraph.
- [ ] `sync_seconds_100k <= 5`. Wall time for a full sync of a 100k-word work with 20k items on a laptop-class machine.
- [ ] `codex_load_seconds_20k <= 1`. Load time for 20k items with all in-memory indexes.
- [ ] `check_detection_rate == 1.0`. `lc codex check` finds every injected defect: dead link, orphan item, stale span, duplicate id, item failing its type schema.
- [ ] `phase1_leftovers == 0`. Phase-1 per-type formats and their code paths are gone: the separate scene-card, register, findings and round-action files, and the docs describing them. Everything they did is done through Codex items and queries. A grep-based test lists any surviving reference.
- [ ] `example_questions_answered == 1.0`. On a hand-built fixture Codex of a corpus text, the named questions answer the four example families exactly as expected: speech per character per chapter; expression frequency and distribution; relevance between two characters (co-presence, interaction, mentions); subplot continuity gaps.
- [ ] `named_questions >= 20` at first release, each with parameters, a description in plain words and a test.
- [ ] `measurable_checks_with_query == 1.0`. Every catalogue check tagged `measurable` maps to a named question. `lc codex questions --coverage` reports any check without one.
- [ ] `question_catalogue_expressible >= 0.9`. A catalogue of at least 60 writer questions in plain words (structure, characters, relationships, plot threads, time, dialogue, style, lexicon, rhythm and density, mechanics) is written before the tables. At least 90% of them translate into SQL against the documented tables, checked by a test. Each question that cannot be translated names the missing data, and that gap feeds the next item types.
- [ ] `query_seconds_typical <= 0.5` for any named question on a 100k-word work with 20k items, after load.
- [ ] `new_type_core_changes == 0`. Adding an item type takes one type definition (fields and schema) and no change to core modules (judged by a test that registers a dummy type).
- [ ] `new_kind_core_changes == 0`. A second text kind (minimal poetry: stanzas and lines) plugs in its structure detection, item types and checklist without touching core modules.
- [ ] `library_id_collisions == 0`. Two works with the same title by different authors coexist. Moving or regrouping a work folder breaks no reference. `lc library --by author|kind|series|tag` lists them.
- [ ] Rename scenario passes: changing a character's name throughout a draft keeps the entity id. Old and new names become aliases, and mention spans are found again.
- [ ] Deletion scenario passes: deleting a paragraph that an item's span or a link depends on flags every dependent item.
- [ ] LLM usability (judged): one documented envelope schema and one documented query schema; `lc codex show|find|ask` output fits its token budget. A fresh LLM session must answer, through the CLI alone, "where is X", "what depends on it", "what changed", and three of the example questions turned into queries. This is checked by a scripted prompt-and-answer review.
- [ ] Skills are built and checked with skill-workshop (the repo skill and any new ones); its validation passes.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `spans.py` (new) | Primary | Create, store and find again text spans: paragraph address with character positions, plus a W3C TextQuoteSelector (exact text, prefix, suffix). Report spans it lost or whose text changed. | Yes | New module | High |
| `codex.py` (new) | Primary | The only reader and writer of Codex files. Item envelope, type registry, in-memory indexes, atomic writes, `check`. | Yes | New module | High |
| Query layer (new) | Primary | The Codex query API (`lc codex ask`): a documented, read-only query surface that the LLM writes against. A library of named questions (parameterised queries) backs checks and proactive feedback. | Yes | New module; the contract other tools depend on, so a replacement Codex must keep it | High |
| Text facts layer (new, computed) | Primary | Facts computed by scripts at load and never stored: tokens and n-grams per span; dialogue spans and their speaker when the item gives one; co-presence of entities per scene and chapter. Expression and relevance questions run on these. | Yes | Rebuilt on load | Medium |
| Sync orchestrator (new, in `codex.py` or `sync.py`) | Primary | New draft → anchor → align (reuses `diff.py`) → relocate spans → flag affected items and their links → re-read queue. | Yes | New flow, replaces the per-type carry-over | High |
| Text kinds (new `kinds/` package) | Primary | Per-kind structure detection, item types and checklist: `novel` (current behaviour), `poem` (proof of modularity). | Yes | `structure.py` becomes the novel kind's detector | Medium |
| Library (`workspace.py`) | Primary | Works found anywhere under the home folder by their settings file. Unique work ids; metadata (author, kind, series, tags); `lc library`. | Yes | Registry and resolve change; existing workspaces keep working | Medium |
| `ingest.py`, `structure.py`, `diff.py` | Dependent | Text, anchors and alignment feed spans and sync. | Small | `diff.py` alignment is reused; may expose character-level diffs within paragraphs | Low |
| `index.py`, `query.py`, `locate.py` | Dependent | Registers, show/find/context and writer locators become views over the Codex. | Yes | Registers computed from items; queries gain span and link answers | Medium |
| `rounds.py`, `report.py`, `docx_out.py` | Dependent | Findings and actions become Codex items. Letters, reports and Word comments read them through queries. | Yes | Rewritten on the Codex; phase-1 round files deleted | Medium |
| `schemas/` | Shared resource | Envelope schema, one schema per item type and the query schema. Phase-1 per-type schemas that the Codex replaces are deleted. | Yes | New schemas, validator reused | Low |
| Workspace folder (writer's Drive) | Shared resource | Codex files: plain JSON/JSONL, synced by Drive. | Yes | New `codex/` folder; atomic file replace; no database files | Medium |
| `prompts/`, Claude skill, chat kit | UI | Procedures that tell the LLM how to read, write and query the Codex through `lc`, including how to turn a writer's question into a query. | Yes | Rewritten around Codex commands; skills built with skill-workshop | Medium |
| `checklist/` | Dependent | Checks that can be measured are tagged `measurable` and point to a named question. | Yes | New field per check | Medium |
| docx-fixer (separate repo) | External | Possible future source of mechanical findings, as items (D-2). | No (later) | None in S0 | Low |

**Impact dimensions**

- **Data:** new `codex/` store per work. Phase-1 per-type files are not migrated: no novel has been analysed yet (D-18).
- **API:** new `lc codex …` (including `ask` and `questions`) and `lc library` commands. Phase-1 commands made obsolete by the Codex are removed, not kept as aliases.
- **Performance:** bounded by the criteria above.
- **User-facing:** none directly; the writer sees the effects in S1 and S2.
- **Operational:** stdlib only; no new dependency.
- **Risk of inaction:** high. S1 (report), S2 (session flow) and any editing tool would each rebuild their own memory, and the rot D-11 forbids would appear.

## 3. Options

### Option A: Extend phase-1 formats (Conservative)

- **Description**: Keep scene cards, registers, findings and actions as separate formats. Add span fields and a carry-over step to each, and a per-format check.
- **Scope**: `index.py`, `rounds.py`, `diff.py`, schemas.
- **Effort**: Medium.
- **Tradeoffs**:
  - Pro: smallest change and familiar files.
  - Con: every new kind of knowledge (facts, references, decisions, entities with aliases) needs its own loader, carry-over and check, which is exactly the maintenance cost D-11 rejects.
  - Con: no common link model, so "what depends on this paragraph" cannot be answered across formats.
  - Con: other text kinds need their own copies.
- **Compatibility**: keeps phase-1 formats, which D-18 no longer requires.

### Option B: Codex core with typed items, spans and sync (Recommended)

- **Description**:
  - `spans.py` keeps spans in place (D-9). `codex.py` holds items in one envelope with typed fields (D-12), stored as plain JSON/JSONL with in-memory indexes (D-10).
  - A sync orchestrator follows each new draft; `lc codex check` keeps the store free of dead or stale knowledge (D-11).
  - Text kinds are plug-ins (D-13); the library holds many works (D-14, D-15).
  - A query layer answers questions (D-16). Measurable checks and proactive feedback are named questions (D-17).
  - Phase-1 per-type formats, code paths and docs are replaced, not migrated (D-18). Registers become computed views.
- **Scope**: new `spans.py`, `codex.py`, query layer, sync, `kinds/`, library. `index.py`, `query.py`, `locate.py`, `rounds.py`, `report.py` and `docx_out.py` are rewritten on the Codex. Prompts, skills (via skill-workshop) and the checklist's `measurable` tags.
- **Effort**: Large.
- **Tradeoffs**:
  - Pro: one shape for every kind of knowledge; spans, links, sync and checks written once; new types and kinds are cheap; the Codex can be replaced behind one module.
  - Con: a larger first build, and phase-1 code paths must be removed cleanly.
- **Compatibility**: breaking by design (D-18). No novel has been analysed, so nothing needs converting.

### Option C: Graph or database store

- **Description**: Same model as B, stored in SQLite or a graph database, with queries in SQL or a graph language.
- **Scope**: as B, plus a storage engine.
- **Effort**: Large.
- **Tradeoffs**:
  - Pro: rich queries.
  - Con: rejected in D-10. Binary files are unsafe under Drive sync, unreadable for writers and LLMs, and add a second representation to keep consistent. At the expected size (≤ 20k items) in-memory indexes are fast enough.
- **Compatibility**: needs a migration and a non-text store.

### Query surface (part of Option B)

The query API is the Codex's contract with the LLM and with every other tool,
so its form matters as much as storage. Three forms fit D-10 (plain-text
storage):

| | Q-a: named questions only | Q-b: JSON query language | Q-c: read-only SQL over an in-memory view |
|---|---|---|---|
| What the LLM writes | A question name and its parameters | A JSON object: select, filter, join, group, as defined by our schema | SQL against documented tables (items, spans, mentions, links, paragraphs, chapters, tokens, n-grams), built in memory at load by Python's standard `sqlite3` and never written to disk |
| New question | New code each time | Usually expressible; joins and grouping must be designed and built by us | Usually expressible; LLMs write SQL fluently |
| Effort | Small | Large (we own a query engine) | Medium (tables and loaders; the engine is stdlib) |
| Risk | Rigid: unplanned questions fail | Our engine's bugs and limits | Table layout becomes a contract; mitigated by documenting it as the API and versioning it |
| Fits "our special SQL, some kind of API" | Partly | Yes | Yes, with real SQL |
| Storage (D-10) | Unchanged | Unchanged | Unchanged: plain files stay the only storage; the SQL view is rebuilt on each load |

Named questions sit on top in Q-b and Q-c alike: they are saved, tested
queries with parameters, and the checks and proactive feedback use them.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Medium | Large | Large |
| Risk | Low now, high later (rot, duplicated code) | Medium (new core, rewrite of phase-1 paths) | High (sync corruption, opacity) |
| Completeness | Partial: no links, no cross-type sync | Full | Full |
| Compatibility | Full | Breaking by design (D-18); nothing to convert | Needs migration and a binary store |
| Maintenance | Grows with every type and kind | Flat: one envelope, one sync, one check | Flat, plus storage engine upkeep |

## 4. Recommendation

**Recommended option**: Option B. It is the only option that meets D-11 (one envelope, one sync, one check, nothing stored that can be recomputed) and D-13 (kinds as plug-ins). It does so with plain-text storage (D-10) and without the maintenance growth of Option A.

**Recommended query surface**: Q-c, read-only SQL over an in-memory view, with named questions on top. Reasons:
- LLMs already write SQL well, so turning a writer's question into a query needs no new language.
- The engine is in the standard library, so we build only the tables.
- Storage stays plain text (D-10), because the view lives only in memory.
- Questions nobody planned for still work.

The documented table layout is the API, versioned like a schema, so the Codex stays replaceable (D-10). Agreed in D-19.

**Immediate next action**: `design` splits B into tasks, in this order:
1. `spans.py` with its relocation test corpus (it carries the riskiest criteria).
2. The `codex.py` envelope, type registry and check.
3. The query layer, the text facts layer and the first named questions, built on a fixture Codex of a corpus text.
4. Sync on top of `diff.py`.
5. Kinds: `novel` (current structure detection moved in), then `poem`.
6. Library.
7. Rewrite of locate, rounds, report and Word comments on the Codex; removal of phase-1 formats and docs.
8. The checklist's `measurable` tags mapped to named questions; prompts and skills via skill-workshop.

**Open questions** (for `design`, none blocks the direction):
- [ ] File layout inside `codex/`: one JSONL per item type, or one per layer (bible, threads, ledger, journal). Either way, only `codex.py` knows.
- [ ] Item history: kept inside each item (last N changes) or in an append-only change log per work.
- [ ] Which item types ship first: entity (character, place, object, rule), mention, fact, reference/link, issue, decision, scene card, session note.
- [ ] Information-density measure (D-8): items per 1,000 words per span, or weighted by item type. Defined with the first metric that uses it.
- [ ] Work ids: slug from author and title, or random short id plus a readable slug.
- [ ] Speaker attribution for dialogue: written by the LLM into items (who speaks in each dialogue span), with a script heuristic as a first guess. Which part goes where.

**Decisions log** (carried unchanged from `explore-idea`):

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | First surface is Claude | agreed | 2026-10-11 |
| D-2 | docx-fixer stays a separate repo, used as a tool or API, possibly merged later | agreed | 2026-10-11 |
| D-3 | Report and session flow first; editing real files later | agreed | 2026-10-11 |
| D-4 | Order: report (S1), session flow (S2), Claude packaging (S3) | superseded by D-6 | 2026-10-11 |
| D-5 | Working notes are separate from writer-facing output; writer output is a per-session view chosen by the session goal; summarise status, let the writer choose, never repeat settled points | agreed | 2026-10-11 |
| D-6 | The knowledge base (S0) is the core and comes first, then S1–S3 | agreed | 2026-10-11 |
| D-7 | The knowledge base is the Codex; "bible" is its characters-and-world layer | agreed | 2026-10-11 |
| D-8 | No fixed sentence level; knowledge is anchored to spans of any length, which also measure information density | agreed | 2026-10-11 |
| D-9 | Spans: paragraph address and character positions, plus a W3C text-quote selector (as Hypothesis does); changed or lost text is flagged, never moved silently; own module | agreed | 2026-10-11 |
| D-10 | Storage: plain JSON/JSONL behind one module (`codex.py`) with in-memory indexes; no SQLite; replaceable later | agreed | 2026-10-11 |
| D-11 | Design rules: simple, LLM-friendly; store only what cannot be recomputed; stable ids; a check command against dead references, orphans and stale spans; a small change costs a small update | agreed | 2026-10-11 |
| D-12 | Items: one shared envelope (id, type, spans, links, status, text, history) plus a few typed fields per type | agreed | 2026-10-11 |
| D-13 | Modular by kind of text (novel, short story, poetry, script, thesis, textbook…); a core that does not depend on the kind | agreed | 2026-10-11 |
| D-14 | Many works side by side without collisions | agreed | 2026-10-11 |
| D-15 | Works live anywhere under the home folder, found by their settings file; unique ids; author, kind, series and tags are metadata; grouping is a command | agreed | 2026-10-11 |
| D-16 | The Codex answers questions through a query API (the LLM turns a question into a query), like a database | agreed (spec notes r1) | 2026-10-11 |
| D-17 | Measurable checks and proactive feedback are named questions run against the Codex | agreed (spec notes r1) | 2026-10-11 |
| D-18 | No migration: phase-1 per-type formats and docs are replaced; the tool is rebuilt on the Codex from corpus examples; real novels may add item types later | agreed (spec notes r1) | 2026-10-11 |
| D-19 | Query surface: read-only SQL over an in-memory view (stdlib `sqlite3`, never persisted), with named questions on top; what the Codex stores and computes is derived from a catalogue of writer questions, so translations have enough to work with | agreed | 2026-10-11 |

---

> Sections 5–6 (contracts, risks) are appended by `design`.
