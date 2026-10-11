# Specification notes

_Exported 2026-10-11 · 3 notes._

> Send this file back to continue the review. Notes are embedded as data at the bottom
> so importing this file restores them in the reader.

## Spec

**§1 Problem statement**  `SPEC §1`
> We need to upgrade phase 1 now  but we don't need a converter. It's only for current examples, no novel has been analyzed yet.

**§2 Systems & Impact**  `SPEC §2`
> Remember to create skills with skill-workshop.
> Phase 1 old docs can be deleted. Maybe it's better to redo the job rather than use them.

**Option B: Codex core with typed items, spans and sync (Recommended)**  `SPEC › Option B: Codex core with typed items, spans and sync (Recommended)`
> No need to keep old material. When we use a real novel, we may find new data types or needs, that's why we'll create the tool from an example. At the end  I want to be able to ask things like " in how many chapters this character says something?" Or "am I abusing of this expression?" Or "which character has more relevance for this other character?" Or "is every sub story continuously narrated or there are gaps?"... That kind of things. Còdex must be a tool to help answering questions. We could predefined some of these questions so feedback for the writer is proactive. Our checks should be able to be translated to a query to codex. It should work as a database and the LLM will translate the question to our special "SQL", which should be some kind of API.

<!-- SPEC-NOTES-DATA
{"s-spec-1":"We need to upgrade phase 1 now  but we don't need a converter. It's only for current examples, no novel has been analyzed yet.","s-spec-2":"Remember to create skills with skill-workshop.\nPhase 1 old docs can be deleted. Maybe it's better to redo the job rather than use them.","s-spec-option-b-codex-core-with-typed-i":"No need to keep old material. When we use a real novel, we may find new data types or needs, that's why we'll create the tool from an example. At the end  I want to be able to ask things like \" in how many chapters this character says something?\" Or \"am I abusing of this expression?\" Or \"which character has more relevance for this other character?\" Or \"is every sub story continuously narrated or there are gaps?\"... That kind of things. Còdex must be a tool to help answering questions. We could predefined some of these questions so feedback for the writer is proactive. Our checks should be able to be translated to a query to codex. It should work as a database and the LLM will translate the question to our special \"SQL\", which should be some kind of API."}
-->