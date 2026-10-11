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
   - `findings`: `<ws>/analysis/findings.json`; `backlog`: the actions of past
     rounds in `<ws>/revisions/`;
   - `metrics`: `<ws>/metrics/<version>.json` (script-measured; trust them over
     impressions, and say when a metric was `unmeasured`).
3. Decide. A deliberate choice is not a defect; separate error, licence and a
   character's belief. Strength checks record what works.
4. Record each finding in `<ws>/analysis/findings.json` (a JSON list):

   ```json
   {
     "schema_version": 1,
     "id": "F12",
     "check_id": "scene-craft.value-shift",
     "anchors": ["c07.s2"],
     "evidence": [{"anchor": "c07.s2.p4", "quote": "at most 25 words copied from the text"}],
     "explanation": "What the problem (or strength) is and why it matters.",
     "severity": "medium",
     "confidence": 0.7,
     "effort": "M",
     "kind": "problem",
     "status": "open"
   }
   ```

5. Validate after each batch: `lc validate finding <ws>/analysis/findings.json`.

## Rules

- No anchor, no finding. Quotes are copied, never paraphrased or improved.
- One finding per distinct problem; group repeats under one finding with
  several anchors.
- A proposed cut states what redundancy it removes, which effect it keeps and
  what else it touches (setups, motifs, relations).
- Never write replacement prose; options describe what to do, not the words.
