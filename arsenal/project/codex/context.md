# codex: Context

The Codex is the per-work knowledge base: text spans of any length (kept in place
by paragraph address + offsets and a W3C text-quote selector), items in one
envelope with typed fields, links between items, a sync step that follows each
new draft and flags exactly what changed, and `lc codex check` against dead or
stale knowledge. Plain JSON/JSONL behind `codex.py` only; nothing stored that can
be recomputed. Modular by text kind (novel first, poem as proof). Works live in a
library under the home folder with unique ids. Stdlib only; no working-novel
content in the repo. Spec: arsenal/project/codex/spec.md (D-1..D-15).
