# Run checks and record findings

Work in the order `lc checklist plan --profile analysis/profile.toml` prints:
orientation, developmental, scene, line, verification. Finish the big picture
before line-level work.

## For each check

1. Read its question, `look_for`, `inputs`, `evidence` and `severity` in
   `checklist/areas/`.
2. Load only the inputs it names:
   - `L0`/`L1`: `lc show --workspace <slug>` and `analysis/synopsis.md`;
   - `L2`: the scene cards, and registers in `index/<version>/registers/`;
   - `L3`: `lc find "<phrase>" --workspace <slug>`,
     `lc context c05.s1.p3 --workspace <slug>`, or `lc show c05.s1`;
   - `metrics`: `metrics/<version>.json` (script-measured; trust them over
     impressions, and say when a metric was `unmeasured`).
3. Decide. A deliberate choice is not a defect; separate error, licence and a
   character's belief. Strength checks record what works.
4. Record each finding in `analysis/findings.json` (a JSON list):

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

5. Validate after each batch: `lc validate finding analysis/findings.json`.

## Rules

- No anchor, no finding. Quotes are copied, never paraphrased or improved.
- One finding per distinct problem; group repeats under one finding with
  several anchors.
- A proposed cut states what redundancy it removes, which effect it keeps and
  what else it touches (setups, motifs, relations).
- Never write replacement prose; options describe what to do, not the words.
