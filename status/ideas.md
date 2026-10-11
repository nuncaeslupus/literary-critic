# Ideas backlog (phase 2)

Living list of ideas for the next phase. New ideas are appended under their
group; decisions move to the log at the end. Nothing here is committed work
until it reaches a spec and a plan.

## Core idea (owner, 2026-10-11)
The heart of the tool is a structured knowledge base about the novel (a
"meta-novel"): text, structure, entities, facts, references between parts,
issues and decisions, all anchored to the text and kept in sync with every
draft by scripts. Reading, finding, advising, reports, chats and any later
editing tool are views on it or operations over it. An orchestrator keeps it
current when the text changes, including changes made while the tool was not
looking (renamed character, new plot twist, deleted paragraph that orphans
later references). Knowledge sits on spans of any length (see D-8).
Efficiency: scripts first, the LLM only reads what changed.


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
| 4 | 2026-10-11 | Shape the critical report (S1) first; then session flow and memory (S2); then Claude packaging (S3). |
| 5 | 2026-10-11 | Working notes (many files) are separate from what the writer gets. Writer-facing output is a per-session view chosen by the session's goal; summarise status, let the writer choose, never repeat settled points. |
| 6 | 2026-10-11 | The knowledge base is the core (sub-project S0) and comes before S1-S3. |
| 7 | 2026-10-11 | The knowledge base is the Codex; "bible" is its characters-and-world layer. |
| 8 | 2026-10-11 | No fixed sentence level. Every piece of knowledge is anchored to a span of any length (a word, a sentence, a dialogue, a scene, a multi-page digression). Spans also measure information density (knowledge per word) to find rhythm and excess. |
| 9 | 2026-10-11 | Spans keep their place with paragraph address + character offsets (fast path) and a W3C text-quote selector (exact text + prefix/suffix), as Hypothesis does. Text under the span changed or not found -> flagged for re-reading, never moved silently. Its own module. |
