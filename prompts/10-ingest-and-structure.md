# Bring a draft in and check its structure

1. Create the workspace once: `lc init <slug> --title "<title>" --language <es|en>`.
   Then fill `guard-terms.txt` with the title, character and place names.
2. Ingest the file the writer gives you (`.docx`, `.odt`, `.md` or `.txt`;
   export Google Docs as `.docx`):
   `lc ingest <file> --workspace <slug>`.
3. Detect parts, chapters and scenes: `lc anchor --workspace <slug>`.
   It prints what it found and which signal it used.
4. Check the result against the writer's intent with `lc show --workspace <slug>`
   (table of contents). Look for chapters that are really author notes, a
   missing chapter, a chapter split in two, scenes that should be separate.
5. When a boundary is wrong, read the area with fingerprints:
   `lc show c07 --fp --workspace <slug>`, then write corrections to
   `<ws>/analysis/structure-overrides.json` using those fingerprints:

   ```json
   {"chapter_starts": ["<fp>"], "not_chapter": ["<fp>"],
    "scene_starts": ["<fp>"], "not_scene": ["<fp>"]}
   ```

   Re-run `lc anchor --workspace <slug>`. If it reports a rejected override,
   fix that fingerprint; nothing is applied until all of them are valid.
6. When the novel has no scene breaks at all, propose scene starts the same
   way: read each chapter with `--fp`, decide where time, place or viewpoint
   changes, and list those fingerprints under `scene_starts`.
7. Measure the draft: `lc metrics --workspace <slug>`.

When the structure is right, index the novel: `20-codex-items.md`.

Tell the writer, in plain words, how many chapters and scenes you found and
anything that looked like a leftover note in the manuscript.
