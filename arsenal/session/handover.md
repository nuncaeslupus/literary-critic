# Handover

**Last session (2026-10-13):** workspaces `doccontrol` (literary-critic on doc-control) and `index` (token-lean literary index).

- **index — done:** T1–T7 merged (#111–#116, #117 new-names fix, #118 prompts). Loop: `lc index plan` → entity packets (strong) → scene packets (standard, parallel answers, sequential imports) → `n1` new-names packet (strong) → done. Owner-manuscript run: 1,289 input tokens per 1k text tokens, 144 output tokens per scene, 0.22 calls per scene (0.12 chained). Cheap tier failed D-4 (≤ 0.8 agreement with strong on entities; omitted fields on scenes).
- **doccontrol — blocked upstream:** T5 (#110, ingest via doc-control) waits on doc-control 0.2.0 on PyPI, which needs the owner's approval of doc-control's `pypi` environment. Then: switch the git pin to the release, re-tighten the page assertion in the fixture test, merge; T6–T13 per plan.
- **doc-control (session `session_01VhMKAsUrRXQ8Mo467qkQCh`):** T39–T48 done or in CI (handle API, structure, perf ~1.05 s cold read, page counting fixed). Keep sending it needs found on the novel.
- **Owner's manuscript:** local git-ignored copy only; names in the local guard terms. Never commit or mention its content.
- **Arsenal issues filed:** claude-arsenal#514 (drawspec from PyPI), #515 (plan graph vs drawspec edge budget).
- Environment: REST token can't create refs (claims via MCP `create_branch`); force-push is blocked (restart a merged branch with `git merge -s ours`).
