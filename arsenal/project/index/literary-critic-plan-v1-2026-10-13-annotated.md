# Literary Critic — Plan (annotated edition)

> Generated 2026-10-13. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Plan

## Preamble & scope

**Date**: 2026-10-13
**Specification**: `arsenal/project/index/spec.md` (approved, revision 2)
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: approved (2026-10-13, revision 1) — without annotations (approved in advance by the owner)
**Revision log**:
- r1 — first draft, approved in advance

> Review record, kept the way the spec keeps its own.

<!-- -->

> **✎ Notes** · `PLAN · intro`
> _(your notes here — replace this line)_

## Technical solution

### Architecture overview

Scripts do everything countable; the LLM gets bounded packets and answers in compact JSON
that one command validates and imports.

```drawspec
{"version": 1, "kind": "flow",
 "nodes": [
  {"id": "txt", "text": "text/vNNN.txt\n+ structure", "role": "start"},
  {"id": "pre", "text": "prepass\n(candidates, KWIC,\nspeaker tags)"},
  {"id": "ent", "text": "entity packet\n(cheap model)"},
  {"id": "ref", "text": "reference index\n(mentions, script)"},
  {"id": "scn", "text": "scene packets\n(cheap model, parallel)"},
  {"id": "imp", "text": "lc index import\n(validate + anchor)"},
  {"id": "cx", "text": "Codex"},
  {"id": "syn", "text": "synopsis, threads\n(stronger model,\nfrom items)"}
 ],
 "edges": [
  {"from": "txt", "to": "pre"}, {"from": "pre", "to": "ent"}, {"from": "ent", "to": "imp"},
  {"from": "imp", "to": "cx"}, {"from": "cx", "to": "ref"}, {"from": "ref", "to": "scn"},
  {"from": "scn", "to": "imp"}, {"from": "cx", "to": "syn"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Architecture overview`
> _(your notes here — replace this line)_

### Data flow

1. `lc index plan` runs the pre-pass and writes `<ws>/index/work/plan.json`: the packet list (one entity packet; scene packets of ≤ 8k text tokens; split points at scene boundaries), each with an id and a status.
2. `lc index packet <id>` prints one packet: instructions, the closed JSON answer schema, the inputs (candidates with snippets, or scene text with entity ids, mentions and speaker tags). Nothing else enters the LLM's context.
3. The LLM answers with JSON only; `lc index import <id> --file answer.json` validates against the schema, anchors every quote exactly, writes all items in one Codex batch (all or nothing), marks the packet done and prints a one-line result.
4. Mentions and co-presence are rebuilt from the Codex entities (names, aliases, titles); scene packets carry them so the LLM need not find names.
5. After `lc codex sync`, `lc index plan --changed` packs only the scenes flagged for re-reading.
6. `lc index cost` reports tokens in/out (chars/4 estimate or recorded counts), calls and wall time per packet and in total.

<!-- -->

> **✎ Notes** · `PLAN › Data flow`
> _(your notes here — replace this line)_

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| Workspace | `index/work/plan.json`, `index/work/answers/` | CREATE | packet list, statuses, raw answers kept for audit |
| Workspace | `codex/items/*` | UPDATE | items written in batches; envelope unchanged |
| Codex types | `entity.toml` | UPDATE | `titles` field (role titles used as names), `same_as` link (D-3) |

<!-- -->

> **✎ Notes** · `PLAN › State changes`
> _(your notes here — replace this line)_

### Technology choices

| Choice | Justification |
|--------|--------------|
| Stdlib heuristics for candidates (capitalisation outside sentence starts, honorific + name, repeated article + role noun, dialogue tags) | Rule 7/9; the probe reached entity recall 0.92–1.00 at ~10 % of text tokens |
| Closed JSON answer schemas validated by `validate.py` | Cheap models stay on rails; invalid answers are refused, not repaired by hand |
| Model tiers named, not ids (`cheap`, `strong`) | Portable across chatbots |

<!-- -->

> **✎ Notes** · `PLAN › Technology choices`
> _(your notes here — replace this line)_

### Out of scope

- Document reading, segmentation, dialogue detection: doc-control (its T43 ranges improve speaker tags when released).
- Checks and letters (they consume the Codex; unchanged here).

<!-- -->

> **✎ Notes** · `PLAN › Out of scope`
> _(your notes here — replace this line)_

## Implementation tasks

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | `prepass.py` + `lc index prepass`: entity candidates (count, first quote, ≤ 2 KWIC snippets), role titles, speaker tags, per-scene stats; corpus gold lists in `tests/fixtures/gold/` | prepass | M | — | `candidate_entity_recall >= 0.92` | `test_prepass_recall_on_gold` in `tests/test_prepass.py` — every gold entity of both corpus texts but at most 8 % is reached by some candidate; `test_candidate_list_tokens_bounded` — the rendered list is ≤ 12 % of the text's tokens |
| T2 | Packet engine: `lc index plan/packet/import/status`, answer schemas, one all-or-nothing Codex batch per packet with exact quote anchoring | packets | L | T1 | `tool_calls_per_scene <= 0.2` | `test_import_is_all_or_nothing` in `tests/test_index.py` — one bad item rejects the whole answer and writes nothing; `test_scene_packets_bounded` — no packet exceeds 12k tokens on a 300k-word synthetic book |
| T3 | Entity packet and reference index: `titles` + `same_as` in the entity type, mentions by name/alias/title per paragraph and scene | entities | M | T2 | `reference_recall >= 0.95` | `test_reference_recall_on_gold` in `tests/test_index.py` — with the gold entities imported, mentions find ≥ 95 % of gold occurrences in both corpus texts |
| T4 | Scene packets: compact answer (summary ≤ 80 words, pov, location, time, setups by quote, new entities), mentions and speaker tags as inputs | scenes | M | T3 | `llm_output_tokens_per_scene <= 250` | `test_scene_answer_schema_caps_lengths` in `tests/test_index.py` — answers over the caps are refused with the field named |
| T5 | Evaluation harness `lc index eval` + cost meter; cheap vs strong comparison on corpus and, locally, on the owner's manuscript (numbers only) | eval | M | T4 | `entity_f1_cheap_vs_gold >= 0.95` | `test_eval_scores_against_gold` in `tests/test_eval.py` — a recorded answer set scores exactly the expected precision/recall |
| T6 | Re-index after a new draft: `lc index plan --changed` packs only re-read scenes | reindex | S | T4 | `reindex_input_tokens_ratio <= 0.15` | `test_reindex_packs_only_changed_scenes` in `tests/test_index.py` — a draft changing 2 of 20 scenes yields packets for those 2 only |
| T7 | Prompts and SKILL.md: packet loop, model tiers, parallel where the surface allows; old item-by-item prompt kept for spot fixes | prompts | S | T5 | `prompts_reference_valid_commands == 1.0` | `test_prompts_name_only_lc_commands` in `tests/test_prompts.py` — every `lc` command the prompts name exists |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1 → T2 → T3 → T4 → (T5, T6) → T7
**Branch pattern**: `claude/focused-hopper-0nq71a-idx-t<N>` from the default branch

<!-- -->

> **✎ Notes** · `PLAN › Implementation tasks`
> _(your notes here — replace this line)_

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|

<!-- -->

> **✎ Notes** · `PLAN › Evidence log`
> _(your notes here — replace this line)_

### Dependency graph

```drawspec
{"version": 1, "kind": "flow", "title": "Task dependencies",
 "nodes": [
  {"id": "T1", "text": "T1\nprepass.py + lc index prepass: enti…"},
  {"id": "T2", "text": "T2\nPacket engine: lc index plan/packet…"},
  {"id": "T3", "text": "T3\nEntity packet and reference index:…"},
  {"id": "T4", "text": "T4\nScene packets: compact answer (summ…"},
  {"id": "T5", "text": "T5\nEvaluation harness lc index eval +…"},
  {"id": "T6", "text": "T6\nRe-index after a new draft: lc inde…"},
  {"id": "T7", "text": "T7\nPrompts and SKILL.md: packet loop,…"}
 ],
 "edges": [
  {"from": "T1", "to": "T2"},
  {"from": "T2", "to": "T3"},
  {"from": "T3", "to": "T4"},
  {"from": "T4", "to": "T5"},
  {"from": "T4", "to": "T6"},
  {"from": "T5", "to": "T7"}
 ]}
```

<!-- -->

> **✎ Notes** · `PLAN › Dependency graph`
> _(your notes here — replace this line)_

## Sign-off

- [x] Approved by the owner (in advance)
- [ ] Cheap-model steps validated against the strong model on the owner's manuscript (T5)

<!-- -->

> **✎ Notes** · `PLAN › Sign-off`
> _(your notes here — replace this line)_

