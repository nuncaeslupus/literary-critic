# Plan: literary-critic — LLM-assisted novel indexing, analysis and revision feedback

**Date**: 2026-10-10
**Specification**: `status/specification.md`
**Author**: imarcos + Claude
**Revision**: 1
**Status**: approved (by the user, 2026-10-10)
**Revision log**:
- r1 — first draft

---

## Technical solution

### Architecture overview

Three layers. **Scripts** (`src/litcritic`, `lc` CLI, stdlib only) do everything
deterministic. **Catalogue and schemas** (`checklist/`, `schemas/`) define what is
checked and the shape of every LLM-produced artefact. **Procedures** (`prompts/`,
wrapped as `.claude/skills/` for Claude Code) tell the LLM how to run a guided,
conversational session: orientation → indexing → staged analysis → revision
rounds → re-index and verify. All novel state lives in a workspace outside the repo.

### Data flow

```text
manuscript (.docx/.odt/.md/.txt)
  → lc ingest → text/vNNN.txt
  → lc anchor → index/vNNN/structure.json
  → LLM scene cards (per scene, validated) → lc build → registers (characters, timeline, motifs, ledger…)
  → lc metrics → metrics/vNNN.json
  → lc checklist plan (profile) → LLM runs checks with lc show/find/context → findings
  → lc round build → actions + letter (writer locators) → conversation with the writer
  → new draft → lc ingest/anchor → lc diff → stale scenes re-carded → actions verified
```

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| workspace | files | CREATE/UPDATE | per-draft text, index, metrics; append-only findings and actions with status |

### Technology choices

| Choice | Justification |
|--------|--------------|
| Python ≥3.12 stdlib runtime | Runs in chat code interpreters; `tomllib` for catalogue |
| TOML catalogue, JSON artefacts | Human-editable checks; machine-validated outputs |
| Paragraph fingerprints + `difflib` alignment | Deterministic anchors that survive edits without pages |
| `.docx` comments via zip/XML | Write-back the writer can review in Word or Google Docs |

### Out of scope

- Writing or rewriting manuscript prose (D-12).
- Heavy NLP/embeddings (Option C); possible optional extras later.
- PDF ingestion beyond plain text extraction (later, if needed).

---

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Bootstrap: arsenal base, rules, workspace resolver, content guard, CI | lc | S | — | `guard_false_negatives == 0` | `test_term_in_content_blocked_accent_insensitive` in `tests/test_guard.py` — accented variants are blocked |
| T2 | Analysis checklist: format, validator, generic catalogue (≥20 areas, all stages), traits, metric registry | checklist | M | T1 | `checklist_errors == 0` | `test_repo_catalogue_is_valid` in `tests/test_checklist.py` — catalogue loads with 0 errors and covers all stages |
| T3 | Corpus: public-domain novels (es, en) with source notes; synthetic-edit generator | corpus | S | T1 | `corpus_sources_documented == 1.0` | `test_corpus_has_source_notes` in `tests/test_corpus.py` — every text has origin and licence note |
| T4 | Ingest `.txt/.md/.docx/.odt` to normalised paragraphs + snapshots | lc | M | T3 | `ingest_paragraph_fidelity >= 0.999` | `test_docx_paragraphs_match_text` in `tests/test_ingest.py` — docx fixture yields the same paragraphs as its txt twin |
| T5 | Anchors + structure detection (parts, chapters, scene breaks; LLM-proposed boundaries validated) | lc | M | T4 | `scene_boundary_f1 >= 0.95` | `test_structure_detects_chapters_and_breaks` in `tests/test_anchor.py` — known corpus structure recovered |
| T6 | Draft alignment: old→new anchor map, changed/moved/new/deleted, stale scenes | lc | M | T5 | `anchor_stability_after_synthetic_edits >= 0.99` | `test_alignment_survives_synthetic_edits` in `tests/test_diff.py` — unchanged paragraphs keep anchors; recall ≥0.98, precision ≥0.95 |
| T7 | Metrics engine (es, en) for the registry in `checklist/metrics.toml` | lc | M | T5 | `planned_metrics_implemented >= 0.8` | `test_readability_es_golden` in `tests/test_metrics.py` — Fernández-Huerta/INFLESZ match hand-computed values |
| T8 | Schemas + `lc validate` for scene cards, registers, findings, actions, profile | schemas | S | T2 | `schema_validity_on_fixtures == 1.0` | `test_invalid_finding_without_anchor_rejected` in `tests/test_validate.py` — finding without anchors fails |
| T9 | Index build (registers from scene cards) + `lc show/find/context --budget` | lc | M | T6, T8 | `index_query_tokens_p95 <= 2500` | `test_context_respects_budget` in `tests/test_query.py` — output never exceeds the budget |
| T10 | Procedures: orientation, scene-card extraction, check execution, conversational guide; skills wrapping them | prompts | M | T2, T9 | `prompts_reference_valid_commands == 1.0` | `test_prompts_only_reference_existing_commands` in `tests/test_prompts.py` — every `lc` call in prompts exists |
| T11 | Findings → rounds → actions + writer locators + letter render | lc | M | T9, T10 | `writer_locators_complete == 1.0` | `test_locator_first_last_words_unique` in `tests/test_locate.py` — quoted openings/closings occur once in the draft |
| T12 | `.docx` copy with anchored comments (never touches the original) | lc | M | T11 | `docx_comment_anchor_accuracy == 1.0` | `test_comments_attach_to_target_paragraphs` in `tests/test_docx_out.py` — each comment wraps the intended paragraph |
| T13 | `lc pack/unpack` with checksummed manifest; stale-overwrite refusal | lc | S | T4 | `stale_overwrite_blocked == 1.0` | `test_unpack_refuses_older_zip` in `tests/test_pack.py` — older zip cannot overwrite newer workspace |
| T14 | Chat kit: zip, `START_HERE.md`, no-code reduced mode; platform check | kit | M | T10, T13 | `runtime_third_party_imports == 0` | `test_runtime_is_stdlib_only` in `tests/test_stdlib_only.py` — no non-stdlib import in `src/litcritic` |
| T15 | `reader-report` mode (agency/editor assessment) | prompts | M | T11 | `reader_report_sections_complete == 1.0` | `test_reader_report_template_sections` in `tests/test_report.py` — rendered report has every required section |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

T1 ☑ · T2 ☑ (PR #1) · T3 ☑ (PR #2) · T8 ☑ (PR #16) · T4 ◐ · other T5–T15 ☐ (queued as `arsenal/tasks/`, issues #3–#14)

**Merge order**: T1 → T2 → T3 → T4 → T5 → (T6, T7, T8) → T9 → T10 → T11 → (T12, T13) → T14 → T15
**Branch pattern**: `claude/<slug>` per task PR

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|
| T1 | `guard_false_negatives == 0` | 0 | `uv run pytest tests/test_guard.py` | 9e6cf92 | [HERE] | 2026-10-10 |
| T2 | `checklist_errors == 0` | 0 (23 areas, 201 checks after critical pass) | `uv run lc checklist validate` | 9e6cf92 | [HERE] | 2026-10-10 |
| T3 | `corpus_sources_documented == 1.0` | 1.0 (2 texts: es 50.5k words, en 25.6k words) | `uv run lc corpus check` | a440478 | [HERE] | 2026-10-10 |
| T4 | `ingest_paragraph_fidelity >= 0.999` | 1.0 (9,720 paragraphs, docx+odt twins) | `uv run pytest tests/test_ingest.py` | 741fa89+ | [HERE] | 2026-10-11 |
| T5 | `scene_boundary_f1 >= 0.95` | 1.0 (9 variants, both corpus texts) | `uv run pytest tests/test_anchor.py` | 434307b+ | [HERE] | 2026-10-11 |
| T6 | `anchor_stability_after_synthetic_edits >= 0.99` | ≥0.999 on corpus (recall 1.0, precision ≥0.99) | `uv run pytest tests/test_diff.py` | T5+ | [HERE] | 2026-10-11 |
| T7 | `planned_metrics_implemented >= 0.8` | 0.942 (49/52; golden FH (corrected)/INFLESZ/Flesch exact) | `uv run pytest tests/test_metrics.py` | T6+ | [HERE] | 2026-10-11 |
| T13 | `stale_overwrite_blocked == 1.0` | 1.0 (4/4 stale cases refused) | `uv run pytest tests/test_pack.py` | T7+ | [HERE] | 2026-10-11 |
| T9 | `index_query_tokens_p95 <= 2500` | 1929 (125 queries, default budget 2000) | `uv run pytest tests/test_query.py` | T13+ | [HERE] | 2026-10-11 |
| T10 | `prompts_reference_valid_commands == 1.0` | 1.0 (37 references, 9 documents) | `uv run pytest tests/test_prompts.py` | T9+ | [HERE] | 2026-10-11 |
| T11 | `writer_locators_complete == 1.0` | 1.0 (corpus sample; private draft also 1.0) | `uv run pytest tests/test_locate.py` | T10+ | [HERE] | 2026-10-11 |
| T8 | `schema_validity_on_fixtures == 1.0` | 1.0 (19 fixtures, 5 kinds) | `uv run pytest tests/test_validate.py` | 741fa89+ | [HERE] | 2026-10-10 |

### Dependency graph

```text
T1 ─> T2 ─────────────┬─> T8 ──┐
 └──> T3 ─> T4 ─> T5 ─┼─> T6 ──┼─> T9 ─> T10 ─> T11 ─┬─> T12
            │         └─> T7   │                    ├─> T15
            └─> T13 ───────────┴────────────────────┴─> T14
```

---

## Sign-off

- [ ] Design reviewed
- [ ] Contracts agreed
- [ ] Ready for execution
