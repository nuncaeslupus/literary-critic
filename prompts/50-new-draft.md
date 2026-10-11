# A new draft arrives

1. `lc ingest <file> --workspace <slug>` (it becomes the next version) and
   `lc anchor --workspace <slug>`. Structure overrides are keyed by paragraph
   fingerprints, so an edited paragraph no longer matches: if `lc anchor`
   reports a rejected override, find that paragraph's new fingerprint with
   `lc show <chapter> --fp --workspace <slug>`, fix
   `<ws>/analysis/structure-overrides.json` and run `lc anchor` again — none of
   the overrides apply until all of them match.
2. Compare with the previous version:
   `lc diff v001 v002 --workspace <slug>`.
   `index/v002/alignment.json` maps every old paragraph to its new place and
   lists `stale_scenes`.
3. Bring the Codex to the new draft: `lc codex sync --workspace <slug>`. It
   moves every item's spans and lists the items to re-read; re-read only those
   and fix them with `lc codex update <id> --workspace <slug>`.
4. Re-run `lc metrics --workspace <slug>` and compare with the previous
   metrics file: say what moved and whether it moved the intended way.
5. Open `issue` items moved with the sync; re-check those it flagged against
   the new text, and retire one (`lc codex retire <id> --workspace <slug>`)
   only when its evidence is gone or changed as intended. Tell the writer what
   still needs attention.
