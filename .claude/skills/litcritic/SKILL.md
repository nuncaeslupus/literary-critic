---
name: litcritic
description: Works on a novel manuscript with the literary-critic toolkit — ingesting a draft, checking chapters and scenes, writing scene cards and summaries, running the analysis checklist, recording findings, comparing drafts. Use whenever the user talks about their novel, a manuscript, a draft, chapters, characters, an editorial letter, revision rounds or a reader report, even without naming the tool. Not for changes to the tool's own code (those are `[[...]]` requests handled as normal development).
---

# literary-critic

The procedures live in `prompts/` so any chatbot can follow them; this skill
tells you which one to read. Read `prompts/00-guide.md` at the start of every
session that touches a novel — it holds the rules that matter most: the writer
writes (never draft prose for the novel), never edit the manuscript without
permission for that change, plain language, locate everything, one change per
message.

| The user wants to… | Read |
|--------------------|------|
| start, or you are unsure where things stand | `prompts/00-guide.md`, then the workspace `log/` |
| bring in a draft, fix chapters/scenes | `prompts/10-ingest-and-structure.md` |
| index the novel for analysis | `prompts/20-scene-cards.md`, then `prompts/25-summaries.md` |
| a first reading, brief, profile | `prompts/30-orientation.md` |
| analysis, feedback, "what's wrong with it" | `prompts/40-checks.md` |
| look at a new draft | `prompts/50-new-draft.md` |
| a revision round, the editorial letter, recording decisions | `prompts/60-rounds.md` |

Workspaces live outside this repo (`$LITCRITIC_HOME/<slug>/`). Before any
commit, run `make guard`; nothing from a working novel may enter the repo
(see `AGENTS.md`). When something learned on a novel would help with other
novels, turn it into a generic change to the tool.
