# Schemas

JSON Schemas (draft 2020-12 subset) for the artefacts an LLM writes into a
workspace. `lc validate <kind> <file>` checks a file against them with a
stdlib-only validator; findings and profiles are also checked against the
catalogue (known check ids, traits and areas).

| Kind | File | Written by |
|------|------|------------|
| `scene-card` | `scene-card.schema.json` | LLM, one per scene |
| `register` | `register.schema.json` | script, from scene cards (T9) |
| `finding` | `finding.schema.json` | LLM, per check result |
| `action` | `action.schema.json` | script + LLM, per revision round (T11) |
| `profile` | `profile.schema.json` | LLM + writer, `analysis/profile.toml` |

Supported keywords: `type`, `const`, `enum`, `required`, `properties`,
`additionalProperties`, `items`, `minItems`, `minLength`, `minimum`,
`maximum`, `pattern`, local `$ref`, and the extension `x-maxWords` (word
limit for summaries, quotes and locator snippets). A JSON file may hold one
object or a list of them.

Anchors look like `c01.s2.p3` (chapter, scene, paragraph), optionally prefixed
by a part (`p1.`). Every artefact carries `schema_version = 1`.
