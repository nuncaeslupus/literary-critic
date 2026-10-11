# Revision rounds and the letter

Rounds follow editorial order: **structure** first, then **scenes and
characters**, then **prose and dialogue**. Line-level work on scenes that may
be cut is wasted.

1. With findings recorded and valid, build the next round:
   `lc round build --workspace <slug>`.
   It takes the open problems of the earliest level that still has any,
   orders them by severity, confidence, the profile's weights and effort, and
   writes `<ws>/revisions/round-NN/actions.json` with a writer locator for each.
   If it warns about quoted text not in the manuscript, rewrite that action:
   actions describe, they never supply the novel's words.
2. Render the letter: `lc round letter --workspace <slug>` writes
   `<ws>/revisions/round-NN/letter.md` in the novel's language. Read it before
   sending; improve the `what`, `why` and `options` wording in the findings if
   something reads badly, then rebuild.
3. Walk the writer through it **one action at a time**. For each, describe the
   place as the letter does (chapter, page, first and last words), the
   problem, why it matters and the options. Record their decision:
   `lc round mark --id A3 --status accepted --workspace <slug>`
   (`accepted`, `rejected`, `deferred`, `done`).
4. `lc round status --workspace <slug>` says whether the round can close: no
   open high-severity action left, or the writer decides to close it.
5. To find any paragraph for the writer: `lc locate c05.s1.p3 --workspace <slug>`.
