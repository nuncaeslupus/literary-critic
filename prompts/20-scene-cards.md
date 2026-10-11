# Write scene cards (L2)

One card per scene, written by you, checked by script. Cards are what most
checks read instead of the text, so they must be accurate and consistent.

## For each scene

1. Read it: `lc show c03.s2 --workspace <slug> --budget 3000`
   (if it is cut, run the continuation command printed on its last line).
2. Write the card in `<ws>/index/<version>/scene_cards.json` (a JSON list, one
   object per scene):

   ```json
   {
     "schema_version": 1,
     "anchor": "c03.s2",
     "summary": "What happens, in at most 80 words.",
     "pov": "Viewpoint character, or 'omniscient' / 'none'",
     "characters": ["Everyone present or acting, by their usual name"],
     "location": "Where",
     "story_time": "When, as precise as the text allows (Day 3, evening)",
     "events": ["Each thing that changes, in order"],
     "setups": ["short label of something planted for later"],
     "payoffs": ["the same short label when it pays off"],
     "open_threads": ["questions the scene leaves open"],
     "notes": "Anything odd: a slip, a strength, an ambiguity"
   }
   ```

## Consistency rules

- Use one name per character across all cards (the most usual one); the
  register merges only case and accent differences.
- Reuse the exact **same short label** for a setup and its payoff, so the
  script can pair them ("the locked drawer", not a new phrase each time).
- Report what the text says, not what you expect; mark uncertainty in `notes`.
- Never put replacement prose in a card.

## After a batch of cards

Validate and build the registers:
`lc validate scene-card <ws>/index/<version>/scene_cards.json` and
`lc index --workspace <slug>`. Fix every reported error before going on.
