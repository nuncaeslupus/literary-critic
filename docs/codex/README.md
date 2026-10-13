# The Codex

A work's knowledge base: typed items, each tied to the text it comes from,
stored as plain JSON lines in `<ws>/codex/` and read through `lc codex`.
Never edit its files by hand.

```
codex/
  codex.toml           # codex_schema, synced_draft
  items/<type>.jsonl   # one item per line, sorted by id
  changes.jsonl        # append-only change log
  reread.jsonl         # items the last sync asks to re-read
```

## Item envelope

Every item, whatever its type:

| Field | Meaning |
|-------|---------|
| `id` | `<prefix>-<8 hex>`, never reused (`en-…` entity, `sc-…` scene…) |
| `type` | one of the types below |
| `text` | one line saying what the item is |
| `spans` | where it lives in the text: `{draft, start: {para, off}, end: {para, off}, prefix, exact (or head, tail for long spans), suffix, state}`; `state` is `ok`, `moved`, `changed` or `lost` after a sync |
| `links` | `[{rel, to}]`: typed edges to other items (`pays_off`, `about`, `depends_on`…) |
| `status` | `active`, `needs_reread` or `retired` (items are retired, never deleted) |
| `fields` | the type's own fields, checked against its schema |
| `by`, `rev`, `created`, `updated` | who changed it last, revision number, timestamps |

## Item types

Defined in `src/litcritic/codex_types/<type>.toml` (fields, schema, allowed
links); a work's kind can add its own. A new type needs no code change.

| Type | Fields | For |
|------|--------|-----|
| `entity` | `kind` (character, place, object, group, rule, motif), `name`, `aliases`, `titles` (role titles used as names), `exact_case`; link `same_as` joins one character under two names the text keeps apart | who and what the novel is about |
| `scene` | `summary`, `pov`, `location`, `time` | one per scene |
| `dialogue` | `speaker`, `addressee` | who speaks where |
| `fact` | `role` | a fact the text states, to keep continuity |
| `thread` | `name`, `role` | a storyline |
| `setup` | `label`, `side` (setup or payoff) | planted details and their payoffs (`pays_off` link) |
| `issue` | `level`, `severity`, `kind` (problem or strength), `check`, `why`, `options`… | findings |
| `decision` | `verdict`, `at`, `reason` | the writer's answer to an issue |

## Query schema

`lc codex sql "<query>" --workspace <slug>` runs one read-only SQLite query;
`lc codex sql --schema --workspace <slug>` prints this list for the work.
Computed tables are built only when a query names them.

| Table | Columns |
|-------|---------|
| `works` | id, title, author, kind, series, language, draft |
| `paragraphs` | idx, anchor, part, chapter, scene, words, text |
| `chapters` | id, idx, title, words, first_idx, last_idx |
| `scenes` | id, chapter, idx, words, first_idx, last_idx |
| `para_pos` | idx, word0 (words before it), words |
| `items` | id, type, status, text, by, rev, fields_json |
| `spans` | item_id, k, start_idx, start_off, end_idx, end_off, words, state |
| `links` | src, rel, dst |
| `v_<type>` | id, status, text, the type's columns, para_idx, words |
| `tokens` | para_idx, pos, form, norm, is_word (computed) |
| `ngrams` | n, norm, para_idx, pos (computed) |
| `mentions` | entity_id, para_idx, off, form, scene, via (name, alias or title) (computed: whole words, longest match first; a title counts only in a scene that also names the entity) |
| `copresence` | a, b, scene, chapter (computed) |
| `changes` | at, draft, item, type, op (add, update, sync; a retirement is an update), by, status, text, fields_json, before_status, before_text, before_fields_json (computed, from the change log) |

SQL functions: `norm(x)` (lower case, no accents) and `phrase(x)` (words of x
in `ngrams.norm` form). Named questions (`lc codex questions`, `lc codex ask`)
are saved queries in `src/litcritic/questions/`; prefer them.
