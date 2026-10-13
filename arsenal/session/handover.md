# Handover

**Last session (2026-10-13):** workspace `doccontrol` — literary-critic moves every document read/write onto the PyPI package doc-control (spec r2 and plan r2 approved; D-1…D-8).

- **Merged:** spec/plan/tasks (#81), T1 adapter `dc.py` (#95), claude-arsenal 5.9.1 (#96), T11 kit bundles doc-control (#97), T3 comments via `batch` (#98), T4 `convert.py` (#99), T2 `lc docx edits|rename|status|undo` on doc-control, `safe_edit.py`/`docx_edit.py` deleted (#100).
- **Blocked upstream (doc-control session `session_01VhMKAsUrRXQ8Mo467qkQCh`, accepted):** T39 `api.open(path)` handle with uncapped bulk `paragraphs()` → unblocks T5; T40 parts / front / chapter-from-style → unblocks T6. Then T7–T10, T12, T13 follow the plan.
- **Also requested of doc-control (with gates):** exact anchors on normalised text (today a quote across a soft hyphen/tab/double space is refused by `lc docx edits`), LibreOffice lock files, `term.rename` skipped locations, caller-chosen backup store (backups now sit in `.doc-control/` beside the manuscript), perf budgets, `page.estimate` over-count vs rendered breaks, multi-paragraph ranges for dialogue/sentences, `find` total.
- **Owner's instructions:** be demanding with doc-control (fast, reliable, efficient, useful); send it every need found while analysing the novel; never build doc-control-owned features here; `lc upgrade` (T10) is tested on a copy only.
- **Owner's manuscript:** local, git-ignored copy only; its names are in the local guard terms. Never commit or mention its content.
- **Arsenal issues filed:** claude-arsenal#514 (drawspec from PyPI), #515 (plan graph vs drawspec edge budget — the doccontrol plan reader can't be regenerated until fixed).
- Environment: REST token can't create refs (claims via MCP `create_branch`); force-push is blocked, so restart a merged branch with `git merge -s ours` instead.
