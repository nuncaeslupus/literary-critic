# Literary Critic — Plan (annotated edition)

> Generated 2026-10-13. This is the document with a **note slot** after every section. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Plan

## Preamble & scope

**Date**: 2026-10-13
**Specification**: `arsenal/project/doccontrol/spec.md` (approved, revision 2)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft

> Review record, kept the way the spec keeps its own: each round of notes bumps
> **Revision** with a log line naming the `<project>-plan-notes-<date>-rN.md`
> export it applied, committed beside this file in the same commit. Approval is
> `approved (YYYY-MM-DD, revision N)`, plus `— without annotations` when there
> were none.

<!-- -->

> **✎ Notes** · `PLAN · intro`
> _(your notes here — replace this line)_

## Technical solution



<!-- -->

> **✎ Notes** · `PLAN › Technical solution`
> _(your notes here — replace this line)_

### Architecture overview

One adapter, `litcritic.dc`, is the only module that imports `doc_control`. Everything that
reads or writes a document goes through it. literary-critic keeps the literary layer on top:
`cNN.sN.pN` labels, the Codex and its spans, checks, rounds, reports, prompts, metrics, setup
and the kit. Non-`.docx` manuscripts pass through `litcritic.convert` (D-6) and then follow the
`.docx` path.

```drawspec
{"version": 1, "kind": "flow",
 "nodes": [
  {"id": "src", "text": "Writer's file\n.docx / .txt / .md / .odt"},
  {"id": "conv", "text": "convert\n(non-.docx only)"},
  {"id": "dc", "text": "litcritic.dc\nadapter"},
  {"id": "doc", "text": "doc-control\nread · segment · diff · locate\nbatch · rename · comments · undo"},
  {"id": "lit", "text": "literary layer\nlabels · Codex · checks\nrounds · reports"}
 ],
 "edges": [
  {"from": "src", "to": "conv"}, {"from": "conv", "to": "dc"}, {"from": "src", "to": "dc", "label": ".docx"},
  {"from": "dc", "to": "doc"}, {"from": "dc", "to": "lit"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Architecture overview`
> _(your notes here — replace this line)_

### Data flow

- **Ingest**: snapshot to `manuscript/vNNN.<ext>` → (convert) → `dc.paragraphs` → `text/vNNN.txt` + `meta.json` (schema 2, `at` per paragraph).
- **Index**: `segment` (with the workspace overrides) → `index/vNNN/structure.json` with labels and doc-control ids.
- **New draft**: `diff old new` → address map → `sync` re-anchors Codex spans (exact only) and flags re-reads.
- **Edits the writer approved**: rounds → `batch` / `term.rename` / `comment.add` on the writer's `.docx` (doc-control backs up, checks locks and on-disk changes, verifies, logs, can undo).
- **Locating for the writer**: `locate` (chapter, scene, page, unique phrase, Word Find string) → described in the writer's language by `locate.describe`.

<!-- -->

> **✎ Notes** · `PLAN › Data flow`
> _(your notes here — replace this line)_

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| Workspace | `text/vNNN.meta.json` | UPDATE | `schema_version: 2`, `at` replaces `src` |
| Workspace | `index/vNNN/structure.json` | UPDATE | doc-control ids and signals beside the labels |
| Workspace | `analysis/structure-overrides.json` | UPDATE | doc-control override shape (D-7) |
| Workspace | `.safe-edit/` state and backups | DELETE (after upgrade) | doc-control's store holds backups and the undo log |

<!-- -->

> **✎ Notes** · `PLAN › State changes`
> _(your notes here — replace this line)_

### Technology choices

| Choice | Justification |
|--------|--------------|
| `doc-control>=0.0.1,<0.1` as the only runtime dependency | D-1; stdlib only itself, so the kit still runs in chat sandboxes |
| In-process calls, not the CLI | No process start per call; same schemas and error codes |
| Converted `.docx` for other formats | D-6; one detector, one diff, one locator for every format until doc-control reads them natively |

<!-- -->

> **✎ Notes** · `PLAN › Technology choices`
> _(your notes here — replace this line)_

### Out of scope

- Anything doc-control owns (D-3, D-5): live-Word engine, `.odt` or other native readers, MCP server, generic diff or redline, new edit operations. Gaps go to the doc-control session.
- Changes to the checklist, Codex types, prompts' literary content, metrics definitions.
- The computer-use fallback for live Word stays as is until doc-control's live engine ships.

<!-- -->

> **✎ Notes** · `PLAN › Out of scope`
> _(your notes here — replace this line)_

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | Adapter `litcritic/dc.py` (`run`, `check`, `DocError`), dependency pinned in `pyproject.toml`/`uv.lock`, AGENTS.md rule 9 and `test_stdlib_only.py` allow exactly doc-control | adapter | S | — | `api_major_mismatch_runs == 0` | `test_dc_check_rejects_other_major` in `tests/test_dc.py` — a faked `capabilities.api` of `2.0` makes `lc` exit with the install hint; `test_runtime_deps_only_doc_control` in `tests/test_stdlib_only.py` — the only non-stdlib import under `src/` is `doc_control`, inside `dc.py` |
| T2 | `lc docx edits\|rename\|status` on doc-control: quotes resolved with `anchor.resolve` (exact), applied with one `batch`/`term.rename`; doc-control's `open`, locks, backups, verify and undo replace `safe_edit.py` and `docx_edit.py` (both deleted); `setup`/`ingest` lock and read checks go through the adapter | edits | L | T1 | `unintended_docx_changes == 0` | `test_edits_change_only_target_text`, `test_edits_are_tracked_revisions`, `test_edit_refused_when_ambiguous_missing_or_overlapping` moved to `tests/test_docx_cli.py` and run through `lc docx`; `test_edit_refused_when_word_has_file_open` — a lock file makes `lc docx edits` refuse and leave the file byte-identical; `test_undo_restores_previous_bytes` — `lc docx undo` returns the document to its pre-edit text |
| T3 | Feedback comments (`lc docx-out`/`docx_out.build`) as one `batch` of `comment.add` on a copy, anchored by address; XML code removed | comments | S | T1 | `comments_on_wrong_paragraph == 0` | `test_comments_land_on_target_paragraph` in `tests/test_docx_out.py` — every action's comment is on the paragraph its locator names, read back with `comments.list` |
| T4 | `litcritic/convert.py`: `.txt`/`.md`/`.odt` → minimal `.docx` (headings, centring, page breaks, blank lines), one function per format | convert | M | T1 | `converted_layout_fact_mismatches == 0` | `test_convert_roundtrip_keeps_layout_facts` in `tests/test_convert.py` — for both corpus texts in each format, the reader's paragraphs and facts equal those doc-control reads from the converted file |
| T5 | Ingest through doc-control's uncapped bulk read (waits on doc-control's in-process API); `meta.json` schema 2 with `at`; `read_docx`, `_docx_styles` and the odt/md/txt readers' layout code reduced to `convert` | ingest | M | T4, upstream bulk API | `ingest_100k_words_s <= 3` | `test_ingest_100k_words_under_budget` in `tests/test_ingest.py` — a generated 100k-word `.docx` ingests in under 3 s; `test_meta_paragraphs_carry_addresses` — every paragraph in `meta.json` has an `at` that `para.get` resolves |
| T6 | Structure from `segment`: labels over doc-control chapters and scenes, ids and signals in `structure.json`, overrides in doc-control's shape; `structure.detect` heuristics deleted (novel-kind settings passed as `profile`) | structure | M | T5 | `chapter_boundary_f1 >= 0.99` | `test_corpus_chapters_match_gold` in `tests/test_structure.py` — chapter starts on both corpus texts match their known chapters; `test_override_forces_and_denies_chapter` — a force and a deny override change the labels as expected |
| T7 | Draft alignment from doc-control `diff` (manuscripts or converted copies); `diff.py`'s aligner deleted, `sync` reads the address map | sync | M | T5 | `sync_report_mismatches == 0` | `test_sync_moves_kept_spans_silently` and `test_sync_flags_changed_spans` in `tests/test_sync.py` — the existing sync scenarios give the same report through doc-control's diff |
| T8 | Writer locators from `locate`/`page.estimate`; `LocatorBuilder` and `docx_cli.Finder` removed, `locate.describe` keeps the writer wording | locate | S | T5, T6 | `locators_not_unique == 0` | `test_locator_phrase_unique_in_document` in `tests/test_locate.py` — every head…tail phrase and Find string returned for the corpus occurs once |
| T9 | Codex span relocation via `anchor.resolve` in exact mode (`spans.relocate` keeps its changed/lost outcomes) | spans | M | T7 | `fuzzy_relocations == 0` | `test_relocate_exact_only` in `tests/test_spans.py` — a one-character edit inside a span yields `changed`, never a fuzzy move |
| T10 | `lc upgrade`: backup, re-ingest every version from `manuscript/`, migrate overrides by text match (D-7), re-anchor Codex spans, write `analysis/upgrade-report.md`; drop `.safe-edit/` state | upgrade | M | T6, T7, T9 | `codex_spans_lost_on_upgrade == 0` | `test_upgrade_keeps_every_resolved_span` in `tests/test_upgrade.py` — a fixture workspace built by the current release keeps every span that resolved before; `test_upgrade_lists_unmatched_overrides` — an override whose paragraph text changed is reported, not dropped silently |
| T11 | Kit bundles doc-control; offline self-test on Python 3.11 in CI | kit | S | T1 | `kit_selftest_failures == 0` | `test_kit_zip_contains_doc_control` and `test_kit_selftest_offline` in `tests/test_kit.py` — the zip holds `doc_control/` and its self-test passes with no network |
| T12 | Live Word: retire `docs/word-control-interface.md` in favour of doc-control's live engine contract; `word_live.py` keeps the computer-use fallback, fed by `locate`'s Find string; prompts `60-rounds`/`80-live-word` and SKILL.md point at `lc` only | live | S | T8 | `docs_naming_word_control_interface == 0` | `test_prompts_name_only_lc_commands` in `tests/test_prompts.py` — no prompt names a removed command or the retired interface doc |
| T13 | Final sweep: source guard test, docs (`docs/architecture.md`, README), handover | repo | S | T2, T3, T10, T11, T12 | `docx_xml_modules_in_litcritic == 0` | `test_no_module_reads_docx_parts` in `tests/test_stdlib_only.py` — no file under `src/litcritic/` other than `convert.py` writes a `word/` part, and none reads one |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1; then T2, T3, T4, T11 (parallel); T5 when doc-control's bulk API is released; then T6, T7 (parallel); T8, T9; T10, T12; T13 last.
**Branch pattern**: `doccontrol-T<N>-description` from the default branch

<!-- -->

> **✎ Notes** · `PLAN › Implementation tasks`
> _(your notes here — replace this line)_

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

<!-- -->

> **✎ Notes** · `PLAN › Evidence log`
> _(your notes here — replace this line)_

### Dependency graph

```text
T1 ─┬─> T2 ───────────────────────────────┐
    ├─> T3 ───────────────────────────────┤
    ├─> T11 ──────────────────────────────┤
    └─> T4 ─> T5* ─┬─> T6 ─┬─> T8 ─> T12 ─┤
                   │       └──────┐       ├─> T13
                   └─> T7 ─> T9 ──┴─> T10 ┘
* T5 also waits on doc-control's uncapped in-process read API
```

<!-- -->

> **✎ Notes** · `PLAN › Dependency graph`
> _(your notes here — replace this line)_

## Sign-off

- [ ] Design reviewed by the owner
- [ ] Contracts agreed with doc-control (bulk read API)
- [ ] Migration strategy validated on a copy of the working-novel workspace
- [ ] Ready for execution

<!-- -->

> **✎ Notes** · `PLAN › Sign-off`
> _(your notes here — replace this line)_

