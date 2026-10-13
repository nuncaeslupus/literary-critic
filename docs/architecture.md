# Architecture

literary-critic is two layers: a **document layer** it borrows and a **literary
layer** it owns.

- **doc-control** ([PyPI `doc-control`](https://github.com/nuncaeslupus/doc-control),
  stdlib only) owns everything generic about a document: reading paragraphs with
  stable addresses, chapters and scenes, draft-to-draft diff, locating a passage
  for a writer, page estimates, anchors, tracked-change edits, comments, locks,
  backups, verification and undo. literary-critic never rebuilds any of it; a gap
  is a request to doc-control, not new code here.
- **literary-critic** owns what is about the novel: the workspace, the literary
  index (structure labels, scene and chapter ids, metrics), the Codex, the
  analysis checklist, findings, editorial letters, revision rounds and the
  writer-facing wording of every location.

The runtime is the Python standard library plus doc-control (AGENTS.md rule 9),
so the kit runs inside a chat's code sandbox; the kit zip bundles doc-control.

## The one door: `dc.py`

`src/litcritic/dc.py` is the only module that imports `doc_control`
(`tests/test_stdlib_only.py::test_runtime_deps_only_doc_control`). It offers:

- `dc.run(op, request)` — one operation in-process, with doc-control's own request
  schema; errors come back as `dc.DocError` (code, message, hint, details).
- `dc.open(path)` — a `Document` that parses the file once and reuses the parse for
  every read (`Document.run(op, …)`, `Document.paragraphs(…)`).
- `dc.check()` — refuses a doc-control whose API major version is not 1, with the
  install hint.

No module reads or writes Word XML itself
(`tests/test_stdlib_only.py::test_no_module_reads_docx_parts`). The one exception
is `convert.py`, which writes a minimal `.docx` for `.txt`, `.md` and `.odt`
manuscripts (spec D-6) until doc-control reads those formats natively.

## Which module uses which doc-control operation

| Module | doc-control operations | What literary-critic adds |
|--------|------------------------|---------------------------|
| `ingest.py` | `Document.paragraphs` (bulk read, normalised, with pages), `page.estimate`, `open` (read check) | Workspace snapshots, `meta.json` with each paragraph's address (`at`), read records |
| `convert.py` | — (writes the `.docx` doc-control then reads) | `.txt`/`.md`/`.odt` → minimal `.docx`, layout facts kept |
| `structure.py` | `segment` (chapters, parts, scenes), `Document.paragraphs` | Labels, stable ids, novel-kind settings, overrides, `structure.json` |
| `diff.py` | `diff`, `Document.paragraphs` | The address map between drafts that `sync` reads |
| `spans.py` | `anchor.resolve` (exact mode only) | Codex span relocation with changed/lost outcomes |
| `sync.py`, `upgrade.py` | through `diff`, `spans`, `ingest`, `structure` | Codex sync report; `lc upgrade` of old workspaces |
| `locate.py` | `locate`, `page.estimate`, `Document.paragraphs` | Writer wording: chapter, page, first and last words, Find string |
| `docx_cli.py` (`lc docx`) | `anchor.resolve`, `find`, `batch` (`text.replace`), `term.rename`, `info`, `history.list`, `undo` | Quote-to-address resolution, refusals in writer language |
| `docx_out.py` (`lc docx-out`) | `batch` (`comment.add`) | Feedback comments from round actions, on a copy |
| `setup.py` | `info` (Word lock) | Writer onboarding |
| `kit.py` (`lc doctor`) | `capabilities` | Platform self-test |
| `word_live.py` (`lc word`) | — (fed by `locate`) | Computer-use steps for an open Word until doc-control's live engine ships |

Everything else — `checklist`, `codex`, `metrics`, `query`, `rounds`, `report`,
`pack`, `guard`, `workspace` — works on the workspace's own files and never touches
a document.

## Data flow

1. **Ingest** — `lc ingest` copies the manuscript into the workspace, converts it
   when it is not `.docx`, and reads it through doc-control into a versioned
   snapshot (`v001/`), every paragraph tagged with its address.
2. **Index** — `structure` labels doc-control's chapters and scenes; `metrics` and
   the Codex build on those ids.
3. **Analyse and advise** — the checklist, findings, letters and rounds are files in
   the workspace; every location shown to the writer comes from `locate`.
4. **Next draft** — `diff` aligns drafts, `spans` re-anchors the Codex exactly,
   `sync` reports what changed.
5. **Write back** — only with the writer's approval: `lc docx` (tracked-change edits,
   renames, undo) and `lc docx-out` (comments) go through doc-control's `batch`,
   which locks, backs up and verifies.
