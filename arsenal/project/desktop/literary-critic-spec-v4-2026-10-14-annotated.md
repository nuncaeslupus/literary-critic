# Literary Critic — Specification (annotated edition)

> Generated 2026-10-14. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Spec

## Preamble & scope

**Date**: 2026-10-14
**Ticket / PR**: workspace `desktop`
**Author**: Claude (with the owner)
**Revision**: 4
**Status**: draft
**Revision log**:
- r1 — first draft, from the owner's test on their own PC (live Word with the
  test novel, 2026-10-14): "my problem keeps being which chat type I need to use"
- r2 — the owner's decisions in conversation (no notes export): Option B is
  chosen. Install must be one step, close to invisible for the writer, then a
  few permissions. The chat must understand "work on my novel" and similar.
  Any skill is built under skill-workshop. Research on the desktop app's
  extension and plugin formats turned the setup step into a one-click desktop
  extension (D-5…D-9; D-2 and D-3 superseded).
- r3 — owner's question in conversation (no notes export): "what if the
  writer wants to start a chat with another novel?" The picked folder holds
  every novel; a chat switches by naming one. The picker takes several
  folders. A novel outside them gets one plain sentence. New criterion
  `switch_novel_without_setup`, D-10 and Q-6.
- r4 — probe extension installed on the owner's PC (2026-10-14, no notes
  export). The owner's case: one folder per novel, only one granted at
  install, another novel wanted days later. Results:
  - Chat ignores server `instructions` (Q-2), but the tool descriptions alone
    trigger on "let's work on my novel".
  - The `uv` runtime works (Q-3, partly).
  - The folder setting is editable after install, but saving it dropped the
    server (Q-6).
  - A chat-side folder-picker tool added the second novel's folder.
  - Double-click does not open `.mcpb` on a packaged (MSIX) install of the
    app.
  - The install shows several warnings for an unsigned extension.

  New D-11 and D-12; D-5, D-7 and D-8 revised; Q-7 and Q-8 opened.

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<repo>-spec-v1-<date>-notes.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

<!-- -->

> **✎ Notes** · `SPEC · intro`
> _(your notes here — replace this line)_

## §1 Problem statement

The `install` workspace made "take me there" fast. `lc docx locate 7 --go`
puts Word on the chapter in about 2 s of tool time. `lc docx places` turns a
list of places into doc-control `live_places` buttons, and a click on one moves
Word in about 1 s with no model turn. All of it needs `lc` to run **on the
writer's PC**, where the working folder and Word are. In the Claude desktop
app today that means a Cowork project relaying to a Remote Control thread, or
a Code-tab session.

On the owner's test this was confusing. The project chat opened a thread,
the thread opened another chat, and the owner could not find the way back.
A plain Chat runs code only in a cloud sandbox, which cannot see the PC's
working folder, so a plain chat cannot resume the novel.

The writer wants to:

- install once, in one step, with nothing technical to understand;
- answer a few permission prompts;
- then open any ordinary chat, write "let's work on my novel" or "let's
  continue with `<novel>`", and get the novel's state, the next step and the
  jumps into Word.

None of that should involve projects, threads, uploads or config files.

The desktop app has a format made for this. A **desktop extension**
(`.mcpb`) is a zip with a local MCP server and a `manifest.json`. The app
installs it from Settings → Extensions (or by double-click where the app
registered the file type, which a packaged install on the owner's PC did not).
It shows an install dialog where the user reviews warnings and fills in
settings; a setting can be a folder picker. The extension's tools are then available in ordinary conversations.
doc-control already runs as a local server in the Chat tab, and its
`live_places` buttons render there.

What is missing is a literary-critic extension. It would find the novel's
working folder, read its state, carry the guide to the chat and drive Word.

This is a planned improvement. It decides whether a writer can use the tool
without learning the app's session types.

**Success criteria (measurable)**

- [ ] `writer_setup_actions <= 3` for a writer who already has the desktop app,
      Word and the novel. The three actions are:
      - bring the downloaded `literary-critic.mcpb` to the app (double-click,
        or drag it onto Settings → Extensions; Q-7);
      - in the install dialog, pick the novel's folder and press Install;
      - allow the tools the first time a chat uses them.

      Install warnings the writer must accept count as one action each beyond
      the first (Q-8). Nothing else is required: no terminal, no config file, no separate
      doc-control install, and no Python install unless Q-3 shows the app
      cannot provide it. Counted on a scripted walkthrough on a Windows user
      account that has never run the tool.
- [ ] `resume_without_questions == 1.0`. In a new Chat, "let's continue with
      `<title>`" (title, slug or folder name, any capitalisation or accents)
      finds the right work. It answers with where the writer left off and the
      next step, and asks no setup question. Checked over a fixture novels
      folder with 3 works, one title with accents, and one title that is not
      there (the answer lists the works it found).
- [ ] `generic_request_resolves == 1.0`. "Let's work on my novel", "sigamos con
      la novela" and similar phrasings with no title:
      - with exactly one work in the folder, behave as the line above;
      - with several, ask one question that lists them, most recent first.
      Judged over a fixed set of 10 phrasings in English and Spanish, on a
      recorded transcript.
- [ ] `switch_novel_without_setup == 1.0`. Over the same fixture:
      - a new chat about another work resumes that work;
      - in a chat already on one work, "now let's look at another title"
        moves to the other work, and later tool calls use it;
      - a work added to a picked folder after install is found with no
        reinstall, and its first-time setup runs in the chat as today;
      - a work outside every granted folder is added from the chat: the
        chat offers the folder picker, the writer chooses the folder, and the
        work resumes in the same chat (D-11). Folder names with accents
        survive the round trip.

      None of these asks a setup question beyond the new work's own
      first-time setup. Judged on a recorded transcript.
- [ ] `resume_tool_calls <= 2` from the writer's first message to the first
      answer, counted on a recorded transcript.
- [ ] `chapter_jump_wall_s <= 8` (median of 5) from "take me to chapter 7" to
      Word at the chapter, in a plain Chat. That is one model turn with one tool
      call, which drives Word itself.
- [ ] `places_render_as_buttons == 1.0`. A reply that lists places shows one
      button per place in the Chat tab, and a click moves Word with no new chat
      message.
- [ ] `paths_outside_novels_folder_refused == 1.0`. No tool reads or writes
      outside the folder the writer picked at install, plus the tool's own
      cache. Tested with `..`, absolute paths, symlinks and junctions.
- [ ] `mcpb_validation_errors == 0`. The manifest passes the MCPB CLI's
      validation, and `mcpb pack` builds the bundle in CI.
- [ ] `skill_workshop_errors == 0` for every skill this work adds or changes.
      The skill is built and checked with skill-workshop: its validator and
      rubric pass.
- [ ] `server_runtime_deps == {stdlib, doc-control}` (rule 9), checked by the
      existing import test.
- [ ] No session type to choose. The setup prompt and the walkthrough for
      the writer never name threads, projects, Cowork, the Code tab or config
      files. Judged by reading them.
- [ ] The writer channel's rules still hold: novel content stays out of the
      repo, the writer approves every manuscript change, and the writer writes.
      Judged by the existing guard and prompt tests, which pass unchanged.

<!-- -->

> **✎ Notes** · `SPEC §1`
> _(your notes here — replace this line)_

## §2 Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `src/litcritic/` new `mcp` module | Primary | stdio MCP server, `lc mcp`; the extension runs it | Yes | New entry point; tools wrap existing commands | Med |
| Extension bundle (`manifest.json`, icon, packing script) | Primary | The one-click install; folder picker; tool list | Yes | New build output from the repo; `mcpb` CLI in CI (dev tool, not runtime) | Med |
| `src/litcritic/workspace.py` | Primary | Finds works under the novels folder by title, slug or folder name | Yes | Lookup and "most recent" ordering; the registry stays for paths outside that folder | Med |
| `lc` CLI (`cli.py`, `docx_cli.py`, `word_live.py`) | Dependent | The commands the tools call | Small | Unchanged behaviour; a `resume` summary may be added | Low |
| doc-control (≥ 0.6.3) | Dependent | Live Word engine; `doc_control.api.run` as its stable Python entry; reference code for the server and the places page | No | Bundled as a library inside the extension; Word moves go through `doc_control.api.run` | Med |
| `prompts/`, `.claude/skills/litcritic/SKILL.md` | Dependent | The guide the chat follows | Yes | Server instructions and tool descriptions carry the short guide; the skill is reworked under skill-workshop | Med |
| skill-workshop (claude-arsenal marketplace plugin) | Dev tool | Authoring gate for every skill | Install only | Must be installed in the dev session before skill work | Low |
| Writer's novels folder (`<novel>/literary-critic/`, chat D-10) | Data | All state | No | Read and written exactly as today, now confined to the picked folder | Low |
| `claude_desktop_config.json` | Infrastructure | Hand-added local servers (today's doc-control entry) | No | The extension does not touch it; a writer's manual doc-control entry may stay | Low |
| Cowork / Code-tab threads, Skill zip | UI | Today's paths | No | Remain as alternatives; no longer the main path on the desktop app | Low |

**Facts this rests on** (checked 2026-10-14, from the desktop app's
documentation):

- A desktop extension installs by double-click, by drag-and-drop or from
  Settings → Extensions. Its install dialog shows the extension's
  permissions and settings. `user_config` can declare a `directory` picker,
  with defaults such as `${DOCUMENTS}`.
- An extension's server type is one of:
  - `node`: the app bundles Node.js;
  - `python`: the dependencies are bundled, and the app does not say it
    supplies Python;
  - `uv`: the host installs the dependencies with uv, and the spec lists "no
    user Python installation required";
  - `binary`: self-contained.
- An extension installed from a file does not update itself. The writer
  installs the newer `.mcpb`.
- A plugin's skills work in Chat. A plugin's bundled local server ("runs in
  each session") works in Cowork and Claude Code, **not in Chat**. So a plugin
  alone cannot bring the server to a plain chat.
- An MCP App's buttons can call only tools of the server that served the
  page (doc-control, Q-1 answer).

**Measured with a probe extension on the owner's PC** (2026-10-14; Windows
11, the app installed as an MSIX package):

- Double-clicking the `.mcpb` opened Windows' "choose an app" dialog: the
  packaged app registers no `.mcpb` file type. Installing from Settings →
  Extensions worked.
- The install showed several warnings for an unsigned extension, including
  one that it can read the whole PC.
- The `uv` server type worked. The app built the extension's own
  environment and started the server, passing the picked folder in `args`.
  uv was already installed on that PC.
- The app starts one server process for Chat and another for Cowork. Both
  receive the server `instructions`, and both declare MCP Apps support.
  Only Cowork declares `roots`.
- Chat did not use the `instructions`: asked for a word that only they
  contained, it did not know it. "Let's work on my novel" did call `works`
  from its description alone.
- The folder setting can be edited in Settings after install. Saving it
  left the extension unreachable ("Unable to connect to extension server…
  disable and re-enable").
- A tool that opens a native folder picker on the writer's screen worked
  from a plain chat after the tool permission prompt. The chosen folder was
  saved in the extension's own state. tkinter in the app's Python returned
  an accented folder name garbled (`Ã±` for `ñ`), so the picker must
  use the Windows dialog with UTF-8 output.

**Risk of inaction**: every session starts with "which chat do I use?". A
plain Chat cannot see the novel. Writers who are not developers stop at
setup, which is the very audience the chat workspace targets.

<!-- -->

> **✎ Notes** · `SPEC §2`
> _(your notes here — replace this line)_

## §3 Options

Every option keeps:

- chat D-10: state lives in `<novel>/literary-critic/`;
- install D-1: the live engine is tried first, then computer use, then the
  plain locator;
- install D-4: a returning writer resumes without setup questions.

<!-- -->

> **✎ Notes** · `SPEC §3`
> _(your notes here — replace this line)_

### Option A: doc-control only, with a remembered folder (Conservative)

- **Description**: Add nothing on the literary-critic side. Claude's memory or
  a custom instruction stores the novel's folder, and the cloud sandbox runs
  the kit. In a plain Chat, doc-control's tools (`live_select`, `live_places`,
  `outline`, `find`) work on the open `.docx` directly. Codex state, metrics and
  rounds come from a workspace zip that the writer uploads.
- **Scope**: `prompts/05-setup.md` and `80-live-word.md` text only.
- **Effort**: Small
- **Tradeoffs**: Nothing to build. But the sandbox still cannot read the PC
  folder, so there is no resume without an upload. The writer still edits a
  config file to add doc-control. The paragraph anchors that `lc` computes
  (`c07.s2.p4`) are unavailable.
- **Compatibility**: Fully compatible.

<!-- -->

> **✎ Notes** · `SPEC › Option A: doc-control only, with a remembered folder (Conservative)`
> _(your notes here — replace this line)_

### Option B: a literary-critic desktop extension (Recommended; chosen by the owner)

- **Description**: One `literary-critic.mcpb` that the writer installs from
  the app.
  - **Install.** The dialog asks one thing: the folder that holds the
    novels (default: Documents). It is the parent of every novel, not one
    novel, and the picker takes several folders (`multiple: true`) for
    novels kept in different places (D-10). Each chat names its work. A new
    chat can be on any novel. A chat can switch at any time ("now let's
    look at …"), and every tool takes the work by name. A novel added to
    those folders later is found with no reinstall. The extension's tools then work in any
    plain chat. The first use of a tool asks the writer's permission, as the
    app always does.
  - **A novel the tool cannot see** (D-11). Writers often keep one folder
    per novel, so the next novel is usually outside what was granted. When
    a named work is not found, the tool answers with the works it can see
    and tells the chat to offer `add_folder`. That tool opens the Windows
    folder picker on the writer's screen, which is the writer's explicit
    grant. It stores the folder in the extension's own state and resumes
    the work. The writer never opens Settings. Editing the install setting
    stays possible, but it drops the server until the extension is
    re-enabled.
  - **Server.** `lc mcp`: MCP over newline-delimited JSON-RPC on stdio, with
    its own small standard-library module (D-4). It offers a small set of
    tools:
    - `works` lists the novels in the folder, most recent first.
    - `resume(work?)` returns the state, the open round and the next step.
      With no work named, it picks the only work there, or returns the list
      for one question.
    - `locate(work, target, go)` covers `lc docx locate --go`.
    - `places(work, targets)` returns the buttons.
    - `show`, `find` and codex `ask` let the chat read the novel.
    - `run(work, command)` runs any other `lc` subcommand from an
      allow-list.

    - `add_folder` opens the folder picker (above).

    Every path is confined to the granted folders: the install setting
    plus the folders added with `add_folder`.
  - **Word.** doc-control is bundled as a library, not as a second server
    for the writer to install. Word moves go through `doc_control.api.run`,
    doc-control's stable entry point. The places page is served by the
    extension itself, adapted from doc-control's 0.6.3 page, which doc-control
    offered to share. Its buttons call the extension's own `select` tool.
    Only the server that served a page can answer its buttons, so this is
    what makes one install enough (D-6).
  - **Understanding "work on my novel"** (D-8, D-12). The tool descriptions
    say when to use them ("when the writer talks about their novel, wants to
    continue, resume or work on it"); the probe showed that is enough to
    trigger. Chat ignores server `instructions`, so the short guide travels
    in the first tool result instead. `resume` returns it with the novel's
    state:
    - the two channels;
    - the writer rules;
    - a jump is one call, then "Done.".

    The prompts are served on demand. A skill, built under skill-workshop
    and delivered by a plugin from the repo's marketplace (a second,
    optional install), is added only if the guide in tool results proves
    weaker than a skill.
  - **Runtime.** The extension's server type is `uv`: dependencies are
    declared in `pyproject.toml` and installed by the host. Q-3 checks this
    on the owner's PC. `binary` (a frozen executable) is the fallback.
  - **Updates.** The update check (install D-2) tells the writer, in one
    sentence, when a newer `.mcpb` exists and where to get it.
- **Scope**:
  - New `src/litcritic/mcp.py` and the `mcp` subcommand.
  - The extension's `manifest.json`, icon and pack script, with a CI job.
  - Folder lookup in `workspace.py`.
  - The places page and the `select` proxy.
  - Prompts, plus the skill reworked under skill-workshop.
  - Tests:
    - a JSON-RPC transcript test;
    - the path-confinement cases;
    - the lookup fixtures;
    - manifest validation.
- **Effort**: Medium–Large
- **Tradeoffs**:
  - One install, one plain chat, and a local resume.
  - Jumps keep the speed of `word_live`.
  - It removes the config-file step that the writer, and the assistant
    (refused earlier), could not do safely.
  - There is a copy of the places page to keep in step with doc-control's.
  - Private extensions do not auto-update.
  - The `uv` server type is the newest of the four. It worked on the
    owner's PC, but a machine without uv is still to be proven (Q-3).
  - The install warnings for an unsigned extension are alarming for a
    writer (Q-8).
- **Compatibility**: Additive. Every CLI command, the Skill zip, the thread
  paths and a manual doc-control entry still work.

<!-- -->

> **✎ Notes** · `SPEC › Option B: a literary-critic desktop extension (Recommended; chosen by the owner)`
> _(your notes here — replace this line)_

### Option C: package the PC thread as the only path (Code tab / Remote Control)

- **Description**: Keep `lc` running as the user-level skill, and make the
  thread path less confusing. A pinned Code-tab session or a pinned Remote
  Control folder per novel becomes "the novel's chat". The setup prompt teaches
  the writer to open it from the sidebar.
- **Scope**: Prompts and setup text; the app's pinning settings.
- **Effort**: Small
- **Tradeoffs**:
  - Full `lc` with no new code.
  - But the writer must still learn a session type that is not the plain
    chat, which is the confusion reported.
  - Threads relaying through a project measured about 2 minutes per turn.
- **Compatibility**: Fully compatible.

<!-- -->

> **✎ Notes** · `SPEC › Option C: package the PC thread as the only path (Code tab / Remote Control)`
> _(your notes here — replace this line)_

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Medium–Large | Small |
| Risk | Low (no code) | Medium (new server; `uv` type to prove) | Low |
| Completeness | Low: no local resume, config edit remains | High: every criterion | Partial: fails "no session type to choose" |
| Compatibility | Full | Additive | Full |
| Maintenance | None | Server, manifest, places page; manual updates | Follows the app's UI changes |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Recommended option**: Option B, chosen by the owner on 2026-10-14. It is
the only option that meets one install, one plain chat and resume without
questions. It uses the format the desktop app provides for exactly this.

**Immediate next action**: the first probe ran (§2, measured facts).
Before the plan:

1. Rerun the probe on a Windows user account without uv or Python (Q-3).
2. Find how far signing reduces the warnings (Q-8).
3. Find whether a link can open the app's install dialog (Q-7).

skill-workshop is run from a checkout of the claude-arsenal repository,
without installing the plugin (the owner's choice).

**Open questions**:
- [x] Q-1: Should lc reuse doc-control's `mcp` module? Answered by doc-control:
      no. Its `handle`/`serve` and the registry hooks are internal and may change
      in any release, so lc writes its own small stdlib server (D-4), using
      doc-control 0.6.3's `mcp.py` as a reference. Word moves go through
      `doc_control.api.run("live.select", …)`, its stable Python entry point.
- [x] Q-2: Does the Chat tab give the model an extension's `instructions`,
      and do the tool descriptions alone make "work on my novel" call
      `resume`? Answered by the probe. The instructions are sent but not
      used. The descriptions alone trigger. The guide moves into tool
      results (D-12).
- [ ] Q-3: Does a `uv`-type extension install on Windows with no Python and
      no uv already on the machine? Does it install doc-control's live extra
      (pywin32)? Yes means one step. No means `binary` (a frozen
      executable, larger) or `python` (the writer installs Python first,
      which costs one action). The probe ran on a PC that has uv. A clean
      account is still to be tried.
- [ ] Q-4: How does a writer get the `.mcpb`: a release on GitHub, a link
      on a project page, or a file sent by the person who recommends the
      tool? The owner decides; publishing needs the `repo-housekeeping`
      metadata.
- [ ] Q-5: Should doc-control publish its places page as a reusable file in
      its package, so the extension can serve it rather than keep a copy?
      To be asked of doc-control. Until then, a copy is kept.
- [x] Q-6: Can the writer change the extension's folders after install?
      Answered by the probe. Yes, but saving left the server unreachable
      until the writer disabled and re-enabled the extension. Too fragile
      for a writer, so a chat-side folder picker adds folders instead
      (D-11).
- [ ] Q-7: Can the writer get to the install dialog in one step on a
      packaged install of the app, where double-click does not work? To
      check: a link that opens the app's extension install, or the app's
      extension directory. If neither works, the walkthrough says "drag
      the file onto Settings → Extensions".
- [ ] Q-8: Which install warnings remain for a signed extension
      (`mcpb sign`), and for one listed in the app's directory? This
      decides how the walkthrough prepares the writer for them.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| chat D-10 | Working files in `<novel>/literary-critic/` | agreed (kept) | 2026-10-11 |
| install D-1 | "Take me there" tries the live engine first, then computer use, then the plain locator | agreed (kept) | 2026-10-14 |
| install D-2 | The update check is a script, silent when offline; the writer sees one plain sentence | agreed (kept; it now points to the newer `.mcpb`) | 2026-10-14 |
| install D-3 | Packaging the live engine for writers belongs to doc-control | agreed (kept: the extension uses doc-control's published package as is) | 2026-10-14 |
| install D-4 | A returning writer resumes from the existing working folder, without setup questions | agreed (kept; this spec makes it work in a plain Chat) | 2026-10-14 |
| D-1 | The main path on the desktop app is a plain Chat; threads and projects become alternatives | agreed | 2026-10-14 |
| D-2 | `live_places` buttons stay doc-control's; the chat calls doc-control's tool | superseded by D-6 | 2026-10-14 |
| D-3 | A setup step merges an entry into `claude_desktop_config.json` | superseded by D-5 | 2026-10-14 |
| D-4 | lc has its own stdlib MCP server and does not import doc-control's `mcp` module, which is internal (doc-control's answer to Q-1) | agreed | 2026-10-14 |
| D-5 | The writer installs one desktop extension (`.mcpb`) from the app (double-click where it works); nobody edits a config file | agreed (revised r4) | 2026-10-14 |
| D-6 | The extension bundles doc-control as a library and serves its own places page, so the writer installs nothing else | proposed | 2026-10-14 |
| D-7 | The writer picks the first folder in the install dialog; every tool is confined to the granted folders (that one plus those added with `add_folder`) | proposed (revised r4) | 2026-10-14 |
| D-8 | "Work on my novel" is understood through tool descriptions; a skill (under skill-workshop, via plugin) is added only if the guide in tool results proves weaker | proposed (revised r4) | 2026-10-14 |
| D-9 | Every skill this project ships is authored and validated with skill-workshop | agreed | 2026-10-14 |
| D-10 | The install grants the folders that hold the novels, not one novel; each chat names its work and can switch, with no setup | proposed | 2026-10-14 |
| D-11 | A novel outside the granted folders is added from the chat: `add_folder` opens the Windows folder picker, and the writer's choice is the grant | proposed | 2026-10-14 |
| D-12 | Chat ignores server instructions, so the short guide is returned by `resume` with the novel's state | proposed | 2026-10-14 |


> Sections 5–6 (contracts, risks) are appended by `design`.

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

