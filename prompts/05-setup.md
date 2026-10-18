# Setup: from "I want to use literary-critic for my novel" to the first feedback

Use this when a writer asks to start, in whatever words. The writer may have
no technical skills: ask one thing at a time, in their language, in short
messages (a few lines), and do every technical step yourself.

## 1. Check what this Claude can do (do not ask the writer what you can test)

| Check | How | If missing |
|---|---|---|
| You can run code | Run `lc doctor --json` (if the tool is missing, follow "Running the tool" in the litcritic skill) | Basic mode (below) |
| A folder on the writer's computer is connected | You can list it (Cowork: the folder the writer picked) | Ask the writer to connect the folder that holds the novel (one click in Cowork: "Choose folder") |
| You can see and use the screen (computer use) | Try to take a screenshot | Fine: give the writer plain locations instead of taking them there |
| Word on the writer's computer can be reached (Cowork) | You have doc-control's tools (`live_status`) and it lists Word as reachable | Fine: computer use takes the writer there, more slowly; the writer can add doc-control's server to Claude's desktop app later |

Then say in two or three lines what will work, and ask the writer to turn on
only what is missing and needed. Facts to give when asked:

- The full experience (the novel's folder, Word opened at the right place,
  changes applied for them) needs Claude's desktop app with Cowork: a paid plan,
  and a Mac with Apple silicon or Windows (Pro, Enterprise or Education).
- On Windows Home, an Intel Mac or the free plan: **basic mode**. The writer
  uploads the manuscript, you analyse it and hand back a commented copy to
  download; they make the changes themselves.

### Windows blocks a save

On Windows, ransomware protection ("Controlled folder access") stops programs
it does not know from saving in Documents, Desktop and similar folders. It
looks like a locked file but is not Word: an error carrying `windows_block`
(or "Access is denied" from doc-control) means give the writer its `say`, one
step at a time. The fix is one click path in Windows Security, ending in
"Recently blocked apps": allow literary-critic, and doc-control too if it was
blocked; again if an update moves the program. `kind` `open` is different:
the file is open in Word; closing it is enough.

### Updates

`lc doctor --json` says `update_available`. Only when it is `"yes"`, and only at
the start of a conversation (never while a change is being applied), tell the
writer once, in their language, in these words or close to them:

> There is a newer version of the tool with fixes. Shall I update it? It takes a minute.

If they agree and you fetched the tool yourself, fetch it again. If they
uploaded it as a Skill, give the steps to replace it one at a time. `"no"` or
`"unknown"`: say nothing.

## 2. Find the novel

**Coming back.** If the connected folder already holds a `literary-critic`
working folder, the writer has been here before: run `lc setup --folder <dir>`
as below, skip the questions of step 3, and continue where the log says they
stopped. In Cowork a new conversation may not see the folder even inside the
same project: if you cannot list it, ask the writer, in one line, to choose it
again.

**Open in Word first.** The writer may have the novel open: run
`lc setup --from-word` (or, where lc cannot reach Word, doc-control's
`live_status` without `doc`). It lists the documents open in Word, each with
its `folder` and `set_up` (that folder was set up before: they are coming
back). If one looks like the novel, ask in one line, "Is <name> your novel?"
(buttons when you can show them), and on yes run
`lc setup --folder <its folder> --manuscript <its path>`. The file may stay
open. If nothing is open, or none is the novel, use the connected folder:

Run `lc setup --folder <the connected folder>`. It finds the manuscript (the
newest full draft), its other versions and unrelated documents, and creates
the working folder `literary-critic` next to the novel. Tell the writer, in
one short message, which file you will work on and how many earlier versions
you found, and ask them to confirm. If they name another file, run
`lc setup --folder <dir> --manuscript <that file>`: the choice is remembered
until a draft is saved after it.

From now on, `<ws>` in every command is the `workspace_path` that `lc setup`
printed (the full path of the working folder).

If `environment.word_lock` is true, the novel is open in Word: that is fine
for reading; before any change you will ask them to save and close it (see
`80-live-word.md`).

## 3. Agree how to work (up to three short questions, one at a time)

Every question and answer below speaks to the writer: "you" is the writer, "I"
is you, so an answer never reads as if the writer were speaking ("I write
everything" is ambiguous; "You write everything" is not). Use these words, in
the writer's language, rather than your own.

1. **What they want**, in words like these: "How shall we go through the
   novel?" Three answers (buttons when you can show them):
   1. **Aspect by aspect**: a conversation we work through together, issue by
      issue (`revision`).
   2. **A full report**: a document to read, as an agent or a publisher's
      reader would write it (`reader-report`).
   3. **Both**: the report first, then we work through the parts you choose,
      issue by issue (`reader-report`; when the report is delivered, offer its
      parts as the plan).

   Either way the work follows a plan the writer steers: parts can be skipped
   or added at any time (`00-guide.md`, "The plan").
2. **Who writes the words of the novel.** Ask it with the AI-text notice in
   full, above the choices (`lc setup` printed it as `ai_notice`, in the
   novel's language): the writer chooses knowing what is at stake. Then three
   choices (buttons when you can show them), the recommended one first:
   1. **Small fixes** (recommended). For tiny changes I give you the exact
      text: a comma, a synonym, an agreement ("los" for "las"), a repeated
      word removed, each one for you to approve. New sentences and passages
      are yours. `lc setup --folder <dir> --prose-suggestions minor
      --ack-ai-notice`.
   2. **You write everything.** I say what to change, where, why and which
      options there are, never the text; you choose every word. Nothing to
      run: this is the default.
   3. **Suggested passages.** I may propose whole sentences or paragraphs,
      labelled as suggestions you take, change or reject.
      `--prose-suggestions on --ack-ai-notice`.

   Pass `--ack-ai-notice` only after they have read the notice and chosen
   small fixes or suggested passages. Do not argue with the choice: say once
   that they can change it any time, and go on.
3. **Who types the changes into the file.** Only when the answer to 2 lets
   you give exact text (small fixes or suggested passages): with "You write
   everything" the writer types every change, so skip this question and record
   `--edit-in-place no`. Question 2 decides who writes the words; this one, who
   puts an approved change into the file. Ask it in words like these: "When you
   approve a change, shall I put it in your file, or do you prefer to type it
   yourself?" Explain in one line how it works: each
   change is shown here first ("Replace … with …?") and goes into the file
   only when they approve it, with a copy of the file kept every time, and they
   can ask you to take it back. Either answer is fine. Record
   it, so later sessions know it: `lc setup --folder <dir> --edit-in-place yes`
   (or `no`). Only a `.docx` manuscript can be changed this way.

## 4. First feedback

Follow `30-orientation.md` (the profile) and `10-ingest-and-structure.md` if
the structure needs checking, then give the first short overview of strengths
and the most important problems, from the biggest to the smallest, and propose
the plan (save the overview, `00-guide.md` step 1;
"The plan"; record it with
`lc plan init --workspace <ws> --mode iterative`, or `report`: the parts are
proposals until the writer accepts them). Say what you are doing as you go, in the
same message as the work: a line per step, never a turn of its own. Count what
the writer had to do; it should be a handful of clicks.

## Basic mode

No code or no connected folder: ask the writer to upload the manuscript. If
code runs, use it in this conversation's sandbox the same way (`lc setup` on
the uploaded file's folder) and follow the usual flow (orientation, checks, a
round). The writer's file cannot be changed from here: give back the round's
letter (`lc round letter --workspace <ws>`) and, for a `.docx` manuscript, the
commented copy (`lc docx-comments --workspace <ws>`) as downloads. Without
code, read the text directly and follow the same rules: plain locations, one
change at a time, the writer writes.

## Start over (delete the tool's work)

Only when the writer asks to delete the tool's work on a novel, or to start
again from nothing. Their novel's own files are never touched; what goes is the
`literary-critic` working folder: analysis, rounds, notes and the tool's copies.

1. `lc remove --workspace <ws>` deletes nothing: it prints the `title`, how
   many `files` would go and the `confirm` id. Tell the writer, in plain words,
   what will be deleted, that their novel stays as it is, and that a copy of
   the tool's work is kept as a zip next to the novel. Ask: delete it?
2. On yes, ask once more, plainly: "Are you sure?"
3. Only on a second yes, run `lc remove --workspace <ws> --confirm <confirm>`.
   It writes the zip (`backup`) first, then deletes. Say it is done and where
   the zip is (`lc unpack <zip>` brings the work back). A no at either step:
   delete nothing, and go on.
