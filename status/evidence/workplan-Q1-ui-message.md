# Change card `ui/message` in the Claude desktop app (owner, 2026-10-15)

Probe for the workplan spec's Q-1: does the desktop app take the change page's
`ui/message`, so the model learns of a click without the writer typing?

Setup: Windows x64, Claude desktop app, Chat tab, Opus 5.5. literary-critic
from `main` (after #214, doc-control 0.7.2) as a hand-added `mcpServers` entry
running `lc mcp` (the `.mcpb` is not built yet). Test work: the first two
chapters of `corpus/jekyll-hyde` as a `.docx`, set up with
`--edit-in-place yes`, not open in Word.

## Q-1

**Answer: yes, after one press of Send.** The host advertises the `message`
capability, so the page sends `ui/message`. The app does not deliver it to the
model straight away. It puts "Approved C1" in the writer's message box, under a
red banner ("Use caution before running this prompt…"), and the writer
presses Send. Then the model sees it as an ordinary user message and answers.

| Step | Result |
|---|---|
| First call of each tool | The app asks to allow it (one prompt per tool) |
| `change_card` | The card rendered inline: quote, replacement, who wrote it, reason |
| Approve | ✓ Approved; one plain write (no tracked revision), backup kept; plan log `change.approved` then `change.applied` |
| `ui/message` | "Approved C1" prefilled in the message box with the caution banner; sent by the owner |
| After Send | The model checked and confirmed the change in one line |
| Approve again on the same card | Refused, "not proposed: C1 is applied"; the file is not touched |

## Consequences

- The click alone changes the file; the message only tells the model. A writer
  who never presses Send loses nothing: the plan log and `lc plan status`
  carry the click, as the spec's fallback says.
- The caution banner is the app's, shown for any page-written message; it
  cannot be removed from the page.
- A card that is already settled still shows active buttons; a second click
  is refused with a red ✗. The card should show the settled state instead.

## Not covered

- Dismiss was not clicked.
- Live Word (document open) was not part of this run.
- Not on a Mac, not in Cowork.
