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

Then say in two or three lines what will work, and ask the writer to turn on
only what is missing and needed. Facts to give when asked:

- The full experience (the novel's folder, Word opened at the right place,
  changes applied for them) needs Claude's desktop app with Cowork: a paid plan,
  and a Mac with Apple silicon or Windows (Pro, Enterprise or Education).
- On Windows Home, an Intel Mac or the free plan: **basic mode**. The writer
  uploads the manuscript, you analyse it and hand back a commented copy to
  download; they make the changes themselves.

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

## 3. Agree how to work (two short questions)

1. **What they want:** improve their own novel (`revision`, the default) or an
   assessment of it as a reader or agent would write it (`reader-report`).
2. **Changes in the file:** you only ever change the file after they approve
   each change, as tracked changes they can accept or reject in Word, with a
   backup every time. Do they want that, or do they prefer to type every
   change themselves? Either is fine. Record the answer, so later sessions
   know it: `lc setup --folder <dir> --edit-in-place yes` (or `no`). Only a
   `.docx` manuscript can be changed this way.

Wording suggestions stay off unless the writer asks for them; then follow
house rule 1 of `00-guide.md` (the AI-text notice comes first).

## 4. First feedback

Follow `30-orientation.md` (the profile) and `10-ingest-and-structure.md` if
the structure needs checking, then give the first short overview of strengths
and the most important problems, and propose the plan (`00-guide.md`, "The
plan"). Count what the writer had to do; it should be a handful of clicks.

## Basic mode

No code or no connected folder: ask the writer to upload the manuscript. If
code runs, use it in this conversation's sandbox the same way (`lc setup` on
the uploaded file's folder) and follow the usual flow (orientation, checks, a
round). The writer's file cannot be changed from here: give back the round's
letter (`lc round letter --workspace <ws>`) and, for a `.docx` manuscript, the
commented copy (`lc docx-comments --workspace <ws>`) as downloads. Without
code, read the text directly and follow the same rules: plain locations, one
change at a time, the writer writes.
