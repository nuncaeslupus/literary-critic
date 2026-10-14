# Handover

**Last session (2026-10-14, day):** install workspace — spec and plan approved; T1 version stamp (#158), T5 owner hand tests (#159, `status/evidence/install-Q1-Q3.md`), T3 live-first locate (#160), T2 update check (#162), T4 prompts (#163) merged.

- **Blocked:** T6 one-click offer (#156) waits on doc-control's one-click bundle (Q-2); its claim ref `arsenal/claims/t-a65ebe58` is stale (released on the issue). T7 walkthrough (#157) needs T6 and the owner on Windows and a Mac.
- **Tell doc-control (owner relays; no peer session reachable):** `live.select` should bring the app window to the front; a find phrase starting with `--` should match the writer's text; one-click bundle (Q-2).
- **Not done:** `SKILL.md` "Running the tool" does not mention the update check or `l1` yet (skill edits need skill-creator loaded).
- Cloud surface: force-push is refused; restart this branch from main with `git merge -s ours origin/<branch>`. `open_task_pr.sh` needs `ARSENAL_ALLOW_SHARED_ADD=1` here and runs the full suite (~3 min, run it in the background).

**Last session (2026-10-14, overnight, unattended):** PR #145 (open, watched) fixes #138–#141 from the Cowork run: `speech` table for dialogue-share (#139), no redundant entity packet on re-plan (#140), links packet `l1` for payoffs parallel scene packets left unlinked (#141), hard-wrapped file warning at ingest (#138). Also a draft spec `arsenal/project/install/spec.md` (writer install, live Word, updates; open Q-1..Q-5) and feature ideas H1–H16 in `status/ideas.md`.

- **Not done:** `.claude/skills/litcritic/SKILL.md` does not mention `l1` yet (editing a skill needs skill-workshop/skill-creator loaded); `prompts/20-codex-items.md` covers it.
- **Owner to decide:** the install spec's open questions; which H-ideas first.

**Last session (2026-10-13, evening):** the owner ran the tool as a writer in Cowork (paid plan) on the corpus novel; record in `status/evidence/W9-walkthrough.md`, "Owner's run in Cowork".

- **Merged:** #136 (the full experience needs a paid plan), #137 (say when a step takes a while), #142 (no tool talk to a writer unless asked with `[[...]]`), #143 (doc-control 0.6: live engine with a Word adapter, `live` extra).
- **Next step, waiting on the owner:** add doc-control's MCP server to the Claude desktop app (Settings → Developer → Edit Config; `mcpServers` → `doc-control`: `uvx --from "doc-control[live]" doc-control mcp`), restart the app, and in Cowork ask for `live_select` on a document open in Word. The assistant may not edit that config itself (refused). The question is whether a Cowork conversation can call a host MCP server; Cowork's own commands run in a sandbox and cannot reach Word.
- **Then:** tell the doc-control session the result (it waits for it before building the one-click writer install); make "take me there" use `live_select` first with the computer-use steps as fallback (`prompts/80-live-word.md`, `src/litcritic/word_live.py`, `SKILL.md`). Measured on the host: `doc-control live.select --json '{...}'` selects the paragraph in an open Word in about 2.5 s; locate by computer use took 30 s and about 15 steps.
- **Open from the Cowork run:** replies run well over 120 words; no check that an uploaded Skill is out of date; whether a Cowork project keeps the novel's folder across conversations (if so, say it in `prompts/05-setup.md`); issues #138–#141 (opened from that run, generic, not triaged; #138 comes from this project's own test `.docx` having one paragraph per line); the desktop app leaves its window always on top after computer use (the app's fault, not fixable from a prompt).
- **doc-control CLI:** requests go as `doc-control <op> --json '<request>'`.

**Earlier the same day (Windows 11 Pro with Word 16.0.17932 in Spanish):** first run on Windows; hand tests against real Word.

- **Windows — done:** the suite passes on Windows and CI has a `windows` job (#129: LF on every checkout, Codex change log written once per batch, `lc` reads and prints UTF-8, portable tests). `lc word` uses keys that mean the same in every Word for Windows (#131): in a Spanish Word Ctrl+F indents, Ctrl+S underlines and Ctrl+W resets the paragraph; save is Shift+F12, close is Ctrl+F4, Find is named by language (Ctrl+B in Spanish).
- **Hand tests run** (`status/evidence/W9-walkthrough.md`): tracked change by `literary-critic` seen by Word and undone by Reject All; edit refused while Word has the file open, nothing lost; Word's Find lands on the right paragraph for 100 of 100 `lc docx locate` Find strings. Word was driven through its automation interface (COM), on the corpus novel saved by Word as `.docx`.
- **Hand tests still open:** ten located actions with computer use on Windows (`live_locate_success`; needs a session with computer use and the owner's own documents closed), the same on a Mac, D-18 (Skills on each plan), D-7 path B, the Cowork main path.
- **Soft hyphens in Find strings (doc-control's, reported with a reproduction):** `^-` matches Word's typed optional hyphen (char 31) but not a literal U+00AD (char 173, what pasted text keeps), which needs `^u173`. It only bites when the shortest unique phrase must include that word; the plain locator is the fallback.
- **Keyboard-driven locate was not run:** sending keys to a foreground Word by script was refused by the session's safety check while the owner had a document open. doc-control 0.4.1 still lists only the `file` engine, so `lc word` keeps giving steps.
- **Windows working notes:** the repo's hooks need a real `python3` (Microsoft Store Python works; without it the edit gate refuses every write). With PowerShell 5.1, capture `lc` output through a UTF-8 file, not a pipe. PowerShell's COM binder needs `[ref]` on `Close` and `Quit`; a failed `Quit` leaves a windowless Word behind.

**Earlier (2026-10-13):** workspaces `doccontrol` (literary-critic on doc-control) and `index` (token-lean literary index).

- **index — done:** T1–T7 merged (#111–#116, #117 new-names fix, #118 prompts). Loop: `lc index plan` → entity packets (strong) → scene packets (standard, parallel answers, sequential imports) → `n1` new-names packet (strong) → done. Owner-manuscript run: 1,289 input tokens per 1k text tokens, 144 output tokens per scene, 0.22 calls per scene (0.12 chained). Cheap tier failed D-4 (≤ 0.8 agreement with strong on entities; omitted fields on scenes).
- **doccontrol — done:** T1–T13 (#95–#100, #110, #119–#125), signed off by the owner (#126); doc-control 0.4.1 (#127, #128). doc-control is the document layer; only `dc.py` imports it, only `convert.py` writes Word parts (`docs/architecture.md`).
- **Open doc-control asks:** find phrases that cross mark boundaries; range phrases; `find_phrase_word`; in-memory open; live engine (pending the owner).
- **doc-control:** its own session on the same Windows machine ran its real-Word tests there (doc-control#136). Keep sending it needs found on the novel.
- **Owner's manuscript:** local git-ignored copy only; names in the local guard terms. Never commit or mention its content.
- **Arsenal issues filed:** claude-arsenal#514 (drawspec from PyPI), #515 (plan graph vs drawspec edge budget).
- Environment: on the cloud surface the REST token can't create refs (claims via MCP `create_branch`) and force-push is blocked (restart a merged branch with `git merge -s ours`); auto-merge is off for this repository.
