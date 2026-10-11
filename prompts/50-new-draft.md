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
3. Copy scene cards whose scenes did not change to the new version (update
   their anchors from the alignment) and rewrite only the cards of stale
   scenes; then `lc index --workspace <slug>`.
4. Re-run `lc metrics --workspace <slug>` and compare with the previous
   metrics file: say what moved and whether it moved the intended way.
5. Move the open findings to the new version: for each anchor, take its new
   anchor from the alignment (`old` entries). When the paragraph was modified,
   deleted, split or merged, set the finding's `status` to `stale` and re-check
   it against the new text; mark it `resolved` only when the evidence is gone
   or changed as intended. Tell the writer what still needs attention.
