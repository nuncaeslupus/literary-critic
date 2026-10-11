# Handover

**Last session (2026-10-10/11, overnight, autonomous):** the whole plan (T1–T15) is implemented and merged, one PR per task, each with its own review (CodeRabbit was rate-limited, so `code-review` ran on every PR and its findings were fixed before merge).

- Tool surface: `lc init / ingest / anchor / diff / metrics / index / show / find / context / locate / round / docx-comments / report / validate / checklist / pack / unpack / kit / doctor / corpus / synth / guard`. Procedures in `prompts/`, Claude Code skill `.claude/skills/litcritic`.
- Gates: all in `status/evidence/`; plan evidence log updated.
- A working novel is in progress; its details stay in local, git-ignored notes. Keep its terms in a local, git-ignored `.litcritic-guard-terms` (recreate in a fresh container) or in the workspace `guard-terms.txt`; never commit novel content. Evidence files and PR texts must not describe it (rule 1) — say "a private working draft".
- Environment notes: gutenberg.org is blocked by the proxy (GITenberg mirror on raw.githubusercontent.com works); GitHub REST token cannot create refs (use the MCP `create_branch` for claims); CodeRabbit free tier rate-limits after ~1 review/hour.
- Arsenal issues filed: nuncaeslupus/claude-arsenal #500–#503.
- Next: real use on the working novel (orientation → scene cards → checks → round 1), driven by the writer; then a retrospective (spec success criterion: usability on the first working novel).
