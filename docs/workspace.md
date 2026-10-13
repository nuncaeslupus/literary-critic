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
                        # + v001.meta.json: per-paragraph doc-control address (`at`), heading level,
                        #   centred, page, page break before, blank lines before, style name
  index/                # anchors, structure, alignment (per draft)
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

doc-control's `segment` finds the parts, chapters and scenes, each with a
stable id and the signals behind it (`stable_id` and `signals` in
`structure.json`): heading styles and outline levels, chapter words and
numerals ("Capítulo 3", "Prólogo"), a chapter-start paragraph style; ornament
lines ("* * *") start scenes. A plain-text draft has no styles, so a short line
with two or more extra blank lines above it is read as a heading. The kind of
text sets the detection settings. When it gets something wrong, put corrections
in `analysis/structure-overrides.json`, in doc-control's override shape: force or
deny a chapter or scene at a paragraph, named by its doc-control fingerprint
(`lc show <chapter> --fp`; `nth` picks one of several identical paragraphs):

```json
{"schema_version": 2, "overrides": [{"fp": "7d3684d2", "kind": "chapter", "action": "force"},
                                    {"fp": "a1b2c3d4", "kind": "scene", "action": "deny", "nth": 2}]}
```

An override whose paragraph no longer exists is reported by `lc anchor` (exit
1) and the others still apply. The first format (`chapter_starts`,
`not_chapter`, `scene_starts`, `not_scene` lists of 12-hex fingerprints) is still
read; there every fingerprint must match exactly one paragraph or nothing is
applied.

## Index pre-pass

`lc index prepass --workspace <slug> [--version vNNN] [--json]` (no LLM) writes
`index/work/prepass.json`: entity `candidates` (capitalised names outside
sentence starts, honorific + name, article + name, repeated role titles such as
"the lawyer"), each with its count, surface forms, first quote and up to two
keyword-in-context snippets; `speakers`, the speaker tags found in dialogue per
scene; `scenes`, with words, paragraph range and the candidates present; and
`render`, the candidate list as compact text for the entity packet (names seen
once are listed without context), kept under 10 % of the text's tokens by
default (`--budget` to change). Word lists are in
`src/litcritic/data/prepass_<lang>.toml`.

## Index packets

The LLM fills the Codex in bounded packets, each answered with JSON only:

- `lc index plan --workspace <slug> [--changed]` runs the pre-pass and writes
  `index/work/plan.json`: entity packets (the candidate list, most frequent names
  first, cut into self-contained packets of at most ~6k tokens that name each
  other's candidates) and scene packets (consecutive scenes up to ~8k tokens of
  text; a scene is never split unless it is over ~11k tokens, then it is cut at
  paragraph boundaries into parts). Each packet has an id (`e1`, `s001`…), a
  status (`todo`, `done`, `failed`) and its inputs. Re-planning keeps the status of
  packets whose inputs did not change; `--changed` packs only the scenes the last
  `lc codex sync` asks to re-read. Creates the Codex when there is none.
- `lc index packet <id>` prints one packet: instructions, the closed answer
  schema (`schemas/index-entities-answer.schema.json`,
  `schemas/index-scenes-answer.schema.json`) and the inputs, nothing else.
- `lc index import <id> --file answer.json` (`-` reads stdin) validates the
  answer, anchors every quote exactly in its scene (or the whole draft for an
  entity), and writes all of the packet's items in one Codex batch: one bad field
  refuses the whole answer and nothing is written. It prints one line,
  `ok <id>: N items` or `error <id>: <field path>: <reason>`. Entities whose name
  or alias matches a known entity add their forms to it as aliases; an entity
  without a quote is anchored on its candidate's first occurrence. `--next` prints
  the next packet after an `ok`, so a sequential run needs one call per packet.
  Raw answers are kept in `index/work/answers/<id>.json`.
- `lc index status` prints one line per packet and a count by status.
- Scene answers never create entities. Each scene may list `new_names` (at most
  8): proper names of people or places the text uses and its `known:` line lacks,
  never roles, relations or common nouns. Import queues them in `plan.json`
  (`new_names`, deduplicated, with the scenes where each was seen). The next
  `lc index plan` drops queued names the Codex already covers or the draft never
  uses and packs the rest into one small entities packet on the strong tier
  (`n1`: each name with its count in the draft and up to two contexts); importing
  it clears those names from the queue. An answer that still carries a scene
  `entities` field is refused naming it.
- Scene `time` is when the scene's main action happens (not an opening frame,
  memory or dream unless that is the scene); `location` is where it happens (not
  where a character lives or comes from).

## Comparing drafts

`lc diff v001 v002 --workspace <slug>` (both drafts anchored) writes
`index/v002/alignment.json`: for every old paragraph its status — unchanged,
moved, modified (with similarity), split, merged or deleted — and its new
anchors; the inserted paragraphs; and `stale_scenes`, the new scenes whose text
changed. `lc codex sync` uses it to move the Codex to the new draft.

## Metrics

`lc metrics --workspace <slug>` writes `metrics/vNNN.json` with every metric in
`checklist/metrics.toml` that the script implements: lengths, sentence and
paragraph statistics, readability (Fernández-Huerta and Szigriszt/INFLESZ for
Spanish, Flesch for English — relative gauges only), dialogue, word choice,
names, proofreading signals. Items carry anchors.

Some metrics aggregate what the LLM records and report `unmeasured` until
that input exists:

| Input | Path | Used by |
|-------|------|---------|
| Codex items (synced to the draft) | `entity` (kind `character` or `motif`), `setup` (payoffs link with `pays_off`), `scene` | characters, motifs, setups/threads, POV distribution |
| Labels | `analysis/labels.json`: `chapter_endings` {chapter id: type}, `summary_passages` [anchors], `climax` anchor, `opening_hook` anchor | chapter endings, scene/summary ratio, dénouement share, opening hook |

## Index and queries

The LLM records scenes, characters, places, motifs and setups as Codex items
(`prompts/20-codex-items.md`) and writes the synopsis into
`analysis/synopsis.md`.

Queries print at most `--budget` tokens (default 2000) and say how to continue:

| Command | Shows |
|---------|-------|
| `lc show` | table of contents: chapter, words, scenes, title |
| `lc show c03` / `c03.s2` / `c03.s2.p4` | that text, one anchored paragraph per line (`--fp` adds fingerprints for overrides) |
| `lc show c03.s2.p17-` | continue reading from that paragraph |
| `lc find <words>` / `"<phrase>"` `[--in c03]` | matching paragraphs, accent-blind, with snippets |
| `lc context c03.s2.p4` | chapter, Codex scene, the paragraph and its neighbours |

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
