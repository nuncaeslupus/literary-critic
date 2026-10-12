# Word-control interface

The contract between literary-critic and whatever controls the writer's open
Word. Today that is the agent itself, using computer use; later it is the
separate Word-control extension (D-21). literary-critic talks to both through
one adapter, `src/litcritic/word_live.py`, and the `lc word` command:

```bash
lc word locate --payload '{"document": "MyNovel/MyNovel_v3.docx", "find": "Ya voy —dijo"}'
```

## Rules for every operation

- One JSON object in, one JSON object out.
- `status` is `ok` (done), `manual` (the agent must do it, see below),
  `refused` (a safety check failed; nothing changed) or `error`.
- `document` is the path of the `.docx`, as `lc setup` and `lc docx` print it.
- The writer's unsaved work is never discarded. Before the file is changed on
  disk, Word has saved and closed it; `lc docx status` says whether it is open.
- Edits are tracked changes, authored `literary-critic`, so the writer can
  accept or reject each one in Word.

### Manual answers (today)

Until the extension exists, every operation answers:

```json
{"status": "manual", "how": "computer-use",
 "steps": ["Bring Word to the front …", "Press Ctrl+F, type exactly: …"],
 "writer": "In MyNovel_v3.docx, go to chapter 7, around page 112, …"}
```

`steps` are for the agent, done with computer use. `writer` is the plain
instruction to give the writer when computer use is off or fails. If
`$LITCRITIC_WORD_CONTROL` names the extension's command, the adapter runs
`<command> <operation>` with the request on stdin, and uses its JSON answer;
when it fails, the manual answer comes back with `extension_error`: the
operation was not done, and the agent does it by hand (or tells the writer).

## Operations

### `locate`

Bring Word to the front and select a passage, so the writer sees it. The
`find` string comes from `lc docx locate` (Word's Find syntax: `^p` paragraph
mark, `^t` tab, `^l` line break, `^~` non-breaking hyphen, `^s` hard space,
`^^` caret; at most 255 characters).

- Request: `document`, `find`, `locator` (optional; the plain locator from `lc docx locate`), `language` (optional; of the writer line, default `en`)
- Response: `status`, `found`

### `apply_edits`

Apply approved edits as tracked changes. Request `edits` items are the ones of
`lc docx edits`: `id`, `quote`, `prefix`, `suffix`, `replace`, `reason`.

- Request: `document`, `edits`
- Response: `status`, `applied`, `skipped`

### `rename`

Whole-word rename across the document, as tracked changes.

- Request: `document`, `old`, `new`, `case_sensitive`
- Response: `status`, `count`

### `save`

Save the document in Word.

- Request: `document`
- Response: `status`

### `close`

Close the document in Word, saving first when `save` is true. Never discards
unsaved changes without the writer's answer.

- Request: `document`, `save`
- Response: `status`

### `reopen`

Open the document in Word again (after a change on disk) and bring it to the front.

- Request: `document`
- Response: `status`

### `selection`

What the writer has selected in Word, so they can point at a passage.

- Request: `document`
- Response: `status`, `text`, `find`

## Notes for the extension

- Address passages by the `find` string or by quote plus `prefix`/`suffix`
  context (see `lc docx edits`); a match must be unique or the request is
  refused.
- Never wrap a revision across a hyperlink or field boundary.
- `apply_edits` and `rename` may run on the open document (COM on Windows,
  AppleScript on Mac); the result must be the same tracked changes `lc docx`
  writes to the file.
