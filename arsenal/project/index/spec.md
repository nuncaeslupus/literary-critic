# Specification: a fast, token-lean literary index

**Date**: 2026-10-13
**Ticket / PR**: workspace `index`
**Author**: Claude (with the owner)
**Revision**: 2
**Status**: approved (2026-10-13, revision 2) — without annotations
**Revision log**:
- r1 — first draft, from the owner's request (2026-10-13): "be especially careful with the index part doc-control doesn't provide (references, etc.); build the part that may need an LLM and make it time and token efficient"
- r2 — owner approved Option B and the plan in advance (in conversation); dual-identity decision D-3 (owner confirmed: two linked entities); validation on the owner's manuscript with a stronger model as reference (D-4)

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<project>-spec-notes-<date>-r1.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

---

## 1. Problem statement

doc-control gives literary-critic the document layer: paragraphs, chapters,
scenes, dialogue lines, sentences, anchors, diffs. It will never give the
literary layer: who the characters, places, objects and motifs are, where each
is referenced (by name, alias, title or role), what happens in each scene, whose
viewpoint, where and when, what is set up and paid off. That layer is the
Codex, and today it is filled entirely by the LLM, one item at a time
(`prompts/20-codex-items.md`): read each scene through `lc show`, then one
`lc codex add` call per scene, entity or setup. On a real 74k-word manuscript
(157 scenes, ~106k tokens of text) that is the whole text through the chat
context plus 300+ tool calls with their echoes, in a context that keeps
growing, and hours of wall time. Much of it is deterministic work the LLM is
doing by hand (finding names, counting mentions, finding who speaks), against
rule 7. The index must cost little more than reading the text once, stay
bounded per step whatever the novel's length, use the cheapest model that is
accurate enough, and leave the LLM only the judgment calls.

**Success criteria (measurable)** — measured on both corpus texts, and on the
owner's manuscript locally (numbers only, never content):

- [ ] `llm_input_tokens_per_1k_text_tokens <= 1300` for a full first index (the text read once, plus at most 30 % overhead for instructions, candidate lists and ids).
- [ ] `llm_output_tokens_per_scene <= 250` (compact JSON, no echoes).
- [ ] `tool_calls_per_scene <= 0.2` (writes batched: one validated import per packet of scenes, not one call per item).
- [ ] `peak_context_tokens_per_step <= 12000` whatever the novel's length (each step is a bounded packet; nothing accumulates in one context).
- [ ] `entity_recall >= 0.95` and `entity_precision >= 0.95` for characters and places against a hand-made gold list for each corpus text; `alias_merge_errors == 0` on the gold list.
- [ ] `reference_recall >= 0.95`: every gold occurrence of a character (name, alias, title such as "the doctor") found by the deterministic mention index once the entity is known.
- [ ] `reindex_input_tokens <= 0.15 × first_index` after a new draft that changes ≤ 10 % of scenes (only changed scenes are re-read).
- [ ] `index_wall_seconds_100k_words <= 600` with packets run in parallel where the surface allows it (Claude Code, Cowork), and a sequential path for plain chats that keeps the same per-step bound.
- [ ] No step writes prose for the novel (rule 5) — judged by `lc codex check` refusing replacement prose fields and by review.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| New `litcritic/prepass.py` | Primary | Deterministic candidates: proper-noun and title candidates with counts and first quote, speaker attributions from dialogue tags, keyword-in-context snippets, scene stats | Yes (new) | Replaces work the LLM does by hand | High |
| New `litcritic/packets.py` + `lc index plan/packet/import` | Primary | Splits the work into bounded packets (entity resolution, scene batches), renders each as one prompt input, validates and imports the JSON answer in one call | Yes (new) | The token and tool-call savings | High |
| `codex.py`, `codex_cli.py` | Dependent | Batch import with all-or-nothing validation and quote anchoring | Yes | One write per packet | Med |
| `view.py` mentions/copresence | Dependent | Reference index from entity names, aliases and titles | Small | Titles/roles as aliases; per-scene counts | Med |
| `sync.py` | Dependent | Which scenes need a re-read after a new draft | Small | Re-index only changed scenes | Med |
| `prompts/20-codex-items.md`, SKILL.md | UI | What the LLM is told | Yes | Packet loop instead of item-by-item; model tier per step | Med |
| doc-control | Upstream | Paragraphs, scenes, dialogue lines, normalised text | No (consumer) | Dialogue and sentence segmentation come from doc-control (T43 ranges) once released | Low |
| Workspaces | Data | `codex/` items | No format change | Items stay the same envelope | Low |

Risk of inaction: High — indexing a real novel is the most expensive step of the
whole tool and the one writers hit first.

## 3. Options

### Option A: Batch writes only (Conservative)

- **Description**: keep the item-by-item reading, add `lc codex import` for a JSONL batch per scene.
- **Effort**: Small
- **Tradeoffs**: + cuts tool calls; − the LLM still finds names, counts and reads with no help; tokens unchanged; context still grows.
- **Compatibility**: full.

### Option B: Script-first pre-pass + bounded LLM packets (Recommended)

- **Description**:
  1. **Pre-pass (no LLM)**: candidates for entities (capitalised tokens never seen lower-case, multi-word names, honorific + name, role titles repeated with the definite article), each with count, first quote and 2–3 keyword-in-context snippets; speaker attributions from dialogue tags (doc-control dialogue lines + verbs of saying); per-scene stats.
  2. **Entity packet (one LLM call, cheap model)**: the candidate list with snippets (~3–5k tokens, never the full text) → entities with kind, canonical name, aliases (merging "Dr. X", "X", "the doctor"), and rejects. Import validates and anchors each entity on its first quote.
  3. **Reference index (no LLM)**: mentions of every entity by name, alias and title, per paragraph and scene, from the confirmed entities; co-presence follows.
  4. **Scene packets (cheap model, parallel)**: a few scenes per packet up to ~8k tokens of text, plus the entity id list and the scene's pre-pass facts (who is mentioned, who speaks); answer is compact JSON per scene (summary ≤ 80 words, pov, location, time, setups/payoffs by quote, new entities if any). One import per packet.
  5. **Synopsis and threads (stronger model, from items, not text)**: built from scene summaries only.
  6. **Re-index**: after a new draft, only scenes `sync` flags are packed again.
- **Effort**: Large
- **Tradeoffs**: + reads the text once, bounded per step, parallel, cheap model where it suffices, fewer and smaller calls; + every number above becomes measurable; − more scripts and a packet format to maintain.
- **Compatibility**: Codex format unchanged; the old item-by-item prompt stays usable for spot fixes.

### Option C: Embeddings / external NER

- **Description**: use an NER model or embeddings to find entities and references.
- **Effort**: Medium
- **Tradeoffs**: − breaks rule 9 (stdlib + doc-control) and the chat-sandbox story; − Spanish literary text (raya dialogue, nicknames) needs tuning anyway.
- **Compatibility**: new dependencies.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Large | Medium |
| Token saving | none | text read once, ~1.3× | similar to B |
| Tool calls | ↓ | ↓↓ | ↓ |
| Rule 7 / 9 fit | partial | full | breaks 9 |

## 4. Recommendation

**Recommended option**: Option B. It moves everything countable into scripts
(rule 7), bounds every LLM step so a 300k-word novel costs the same per step as
a short one, and lets cheap models do extraction while the stronger model only
reads summaries for synopsis, threads and checks.

**Immediate next action**: on approval, `design` splits it: pre-pass with a gold
list on the corpus first (it decides how much the LLM must do), then the packet
format and import, then the entity packet, reference index, scene packets,
re-index, prompts, and a cost-measurement harness that records tokens, calls
and wall time per run.

**Open questions**:
1. Model tiering is named per step in the prompts (e.g. "cheap model" = Haiku-class for packets 2 and 4, the session's model for 5). Default: name the tier, never a specific model id, so other chatbots can map it.
2. Gold lists for the corpus texts are hand-made once (characters, places, aliases, occurrence counts) and committed under `tests/fixtures/` — public domain only.

**Decisions log**

| # | Decision | Status | Date |
|---|----------|--------|------|
| D-1 | The literary index (entities, references, scenes, setups) is literary-critic's; generic segmentation and reading come from doc-control | agreed | 2026-10-13 |
| D-2 | Time and tokens are first-class gates for the index | agreed | 2026-10-13 |
| D-3 | One character under two names that the text keeps apart (e.g. Jekyll / Hyde) is two entities linked `same_as`; plain aliases stay in one entity | agreed (owner deferred to recommendation) | 2026-10-13 |
| D-4 | Every cheap-model step is first validated against a stronger model's output on the corpus and, locally, on the owner's manuscript (numbers only); a step stays on the cheap tier only where it agrees ≥ 0.9 | agreed | 2026-10-13 |
| D-5 | Option B approved; plan approved in advance | agreed | 2026-10-13 |
