---
id: t-dfcab048
title: "C5: named questions"
label: "named questions"
priority: 5
deps: [t-c05a183b, t-dbfae825]
workspace: codex
status: merged
---

# C5: Fixture Codex for a corpus text, hand-written items for entities, dialogue speakers, threads and setups; named questions engine and the first 20 questions; `lc codex ask/questions`

## Acceptance gate
Gate: `example_questions_answered == 1.0` (spec: arsenal/project/codex/spec.md, plan: arsenal/project/codex/plan.md)

```bash
uv run pytest tests/test_questions.py -q -k "test_example_question_families_on_fixture"
```

## Tests
`test_example_question_families_on_fixture` in `tests/test_questions.py` — speech per chapter, expression use, relevance between characters and subplot gaps give the expected answers

## Location
lc
