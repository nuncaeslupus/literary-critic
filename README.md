# literary-critic

Tooling that lets an LLM work through a full novel manuscript as a professional
editor would — and that keeps working across many chat sessions and drafts.

1. **Index** — turn the manuscript into stable anchors (part → chapter → scene →
   paragraph) and a Codex — a knowledge base of scenes, characters, places,
   facts, setups/payoffs and findings, each tied to its text — so the LLM can
   find and relate anything without loading the whole book.
2. **Analyse** — run a generic catalogue of checks (structure, characters, plot,
   scenes, POV, prose, dialogue, continuity, …), adapted to each novel, with
   evidence anchored to the text and script-measured metrics wherever possible.
3. **Advise** — produce prioritised, concrete revision actions in rounds
   (structural first, then scene, then line level), track their status, re-index
   the next draft and measure what changed.

Status: early development. See `status/specification.md` and `status/plan.md`.

## How it is used

| Where | How |
|-------|-----|
| Claude Code (local or cloud) | Clone, open, talk. Scripts run directly. |
| Chat with code execution (ChatGPT, Claude.ai, Gemini) | Upload the kit zip (`lc kit` builds it; the assistant reads its `START_HERE.md`) and your workspace zip; the assistant runs the scripts and returns an updated workspace zip. |
| Chat without code execution | Paste the portable prompts from `prompts/`; reduced mode without metrics. |

Your novel and all working files live in a **workspace folder outside this
repo** — a Google Drive folder works well. See `docs/workspace.md`.

## Development

```bash
uv sync          # Python >= 3.11; runtime uses only the standard library
make ci          # lint, typecheck, tests, content guard
```

Rules for contributors and assistants: [`AGENTS.md`](AGENTS.md).

## License

Apache License 2.0 — see `LICENSE` and `NOTICE`.
