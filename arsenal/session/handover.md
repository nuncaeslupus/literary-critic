# Handover

**Last session (2026-10-12):** the chat workspace (`arsenal/project/chat/`, tasks W1–W9) is implemented and merged, one PR per task (#70–#78), each reviewed with `code-review` and every finding fixed before merge. No open `arsenal:task` issues remain.

- **Safe in-place editing:** `docx_edit` (tracked revisions by quote plus context; never across fields or hyperlinks) and `safe_edit` (locks, on-disk change, backup, verify, restore). CLI: `lc docx edits|rename|locate|status`; `locate` gives Word's unique Find string.
- **Setup:** `lc setup --folder` finds the manuscript and versions and creates `<folder>/literary-critic/`. Options: `--manuscript` (the writer's choice, remembered), `--edit-in-place yes|no`, `--prose-suggestions on --ack-ai-notice` (D-22; off by default; rule 5 reworded).
- **Live Word:** `word_live.py`, `lc word`, `docs/word-control-interface.md`. Today it gives computer-use steps; `$LITCRITIC_WORD_CONTROL` will plug in the Word-control extension (separate repo).
- **Prompts:** `05-setup` (wizard), `00-guide` (a plan the writer accepts, changes or rejects), `60-rounds` (approved edits via `lc docx`), `80-live-word`. SKILL.md is the chat entry; `lc kit --skill` builds the Skill zip.
- **Python 3.11** is now the floor (claude.ai sandbox), with a CI job.
- **Waiting on the owner:** the hand-test checklists in `status/evidence/W9-walkthrough.md` (D-18 Skills per plan, D-7 pip from GitHub, Cowork main path, computer-use locate 10× on Windows and Mac).
- Known flake: `tests/test_view.py::test_view_load_time_20k_items` can exceed 1 s on a loaded machine.
- A working novel is in progress; its details stay in local, git-ignored notes and the workspace `guard-terms.txt`; never commit novel content.
- Environment notes: GitHub REST token cannot create refs (use the MCP `create_branch` for claims); CodeRabbit rate-limits.
- Next: the owner's hand tests; then real use on the working novel through the chat flow; the Word-control project can take `docs/word-control-interface.md` as its contract.
