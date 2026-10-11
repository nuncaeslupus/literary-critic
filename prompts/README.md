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
| `20-scene-cards.md` | Write one scene card per scene (index layer L2). |
| `25-summaries.md` | Write chapter summaries (L1) and the synopsis (L0). |
| `30-orientation.md` | First reading: writer's brief, profile, traits, what the novel is trying to do. |
| `40-checks.md` | Run the checklist and record findings with evidence. |
| `50-new-draft.md` | Bring in the next draft and see what changed. |
| `60-rounds.md` | Turn findings into a revision round, the letter, and the writer's decisions. |

Index layers: **L0** profile and synopsis · **L1** chapter summaries · **L2**
scene cards · **L3** the text itself, read through `lc show`, `lc find` and
`lc context` with a token budget.
