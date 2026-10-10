# Corpus

Public-domain novels used for tests, examples and gate measurements. This is the
only place manuscript-like text may live in the repo (see `AGENTS.md`).

| Directory | Text | Language | Words |
|-----------|------|----------|-------|
| `marianela/` | Benito Pérez Galdós, *Marianela* (1878) | es | ~50k |
| `jekyll-hyde/` | R. L. Stevenson, *The Strange Case of Dr. Jekyll and Mr. Hyde* (1886) | en | ~26k |

Each directory holds:

- `text.txt` — the body text, UTF-8, LF line endings, paragraphs separated by a
  blank line.
- `source.toml` — origin, licence, processing notes, the SHA-256 of `text.txt`
  and known structure (chapter count, heading style) used as ground truth.

`lc corpus check` verifies every text has a complete source note and an
unchanged checksum (gate metric `corpus_sources_documented`).

## Synthetic drafts

`lc synth <text> --seed N --out <dir>` derives a "next draft" from a text by
applying seeded paragraph edits — modify, insert, delete, move, split, merge —
and writes `draft.txt` plus `truth.json`, the exact old↔new paragraph mapping.
The draft-alignment gates (T6) are measured against that truth. Inserted
paragraphs are scrambled vocabulary from the same text, not new prose.

## Adding a text

Only texts in the public domain in both the source country and the US. Add a
directory with `text.txt` and a `source.toml` carrying every field the two
existing ones have, then run `lc corpus check`.
