# Record the novel in the Codex (L2) and write the synopsis (L0)

The Codex is the work's knowledge base: each item says one thing about the
novel and points at the text it comes from. Most checks read items instead of
the text, so they must be accurate. Start it once per work:
`lc codex init --workspace <slug>`.

## For each scene

1. Read it: `lc show c03.s2 --workspace <slug> --budget 3000`
   (if it is cut, run the continuation command printed on its last line).
2. Record it, spanning the whole scene:

   ```bash
   lc codex add scene --workspace <slug> --unit c03.s2 --text "What happens, in one line." --fields '{"summary": "What happens and what changes, at most 80 words.", "pov": "viewpoint character, or omniscient / none", "location": "where", "time": "when, as precise as the text allows"}'
   ```

3. The first time a character, place, group, object, rule or motif appears,
   record it once, on the words that introduce it:

   ```bash
   lc codex add entity --workspace <slug> --quote "exact words that introduce it" --within c03.s2 --text "Who or what it is, in one line." --fields '{"kind": "character", "name": "usual name", "aliases": ["other names"]}'
   ```

   Look before adding: `lc codex find "<name>" --type entity --workspace <slug>`.
4. Something planted for later is a `setup` item (`"side": "setup"`); its
   payoff is another `setup` item (`"side": "payoff"`) linked to it with
   `--link pays_off:<setup id>`.

## Rules

- One entity per character, place or motif; put other names in `aliases`.
- Report what the text says, not what you expect; say so in `--text` when
  unsure.
- Never put replacement prose in an item.
- After a batch: `lc codex check --workspace <slug>`, and fix every error
  before going on.

## Synopsis

Write `<ws>/analysis/synopsis.md`: the whole story in at most 600 words,
including the ending, then one line each for premise, protagonist's want and
need, central conflict, and theme as the novel presents it.
