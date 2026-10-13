# Literary Critic — Specification (annotated edition)

> Generated 2026-10-13. This is the document with a **note slot** after every section. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Spec

## Preamble & scope

**Date**: 2026-10-13
**Ticket / PR**: workspace `doccontrol`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the owner's decisions in conversation (2026-10-12/13, D-1…D-5) and doc-control's own decisions D-18/D-19 and its research note `docs/research/03-literary-critic-indexer.md`

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

literary-critic carries its own Word engine: it reads `.docx` XML for ingest
(`ingest.py`), writes tracked edits and renames (`docx_edit.py`), adds comments
(`docx_out.py`), guards writes (`safe_edit.py`), builds Word Find phrases
(`locate.py`, `docx_cli.py`) and hands live-Word steps to computer use
(`word_live.py`). doc-control (PyPI `doc-control`, stdlib only, Python ≥ 3.11)
now does all of that as a tested, generic primitive, and by its decisions D-18
and D-19 it owns every generic document primitive, including literary-critic's
`.docx` indexing needs (layout facts, normalised text, chapter and scene
detection, exact anchors, paragraph diff, unique-phrase locators) and, later,
the live-Word engine. Two engines for the same file drift: fixes land in one,
the writer's manuscript is touched by the other. literary-critic should consume
doc-control for everything that reads or writes a document and keep only what
is literary: readable `cNN.sN.pN` labels, the Codex and its spans, checks,
rounds, reports, prompts, metrics, setup and the kit. This is a planned
improvement; nothing is broken today, but every new Word feature built here
would be thrown away.

**Success criteria (measurable)**

- [ ] `docx_xml_modules_in_litcritic == 0`: no module under `src/litcritic/` opens a `.docx` package or names a `word/` part (checked by a test that greps the source).
- [ ] `runtime_dependencies == ["doc-control"]`, pinned to the doc-control API major version the code was built against; `lc` refuses to run with a clear message when `capabilities.api` reports another major version (`api_major_mismatch_runs == 0`).
- [ ] `unintended_docx_changes == 0`, `edits_as_tracked_revisions == 1.0`, `backup_before_edit == 1.0` keep holding on the existing `lc docx` fixtures, now served by doc-control.
- [ ] `codex_spans_lost_on_upgrade == 0`: a workspace indexed by the current release, then re-indexed by the new one, keeps every Codex span that resolved before (fixture workspace on both corpus texts).
- [ ] `chapter_boundary_f1 >= 0.99` on the corpus texts after the move to doc-control's structure detection, with every difference from the old detector listed in the evidence file.
- [ ] `kit_selftest_failures == 0`: `lc kit --skill` bundles doc-control and its offline self-test passes on Python 3.11 with no network.
- [ ] `make ci` green on Python 3.11 and the current Python.
- [ ] No literary-critic task builds a capability that doc-control's spec or plan assigns to doc-control (live engine, `.odt`, MCP, generic diff or redline). Judged at plan review and in each PR review against doc-control's `status/specification.md`.

<!-- -->

> **✎ Notes** · `SPEC §1`
> _(your notes here — replace this line)_

## §2 Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `docx_edit.py`, `safe_edit.py`, `docx_out.py` | Primary | Tracked edits, rename, write safety, comments | Yes — removed | Replaced by doc-control `batch`, `term.rename`, `open`/history/undo and `comment.add` behind one adapter | High |
| `docx_cli.py` (`lc docx edits\|rename\|locate\|status`) | Primary | Writer-approved edits from rounds | Yes | Keeps its literary front (approved actions, writer locators, workspace log); calls the adapter | Med |
| `ingest.py` (`.docx` path), `structure.py`, `diff.py`, `locate.py` | Primary | Indexing and locating | Yes | `.docx` facts, chapters and scenes, alignment and Find phrases come from doc-control; the labels and index files stay literary-critic's | High |
| `.txt`, `.md`, `.odt` ingest | Dependent | Non-Word manuscripts | Yes | Must reach the same detector and diff as `.docx` (open question 1) | Med |
| `spans.py`, `sync.py`, Codex | Dependent | Items anchored to the text, re-read flags | Validation, small changes | Fingerprints and addresses change format; exact-only relocation must keep its guarantees | High |
| `word_live.py`, `docs/word-control-interface.md`, prompt `80-live-word` | Primary | Live Word | Yes | The interface doc gives way to doc-control's live engine; until it ships, the computer-use fallback stays as is — no new live code here | Low |
| Workspaces (`index/vNNN/`, `analysis/structure-overrides.json`) | Shared resource | Writer data on disk | Yes — migration | Re-index from `manuscript/vNNN.*`; overrides keyed by the old 12-hex fingerprint are translated or re-confirmed | High |
| `kit.py`, Skill zip, `pyproject.toml`, `AGENTS.md` rule 9 | Infrastructure | Packaging for chat sandboxes | Yes | doc-control vendored into the zip; rule 9 reads "stdlib plus doc-control (itself stdlib only)" | Med |
| Prompts and `SKILL.md` | UI | What the LLM is told to run | Yes | Point at `lc` only; in Cowork, may mention doc-control's MCP server for direct reads | Low |
| doc-control | Dependent (upstream) | Primitive tooling | No (requests only) | Gaps found here are filed upstream, not built here | Med |

**Impact dimensions**: Data — workspace re-index and override migration (High). API — `lc` commands keep their names and flags; JSON outputs that expose fingerprints or addresses change (Med). Performance — doc-control's measured p95s (find ≤ 1 s, rename ≤ 5 s on 100k words) fit today's budgets (Low). User — the writer sees nothing but better locators (Low). Operational — one more package to pin and vendor (Low). Risk of inaction — duplicated engines drift and new Word work is wasted (High).

<!-- -->

> **✎ Notes** · `SPEC §2`
> _(your notes here — replace this line)_

## §3 Options



<!-- -->

> **✎ Notes** · `SPEC §3`
> _(your notes here — replace this line)_

### Option A: Edits only (Conservative)

- **Description**: Replace `docx_edit.py`, `docx_out.py` and `safe_edit.py` with doc-control calls; keep literary-critic's own ingest, structure, diff and locate.
- **Scope**: `docx_cli.py`, `docx_out.py`, `setup.py`, `ingest.py` (lock check), kit, rule 9.
- **Effort**: Small
- **Tradeoffs**: + no workspace migration; − two readers of the same `.docx` (literary-critic's index vs doc-control's addresses), so mapping positions between them stays a hand-written bridge; − contradicts D-19.
- **Compatibility**: Fully backward compatible.

<!-- -->

> **✎ Notes** · `SPEC › Option A: Edits only (Conservative)`
> _(your notes here — replace this line)_

### Option B: Full move, per doc-control's migration order (Recommended)

- **Description**: One adapter module calls doc-control in-process. In order: edits, rename and comments → write safety and status → `.docx` ingest from `outline`/`para.get`/`text.normalized` → chapters and scenes from `segment` (overrides passed through) → `diff` for draft alignment → `locate`/`page.estimate` for writer locators → `anchor.resolve` (exact mode) inside `spans.relocate`. literary-critic keeps the `cNN.sN.pN` labels as a thin layer over doc-control addresses. Non-`.docx` manuscripts reach the same primitives (open question 1).
- **Scope**: the modules in section 2; tests move from XML-level checks to behaviour checks.
- **Effort**: Large
- **Tradeoffs**: + one engine, every fix upstream benefits both; + literary-critic shrinks to literary logic; − workspace re-index and override migration; − literary-critic's release depends on doc-control's API stability (mitigated by the major-version check).
- **Compatibility**: `lc` commands unchanged; workspaces upgraded once by `lc` on first use, with a backup.

<!-- -->

> **✎ Notes** · `SPEC › Option B: Full move, per doc-control's migration order (Recommended)`
> _(your notes here — replace this line)_

### Option C: No adapter; the LLM calls doc-control directly

- **Description**: Drop `lc docx` and the `.docx` paths; prompts tell the LLM to call doc-control's CLI or MCP tools itself.
- **Scope**: prompts, SKILL.md, deletions.
- **Effort**: Medium
- **Tradeoffs**: + least code; − loses the scripted links between rounds, approvals, the workspace log and the manuscript (rule 7); − the writer-facing locators and approval checks become LLM judgment.
- **Compatibility**: Breaks `lc docx` users.

<!-- -->

> **✎ Notes** · `SPEC › Option C: No adapter; the LLM calls doc-control directly`
> _(your notes here — replace this line)_

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large | Medium |
| Risk | Low | Medium (migration) | High (rule 7) |
| Completeness | Partial | Full | Full, unscripted |
| Compatibility | Full | `lc` kept; workspaces upgraded | `lc docx` removed |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Recommended option**: Option B. It is the only option that satisfies the owner's "align literary-critic with doc-control" and doc-control's D-19, and doc-control has already shipped and gated every primitive it needs (its T31–T36). Option A leaves a second `.docx` reader that would need its own fixes forever; Option C breaks rule 7.

**Immediate next action**: on approval, `design` splits Option B into tasks along the migration order, the first being the adapter plus edits, rename and comments.

**Gates check**: objective, scope, systems, compatibility, risk and validation are stated above; release readiness is the workspace upgrade (criterion 4) and the kit self-test (criterion 6).

**Open questions**:
1. Non-`.docx` manuscripts (`.txt`, `.md`, `.odt`). Asked to the doc-control session on 2026-10-13: will doc-control accept a plain list of paragraphs with layout facts for `segment`/`diff`/`locate`, or read `.odt` soon? Default if not: literary-critic converts these formats to a minimal `.docx` at ingest (format conversion of the writer's input is a literary-critic concern) and runs doc-control on that copy; the original stays untouched.
2. Fingerprints in existing `structure-overrides.json` are 12-hex SHA-1 over folded text; doc-control uses 8-hex. Default: translate by matching paragraph text at upgrade, and list any override that cannot be matched for the writer to re-confirm.

**Decisions log**

| # | Decision | Status | Date |
|---|----------|--------|------|
| D-1 | doc-control is literary-critic's one runtime dependency, version-pinned; AGENTS.md rule 9 amended to "stdlib plus doc-control (itself stdlib only)"; the kit bundles it | agreed | 2026-10-12 |
| D-2 | Work goes through the arsenal process: this spec, a plan, one task and PR per step | agreed | 2026-10-12 |
| D-3 | doc-control is built before literary-critic depends on new features; the live-Word engine will come from doc-control — literary-critic builds no live-Word or other doc-control-owned capability | agreed | 2026-10-12 |
| D-4 | literary-critic work focuses on what doc-control will never own: labels, Codex, checks, rounds, reports, prompts, metrics, setup, kit | agreed | 2026-10-12 |
| D-5 | Gaps found in doc-control are raised with the doc-control session or filed upstream, never patched here | agreed | 2026-10-12 |

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

