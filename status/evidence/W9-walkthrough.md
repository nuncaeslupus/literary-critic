# W9: scripted usability walkthrough (chat workspace)

**Gate:** `writer_setup_actions <= 5`. Also: the median writer-facing reply is
at most 120 words, every place is located, and there is one step at a time.
`tests/test_walkthrough.py` checks this file.

**Method.** An assistant follows the procedures as written (`SKILL.md`,
`prompts/05-setup.md`, `00-guide.md`, `60-rounds.md`, `80-live-word.md`) for
an invented writer. The commands are the real ones, run on a folder holding
the public-domain corpus novel (`corpus/marianela`) as two Word drafts plus a
notes file. Their outputs are quoted from that run (2026-10-12). Where the
platform does something itself (Cowork's folder picker, permission prompts),
the step comes from the Claude documentation. **The owner still has to check
these steps by hand** (checklists at the end).

**Persona.** The writer has written a Spanish novel and has no technical
skills. They use Windows 11 Pro, Word 2021 (perpetual licence) and a Claude
Pro plan with the desktop app. Their folder `Marianela/` holds
`Marianela_v1.docx`, `Marianela_v2.docx` and `notas.txt`.

## Writer actions (main path: Pro plan, Cowork)

Only actions count, not answers typed in the chat: toggles, folder picks,
uploads and permission clicks.

| # | Action | Where | Counts |
|---|--------|-------|--------|
| 1 | Upload the Skill zip once (`lc kit --skill`; Settings → Capabilities → Skills) | Claude settings | yes |
| 2 | Turn on code execution, if the plan does not have it on already (Skills need it) | Claude settings | yes |
| 3 | In Cowork, pick the novel's folder `Marianela/` | Cowork | yes |
| 4 | Allow Claude to work in that folder (first permission prompt) | Cowork | yes |
| 5 | Turn on computer use, only to be taken to the passage in Word (optional; without it, plain locations) | Claude settings | yes |
| — | Type "Quiero usar literary-critic para mi novela" | chat | no |
| — | Answer: confirm the file, choose the mode, agree to changes in the file | chat | no |

**writer_setup_actions = 5** (4 without computer use). D-7 path B, where
Claude fetches the tool with `pip install` from GitHub, would remove action 1;
the owner's hand test decides it.

## Conversation (writer-facing replies)

The replies are written as the procedures ask: plain words, one question per
message, each place located (chapter, page, first and last words).

**Writer:** Quiero usar literary-critic para mi novela.

**Claude:** ¡Encantado! Ya veo la carpeta Marianela que me has dado y puedo
trabajar en ella. Antes de nada, una comprobación: he encontrado tu novela en
«Marianela_v2.docx», la versión más reciente, y otra versión anterior,
«Marianela_v1.docx». También hay un archivo de notas que dejo aparte. ¿Trabajo
sobre «Marianela_v2.docx»?

*(Ran: `lc doctor`, then `lc setup --folder Marianela`. The answer named
`Marianela_v2.docx` as the manuscript, `Marianela_v1.docx` as a
version, `notas.txt` under others, language `es`.)*

**Writer:** Sí.

**Claude:** Perfecto. ¿Qué te gustaría: que te ayude a mejorar tu novela paso a
paso (lo habitual), o un informe de lectura como el que haría una agencia?

**Writer:** Mejorarla.

**Claude:** De acuerdo. Una cosa más: cuando aceptes un cambio, puedo
aplicarlo yo en tu archivo de Word como cambio con control (lo verás marcado y
podrás aceptarlo o rechazarlo), y antes guardo siempre una copia de seguridad.
¿Prefieres eso, o escribir tú cada cambio?

*(Ran: `lc setup --folder Marianela --edit-in-place yes` once the writer said yes.)*

**Writer:** Que lo hagas tú.

**Claude:** Hecho. Te propongo empezar así: primero te digo qué funciona bien en
la novela y los tres problemas más importantes, empezando por la estructura.
Después iremos cambio a cambio. ¿Te parece bien empezar por ese resumen?

**Writer:** Vale.

*(The overview comes from the existing procedures (30, 40); it is not part of
this walkthrough. The writer then accepts the first action of the round.)*

**Claude:** Primer cambio. Está en el capítulo 2 («Guiado»), escena 1, hacia la
página 7: el párrafo que empieza «--Quién sabe...--manifestó Teodoro--¿pero
qué…» y termina «…sorprendente espectáculo es este?». Te lo dejo señalado en
Word ahora mismo. Para aplicarlo necesito que guardes y cierres el documento
en Word. ¿Me avisas cuando esté cerrado?

*(Ran: `lc docx locate c02.s1.p3 --workspace <ws>`, giving `find`
"--Quién sabe...--manifestó" (unique), then `lc word locate --payload w.json`,
which returned the writer line above and the Ctrl+F steps. `lc docx status`
reported `locked: true`.)*

**Writer:** Ya está.

**Claude:** Listo: he aplicado el cambio en el capítulo 2, página 7, en el
párrafo que empieza «--Quién sabe...--manifestó Teodoro--¿pero qué…» y termina
«…sorprendente espectáculo es este?». Ya puedes abrir
Word: lo verás como cambio marcado, y puedes aceptarlo o rechazarlo. Guardé
una copia de seguridad antes. ¿Seguimos con el siguiente?

*(Ran: `lc docx edits --workspace <ws> --edits edits.json --dry-run`, then the
same without `--dry-run`, which returned `applied: ["A1"]` and a backup under
`literary-critic/backups/`. Then `lc word reopen`.)*

## Variant: Word stays open the whole time

The writer forgets to close Word and asks for the next change.

**Claude:** Todavía tienes el documento abierto en Word, y no quiero tocarlo
mientras lo usas: podrías perder lo que no hayas guardado. ¿Puedes guardarlo
(Ctrl+G) y cerrarlo? Te aviso en cuanto termine para que lo vuelvas a abrir.

*(Ran with the Word lock file present: `lc docx edits` answered `refused`,
reason `locked`, and the file and its backups were unchanged. Closing Word
with computer use (`lc word close`, `save: true`) is the alternative once the
writer agrees. Edits never go into a file that is open.)*

## Results

| Measure | Target | Measured |
|---------|--------|----------|
| writer_setup_actions (main path) | ≤ 5 | 5 (4 without computer use) |
| Median writer-facing reply | ≤ 120 words | 44 words (7 replies, 27–52) |
| Every place located | all | both replies that name a place give chapter, page, and the quoted first and last words |
| One step at a time | one question per reply | yes |

**Fixed during the walkthrough:** `lc setup` printed paths from the folder
above the novel's (`Marianela/Marianela_v2.docx`), while `lc docx` and
`--manuscript` take them from the novel's folder. Setup now prints them the
same way (`Marianela_v2.docx`).

## Hand-test checklists for the owner

Each check needs a real account or computer. Record the result in the plan's
evidence log.

**D-18: Skills on each plan**
- [ ] Free plan: can a Skill be uploaded and used? Does code execution run?
- [ ] Pro plan: upload `litcritic-skill-<version>.zip` (Settings → Capabilities → Skills); a new chat saying "I want to use literary-critic for my novel" loads it.
- [ ] Python version in the chat sandbox (expected 3.11; `lc doctor` prints ok).

**D-7 path B: Claude fetches the tool**
- [ ] In a chat with code execution, `pip install git+https://github.com/nuncaeslupus/literary-critic` works (network allowed?), and `lc doctor` runs.
- [ ] In Cowork, the same, or the uploaded Skill's `lc.py` runs from a writable folder.

**Cowork main path (Windows 11 Pro and a Mac with Apple silicon)**
- [ ] Count the actions from a fresh account to the first overview (target ≤ 5).
- [ ] `lc setup` on the real novel folder names the right manuscript.
- [x] An approved change appears in Word as a tracked change by `literary-critic`, and rejecting it restores the text. *(Windows 11 Pro, Word 16.0.17932, 2026-10-13, with `lc` run from a checkout rather than Cowork: Word reports one deletion and one insertion by `literary-critic`; after Reject All its text equals the original's.)*
- [x] With the document open in Word, the change is refused and nothing is lost. *(Same machine: `lc docx status` says `locked`, `lc docx edits` answers `refused` / `locked` with exit 1, the file's bytes are the same and no backup is added; once Word closes it, the same edit applies.)*

**Computer-use locate (`live_locate_success >= 0.9`)**
- [x] 10 located actions on Windows: Claude brings Word to the front and the search selects the paragraph. Successes: 10/10. *(2026-10-13, Spanish Word 16.0.17932, keys sent by script to a visible Word and the selection read back from Word, not through computer-use screenshots: window to the front, Ctrl+B, the `find` string typed, a wait for the search to refresh, Enter, Esc; the selection was the `find` text inside the right paragraph for 10 of 10 random paragraphs. Without the wait, an early Enter jumps to the previous search's result (8/10 and 1/10 on two runs), so `lc word` now says to wait. Also checked without the keyboard: Word's own Find, given the `find` string of `lc docx locate`, lands on the right paragraph for 100 of 100 random paragraphs of the corpus novel as a Word-made `.docx`, 37 of them with accented characters. The key that opens the search depends on Word's language: in a Spanish Word, Ctrl+F indents the paragraph and Find is Ctrl+B, so `lc word` now names the key by language.)*
- [ ] 10 on Mac (Cmd+F): __/10.
- [ ] When it fails, the writer gets the plain location instead.
