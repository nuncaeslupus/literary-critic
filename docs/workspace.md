# Workspace format

One workspace per novel. It is a plain folder **outside this repo** — by default
`$LITCRITIC_HOME/<slug>/` (`~/literary-critic/<slug>/` when unset). Recommended
place: a Google Drive folder (synced by Drive for desktop when working locally).

```
<slug>/
  workspace.toml        # title, language, mode (revision | reader-report), schema_version
  guard-terms.txt       # names that must never reach the tool repo
  manuscript/           # writer's originals, one snapshot per draft (v001.docx, v002.docx…)
  text/                 # normalised text per draft (v001.txt), one paragraph per line
  index/                # anchors, structure, scene cards, characters, timeline… (per draft)
  metrics/              # script-measured metrics per draft
  analysis/             # novel profile (adapted checklist) and findings
  revisions/            # round-NN/: editorial letter + action backlog with statuses
  log/                  # session log: what was done, decisions, next step
```

Everything is text (TOML, JSON, Markdown) except the manuscript snapshots, so a
workspace diffs cleanly and survives any sync tool.

## Moving a workspace between sessions

| Surface | Pattern |
|---------|---------|
| Claude Code, local | Point `LITCRITIC_HOME` at the Drive-synced folder. |
| Claude Code, cloud | Container is ephemeral: `lc pack` → zip the user keeps (or a private repo / Drive connector), `lc unpack` next time. |
| Chat with code execution | Upload kit zip + workspace zip; the assistant runs `lc`, then `lc pack` and returns the zip to download and store in Drive. |
| Chat without code | Upload the latest `index/` summaries and `log/`; reduced mode. |

`lc pack` / `lc unpack` (planned) carry a manifest with checksums so an older zip
never silently overwrites newer work.

## Rules

- `lc init` refuses a workspace inside this repo's work tree.
- Fill `guard-terms.txt` as soon as character and place names are known; the
  repo's content guard reads it.
