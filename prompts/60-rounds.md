# Revision rounds and the letter

Rounds follow editorial order: **structure** first, then **scenes and
characters**, then **prose and dialogue**. Line-level work on scenes that may
be cut is wasted.

1. With the issues recorded and `lc codex check --workspace <slug>` clean, build the next round:
   `lc round build --workspace <slug>`.
   It takes the open problems of the earliest level that still has any,
   orders them by severity, confidence, the profile's weights and effort, and
   records it in `<ws>/revisions/round-NN/round.json`; each action shows its
   issue's text and a writer locator.
   If it warns about quoted text not in the manuscript, rewrite that action:
   actions describe, they never supply the novel's words.
2. Render the letter: `lc round letter --workspace <slug>` writes
   `<ws>/revisions/round-NN/letter.md` in the novel's language. Read it before
   sending; improve the issue's text, `why` and `options` (`lc codex update <id> --workspace <slug>`) if
   something reads badly, then rebuild: while every action is still pending, a
   rebuild replaces the round instead of starting a new one.
3. Walk the writer through it **one action at a time**. For each, describe the
   place as the letter does (chapter, page, first and last words), the
   problem, why it matters and the options. Record their decision:
   `lc round mark --id A3 --status rejected --reason "their words" --workspace <slug>`
   (`accepted`, `rejected`, `deferred`, `done`; `pending` withdraws a decision).
   Each decision is a Codex `decision` item, so a rejected point is never
   raised again.
4. `lc round status --workspace <slug>` says whether the round can close: no
   open high-severity action left, or the writer decides to close it.
5. **Applying a change the writer approved** (in Word, when they agreed to
   changes in the file during setup): write exactly the change they approved
   to `edits.json` (the quote with enough context to be unique, the new text,
   the reason) and follow `80-live-word.md`: `lc docx status --workspace <slug>`,
   save and close Word if needed, then
   `lc docx edits --workspace <slug> --edits edits.json --dry-run` and the
   same without `--dry-run`. Reopen the document at the change and mark the
   action `done`. A name changed everywhere:
   `lc docx rename OLD NEW --workspace <slug> --dry-run`, then without it.
   With prose suggestions off, the new text is the writer's own words.
6. If the writer prefers to type the changes, or works in Google Docs, offer a commented copy:
   `lc docx-comments --workspace <slug>` writes
   `<ws>/revisions/round-NN/<version>-comments.docx` with each open action as a
   comment on its paragraph. It is a copy; the writer's file is never changed.
   (Google Docs imports Word comments when the file is uploaded.)
7. To find any paragraph for the writer: `lc locate c05.s1.p3 --workspace <slug>`;
   to take them there in Word: `lc docx locate c05.s1.p3 --workspace <slug>` and
   `80-live-word.md`.
