# Write chapter summaries (L1) and the synopsis (L0)

Together they let an assistant orient itself in the whole novel cheaply: aim
for at most 8,000 tokens for L0 + L1 on a 150,000-word novel.

1. For each chapter, from its scene cards (read the text only where cards are
   thin): one paragraph of at most 60 words with what happens and what
   changes. Write them to `<ws>/index/<version>/chapter_summaries.json` as
   `{"c01": "…", "c02": "…"}`.
2. Synopsis in `<ws>/analysis/synopsis.md`: the whole story in at most 600 words,
   including the ending, followed by one line each for premise, protagonist's
   want and need, central conflict, and theme as the novel presents it.
3. Check the table of contents now shows the summaries:
   `lc show --workspace <slug>`.
