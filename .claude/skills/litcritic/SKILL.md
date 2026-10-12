---
name: litcritic
description: Works on a novel manuscript with the literary-critic toolkit — ingesting a draft, recording scenes and characters in the Codex, answering questions about the novel from it, running the analysis checklist, recording findings, revision rounds, comparing drafts. Use whenever the user talks about their novel, a manuscript, a draft, chapters, characters, an editorial letter, revision rounds or a reader report, even without naming the tool, and whenever an `lc` or `lc codex` command or a workspace under `$LITCRITIC_HOME` comes up. Not for changes to the tool's own code (those are [[...]] requests handled as normal development).
metadata:
  type: workflow
---

# literary-critic

CANARY: litcritic-loaded-2026-10-11-2ebb846e930ff66d

The procedures live in `prompts/` so any chatbot can follow them; this skill
says which one to read. Read `prompts/00-guide.md` at the start of every
session that touches a novel. It holds the rules that matter most: the writer
writes (no drafted prose unless the writer turned prose suggestions on, after
the AI-text notice), never edit the manuscript without
permission for that change, plain language, locate everything, one change per
message.

What is known about a novel lives in its Codex (`<ws>/codex/`, read and
written only through `lc codex`; reference in `docs/codex/README.md`). Ask
it before reading text, and record what reading teaches.

| The user wants to… | Read |
|--------------------|------|
| start using the tool on a novel ("I want to use literary-critic for my novel"), set it up | `prompts/05-setup.md` |
| start, or where things stand is unclear | `prompts/00-guide.md`, then the workspace `log/` |
| bring in a draft, fix chapters/scenes | `prompts/10-ingest-and-structure.md` |
| index the novel for analysis | `prompts/20-codex-items.md` |
| a first reading, brief, profile | `prompts/30-orientation.md` |
| a question about the novel ("how often…", "where is…", "what changed…") | `prompts/35-ask.md` |
| analysis, feedback, "what's wrong with it" | `prompts/40-checks.md` |
| look at a new draft | `prompts/50-new-draft.md` |
| a revision round, the editorial letter, recording decisions | `prompts/60-rounds.md` |
| an agency/editor assessment, a reader report | `prompts/70-reader-report.md` |
| go to a passage in Word, apply an approved change to the Word file | `prompts/80-live-word.md` |

Workspaces live outside this repo (`$LITCRITIC_HOME/<slug>/`). Before any
commit, run `make guard`: nothing from a working novel may enter the repo
(see `AGENTS.md`). When something learned on a novel would help with other
novels, turn it into a generic change to the tool.
