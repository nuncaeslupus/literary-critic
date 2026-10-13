# Live Word: take the writer to the passage, change the file safely

Use this when the writer works with the manuscript open in Word. The goal: the
writer never searches for anything, and never loses a word of their work.

Everything goes through `lc`. `lc word` gives the steps for the open Word, which
you do with computer use, and the plain line for the writer when you cannot.

## Take the writer to a passage

1. `lc docx locate "<first words of the passage>" --workspace <ws>` (or an
   anchor such as `c07.s2.p4`). It prints `find` (Word's search text), `unique`,
   `paragraphs_after` and the plain `locator` (chapter, page, first and last words).
2. Save that answer, exactly as printed, to a file, `locate.json` (a file,
   because passages contain quotes and apostrophes); add `"language": "es"` for
   a writer line in Spanish. Then `lc word locate --payload locate.json`.
   Follow its `steps` with computer use: bring Word to the front, open the
   search (Ctrl+F, or Cmd+F on a Mac), type `find` exactly, press Enter. Word
   selects the passage. When Find lands on a paragraph above it, the steps say
   how many paragraphs to move down.
3. If computer use is off, or the passage is not found, give the writer the
   `writer` line instead: chapter, page, and the quoted first and last words.

## Change the document (only what the writer approved)

1. `lc docx status --workspace <ws>`. If `locked` is true, Word has the file
   open: follow `lc word close --payload '{"document": "<document>", "save": true}'`,
   or ask the writer to save and close it. Never close Word with unsaved
   changes without the writer's answer.
2. If `changed_on_disk` is true, the writer saved since the tool last read the
   file: run `lc ingest` on it first, then check the edit still applies.
3. Write the approved edits to `edits.json` (the format is in `60-rounds.md`,
   step 5: `id`, `quote`, `prefix`, `suffix`, `replace`, `reason`) and run
   `lc docx edits --workspace <ws> --edits edits.json --dry-run`, then without
   `--dry-run`. For a name changed everywhere: `lc docx rename OLD NEW --workspace <ws> --dry-run`, then without it.
4. Reopen the document (`lc word reopen --payload '{"document": "<document>"}'`)
   and take the writer to the change (above). Tell them, in one short message:
   what changed, where, and that it shows as a tracked change they can accept
   or reject.

If a command answers `refused`, nothing was written: explain the reason in
plain words and what the writer can do (close Word, save, quote more words).
If the writer wants a change the tool made taken back,
`lc docx undo --workspace <ws>` returns the document to how it was before the
last edit or rename (`--dry-run` first).
