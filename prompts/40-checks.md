# Run checks and record findings

Work in the order `lc checklist plan --profile <ws>/analysis/profile.toml` prints:
orientation, developmental, scene, line, verification. Finish the big picture
before line-level work.

## For each check

1. Read its question, `look_for`, `inputs`, `evidence` and `severity` in
   `checklist/areas/`.
2. Load only the inputs it names:
   - `L0`: `<ws>/analysis/synopsis.md` and the profile;
   - `L1`: `lc show --workspace <slug>` (chapter summaries);
   - `L2`: the scene cards (`<ws>/index/<version>/scene_cards.json`);
   - `L3`: `lc find "<phrase>" --workspace <slug>`,
     `lc context c05.s1.p3 --workspace <slug>`, or
     `lc show c05.s1 --workspace <slug>`;
   - `structure`: `<ws>/index/<version>/structure.json` (parts, chapters,
     scenes, word counts);
   - `characters`, `locations`, `timeline`, `ledger` (setups and payoffs):
     `<ws>/index/<version>/registers/` — `ledger` is `setups.json`. They are
     built from scene cards by `lc index`;
   - `relationships`, `motifs`: registers you write yourself in the same
     folder (`relationships.json`, `motifs.json`, schema `register`) when a
     check first needs them;
   - `findings`: the Codex's `issue` items
     (`lc codex find "<words>" --type issue --workspace <slug>`);
     `backlog`: past rounds and the writer's `decision` items
     (`lc codex ask open-issues --workspace <slug>`,
     `lc codex ask rejected --workspace <slug>`);
   - `metrics`: `<ws>/metrics/<version>.json` (script-measured; trust them over
     impressions, and say when a metric was `unmeasured`).
3. Decide. A deliberate choice is not a defect; separate error, licence and a
   character's belief. Strength checks record what works.
4. Record each finding as a Codex `issue`, on the passage it is about:

   ```
   lc codex add issue --workspace <slug> --text "What the writer could change" --quote "exact words from the passage" --within c07.s2 --fields '{"level": "scene", "severity": "medium", "kind": "problem", "check": "scene-craft.value-shift", "confidence": 0.7, "effort": "M", "why": "Why it matters.", "options": ["Ways to address it, never written out"]}'
   ```

   `kind` is `problem` or `strength`; `level` is one of book, part, chapter,
   scene, paragraph, line, mechanics; severity is high, medium or low.
5. Check after each batch: `lc codex check --workspace <slug>`.

## Rules

- No anchor, no finding. Quotes are copied, never paraphrased or improved.
- One finding per distinct problem; group repeats under one finding with
  several anchors.
- A proposed cut states what redundancy it removes, which effect it keeps and
  what else it touches (setups, motifs, relations).
- Never write replacement prose; options describe what to do, not the words.
