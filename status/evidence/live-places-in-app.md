# live_places buttons in the Claude desktop app (owner, 2026-10-15)

What `lc docx places` sends (#171) and what the prompts now give for every
place under discussion (#190): doc-control's `live_places` with
`{"doc": "<bare file name>", "places": [...], "mode": "cursor"}`. Hand test run
together with doc-control's live tests, reported by its session.

Setup: Windows x64, Word 16.0.17932, doc-control 0.6.4 installed as the `.mcpb`
desktop extension (no `mcpServers` config entry), Chat tab of the Claude desktop
app, a test `.docx` open in Word (seven short paragraphs, three chapter headings).

## Result: PASS

| Place given by | Click |
|---|---|
| `at` address | ✓ Word moved to the paragraph |
| find phrase only | ✓ moved |
| stale `at` plus find phrase | ✓ fell back to the phrase, moved |
| phrase not in the text | ✗ on that button only (`ANCHOR_NOT_FOUND`), as expected |

The buttons rendered inline in the chat; a bare file name found the open
document. Owner: all four behaved as expected.

Timings (doc-control's scripted run of the same calls against real Word; the
in-app run was not timed): `live_places` 1 ms (it only validates and echoes;
places resolve on click), `at` 411 ms, phrase 301 ms, stale `at` to phrase
556 ms. Each time the cursor was at the paragraph's start, nothing selected,
Word in front.

## Not covered

- Only `mode: "cursor"`; `select` mode and `find_phrase_across` not clicked in-app.
- Chat tab only, not Cowork or the Code tab.
- Not yet on a Mac.

## Install notes for writers (doc-control 0.6.4)

- On Windows the `.mcpb` does not open by double-click: drag it onto the app's
  Settings → Extensions.
- The app warns in red that the extension can access everything on the
  computer before Install; expected.
- An older `uvx doc-control` entry in `claude_desktop_config.json` registers a
  second doc-control server: remove it by hand.
- The `.mcpb` is a CI build artifact for now, not yet attached to a release.
