# Workspace format

One workspace per novel. It is a plain folder **outside this repo** — by default
`$LITCRITIC_HOME/<slug>/` (`~/literary-critic/<slug>/` when unset). Recommended
place: a Google Drive folder (synced by Drive for desktop when working locally).

```
<slug>/
  work.toml             # id, slug, title, author, kind, series, tags, language, mode, schema_version
  guard-terms.txt       # names that must never reach the tool repo
  manuscript/           # writer's originals, one snapshot per draft (v001.docx, v002.docx…)
  text/                 # normalised text per draft (v001.txt), one paragraph per line,
                        # + v001.meta.json: per-paragraph heading level, centred, page,
                        #   page break before, blank lines before, style name
  index/                # anchors, structure, scene cards, characters, timeline… (per draft)
  metrics/              # script-measured metrics per draft
  analysis/             # novel profile (adapted checklist) and findings
  revisions/            # round-NN/: editorial letter + action backlog with statuses
  log/                  # session log: what was done, decisions, next step
```

Everything is text (TOML, JSON, Markdown) except the manuscript snapshots, so a
workspace diffs cleanly and survives any sync tool.

## Library

Works can live anywhere under the home folder, in subfolders of your choosing
(`novels/`, `clients/ana/`…); the tool finds them by their `work.toml`. Each
work has a unique `id` (its slug plus a short random suffix) that every
command accepts, so moving or regrouping folders breaks nothing. Author, kind,
series and tags are labels: `lc library --by author|kind|series|tag` lists the
works grouped by any of them. `lc init <slug> --title … --language … [--author …
--kind … --series … --tag …]` creates one.

## Ingesting a draft

`lc ingest <file> --workspace <slug|folder>` accepts `.txt`, `.md`, `.docx` and
`.odt`. It copies the file to `manuscript/vNNN.<ext>` and writes `text/vNNN.txt`
plus its meta file. Tracked deletions, field codes, footnotes and comments are
left out; soft line breaks become spaces. Ingesting an unchanged file again
does nothing. Page numbers come from the page breaks Word/LibreOffice last
rendered, so they are approximate.

## Structure and anchors

`lc anchor --workspace <slug> [--version vNNN]` writes `index/vNNN/structure.json`:
parts, chapters (with titles, word counts and scenes) and one anchor plus
fingerprint per paragraph. Anchors read `[pN.]cNN.sN.pN` — part, chapter (`c00`
is front matter), scene (`s0` holds heading lines) and paragraph.

Detection uses the strongest kind of signal the draft uses consistently:
chapter words or numbers, then a chapter-start paragraph style, heading
styles, explicit page breaks, and short upper-case lines. Symbol-only lines and
"after break" styles start scenes. When it gets something wrong, put
corrections in `analysis/structure-overrides.json`, keyed by paragraph
fingerprints (from `structure.json`):

```json
{"chapter_starts": ["<fp>"], "not_chapter": ["<fp>"], "scene_starts": [], "not_scene": []}
```

Every fingerprint must match exactly one paragraph or nothing is applied.

## Comparing drafts

`lc diff v001 v002 --workspace <slug>` (both drafts anchored) writes
`index/v002/alignment.json`: for every old paragraph its status — unchanged,
moved, modified (with similarity), split, merged or deleted — and its new
anchors; the inserted paragraphs; and `stale_scenes`, the new scenes whose text
changed, so only their scene cards are re-read.

## Metrics

`lc metrics --workspace <slug>` writes `metrics/vNNN.json` with every metric in
`checklist/metrics.toml` that the script implements: lengths, sentence and
paragraph statistics, readability (Fernández-Huerta and Szigriszt/INFLESZ for
Spanish, Flesch for English — relative gauges only), dialogue, word choice,
names, proofreading signals. Items carry anchors.

Some metrics aggregate what the LLM or the registers provide and report
`unmeasured` until that input exists:

| Input | Path | Used by |
|-------|------|---------|
| Registers | `index/vNNN/registers/<kind>.json` (schema `register`) | characters, motifs, setups/threads |
| Scene cards | `index/vNNN/scene_cards.json` (list, schema `scene-card`) | POV distribution |
| Labels | `analysis/labels.json`: `chapter_endings` {chapter id: type}, `summary_passages` [anchors], `climax` anchor, `opening_hook` anchor | chapter endings, scene/summary ratio, dénouement share, opening hook |

## Index and queries

The LLM writes one scene card per scene into `index/vNNN/scene_cards.json`
(schema `scene-card`), chapter summaries into `index/vNNN/chapter_summaries.json`
(`{"c01": "…"}`) and the synopsis into `analysis/synopsis.md`.
`lc index --workspace <slug>` validates the cards (schema and anchors) and
builds `index/vNNN/registers/` — characters, locations, timeline, setups — by
script. Use the same short label for a setup and its payoff so they pair.

Queries print at most `--budget` tokens (default 2000) and say how to continue:

| Command | Shows |
|---------|-------|
| `lc show` | table of contents: chapter, words, scenes, title, summary |
| `lc show c03` / `c03.s2` / `c03.s2.p4` | that text, one anchored paragraph per line (`--fp` adds fingerprints for overrides) |
| `lc show c03.s2.p17-` | continue reading from that paragraph |
| `lc find <words>` / `"<phrase>"` `[--in c03]` | matching paragraphs, accent-blind, with snippets |
| `lc context c03.s2.p4` | chapter, scene card, the paragraph and its neighbours |

## Rounds, letters and locators

`lc round build` turns the Codex's open problem `issue` items into the next
round (`revisions/round-NN/round.json`): one action per issue of the earliest
level with undecided problems (structural, then scene, then line), sorted by
severity × confidence × profile weight ÷ effort. `lc round letter` writes
`letter.md` in the work's language; `lc round mark --id A3 --status accepted`
records the writer's decision as a `decision` item; `lc round status` says
whether the round can close.

Every action carries a writer locator from `lc locate <anchor>`: chapter,
scene, page (exact when the source recorded pages, else ≈ at 300 words per
page) and the paragraph's first and last words — the shortest runs that occur
only once in the draft. A very short paragraph that cannot be unique is placed
after its neighbour.

## Comments in Word

`lc docx-comments --workspace <slug>` writes a copy of the draft's `.docx`
snapshot to `revisions/round-NN/vNNN-comments.docx` with each pending or
accepted action of the latest round as a comment on its paragraph. Paragraphs
are matched by their position in the document recorded at ingest; existing
comments are kept. The writer's original file is never modified.

## Moving a workspace between sessions

| Surface | Pattern |
|---------|---------|
| Claude Code, local | Point `LITCRITIC_HOME` at the Drive-synced folder. |
| Claude Code, cloud | Container is ephemeral: `lc pack` → zip the user keeps (or a private repo / Drive connector), `lc unpack` next time. |
| Chat with code execution | Upload kit zip + workspace zip; the assistant runs `lc`, then `lc pack` and returns the zip to download and store in Drive. |
| Chat without code | Upload the latest `index/` summaries and `log/`; reduced mode. |

`lc pack --workspace <slug>` writes `<slug>-gNNN.zip` with a manifest of
SHA-256 checksums, a generation number and a lineage (the ids of the packs it
descends from). `lc unpack <zip>` restores it to `$LITCRITIC_HOME/<slug>`
(`--workspace` names another folder) only as a fast-forward: it refuses,
unless `--force`, an older zip, a zip from a line of work that went separate
ways from this workspace, or a newer zip when this workspace has changes that
were never packed. `--force` makes the workspace an exact copy of the zip.
Damaged zips, unsafe names and unsafe paths are always rejected, and files are
staged before the workspace is touched.

## Rules

- `lc init` refuses a workspace inside this repo's work tree.
- Fill `guard-terms.txt` as soon as character and place names are known; the
  repo's content guard reads it.
