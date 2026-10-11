# Analysis checklist

The generic catalogue of checks an assistant runs on a novel. It is a set of
lenses, not a formula: a per-novel **profile** (kept in the workspace) declares
the novel's traits and mode, and `lc checklist plan` selects and orders the
checks that apply.

## Working principles

1. **Evidence or it didn't happen.** Every finding cites anchors in the text.
   A check is not done because it was discussed; it is done when its evidence
   is recorded. Pending items stay pending and are resumed, not restarted.
2. **Big picture first.** Stages run in editorial order: orientation →
   developmental → scene → line → verification. Line-level polish on scenes
   that may be cut is wasted work.
3. **Strengths count.** `strength` checks record what works and what must be
   protected (voice, deliberate oddities, productive ambiguity). Feedback that
   only lists problems is incomplete, and fixes must not erase strengths.
4. **Lenses, not rules.** Frameworks (three-act, scene/sequel, etc.) are used
   only where they fit the novel's own design; a deliberate choice is not a
   defect. Distinguish error from licence from a character's belief.
5. **Every cut must earn itself.** A proposed cut states which redundancy it
   removes, which effect it keeps, and what else (motifs, setups, relations)
   it touches.
6. **The writer writes.** Checks produce diagnoses and options, never
   replacement prose.

## Files

| File | Content |
|------|---------|
| `areas/NN-<area>.toml` | One area with its checks |
| `traits.toml` | Novel traits that switch conditional checks on (`applies_when`) |
| `metrics.toml` | Script-measured metrics that checks consume |

## Area format

```toml
id = "architecture"            # area id; check ids are "<area>.<slug>"
title = "Global architecture"
stage = "developmental"        # orientation | developmental | scene | line | verification
order = 10                     # unique; working order inside the catalogue
purpose = "Why this area matters, in one paragraph."

[[check]]
id = "architecture.proportion"
title = "Proportion between parts"
question = "Does each part get space in proportion to its weight in the story?"
look_for = ["symptom a reader would notice", "..."]
method = "hybrid"              # script | llm | hybrid (script/hybrid must name metrics)
kind = "diagnostic"            # diagnostic (default) | inventory | strength
action_level = "structural"    # structural | scene | line | none  → revision round
inputs = ["L1", "structure", "metrics"]
metrics = ["words_per_chapter"]
measurable = true             # optional: a named Codex question measures it
codex_question = "chapter-lengths"   # required when measurable (see `lc codex questions`)
applies_when = []              # traits; empty = always applies
modes = ["revision", "reader-report"]   # default: both
evidence = "What must be cited for a finding."
severity = { high = "...", medium = "...", low = "..." }   # required for diagnostic
```

Inputs name index layers: `L0` profile and synopsis, `L1` chapter summaries,
`L2` scene cards, `L3` raw text, and the derived registers `structure`,
`characters`, `relationships`, `timeline`, `locations`, `motifs`, `ledger`
(setups and payoffs), `metrics`, `findings`, `backlog`.

Validate with `lc checklist validate`; see counts with `lc checklist stats`.
