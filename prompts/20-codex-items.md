# Index the novel in the Codex (L2) and write the synopsis (L0)

The Codex is the work's knowledge base: each item says one thing about the
novel and points at the text it comes from. Most checks read items instead of
the text, so they must be accurate. The index is built in **packets**: `lc`
cuts the work into pieces of bounded size, you answer each one with JSON, and
`lc` checks the answer and writes its items. Never read the whole novel at
once, and never add index items one by one (that is for spot fixes, below).

## Model tiers

Each packet names its tier on its first line. Tiers, not model names:
**cheap** (Haiku-class), **standard** (Sonnet-class), **strong** (Opus-class,
or the best this session has).

- Entity packets (`e1`, `e2`…) and the new-names packet (`n1`): **strong**.
- Scene packets (`s001`, `s002`…): **standard**.

On the measured validation the cheap tier stayed below 0.9 agreement with the
strong one on entities, and left fields out on scenes, so it is not used.

## The loop

1. Plan: `lc index plan --workspace <slug>`. It finds name candidates (no
   LLM), creates the Codex if needed, and prints how many packets of each kind.
   `lc index status --workspace <slug>` lists them, one line each.
2. **Entity packets first.** For each `e` packet, print it with
   `lc index packet <id> --workspace <slug>`, answer exactly as its
   instructions and schema say, save the JSON to a file and import it:
   `lc index import <id> --file <answer.json> --workspace <slug>`.
3. Plan again: `lc index plan --workspace <slug>`. Scene packets now list the
   known entities.
4. **Scene packets.** Same steps for each `s` packet. A scene answer carries
   only facts and `new_names` (proper names the scene uses that its `known:`
   line lacks); it never creates entities.
   - Where the surface has subagents (Claude Code, Cowork), answer scene
     packets in parallel: one subagent per packet, on the standard tier,
     each returning its JSON. Import the answers one at a time from the main
     session.
   - In a plain chat, do them one after another; the bound per step is the
     same.
   - `lc index import <id> --file <answer.json> --next --workspace <slug>`
     prints the next packet still to do after an ok, saving a call.
5. Plan again: `lc index plan --workspace <slug>`. If scene answers queued
   new names, this adds the packet `n1` (strong tier). Answer and import it
   like an entity packet. When `lc index status --workspace <slug>` shows
   every packet `done`, the index is complete.

### Reading a packet

- First line: packet id, kind, tier, draft. Then the instructions and the
  JSON schema the answer must follow. Answer with JSON only.
- `known:` under a scene: the Codex entities found in it, `Name [id]`, with
  the other forms that scene uses in brackets. Use it to tell who is who.
- `Open setups:` earlier setups not paid off yet, `label [id]`. A payoff in
  this packet gives that label or id as `pays_off`.
- Every `quote` must be exact words of that scene, long enough to occur only
  once in it.

### Which names are entities

A character is an entity when the text names them or consistently calls them
by one role. A **place or group** is an entity only if a scene happens there,
or it acts or recurs (named in 2 or more places). A passing mention is a
reject. Rejects are remembered and not asked again unless the name becomes
much more frequent in a later draft.

### When an import is refused

The import is all or nothing: a refused answer writes nothing. The error line
names the field to fix, e.g. `error s004: $.scenes[2].setups[0].quote: …`.
Fix that field in the same file and run the same import again. A packet
already imported is not imported twice.

### Measuring

- `lc index cost --workspace <slug>`: tokens in and out, calls and time per
  packet and in total.
- `lc index eval --workspace <slug> --gold <gold.json>`: precision, recall
  and merge errors of the entities against a hand-made list.
- `lc index compare --answers <answer.json> --reference <reference.json>`:
  how far one answer agrees with another to the same packet (e.g. before
  trusting a cheaper tier). Raw answers are kept in `<ws>/index/work/answers/`.

## A new draft

After `lc codex sync --workspace <slug>` (see `50-new-draft.md`), run
`lc index plan --changed --workspace <slug>`: it packs only new or changed
scenes and names no entity covers yet. Run the same loop on what it prints.

## Spot fixes

For one wrong or missing item, fix it by hand (`lc index plan` creates the
Codex; without it, start one with `lc codex init --workspace <slug>`). Look first:
`lc codex find "<name>" --type entity --workspace <slug>`. Change an item with
`lc codex update <id> --workspace <slug>`; add one with `lc codex add`:

```bash
lc codex add entity --workspace <slug> --quote "exact words that introduce it" --within c03.s2 --text "Who or what it is, in one line." --fields '{"kind": "character", "name": "usual name", "aliases": ["other names"]}'
```

A setup planted for later is a `setup` item (`"side": "setup"`); its payoff
is another `setup` item (`"side": "payoff"`) with `--link pays_off:<setup id>`.

## Rules

- One entity per character, place or motif; other names go in `aliases`.
- Report what the text says, not what you expect.
- Never put prose for the novel in an item.
- After the loop or a batch of fixes: `lc codex check --workspace <slug>`,
  and fix every error before going on.

## Synopsis

Write `<ws>/analysis/synopsis.md`: the whole story in at most 600 words,
including the ending, then one line each for premise, protagonist's want and
need, central conflict, and theme as the novel presents it.
