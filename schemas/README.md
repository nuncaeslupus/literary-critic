# Schemas

JSON Schemas (draft 2020-12 subset) for the artefacts an LLM writes into a
workspace. `lc validate <kind> <file>` checks a file against them with a
stdlib-only validator; profiles are also checked against the catalogue
(known check ids, traits and areas). Codex items are checked against their
type's schema (`src/litcritic/codex_types/`) by `lc codex check`.

| Kind | File | Written by |
|------|------|------------|
| `report` | `report.schema.json` | LLM, reader-report mode |
| `profile` | `profile.schema.json` | LLM + writer, `analysis/profile.toml` |
| `index-entities-answer` | `index-entities-answer.schema.json` | LLM, answer to an entity packet (`lc index import`) |
| `index-scenes-answer` | `index-scenes-answer.schema.json` | LLM, answer to a scene packet (`lc index import`) |
| `index-links-answer` | `index-links-answer.schema.json` | LLM, answer to a links packet (`lc index import`) |

Supported keywords: `type`, `const`, `enum`, `required`, `properties`,
`additionalProperties`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`,
`maximum`, `pattern`, local `$ref`, and the extension `x-maxWords` (word
limit for summaries, quotes and locator snippets). A JSON file may hold one
object or a list of them.

Anchors look like `c01.s2.p3` (chapter, scene, paragraph), optionally prefixed
by a part (`p1.`). Every artefact carries `schema_version = 1`.
