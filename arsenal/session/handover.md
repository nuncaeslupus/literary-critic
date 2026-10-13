# Handover

**Last session (2026-10-13, Windows 11 Pro with Word 16.0.17932 in Spanish):** first run on Windows; hand tests against real Word.

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
