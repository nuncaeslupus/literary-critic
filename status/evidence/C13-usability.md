# C13 — scripted LLM usability review

Date: 2026-10-11. Workspace: the Marianela test Codex (`tests/codex_fixture.py`),
plus a synthetic second draft (`lc synth marianela --seed 3 --rate 0.05`)
ingested, anchored, diffed and synced.

A fresh assistant (no prior context) was told to read only `prompts/35-ask.md`
and `docs/codex/README.md`, to use only `lc` commands, and to answer six
questions.

| # | Question | Answered | How |
|---|----------|----------|-----|
| 1 | Where is X (a character): item and first appearance | yes | `codex find --type entity`, `codex ask character-appearances`, `codex sql` on `mentions` |
| 2 | What depends on it (a storyline's links) | yes | `codex show`, `codex sql` on `links` |
| 3 | What changed with the last draft | yes, partly: which items, not how | `codex sql` on `changes` |
| 4 | Example question: chapters where a character speaks | yes (exact) | `codex ask speech-chapters` |
| 5 | Example question: uses of an expression per chapter | yes (exact) | `codex ask expression-use` |
| 6 | Example question: who matters most to a character | yes (exact) | `codex ask relevance` |

Result: 6/6 answered through the CLI alone; 0 invalid commands; no output
exceeded its budget.

Friction it reported, and what was fixed in the same PR:

- `codex show` printed no place for the item → it now prints each span (anchor,
  state, draft, quoted words) and `links: none` when there are none.
- `--type` for `codex find` was undocumented → documented in `35-ask.md`.
- The sync rows of the change log carried the old draft → they carry the new one.
- How each item changed was hard to find → `35-ask.md` gives the span-state query.
