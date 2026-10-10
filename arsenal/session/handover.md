# Handover

**Last session (2026-10-10):** bootstrap + part 2 merged (PR #1); T3 corpus in PR (branch `ccr-c4be7103-q30ya0`).

- Done: arsenal base, AGENTS.md rules, `lc init/guard/checklist`, spec r2 approved, plan (T1–T15), checklist 23 areas / 201 checks after critical pass, Apache-2.0.
- T3: `corpus/marianela` (es) and `corpus/jekyll-hyde` (en) with `source.toml`; `lc corpus check`, `lc synth`. gutenberg.org is blocked by the proxy; `raw.githubusercontent.com/GITenberg/<Title>_<id>/master/<id>-8.txt` works.
- Next: T4 ingest, T5 anchors, T6 diff. Seed arsenal tasks from `status/plan.md` if the queue is empty.
- Working novel: Spanish. The user will share it after indexing tools exist. Keep its terms in a local, git-ignored `.litcritic-guard-terms` (recreate in a fresh container) or in the workspace `guard-terms.txt`; never commit novel content.
- CodeRabbit does not review this repo reliably (free-tier limits); use own review (`code-review` skill).
