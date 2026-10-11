# Ideas backlog (phase 2)

Living list of ideas for the next phase. New ideas are appended under their
group; decisions move to the log at the end. Nothing here is committed work
until it reaches a spec and a plan.

## Groups

### A. Critique
- Cover every level, from architecture to mechanics: structure, plot, characters,
  pacing, scenes, dialogue, style, lexicon, and mechanical typography (double
  spaces, punctuation, dashes, quotes, wrong words).
- Stance of a literary critic: kind but honest; never agrees to everything; says
  plainly when a change is needed and why.
- Literary-agent view: market and imprint fit, positioning, comparable titles,
  what a given publisher would ask for.
- Capture the writer's style profile first; every suggestion must preserve it.
- Name density, brevity, clarity problems ("too dense", "too short", "hard to
  follow") and how to address them; help with lengths, endings, titles, formatting.
- Other forms later: short stories (should work as is), poems, scripts.

### B. Communication
- A complete critical report document for the writer, ordered from general to
  specific (whole book → parts → chapters → scenes → paragraphs → mechanics).
- Chat flow: one change at a time while applying; each session has an agenda and
  always moves forward.
- Large feedback is staged: the writer sees priorities first, details on demand.

### C. Memory and tracking
- A plan/log per novel that grows: open points, new ideas, what to re-read.
- Writer decision log: accepted, rejected (with reason), done differently. A
  rejected point is not raised again unless the text changes around it.
- Re-analyse only what changed; update indexes and auxiliary docs after changes.
- Detect edits the writer made while the tool was not looking.

### D. Real files (later)
- Edit Word / Google Docs safely: tracked-change copies, moves done for the
  writer, nothing deleted or rewritten in bulk without permission.
- Typography and style coherence (fonts, styles, chapter openings, margins).
- Mechanical fixes may come from docx-fixer (separate repo, used as a tool/API).

### E. File hygiene
- One canonical manuscript; detect stray copies by content; help open the right
  file; archive or hide the rest.

### F. Assistant work
- Session recap: what changed last time, where the writer stopped, how productive
  it was, whether recent changes helped; ideas to continue. The writer writes.

### G. Product shape
- Core engine: this repo (stdlib, portable).
- First surface: Claude (skills + local tool server), using the writer's own
  subscription; the chat kit stays as fallback for other chatbots.
- Later: editor add-ins, other chatbots, other forms.

## Decision log
| # | Date | Decision |
|---|------|----------|
| 1 | 2026-10-11 | First surface is Claude. |
| 2 | 2026-10-11 | docx-fixer stays a separate repo; may be used as a tool/API or merged later. |
| 3 | 2026-10-11 | First priority: report and session flow. Editing real files comes later. |
