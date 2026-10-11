# Starter prompt: Word-control tool (new project)

> Paste everything below the line into the new repository's first session. It
> collects what literary-critic and docx-fixer taught us. It is a starting
> point for exploring and specifying, not a spec: question it, push back, and
> ask me one thing at a time.

---

I want to build a standalone tool that lets an AI agent work on Word documents
quickly, precisely and safely, ideally live in the Word window the writer has
open while they chat with the agent. Think of it as an API for documents, made
for LLMs first: the agent orchestrates and keeps track of everything, and the
document changes in front of the writer, who sees every change and can accept
or reject it. The goal is that working on a book feels like working with a
coworker, visually, with no technical skills needed.

It will absorb docx-fixer (my current tool for reviewing and cleaning the
formatting of Spanish novels in `.docx` without opening Word: style inventory,
typography rules for dialogue dashes, quotes, spacing and brackets, house
templates, safe automatic fixes, plus a review page for the rest). docx-fixer
will be retired in favour of this more complete tool. Its rules should become
packs built on this tool's primitives.

## Who uses it

- **Agents:** Claude in Cowork (desktop app, a connected folder, and computer
  use as a preview), Claude Code, and a chat's code sandbox. They call it many
  times per session, so every call must be cheap, predictable and fast.
- **Downstream tools**, the first being literary-critic. Its needs are listed
  below.
- **Writers, indirectly:** non-technical people who must never lose work and
  must always understand what changed.

## Shape I have in mind (challenge it)

- **One core, two engines, one API:**
  - **File engine:** edits the `.docx` directly when it is closed. Pure
    standard library, as in docx-fixer: unzip, rewrite only the parts touched,
    copy everything else byte for byte.
  - **Live engine:** controls the open Word: COM on Windows, AppleScript/JXA on
    Mac. It works with any Word version, including perpetual Office
    2016/2019/2021, not only Microsoft 365.
  - The same operation names work in both engines, and the tool picks the
    engine, or says why it cannot.
- **Two front doors over the same core:** a CLI with JSON in and out, and an
  MCP server that installs in Claude Desktop/Cowork with one click (a desktop
  extension). The core must also run in a chat's Python sandbox (stdlib only)
  for the file engine.
- **Generic, not novel-specific.** Novels are one profile. Contracts, theses and
  manuals must work too.

## What it must do (the API, roughly)

**Addressing and structure**
- Stable addresses for parts, sections, headings, paragraphs, sentences, runs,
  words, comments, tracked revisions and pages. Pages are exact when live and
  estimated when the file is closed.
- Anchors that survive edits: a quote plus its context (W3C TextQuoteSelector
  style), paragraph fingerprints, and re-anchoring after changes.
  literary-critic already does this for its anchors (`c03.s2.p4`) and spans.
- Segmentation like literary-critic's: paragraphs, language-aware sentences
  (abbreviations), dialogue lines, scene breaks, chapter detection from
  headings and patterns. It must be generic, with per-profile settings.

**Read**
- Outline, stats, styles and fonts in use, a paragraph with its formatting, and
  the page of a paragraph.
- Find: literal, regex, case- and accent-insensitive, whole word. The output is
  small and capped (token budgets) with "more" cursors.
- List comments with their replies, and tracked changes with authors.
- Live only: the current selection ("what is the writer pointing at?"), and
  whether there are unsaved changes.

**Write: small primitives that compose**
- Replace a range's text, insert or delete paragraphs, apply a style or direct
  formatting, set alignment and indentation, add a comment, reply to it,
  resolve it, and accept or reject a revision.
- Content edits are tracked changes by default, so the writer can reject each
  one in any Word version.
- Rename a term across the document with word boundaries, case and inflection
  options, as one atomic batch.
- Batches are all-or-nothing, with a dry run that returns a preview diff.
- Downstream tools build bigger fixes in one or two calls. Example: "remove the
  leading spaces that fake a centred line, then centre it" is a find call plus
  a batch with two operations. That rule belongs to the downstream rule pack,
  not to the core.

**Live control**
- Bring Word to the front, select a range and scroll it to the middle of the
  screen, so the writer never has to search for anything.
- Turn Track Changes on or off; save, close, and reopen at a position.

**Safety (non-negotiable)**
- Before writing a file: detect Word's `~$` lock file and any change on disk
  since the last read.
- Back up before every write, verify the result opens and contains exactly the
  intended changes, and restore automatically on failure.
- An operation log with undo for every change the tool makes. Never touch
  anything outside the requested range: `unintended_changes == 0` is a gate.
- No silent rewrites. The tool is deterministic and contains no AI. Judgment
  belongs to the agent, approval belongs to the writer.

**LLM-first ergonomics**
- JSON everywhere, short outputs, stable error codes with a one-line hint on
  what to do next, no interactive prompts.
- A `schema` or `help --json` command that describes every operation, and one
  call per intent.
- Fast enough that the agent never waits: renaming across 100k words takes
  seconds with the file engine, and locating a passage live takes under a
  second.

## What literary-critic needs from it (consumer contract)

literary-critic (a toolkit that indexes a novel into a knowledge base called
the Codex and guides revision rounds) will call this tool through a single
adapter. It needs:

1. **Locate:** given a quote plus context (or a paragraph fingerprint), bring
   the open Word to that passage and select it. Today this is done with
   computer use and Find; this tool replaces that.
2. **Apply an approved batch** of edits to the writer's master `.docx` as
   tracked changes, live if the document is open, through the file engine if
   it is closed.
3. **Rename a character or place** across the book in one call.
4. **Save, close and reopen safely,** with unsaved changes always saved first
   and never lost.
5. **Read comments and replies,** and add and resolve comments.
6. **Map positions:** literary-critic anchors and spans resolve to document
   ranges and back.
7. **Report** what changed, for literary-critic's change log.

## Later, keep the door open

- Google Docs through its API as a third engine, and `.odt`.
- A visual review page like docx-fixer's `review`, built on the same API.

## Open questions I'd like to brainstorm with you

- Name of the project.
- MCP first or CLI first? Windows first or Mac first for the live engine?
- How a non-technical writer installs the live engine: one-click desktop
  extension, signed installer, or something else.
- How docx-fixer's rules and users migrate, and when docx-fixer is archived.
- API versioning, so downstream repos don't break.
- Where the line sits between core operations and downstream rule packs.

Please start by exploring this with me (one question at a time, with options,
pros and cons), then write the spec with measurable gates, as we do in my other
projects.
