# Release T14 — test run on a clean PC

Recorded 2026-10-17/18. Clean PC: Windows Sandbox on the owner's Windows 11 Pro
(never had Python, uv, doc-control or literary-critic), Claude desktop app signed
in, novel (the public-domain `corpus/` text, as `.docx`) in `Documents\Novela`.
The Sandbox cannot run Defender and has no Word, so the criteria that need them
are **unmeasured** here, not passed. Status: **not met** (install actions 4 > 3).

## §1 criteria

| Criterion | Target | Measured | Verdict |
|---|---|---|---|
| `install_actions_clean_pc` | ≤ 3 | 4 | not met |
| `security_detections` | 0 | — | unmeasured (no Defender in Sandbox) |
| `virustotal_detections_mcpb` | 0 | 0 / 65 (0.1.1, `release-probe.md`) | met |
| `manuscript_file_writes_by_server` | 0 | 0 in the run; sha256 unchanged after the commented copy | met (no Word: changes were never written) |
| `state_beside_novel` | 1.0 | working folder created in `<novel>/literary-critic/` | met (one layout only) |
| `cfa_fallback_correct` | 1.0 | — | unmeasured (no Defender in Sandbox) |
| `auto_update_applied_restarts` | ≤ 1 | 1 (0.1.6 → 0.1.7 in-app) | met |
| `writer_update_actions` | ≤ 3 | 3 (0.1.2 → 0.1.6 by hand) | met |
| work kept after update | yes | yes | met |

install_actions_clean_pc: 4
auto_update_applied_restarts: 1
writer_update_actions: 3

## Install (0.1.2)

Download the `.mcpb` from the release page (1), open Settings → Extensions and
drop it there (2), press *Instalar* on the install card (3), confirm the app's
own "¿Instalar extensión?" dialog (4). The red banner ("access to everything on
the computer; developer not verified") needs no click. Dropping the file on a
chat only attaches it (desktop Q-8), so the drop goes on the Extensions page.
The fourth action is the app's confirmation dialog, outside the bundle's
control; the criterion counts it.

The first chat found no novels, reported 0.1.2 as current and the update check
succeeded (the 0.1.2 Windows-TLS retry works on a fresh PC).

## Scripted session

Setup (add folder, three questions, resume), index (23 scenes), overview, full
reader report (~12 min, quotes spot-checked against the corpus text: 6/6
correct), one continuity change through the card, and the commented copy
(94 comments, text identical to the original, anchors 6/6 on the right
paragraph). Without Word, an approved change is recorded as typed by the writer
(the desktop surface writes only through Word), so writing is unmeasured here.

## Updates

| Run | What happened | Fixed in |
|---|---|---|
| 0.1.2 → 0.1.3 in-app | download failed: release assets live on another host whose root a fresh Windows lacks | 0.1.4 (PR 265) |
| 0.1.4 staging | `requirements.txt` had a literal `\n` on the wheel line, every release 0.1.0–0.1.4 | 0.1.5 (PR 266) |
| 0.1.2 → 0.1.6 by hand | download, drop, install: 3 actions, work kept | — |
| 0.1.6 → 0.1.7 in-app | staged, one restart, 0.1.7 runs | — |
| 0.1.7 staged | `resume` crashed: the wheel lacked prompts, schemas and checklist | 0.1.8 (PR 270) |

## Findings filed as follow-ups

- The setup questions: offer both report and aspects; who-writes wording
  (done in PR 271).
- Card approval also sends a chat message, which the app shows behind a
  caution banner; "Approved" shows twice; the status line is not localised.
- Indexing through a cloud helper asked the app for the novel's folder, which
  turned the chat into a task where cards do not render.
- Setup does not store the report/aspects answer, so it is asked again.
- A cached "no update" outlives a newer running version; the cache stays 24 h
  after a "no".
- Plain-words errors on the places card (`ENGINE_UNAVAILABLE`).
- Account memory from another PC reached tool calls (another work's name);
  the tool refused it.
