# Live Word: take the writer to the passage, change the file safely

Use this when the writer works with the manuscript open in Word. The goal: the
writer never searches for anything, and never loses a word of their work.

Everything goes through `lc`. `lc word` asks doc-control's live engine first:
when it answers `"status": "done"`, Word has already done it. Otherwise it
answers `"status": "manual"` with the `steps` for the open Word, which you do
with computer use, and the plain line for the writer when you cannot.

## Where doc-control can reach Word

- **lc runs on the writer's computer with the live engine installed**
  (`pip install "literary-critic[live]"`): `lc word` does it by itself.
- **Everywhere else** (Cowork's sandbox, or the writer's computer without the
  live engine: `live.error` is `ENGINE_UNAVAILABLE`): if you have doc-control's
  tools (`live_select`, `live_open`, …: the writer added doc-control's server
  to Claude's desktop app), call the tool named in the answer's `live` with its
  `arguments` exactly as they are, adding and dropping nothing (they carry the
  `mode` that leaves the cursor without selecting): `doc` is the file name
  alone, and doc-control finds the open document of that name on the writer's
  computer. It answers in a few seconds. If it answers `DOC_AMBIGUOUS` (two
  open documents share the name), call it again with `doc` set to the right
  one of the full paths in `details.candidates`; `live_status` without `doc`
  lists the open documents. Without those tools, or if the tool fails, follow
  the `steps`.
- **A chat without either**: the `writer` line.

## Take the writer to a passage

The writer waits while you work, so a jump is one command and a one-word
answer: "take me to chapter 7" is `lc docx locate 7 --go --workspace <ws>`,
then "Done." Run nothing else first (no `lc show`, no reading this whole
file again in the same session): the steps below are for when that answer
is not `"status": "done"`.

1. `lc docx locate "<first words of the passage>" --workspace <ws>` (or an
   anchor such as `c07.s2.p4`; a chapter `c07` or a scene `c07.s2` lands on its
   first paragraph). For "take me to chapter 7", give the number the chapter's
   heading shows, `7` or `VII`: lc finds the heading that carries it, and when
   none or several do it says so, then find the chapter's id in
   `lc show --workspace <ws>`. It prints `path` and `at` (the file and the
   paragraph's address, for the live engine), `find` (Word's search text),
   `unique`, `paragraphs_after` and the plain `locator` (chapter, page, first
   and last words).
2. To take the writer there, run the same command with `--go`:
   `lc docx locate c07 --go --workspace <ws>`. It finds the passage and
   asks Word to go there in one step, so the writer waits less, and answers as
   `lc word locate --payload locate.json` does, with the writer line in the novel's language.
   (The two steps also work apart: save the answer of step 1, exactly as
   printed, to `locate.json`, then `lc word locate --payload locate.json`.)
   - `"status": "done"`: Word is in front with the passage in the middle of
     the window and the cursor at its start (nothing selected, so a key
     pressed by accident cannot replace it). Answer a direct request ("take me to
     chapter 7", a click on a place) with one word: "Done." ("Hecho." in
     Spanish). The writer is looking at Word, not at a description of it.
   - `live.error` says the document is not open: open it
     (`lc word reopen --payload '{"document": "<path>"}'`, or `live_open` in
     Cowork) and repeat this step.
   - Word has another file of the same novel open (an older copy, the
     original of a cleaned file): do not go there in that file, whose
     paragraphs differ. Tell the writer, in one line, which file the tool
     works on, and open it as for a document that is not open if they agree.
   - Otherwise, call `live` as above, else follow the `steps` with
     computer use: bring Word to the front, open the search with the key the
     steps name, type `find` exactly, press Enter. Word selects the passage.
     When Find lands on a paragraph above it, the steps say how many
     paragraphs to move down. On Windows, Word's shortcuts change with the
     language of its menus (in a Spanish Word, Ctrl+F indents the paragraph
     and Ctrl+S underlines): press only the keys the steps give.
3. If none of this works, or the passage is not found, give the writer the
   `writer` line instead: chapter, page, and the quoted first and last words.
4. Every time the writer asks to be taken somewhere, run these steps again,
   even for a passage you showed before: they may have moved since.

## Lists of places: one click each

A button is the fastest way there: a click moves Word at once, while asking
you to take them there costs a whole turn. So whenever the conversation is
about part of the novel (the issue being worked on, a chapter, a scene, a
character's moments, findings, the repetitions of a word), and Word can be
reached (any of the ways above), give a button for every place the reply is
about, unasked — one place included. Do it before the writer has to ask
"take me there"; leave it out only when the reply names no place. Make each
place a way there:

- If you have doc-control's tools, list the places to `lc docx places`, each
  as `lc docx locate` takes it (an anchor, a chapter's number, a quote):
  `lc docx places 7 c03.s2.p4 --workspace <ws>` prints the call; call the tool in its `live`
  (`live_places`) with its `arguments` exactly. The writer sees one button
  per place, and a click takes Word there at once, without a message to you
  (✓ when Word went there, ✗ when not: then take them there yourself as
  above). Places listed under `missing` were not found: name them in plain
  words. If the buttons do not show (the tool answers with the places as
  text), use the next way.
- Else, if you can show an interactive widget whose buttons send a chat message,
  show the places as a short list, each with a button ("Take me there" in the
  writer's language) that sends "Take me to <anchor>: “<first words>…”".
  The click comes back to you as that request: locate the anchor, take the
  writer there, answer "Done.".
- Otherwise number the places and end with one line: "Tell me a number and I
  will take you there."

Each place still shows its quoted first words, so the list reads on its own.

## Change the document (only what the writer approved)

1. `lc docx status --workspace <ws>`. If `locked` is true, Word has the file
   open: ask the writer whether to save it, then
   `lc word close --payload '{"document": "<path>", "save": true}'` (done by
   itself, or its `live` tool or `steps`), or ask the writer to save and close it. Never close Word with unsaved
   changes without the writer's answer.
2. If `changed_on_disk` is true, the writer saved since the tool last read the
   file: run `lc ingest` on it first, then check the edit still applies.
3. Write the approved edits to `edits.json` (the format is in `60-rounds.md`,
   step 5: `id`, `quote`, `prefix`, `suffix`, `replace`, `reason`) and run
   `lc docx edits --workspace <ws> --edits edits.json --dry-run`, then without
   `--dry-run`. For a name changed everywhere: `lc docx rename OLD NEW --workspace <ws> --dry-run`, then without it.
4. Reopen the document (`lc word reopen --payload '{"document": "<path>"}'`)
   and take the writer to the change (above). Tell them, in one short message:
   what changed, where, and that they can ask you to take it back.

If a command answers `refused`, nothing was written: explain the reason in
plain words and what the writer can do (close Word, save, quote more words).
If the writer wants a change the tool made taken back,
`lc docx undo --workspace <ws>` returns the document to how it was before the
last edit or rename (`--dry-run` first).
