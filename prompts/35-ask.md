# Answer a question from the Codex

Most questions a writer asks ("in how many chapters does she speak?", "am I
overusing this word?", "who matters most to him?", "where did that storyline
go?") have an answer in the Codex. Ask it before reading text: answers are
exact, cheap, and can be repeated on the next draft.

1. Find a named question that fits: `lc codex questions`. Each one has an id,
   a title and its parameters. Run it:
   `lc codex ask relevance --param character=<name> --workspace <slug>`.
   Names match without case or accents.
2. Where is something, and what depends on it?
   `lc codex find "<words>" --type entity --workspace <slug>` lists matching
   items (leave out `--type` to search every type; it searches text and fields);
   `lc codex show <id> --workspace <slug>` prints one item with its fields,
   where it is in the text (anchor, span state, quoted words) and its links
   both ways (`->` what it points to, `<-` what points to it). Where a name
   appears in the text: `lc codex ask character-appearances --workspace <slug>`.
3. What changed since the last draft? `lc codex sync --workspace <slug>`
   prints it when a draft is brought in. Afterwards, the items whose text
   moved, changed or disappeared:
   `lc codex sql "SELECT i.id, i.type, i.text, s.state FROM spans s JOIN items i ON i.id = s.item_id WHERE s.state != 'ok'" --workspace <slug>`;
   and the change log (who changed what, when):
   `lc codex sql "SELECT at, draft, op, type, text FROM changes ORDER BY at DESC" --workspace <slug>`.
4. No named question fits: write one read-only SQL query. See the tables and
   views first with `lc codex sql --schema --workspace <slug>`, then run it:
   `lc codex sql "<query>" --workspace <slug>`. Use `norm(text)` to compare
   names without case or accents. If the same kind of question comes up
   again, propose it as a new named question (`[[...]]`, with no trace of the
   novel).
5. If the Codex cannot answer (the items are not recorded yet), say so, read
   the text with `lc find` or `lc show`, answer, and record what you learned
   (`20-codex-items.md`).

Tell the writer the answer in plain words, located (chapter, page, the quoted
first and last words of the paragraph), never as a table of ids.
