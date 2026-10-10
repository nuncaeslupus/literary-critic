# literary-critic — rules for any LLM working here

This file is the project contract for every assistant (Claude, ChatGPT, Gemini,
others). `CLAUDE.md` imports it; other chatbots should be pointed at it first.

## What this repo is

Generic tooling that lets an LLM read a full novel manuscript, index it so it can
move through it without filling its context, analyse it against a catalogue of
checks, and hand the writer concrete, prioritised revision actions — then
re-index each new draft and track what changed.

## The two channels

Sessions mix two conversations:

- **Plain messages** are about the novel being worked on (the *working novel*).
  Answer in the language the writer uses or the novel is written in.
- **`[[...]]`** marks talk about this repo (the tool). Repo artifacts are
  written in English.

Don't wait for `[[...]]` to improve the tool: when something learned on a
working novel is generic (it would help with other novels), turn it into a
generic change to the repo — and phrase it without any trace of the novel.

## Hard rules

1. **Never add anything about specific working novels to the repo.** No
   manuscript text, titles, character or place names, plot details, findings,
   indexes, letters or notes. Examples in docs and tests use only the
   public-domain texts under `corpus/` or invented placeholders.
2. **Working files live in a workspace outside this repo** (see
   `docs/workspace.md`). `litcritic` refuses a workspace inside a git work tree
   of this repo.
3. **Run the content guard before every commit** (`make guard`; the pre-commit
   hook does it). It blocks manuscript file types outside `corpus/` and any
   term listed in a workspace's `guard-terms.txt`. When you start on a new
   novel, fill its `guard-terms.txt` with title, character and place names.
4. **Never modify the writer's manuscript (Word, Google Docs, any file) without
   explicit permission for that specific change.** Default to comments or
   suggestions; direct edits only after the writer confirms.
5. **Script first.** Anything deterministic (parsing, counting, diffing,
   indexing, validating, rendering reports) is a script with tests. The LLM is
   used for judgment: reading, interpreting, critiquing, writing feedback.
6. **Measure.** Every capability ships with a metric and a gate (see
   `status/plan.md`); evidence goes to `status/evidence/`.
7. **Runtime code is Python standard library only** (`src/litcritic/`), so the
   kit runs inside chat code interpreters. Dev tools (ruff, mypy, pytest) are
   fine.

## Layout

| Path | Purpose |
|------|---------|
| `src/litcritic/` | The `litcritic` package and `lc` CLI (stdlib only) |
| `checklist/` | Generic analysis-check catalogue (part 2) |
| `schemas/` | JSON schemas for index, scene cards, findings, actions |
| `prompts/` | Portable LLM prompts (usable from any chatbot) |
| `corpus/` | Public-domain texts for tests and examples |
| `docs/` | Architecture, workspace format, research |
| `status/` | Specification, plan, gate evidence |
| `tests/` | Pytest suite |
