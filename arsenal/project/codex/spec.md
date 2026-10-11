# Specification: Codex — the structured knowledge base behind every reading, report and edit

**Date**: 2026-10-11
**Ticket / PR**: phase 2, sub-project S0 (from `status/ideas.md`)
**Author**: imarcos + Claude
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the explore-idea session approved 2026-10-11 (D-1…D-15)

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

**Success criteria (measurable)**. Each criterion is measured on the public corpus (`corpus/`) plus scripted edits; no working novel is used.

- [ ] `span_relocation_accuracy >= 0.98`. Spans whose text is unchanged are found again at the right place after scripted edits: moves, insertions and deletions around them, splits and merges of their paragraph.
- [ ] `silent_misanchors == 0`. A span whose text changed, or that cannot be found, is always flagged `needs_reread`; it is never placed at a wrong position.
- [ ] `sync_touched_ratio <= 1.5`. On a single-paragraph edit, items flagged / items whose spans or links actually reach the edited paragraph.
- [ ] `sync_seconds_100k <= 5`. Wall time for a full sync of a 100k-word work with 20k items on a laptop-class machine.
- [ ] `codex_load_seconds_20k <= 1`. Load time for 20k items with all in-memory indexes.
- [ ] `check_detection_rate == 1.0`. `lc codex check` finds every injected defect: dead link, orphan item, stale span, duplicate id, item failing its type schema.
- [ ] `phase1_migration_loss == 0`. Every phase-1 artefact (scene cards, findings, round actions with statuses) converts to Codex items and back without losing a field. Registers are not stored: they are recomputed from items (D-11).
- [ ] `new_type_core_changes == 0`. Adding an item type takes one type definition (fields and schema) and no change to core modules (judged by a test that registers a dummy type).
- [ ] `new_kind_core_changes == 0`. A second text kind (minimal poetry: stanzas and lines) plugs in its structure detection, item types and checklist without touching core modules.
- [ ] `library_id_collisions == 0`. Two works with the same title by different authors coexist. Moving or regrouping a work folder breaks no reference. `lc library --by author|kind|series|tag` lists them.
- [ ] Rename scenario passes: changing a character's name throughout a draft keeps the entity id. Old and new names become aliases, and mention spans are found again.
- [ ] Deletion scenario passes: deleting a paragraph that an item's span or a link depends on flags every dependent item.
- [ ] LLM usability (judged): one documented envelope schema; `lc codex show|find` output fits its token budget; a fresh LLM session can answer "where is X, what depends on it, what changed" through the CLI alone, checked by a scripted prompt-and-answer review.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `spans.py` (new) | Primary | Create, store and find again text spans: paragraph address with character positions, plus a W3C TextQuoteSelector (exact text, prefix, suffix). Report spans it lost or whose text changed. | Yes | New module | High |
| `codex.py` (new) | Primary | The only reader and writer of Codex files. Item envelope, type registry, in-memory indexes, queries, atomic writes, `check`. | Yes | New module | High |
| Sync orchestrator (new, in `codex.py` or `sync.py`) | Primary | New draft → anchor → align (reuses `diff.py`) → relocate spans → flag affected items and their links → re-read queue. | Yes | New flow, replaces the per-type carry-over | High |
| Text kinds (new `kinds/` package) | Primary | Per-kind structure detection, item types and checklist: `novel` (current behaviour), `poem` (proof of modularity). | Yes | `structure.py` becomes the novel kind's detector | Medium |
| Library (`workspace.py`) | Primary | Works found anywhere under the home folder by their settings file. Unique work ids; metadata (author, kind, series, tags); `lc library`. | Yes | Registry and resolve change; existing workspaces keep working | Medium |
| `ingest.py`, `structure.py`, `diff.py` | Dependent | Text, anchors and alignment feed spans and sync. | Small | `diff.py` alignment is reused; may expose character-level diffs within paragraphs | Low |
| `index.py`, `query.py`, `locate.py` | Dependent | Registers, show/find/context and writer locators become views over the Codex. | Yes | Registers computed from items; queries gain span and link answers | Medium |
| `rounds.py`, `report.py`, `docx_out.py` | Dependent | Findings and actions become Codex items. Letters, reports and Word comments read them. | Yes | Migration of round files; behaviour unchanged for the writer | Medium |
| `schemas/` | Shared resource | Envelope schema plus one schema per item type. Existing phase-1 schemas stay valid for migration input. | Yes | New schemas, validator reused | Low |
| Workspace folder (writer's Drive) | Shared resource | Codex files: plain JSON/JSONL, synced by Drive. | Yes | New `codex/` folder; atomic file replace; no database files | Medium |
| `prompts/`, Claude skill, chat kit | UI | Procedures that tell the LLM how to read and write the Codex through `lc`. | Yes | Rewritten around Codex commands | Medium |
| docx-fixer (separate repo) | External | Possible future source of mechanical findings, as items (D-2). | No (later) | None in S0 | Low |

**Impact dimensions**

- **Data:** new `codex/` store per work, plus a one-time migration of phase-1 files (kept, not deleted).
- **API:** new `lc codex …` and `lc library` commands; existing commands keep their flags.
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
- **Compatibility**: fully backwards compatible.

### Option B: Codex core with typed items, spans and sync (Recommended)

- **Description**:
  - `spans.py` keeps spans in place (D-9). `codex.py` holds items in one envelope with typed fields (D-12), stored as plain JSON/JSONL with in-memory indexes (D-10).
  - A sync orchestrator follows each new draft; `lc codex check` keeps the store free of dead or stale knowledge (D-11).
  - Text kinds are plug-ins (D-13); the library holds many works (D-14, D-15).
  - Phase-1 artefacts are migrated into items; registers become computed views.
- **Scope**: new `spans.py`, `codex.py`, sync, `kinds/`, library. Adapters in `index.py`, `query.py`, `locate.py`, `rounds.py`, `report.py`, `docx_out.py`; prompts and skill.
- **Effort**: Large.
- **Tradeoffs**:
  - Pro: one shape for every kind of knowledge; spans, links, sync and checks written once; new types and kinds are cheap; the Codex can be replaced behind one module.
  - Con: a migration step, and a larger first build.
- **Compatibility**: phase-1 files stay readable; migration is explicit (`lc codex migrate`), repeatable, and keeps the originals.

### Option C: Graph or database store

- **Description**: Same model as B, stored in SQLite or a graph database, with queries in SQL or a graph language.
- **Scope**: as B, plus a storage engine.
- **Effort**: Large.
- **Tradeoffs**:
  - Pro: rich queries.
  - Con: rejected in D-10. Binary files are unsafe under Drive sync, unreadable for writers and LLMs, and add a second representation to keep consistent. At the expected size (≤ 20k items) in-memory indexes are fast enough.
- **Compatibility**: needs a migration and a non-text store.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Medium | Large | Large |
| Risk | Low now, high later (rot, duplicated code) | Medium (new core, migration) | High (sync corruption, opacity) |
| Completeness | Partial: no links, no cross-type sync | Full | Full |
| Compatibility | Full | Full, through explicit migration | Needs migration and a binary store |
| Maintenance | Grows with every type and kind | Flat: one envelope, one sync, one check | Flat, plus storage engine upkeep |

## 4. Recommendation

**Recommended option**: Option B. It is the only option that meets D-11 (one envelope, one sync, one check, nothing stored that can be recomputed) and D-13 (kinds as plug-ins). It does so with plain-text storage (D-10) and without the maintenance growth of Option A.

**Immediate next action**: `design` splits B into tasks, in this order:
1. `spans.py` with its relocation test corpus (it carries the riskiest criteria).
2. The `codex.py` envelope, type registry and check.
3. Sync on top of `diff.py`.
4. Migration of phase-1 artefacts.
5. Kinds: `novel` refactor, then `poem`.
6. Library.
7. Adapters, prompts and skill.

**Open questions** (for `design`, none blocks the direction):
- [ ] File layout inside `codex/`: one JSONL per item type, or one per layer (bible, threads, ledger, journal). Either way, only `codex.py` knows.
- [ ] Item history: kept inside each item (last N changes) or in an append-only change log per work.
- [ ] Which item types ship first: entity (character, place, object, rule), mention, fact, reference/link, issue, decision, scene card, session note.
- [ ] Information-density measure (D-8): items per 1,000 words per span, or weighted by item type. Defined with the first metric that uses it.
- [ ] Work ids: slug from author and title, or random short id plus a readable slug.

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

---

> Sections 5–6 (contracts, risks) are appended by `design`.
