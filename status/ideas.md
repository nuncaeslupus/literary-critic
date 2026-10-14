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

### H. What other users and tools would ask for (2026-10-14, for the owner)
Candidates only; none is committed. Size: S (days, mostly scripts), M (a
workspace), L (a project). "Builds on" names what exists already.

**Top picks** (most value for the cost): H1, H2, H5, H9, H12.

Writers
- **H1 Style sheet (S).** The copy-editor's sheet publishers expect: spelling of
  every name, chosen variants (OK/okay, gray/grey), numbers, capitals, hyphens,
  italics; then flag every place the draft departs from it. Builds on: Codex
  entities, `tokens`/`ngrams`, metrics. Script-first; the writer settles each choice.
- **H2 Timeline and continuity (M).** Dates, ages, weekdays, seasons, travel
  times, who knows what when; contradictions become findings with both places
  located. Builds on: scene `time`, setups, Codex spans. LLM resolves relative
  times; a script checks the arithmetic.
- **H3 Genre packs (M).** Checklist modules per genre: mystery clue fairness
  (every clue planted before the reveal; builds on setups/payoffs), romance
  beats, thriller pacing, fantasy world rules. Builds on: `checklist/`, kinds.
- **H4 Voice and viewpoint (M).** Are characters' voices distinct (speech
  features per speaker)? Head-hopping inside a scene. Builds on: `speech`
  table, dialogue records, scene `pov`.
- **H5 Beta-reader feedback (M).** Import comments from beta readers (Word
  comments, a form, an email), place each on its span, group them ("3 of 5 lost
  the thread in chapter 7"), compare with the tool's own findings. Builds on:
  doc-control comment reading, spans, findings.
- **H6 Submission package (S-M).** Check a synopsis and a query letter against
  the Codex (missing arc, wrong order, names that changed), and the agency's
  usual asks (length, first pages). The writer writes them (rule 5).
- **H7 Series and collections (L).** One Codex across books: shared entities,
  cross-book continuity, a series bible. Builds on: decision 14 (works side by
  side), Codex links.
- **H8 More forms and languages (M each).** Short-story collections, scripts,
  memoir/non-fiction (flags for real people named: legal care), more languages
  (fr, de, it, pt: syllables, stopwords, dialogue conventions). Builds on:
  `kinds/`, lexicons.

Editors, agents, translators, publishers
- **H9 Agency triage (M).** Many manuscripts at once: a short reader report
  from the first pages plus synopsis, ranked, comparable titles. Builds on:
  reader report, `lc library`. Needs: privacy and batch cost limits.
- **H10 Editor and writer together (M).** An editor's letter and margin notes
  the writer answers point by point; rounds keep both sides. Builds on: rounds,
  decisions log, Word comments.
- **H11 Translation check (M).** Align a translation with its source by
  paragraph: omissions, additions, names and terms kept consistent, a glossary.
  Builds on: `lc diff` alignment, Codex names.
- **H12 Production hand-off (S-M).** Content notes (opt-in list of sensitive
  topics, for readers who ask), audiobook prep (pronunciation list from the
  Codex, lines per speaker for a multi-voice reading), metadata (keywords,
  categories, word count), front and back matter checklist.

Other tools
- **H13 litcritic as an MCP server (M).** `lc` commands as tools for any MCP
  client (Claude desktop, IDEs, other agents), with `--json` output everywhere.
  Fits the install spec (`arsenal/project/install/spec.md`).
- **H14 Exports (S each).** Codex as a read-only wiki (Markdown/Obsidian pages
  per character and place), Scrivener project import, Google Docs comments.
- **H15 Privacy and local models (M).** A stated data policy (what is sent to
  the model, what is kept, how to delete a workspace), a log of what each packet
  sent, and a local-model mode. Note D-4: the cheap tier failed entities, so a
  local model needs its own measured gate.
- **H16 Cost before big jobs (S).** Tell the writer in plain words how long and
  how much of their plan a full index or analysis will use before starting.
  Builds on: `lc index` cost meter.

Questions for the owner: which of the top picks first? Is agency use (H9) a
goal, or only writers? Is any of H12 out of scope for "the writer writes"?

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
| 10 | 2026-10-11 | Codex storage: plain text files only (JSON/JSONL), behind one module (`codex.py`) with in-memory indexes. No SQLite. Callers never touch the files, so the Codex can be replaced later. |
| 11 | 2026-10-11 | Codex design rules: simple, LLM-friendly, cheap to maintain. Store only what cannot be recomputed (derived views are computed on demand). Stable ids. A check command finds dead references, orphan items and stale spans, so nothing rots silently. A small text change must cost a small, local update. |
| 12 | 2026-10-11 | Codex items share one envelope (id, type, spans, links, status, text, history) plus a few typed fields per type. New types are cheap to add. |
| 13 | 2026-10-11 | Everything is modular by text kind (novel, short story, poetry, script, thesis, textbook...): each kind plugs in its own structure detection, item types and checklist on a kind-agnostic core. |
| 14 | 2026-10-11 | Many works can be analysed side by side, each in its own place without collisions; grouping by kind, author or other criteria. |
| 15 | 2026-10-11 | Works live anywhere under the home folder (user subfolders allowed), found by their settings file; each has a unique id that everything refers to; author, kind, series, tags are metadata; grouping is a command (lc library --by ...). |
| 16 | 2026-10-11 | The Codex answers questions through a query API; the LLM turns a writer's question into a query. |
| 17 | 2026-10-11 | Measurable checks and proactive feedback are named questions run against the Codex. |
| 18 | 2026-10-11 | No migration: phase-1 per-type formats and docs are replaced; the tool is rebuilt on the Codex from corpus examples. |
| 19 | 2026-10-11 | Query surface: read-only SQL over an in-memory view (stdlib sqlite3, never persisted) plus named questions; the stored/computed data is derived from a catalogue of writer questions. Spec approved (r3). |
| 20 | 2026-10-11 | Chat-first use for non-technical writers: Cowork does everything, edits land in the master .docx as tracked changes, Claude takes the writer to the exact paragraph in Word (computer use for now). Spec: arsenal/project/chat/spec.md. |
| 21 | 2026-10-11 | A live Word-control extension (edit the open document while chatting with the agent, any Word version) is a separate project; literary-critic defines the interface it needs and uses it through one adapter. |
| 22 | 2026-10-11 | Later: brainstorming for a novel not yet started, guiding the author through every step (premise, characters, structure, plan) while the author writes. |
