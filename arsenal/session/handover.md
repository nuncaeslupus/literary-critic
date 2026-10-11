# Handover

**Last session (2026-10-11):** phase 2 core — the Codex (workspace `arsenal/project/codex/`, tasks C1–C13) — is implemented and merged, one PR per task, each reviewed with `code-review` and every finding fixed before merge. No open `arsenal:task` issues remain.

- The Codex: typed items on text spans (`docs/codex/README.md`), `lc codex init|add|update|retire|show|find|sql|ask|questions|sync|check`, named questions in `src/litcritic/questions/`, kinds (novel, poem), library of works.
- Phase-1 formats are gone (scene cards, summaries, registers, findings/actions files, `lc index`); rounds, letters, Word comments, report and metrics read Codex items.
- Prompts rewritten around the Codex (`20-codex-items`, `35-ask`, …); skill `.claude/skills/litcritic` passes skill-workshop (`validate.py`, from nuncaeslupus/claude-arsenal `plugins/skill-workshop`, is not installed in the container: clone it to run it).
- Gates and evidence: `arsenal/project/codex/plan.md` evidence log; usability review in `status/evidence/C13-usability.md` (6/6).
- Known flake: `tests/test_view.py::test_view_load_time_20k_items` can exceed 1 s on a loaded machine (passed alone at ~0.5 s).
- A working novel is in progress; its details stay in local, git-ignored notes and the workspace `guard-terms.txt`; never commit novel content.
- Environment notes: GitHub REST token cannot create refs (use the MCP `create_branch` for claims); CodeRabbit rate-limits.
- Next: real use on the working novel through the Codex (orientation → record items → checks → round 1), driven by the writer; then the ideas backlog in `status/ideas.md` (report from general to specific, session flow, …).
