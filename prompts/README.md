# Prompts

Portable procedures for any assistant (Claude, ChatGPT, Gemini…). Each file is
self-contained: paste it, or point the assistant at it, at the start of the
step it describes. They assume the `lc` tool can run; without code execution
an assistant follows the same steps by reading, and says that metrics and
validation were not run.

| File | Use it to |
|------|-----------|
| `00-guide.md` | Talk to the writer: modes, language, the two channels, house rules. Read first, every session. |
| `10-ingest-and-structure.md` | Bring a draft in, check its structure, correct it with overrides. |
| `20-codex-items.md` | Record scenes, characters, places, motifs and setups as Codex items; write the synopsis. |
| `30-orientation.md` | First reading: writer's brief, profile, traits, what the novel is trying to do. |
| `35-ask.md` | Answer a writer's question from the Codex: named questions, links, changes, SQL. |
| `40-checks.md` | Run the checklist and record findings with evidence. |
| `50-new-draft.md` | Bring in the next draft and see what changed. |
| `60-rounds.md` | Turn findings into a revision round, the letter, and the writer's decisions. |
| `70-reader-report.md` | Assess a manuscript for an agency or publisher (reader-report mode). |

Index layers: **L0** profile and synopsis · **L1** table of contents · **L2**
Codex items (scenes, entities, setups…) · **L3** the text itself, read through `lc show`, `lc find` and
`lc context` with a token budget.
