# A new draft arrives

1. `lc ingest <file> --workspace <slug>` (it becomes the next version) and
   `lc anchor --workspace <slug>`.
2. Compare with the previous version:
   `lc diff v001 v002 --workspace <slug>`.
   `index/v002/alignment.json` maps every old paragraph to its new place and
   lists `stale_scenes`.
3. Copy scene cards whose scenes did not change to the new version (update
   their anchors from the alignment) and rewrite only the cards of stale
   scenes; then `lc index --workspace <slug>`.
4. Re-run `lc metrics --workspace <slug>` and compare with the previous
   metrics file: say what moved and whether it moved the intended way.
5. Re-check the open findings: for each, look at its anchors in the
   alignment; mark it resolved only when the evidence is gone or changed as
   intended, and tell the writer what still needs attention.
