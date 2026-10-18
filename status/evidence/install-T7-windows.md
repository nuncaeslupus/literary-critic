# Install T7 — guided test, Windows half

Recorded 2026-10-18 on the owner's Windows 11 Pro PC, literary-critic 0.1.7 from
the release, Word open, work "Prueba T7" (the public-domain `corpus/` text as
`.docx`). **The Mac half (10 actions) is pending**: the owner postponed it, so
the gate (20 actions) is not met yet.

## Located actions

Times are from `mcp.log`, which stamps each call when it ends and records no
duration. "Tool seconds" runs from the end of the first call of the request to
the end of the call that moved Word; a request that needed one call has no
measurable span. The writer-visible wait also includes Claude's turns ("some
seconds", owner) and, the first time, Word opening the file.

| # | Request (kind) | Calls | Tool seconds | Landed | Word moves |
|---|---|---|---|---|---|
| 1 | a phrase, via the places card | find, places, click → select | — | yes | 1 |
| 2 | a quoted phrase | find, locate (refused: quote), locate | 8 | paragraph start, far from the phrase | 1 |
| 3 | a date | find, locate | 5 | yes | 1 |
| 4 | first chapter | locate | — | yes | 1 |
| 5 | last chapter (asked twice) | locate ×2 | — | yes | 1 |
| 6 | a name | find, locate | 4 | yes | 1 |
| 7 | a character's action | find, locate | 4 | yes | 1 |
| 8 | a place name | find, locate | 4 | yes | 1 |
| 9 | second paragraph of a chapter | locate, show, locate | 10 | yes, after a wrong first jump | 2 |
| 10 | a quoted line | find, locate | 4 | yes | 1 |

windows_actions: 10
mac_actions: 0
live_locate_success_windows: 1.0
live_locate_seconds_p50_windows: 4 (tool seconds, 7 measurable requests)
live_locate_writer_visible_steps_ok: 9/10

The first click on the places card is slow (Word opens and processes the file);
the second is near-instant. Request 1 first failed with `ENGINE_UNAVAILABLE`:
setup had picked an older broken draft because the current one, open in Word,
could not be read and was skipped silently. After the writer named the file it
worked.

## Findings filed as follow-ups

- Setup skips a manuscript that is open in Word and silently picks an older
  draft.
- `locate` lands on the paragraph start, not the phrase; a quoted target is
  refused instead of matched loosely; each request takes two calls.
- "Paragraph N of chapter M" counts the subtitle as a paragraph.
- The locate description makes Claude say "Done." in English.
- No visible "opening in Word…" hint after a click; card errors are codes;
  a refused `places` still renders an empty card.
- Errors returned inside the envelope are logged as `ok`; no call durations.
- The index does not follow an applied change until the next ingest.
- The test file came from the test generator, which plants an invalid
  footnotes part, stray field text and deletions: Word repaired it and showed
  revision marks. The test needs a clean `.docx`.
