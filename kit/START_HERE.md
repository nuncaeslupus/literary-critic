# literary-critic — start here

You (the assistant) have been given this kit so you can help a writer revise
a novel, or an editor assess one, using the `lc` tool. Read this file first.

## 1. Check the platform

Unzip the kit, then from its folder run:

```
python lc.py doctor
```

It needs Python 3.11 or newer and only the standard library. If it prints
`ok`, use the full procedures below. If you cannot run code at all, use the
**reduced mode** (section 4).

## 2. Open the writer's workspace

The writer keeps their working files in a workspace zip (made by `lc pack`).
If they uploaded one:

```
python lc.py unpack <workspace-zip> --home ./home
```

If this is a new novel, create it and bring the manuscript in:

```
python lc.py init <slug> --title "<title>" --language es --home ./home
python lc.py ingest <manuscript.docx> --workspace <slug> --home ./home
python lc.py anchor --workspace <slug> --home ./home
```

Every other command works the same way: add `--home ./home` to it.

## 3. Work

Follow the procedures in `prompts/`, starting with `prompts/00-guide.md`:
it holds the rules that matter most (the writer writes; never edit their
manuscript without permission; plain language; locate everything; one change
per message). Where a procedure says `lc`, run `python lc.py`.

Before the conversation ends, always save the work:

```
python lc.py pack --workspace <slug> --home ./home
```

and give the writer the zip it prints, asking them to keep it (for example in
Google Drive) and upload it next time with this kit.

## 4. Reduced mode (no code execution)

Without code you cannot ingest, anchor, measure or validate. Say so to the
writer, then follow the procedures in `prompts/` by reading the text the writer
pastes: work chapter by chapter, keep your own notes in the same formats
(scene cards, findings), locate every comment by chapter and the quoted first
and last words of the paragraph, and never claim a metric you did not compute.
