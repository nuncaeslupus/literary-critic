# Specification: literary-critic — LLM-assisted novel indexing, analysis and revision feedback

**Date**: 2026-10-10
**Ticket / PR**: bootstrap
**Author**: imarcos + Claude
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft

---

## 1. Problem statement

A novel manuscript (80k–200k words) does not fit usefully in an LLM's working
context, has no stable addresses (page numbers change with every edit and many
drafts have no chapter marks), and changes between drafts. An LLM asked to
critique it therefore forgets details, cannot relate distant events or track
characters and timelines, gives vague feedback, and loses all state between chat
sessions. Writers need an editor-like process instead: a reliable map of the
book, a systematic analysis at every level (structure → scene → line) backed by
evidence from the text, and a finite, prioritised list of concrete revision
actions that is re-checked against each new draft. The process must run in
Claude Code (local and cloud) and, in reduced form, in ordinary chatbots
(ChatGPT, Claude.ai, Gemini) used by non-technical writers, with working files
persisted outside the tool repo (a Drive folder by preference) and with no
working-novel content ever entering the repo.

**Success criteria (measurable)**:

- [ ] `anchor_stability_after_synthetic_edits >= 0.99` — share of unchanged paragraphs keeping their anchor after scripted insert/delete/move/edit operations on corpus novels.
- [ ] `changed_paragraph_detection_recall >= 0.98` and `precision >= 0.95` on the same synthetic edit suite.
- [ ] `index_query_tokens_p95 <= 2500` — tokens returned by any `lc` query command at default budget, measured on a 150k-word corpus novel.
- [ ] `l0_plus_l1_tokens <= 8000` — whole-novel orientation (synopsis + chapter summaries) for a 150k-word novel.
- [ ] `scene_card_schema_validity == 1.0` and `findings_schema_validity == 1.0` on generated artefacts.
- [ ] `findings_with_anchor_evidence == 1.0` — every finding cites at least one valid anchor.
- [ ] `checklist_coverage == 1.0` — every check area in the catalogue has ≥1 check with method, inputs, evidence rule and severity rubric.
- [ ] `runtime_third_party_imports == 0` in `src/litcritic/`.
- [ ] `guard_false_negatives == 0` on the guard test suite (guarded terms, accented variants, manuscript files).
- [ ] `ingest_paragraph_fidelity >= 0.999` — normalised paragraphs match the source `.docx`/`.odt`/`.md`/`.txt` text after whitespace normalisation, on corpus fixtures.
- [ ] Usability judged on the first working novel: the writer can complete one full round (index → analysis → letter → revised draft → re-index → verification) and rates the actions concrete and actionable; recorded in a generic retrospective with no novel content.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `src/litcritic/` (`lc` CLI) | Primary | Deterministic work: ingest, anchor, diff, index build, metrics, query, validate, pack/unpack, render, guard | Yes (new) | All scriptable steps; stdlib only so it runs in chat code interpreters | High |
| `checklist/` | Primary | Generic catalogue of analysis checks (TOML) | Yes (new) | Drives part 2; adapted per novel via a profile kept in the workspace | High |
| `schemas/` | Shared resource | JSON schemas: anchors, structure, scene card, character, timeline event, finding, action | Yes (new) | Contract between LLM output and scripts; validation gates | High |
| `prompts/` + `.claude/skills/` | UI | LLM procedures: scene-card extraction, check execution, letter writing; skills wrap prompts + scripts for Claude Code | Yes (new) | Same prompts usable from any chatbot | Med |
| Workspace folder (outside repo) | Shared resource | Per-novel state: snapshots, normalised text, index, metrics, findings, rounds, log | Yes (format) | Persistence across sessions/surfaces; Drive-friendly plain files | High |
| Manuscript sources (.docx, Google Docs) | Dependent | Input; optional comment/suggestion output | Yes (adapters) | Read always; write only with explicit permission, comments/suggestions first | Med |
| Content guard + CI | Infrastructure | Keeps novel content out of the repo; runs lint/type/tests/gates | Yes (done in bootstrap) | Enforces the hard rule mechanically | High |
| claude-arsenal bundle | Infrastructure | Task queue, gates, spec/plan workflow | No | Process only | Low |

Impact dimensions: **Data** — workspace format is a long-lived contract (versioned `schema_version`). **Performance** — token cost per query is a first-class metric. **User-facing** — non-technical writers in plain chat. **Risk of inaction** — feedback stays generic and unrepeatable.

## 3. Options

### Option A: Pure prompt kit (Conservative)

- **Description**: A set of Markdown prompts and a folder convention; the LLM does all chunking, indexing and tracking by itself.
- **Scope**: `prompts/`, docs.
- **Effort**: Small
- **Tradeoffs**: Works in any chatbot, but non-deterministic anchors, no reliable diff between drafts, no metrics, high token use, results not reproducible.
- **Compatibility**: Universal.

### Option B: Stdlib Python core + portable prompts + layered index (Recommended)

- **Description**: Deterministic `lc` CLI (stdlib only) does ingest, content-addressed paragraph anchors, scene segmentation, draft-to-draft alignment, metrics, index assembly, query-with-budget, validation, rendering and zip pack/unpack. The LLM fills judgment slots defined by JSON schemas (scene cards, check results, letters), one bounded unit at a time. Three surfaces: Claude Code (full), chat with code execution (kit zip + workspace zip), chat without code (prompts only, reduced, says so).
- **Scope**: All systems in §2.
- **Effort**: Large (phased)
- **Tradeoffs**: More to build; stdlib-only limits NLP (no POS tagger — use language word lists and heuristics; optional extras later).
- **Compatibility**: Runs wherever Python ≥3.12 runs, including ChatGPT/Claude.ai sandboxes (verify Python version per platform; fall back to 3.10-compatible syntax if needed).

### Option C: Full NLP/RAG stack (spaCy, embeddings, vector DB)

- **Description**: Heavy NLP for coreference, entity linking, semantic search.
- **Scope**: As B plus models and services.
- **Effort**: Large
- **Tradeoffs**: Better entity resolution, but cannot run in chat sandboxes or for non-technical users, adds cost and setup; embeddings add little over a well-built structured index for a single book.
- **Compatibility**: Local/cloud dev only.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large (phased) | Large |
| Risk | High (unreliable) | Medium | High (setup) |
| Completeness | Low | High | High |
| Compatibility | Universal | Broad | Narrow |
| Maintenance | Low | Medium | High |

## 4. Recommendation

**Recommended option**: Option B — the only option that is deterministic, measurable, cheap in tokens and still usable from ordinary chatbots.

Key design points carried into `design`:

1. **Anchors**: hierarchy Part › Chapter › Scene › Paragraph with readable ids (`c03.s2.p14`) plus a content fingerprint per paragraph. Draft alignment = exact-hash match, then fuzzy match for edited paragraphs, then order-aware resolution for moves; output an old→new anchor map and a list of stale scenes. Pages are never used as addresses (only reported, when the source has them, as a convenience).
2. **Segmentation**: scripts detect headings and scene breaks; when absent, the LLM proposes scene boundaries over numbered paragraph windows and a script validates them.
3. **Layered index** (load only what is needed): L0 novel profile & synopsis · L1 chapter summaries · L2 scene cards (summary, POV, characters, place, story time, events, setups/payoffs, open threads) · L3 raw text by anchor. Derived registers built by script: characters (aliases), relationships (evidence anchors), timeline (story vs discourse order), locations, motifs, setup/payoff ledger.
4. **Checklist**: catalogue of checks grouped by level (editorial order: developmental → scene → line). Each check: id, area, question, method (script | llm | hybrid), required index layers, evidence rule, severity rubric, output schema. After the first pass, a per-novel profile (in the workspace) enables, disables and weights checks.
5. **Findings → actions**: findings (check id, anchors, evidence, severity, confidence, effort) are prioritised by script into revision rounds: R1 structural (move/cut/merge/add), R2 scene & character, R3 prose & dialogue. Each round yields a writer-facing letter in the novel's language and a machine-readable backlog (accepted / rejected / done / deferred). A round closes when no open high-severity finding remains or the writer closes it; a new draft is re-indexed and the backlog verified against the diff, with metric deltas.
6. **Audience**: `writer` (default; revision letter) and later `reader-report` (agency/editor assessment: strengths, market fit, verdict) from the same findings.
7. **Documents**: read `.docx`/`.odt`/`.md`/`.txt` (Google Docs via export). Write-back only with explicit permission: `.docx` with anchored comments and tracked changes (`w:ins`/`w:del`), which Google Docs imports as comments/suggestions; direct Docs API edits only for confirmed changes.
8. **Persistence**: workspace folder outside the repo (Drive preferred); `lc pack`/`lc unpack` zip round-trip with checksummed manifest for chat and cloud sessions.
9. **Guarding**: `lc guard` + pre-commit + CI; per-workspace `guard-terms.txt`.
10. **Language**: repo in English; prompts language-agnostic; metrics language-aware (es, en first: Fernández-Huerta / Szigriszt-INFLESZ, Flesch, MTLD, -mente/-ly density, dialogue ratio, sentence-length variance, repetition).

**Immediate next action**: Build part 2 first — the check catalogue (`checklist/*.toml`) with its schema and validator — from `docs/research/analysis-frameworks.md` plus the user-supplied external list (used as input only, not committed).

**Open questions**:
- [ ] Python version available in each chatbot sandbox (confirm ≥3.12 or lower the floor).
- [ ] Whether Claude.ai / ChatGPT Drive connectors can write arbitrary files (JSON/zip) reliably enough to skip the zip round-trip.
- [ ] `reader-report` audience: scope and when (after the first full writer round).

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| D-1 | Never add anything about specific working novels to the repo; enforced by `lc guard` | agreed | 2026-10-10 |
| D-2 | `[[...]]` = repo talk; plain messages = working novel; generic learnings go to the repo unprompted | agreed | 2026-10-10 |
| D-3 | Runtime is Python stdlib only, while possible | agreed | 2026-10-10 |
| D-4 | Workspaces live outside the repo; Drive folder preferred, zip round-trip as portable fallback | agreed | 2026-10-10 |
| D-5 | Public-domain novels (en, es) allowed under `corpus/` for tests and examples | agreed | 2026-10-10 |
| D-6 | Build order: part 2 (checklist) → part 1 (index) → part 3 (feedback) → chat kit | agreed | 2026-10-10 |
| D-7 | Default audience is the writer; agency/editor reader report later | agreed | 2026-10-10 |
| D-8 | Work language follows the writer/novel; repo artefacts in English | agreed | 2026-10-10 |
| D-9 | Manuscript edits only with explicit per-change permission; comments/suggestions first | agreed | 2026-10-10 |

---

> Sections 5–6 (contracts, risks) are appended by `design`.
