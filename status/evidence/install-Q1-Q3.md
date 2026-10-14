# Install hand tests Q-1 and Q-3 (owner, 2026-10-14)

Plan: `arsenal/project/install/plan.md` T5. Windows, Word, Claude desktop app,
Cowork project (beta) with the corpus novel saved by Word as `.docx`.

## Q-1: can a Cowork conversation call doc-control on the writer's computer?

**Answer: yes**, but not as a tool inside the Cowork conversation itself. Cowork
handed the request to a session running on the writer's computer ("running this
on your PC"), which called doc-control's `live.status` and `live.select` and
reported back.

- Permissions asked once: view files (once / always; "always" chosen) and let
  Cowork start sessions on the PC from outside (yes).
- First call slow (first start); then `live.select` selected the paragraph
  (`p304`). A find phrase starting with the plain-text dash `--` failed first;
  the same phrase without the dash worked.
- **Word was not brought to the front**: the paragraph was selected but the
  Claude app stayed on top (`live_locate_writer_visible_steps` not met).
- A repeated request was answered from the earlier result ("already selected")
  without selecting again, after the owner had clicked elsewhere in Word.

## Q-3: does a Cowork project keep the novel's folder across conversations?

**Answer: no, not reliably.** The folder had to be added twice: as project
context, and again in the conversation when the file was looked for ("no folder
was added"). A new conversation assigned to the project continued in the
project's main thread instead of starting a separate one.

## Consequences

- One-click offer (T6) can target Cowork: the request reaches the PC session.
- Asks for doc-control: `live.select` brings the app window to the front; a
  find phrase that starts with `--` (or another dash) is matched as the
  writer's text.
- Prompt rules: "take me there" always runs again (never answered from an
  earlier result); `05-setup.md` tells the writer the folder may need to be
  picked again in a new conversation (`resume_setup_actions == 1`).
