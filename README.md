# <img src="https://raw.githubusercontent.com/nuncaeslupus/literary-critic/main/docs/logo.png" width="40" height="40" alt="" align="top"> literary-critic

<!-- claude-arsenal:attribution: added by claude-arsenal's /init. Delete this block to drop it (it is not put back), or set `attribution = false` in the arsenal config.toml. -->
[![Built with claude-arsenal](https://img.shields.io/badge/built%20with-claude--arsenal-d97756)](https://github.com/nuncaeslupus/claude-arsenal)
<!-- /claude-arsenal:attribution -->

[![CI](https://github.com/nuncaeslupus/literary-critic/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nuncaeslupus/literary-critic/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/nuncaeslupus/literary-critic)](https://github.com/nuncaeslupus/literary-critic/releases/latest)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

<p align="center">
  <img src="https://raw.githubusercontent.com/nuncaeslupus/literary-critic/main/docs/hero.png" width="100%" alt="literary-critic: panels — a manuscript page cut into paragraph anchors with a word marked in red, a codex card for a character whose eye colour differs between two anchors, and a round of revision advice ordered structure, scene, line">
</p>

**Lets an LLM read a full novel manuscript the way a professional editor would, across many chat sessions and drafts.**

A whole novel does not fit in a useful context window, and a chat forgets what
it read last week. literary-critic indexes the manuscript into stable anchors and
a knowledge base (the Codex), runs a catalogue of editorial checks with evidence
tied to the text, and turns the findings into prioritised revision rounds. The
writer writes: the tool diagnoses and explains, and changes the manuscript only
with the writer's approval for each change.

## Quick start

In Claude Code:

```bash
git clone https://github.com/nuncaeslupus/literary-critic.git && cd literary-critic && claude
# then say: "I want to use literary-critic for my novel"
```

In the Claude desktop app (Windows): download `literary-critic-<version>.mcpb`
from the [latest release](https://github.com/nuncaeslupus/literary-critic/releases/latest),
drag it onto the app's window (Settings → Extensions), press Install and choose
your novels' folder.

## Example

The CLI on a public-domain text from `corpus/` (the Python version in `pyproject.toml`, [uv](https://docs.astral.sh/uv/)):

```console
$ uv sync
$ export LITCRITIC_HOME=/tmp/lc
$ uv run lc init jekyll --title "Strange Case of Dr Jekyll and Mr Hyde" --language en --author "R. L. Stevenson"
work created: /tmp/lc/jekyll (id jekyll-645d9a)
add character/place names to /tmp/lc/jekyll/guard-terms.txt
$ uv run lc ingest --workspace jekyll corpus/jekyll-hyde/text.txt
v001: 350 paragraphs -> /tmp/lc/jekyll/text/v001.txt
note: hard-wrapped blocks
$ uv run lc anchor --workspace jekyll
0 parts, 11 chapters, 11 scenes; chapter signals: isolated 10
$ uv run lc show --workspace jekyll
chapter | words | scenes | title
c00 | 13 | 1 |
c01 | 2398 | 1 | STORY OF THE DOOR
c02 | 2935 | 1 | SEARCH FOR MR. HYDE
c03 | 799 | 1 | DR. JEKYLL WAS QUITE AT EASE
c04 | 1668 | 1 | THE CAREW MURDER CASE
...
c10 | 6939 | 1 | HENRY JEKYLL'S FULL STATEMENT OF THE CASE
$ uv run lc find --workspace jekyll '"Edward Hyde"'
17 paragraphs match '"Edward Hyde"'
[c02.s1.p1] … etc., all his possessions were to pass into the hands of his "friend and benefactor Edward Hyde," but that in case of Dr. Jekyll's "disappearance or unexplained absence for any …
[c05.s1.p11] The letter was written in an odd, upright hand and signed "Edward Hyde": and it signified, briefly enough, that the writer's benefactor, Dr. Jekyll, whom he …
[c08.s1.p72] … They drew near on tiptoe, turned it on its back and beheld the face of Edward Hyde. He was dressed in clothes far too large for him, clothes of the …
...
$ uv run lc metrics --workspace jekyll
39 metrics measured, 10 need more input
```

Anchors such as `c08.s1.p72` stay stable across drafts, so the Codex, the
findings and the revision actions keep pointing at the right paragraph after the
writer revises.

## Use with AI agents

The LLM is the editor; the scripts do everything deterministic (parsing,
counting, diffing, indexing, validating, rendering).

| Where | How |
|---|---|
| Claude Code (local or cloud) | Clone, open, talk. The `litcritic` skill in `.claude/skills/` drives the process; scripts run directly. |
| Claude desktop app, normal chat or Cowork | Install the `.mcpb` extension (above). Full experience: the novel's folder connected, approved changes written into the file with a backup, Word opened at the right paragraph. |
| Claude.ai or desktop without the extension | Upload the Skill zip built by `lc kit --skill` (Settings → Skills), then say "I want to use literary-critic for my novel". Basic mode: upload the manuscript, get back a commented copy. |
| Any chat with code execution (ChatGPT, Claude.ai, Gemini) | Upload the kit zip built by `lc kit` (the assistant reads its `START_HERE.md`) and your workspace zip; the assistant runs the scripts and returns an updated workspace zip. |
| Chat without code execution | Paste the portable prompts from [`prompts/`](prompts/); reduced mode without metrics. |

### MCP server

`lc mcp` serves the tools over stdio. The desktop extension runs it for you;
any other MCP client can run it from a clone:

```json
{
  "mcpServers": {
    "literary-critic": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/literary-critic", "lc", "mcp", "/path/to/novels"]
    }
  }
}
```

The folder arguments are the install grant: the server reads only novels under them.

| Tool | What it does |
|---|---|
| `works` | List the writer's novels, most recently used first |
| `resume` | Open a novel: where it stands, the next step, the guide for this chat |
| `setup` | Set up a novel for the first time: find its manuscript and prepare its workspace |
| `add_folder` | Open a folder picker to add a folder that holds a novel |
| `show` | Table of contents, or the text of a chapter, scene or paragraph |
| `find` | Paragraphs containing all the words, or a quoted phrase |
| `ask` | Answer a named question about the novel from its Codex |
| `guide` | Read a procedure guide or a checklist file |
| `run` | Run another `lc` command on the novel (round, codex, index, metrics, diff, report, ...) |
| `plan` | The work plan: parts, the active one, what comes next |
| `locate`, `places`, `select` | Take the open Word document to a passage |
| `change_card` | Propose manuscript changes with Approve and Dismiss buttons; the only way to change the manuscript |
| `change_approve`, `change_dismiss`, `change_go`, `change_status` | Used by the change card's buttons |

The Word tools (`locate`, `places`, `select`, `change_go`) need Word on Windows.
The extension updates itself in the background (*Update automatically*, on by
default) and runs the new release at the next start of the app.

## How it works

1. **Index**: the manuscript becomes stable anchors (part → chapter → scene →
   paragraph) and a Codex of scenes, characters, places, facts, setups/payoffs
   and findings, each tied to its text, so the LLM can find and relate anything
   without loading the whole book.
2. **Analyse**: a generic catalogue of checks (structure, characters, plot,
   scenes, POV, prose, dialogue, continuity, ...) in [`checklist/`](checklist/),
   adapted to each novel, with anchored evidence and script-measured metrics
   wherever possible.
3. **Advise**: prioritised, concrete revision actions in rounds (structural,
   then scene, then line level), with status tracking; the next draft is
   re-indexed and `lc diff` measures what changed.

Documents are read and written through
[doc-control](https://github.com/nuncaeslupus/doc-control), which owns the generic
document work (paragraph addresses, diff, locating, edits with a backup,
comments, undo). literary-critic owns the literary side. See
[`docs/architecture.md`](docs/architecture.md).

## Configuration

- **Workspace.** Your novel and all working files live outside this repository,
  in `$LITCRITIC_HOME/<slug>/` (`~/literary-critic/<slug>/` when unset). A
  Drive-synced folder works well. See [`docs/workspace.md`](docs/workspace.md).
- **Who writes.** `prose_suggestions` in the writer's profile: `off` by default,
  `minor` for small fixes the writer approves one by one, `on` for suggested
  passages. Asked at setup.
- **Commands.** `uv run lc --help` lists all of them (`init`, `ingest`,
  `anchor`, `show`, `find`, `codex`, `index`, `metrics`, `diff`, `round`,
  `docx`, `report`, `kit`, `mcp`, ...).

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — the components and how they fit
- [`docs/workspace.md`](docs/workspace.md) — the workspace, per surface
- [`docs/codex/`](docs/codex/) — the Codex model
- [`prompts/`](prompts/) — the procedures, also usable as portable prompts
- [`AGENTS.md`](AGENTS.md) — rules for contributors and assistants
- [`status/specification.md`](status/specification.md) — the specification

## Development

```bash
uv sync          # Python >= 3.11; runtime is the standard library plus doc-control
make ci          # lint, typecheck, tests, content guard
```

A merged PR that raises `version` in `pyproject.toml` publishes a release with
the `.mcpb`.

## Related projects

- [claude-arsenal](https://github.com/nuncaeslupus/claude-arsenal) — spec-driven Claude Code workflow and gated task queue.
- [drawspec](https://github.com/nuncaeslupus/drawspec) — declarative diagram spec → clean SVG/PNG/text, writable by LLMs; MCP server included.
- [doc-control](https://github.com/nuncaeslupus/doc-control) — lets AI agents read and edit Word documents; literary-critic's document layer.
- [integral-job-search](https://github.com/nuncaeslupus/integral-job-search) — candidate-centred job search run in Claude Code.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
