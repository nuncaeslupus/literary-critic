---
id: t-d0b8bc39
title: "T7: Prompts for the plan and the cards"
label: "prompts for plan and cards"
priority: 5
deps: [t-94f4925f]
workspace: workplan
status: merged
---

## Acceptance gate

`assistant_wording_accepted_when_prose_off == 0` (plan: `arsenal/project/workplan/plan.md` T7; details there under Task details).

```bash
uv run pytest -q tests/test_prompts.py -k "test_guide_tells_writer_moves_need_writer_word or test_cards_prompt_respects_prose_setting"
```

## Tests

- `test_guide_tells_writer_moves_need_writer_word` in `tests/test_prompts.py` — the guide says a writer move needs the writer's word and reason; `test_cards_prompt_respects_prose_setting` — the prompts say cards with the assistant's wording only under `minor` or on, and name each surface's buttons

## Location

`prompts/00-guide.md`, `05-setup.md`, `60-rounds.md`, `80-live-word.md`, `01-chat-guide.md`
