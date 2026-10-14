# Specification: one plain desktop chat for the whole novel

**Date**: 2026-10-14
**Ticket / PR**: workspace `desktop`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
- r1 — first draft, from the owner's test on their own PC (live Word with the
  test novel, 2026-10-14): "my problem keeps being which chat type I need to use"

> Review record. Each round of reviewer notes makes a new revision: bump
> **Revision**, add a log line naming the export it applied
> (``- r2 — applied `<repo>-spec-v1-<date>-notes.md` ``), and commit that
> export beside this file in the same commit. On approval set
> **Status** to `approved (YYYY-MM-DD, revision N)` and, when the reviewer sent
> no notes for that revision, add `— without annotations`.

---

## 1. Problem statement

The `install` workspace made "take me there" fast: `lc docx locate 7 --go`
puts Word on the chapter in about 2 s of tool time, and `lc docx places` turns
a list of places into doc-control `live_places` buttons. A click on one of
those buttons moves Word in about 1 s, with no model turn. All of it, though,
needs `lc` to run **on the writer's PC**, where the working folder and Word
are. In the Claude desktop app that means a Cowork project relaying to a
Remote Control thread, or a Code-tab session.

On the owner's test this was confusing. The project chat opened a thread,
the thread opened another chat, and the owner could not find the way back.
A plain Chat runs code only in a cloud sandbox. That sandbox cannot see the
PC's working folder, so a plain chat cannot resume the novel. The writer
wants to open any ordinary chat, write "Let's continue with `<novel>`" and get
the novel's state, the next step and the jumps into Word, with no projects,
threads or uploads.

The desktop app's Chat tab already starts the local MCP servers listed in
`claude_desktop_config.json`. doc-control runs there today, and its
`live_places` buttons render in that tab. What is missing is a local
literary-critic server beside it. That server would find the novel's
working folder, read its state, give the chat the guide and expose the `lc`
commands the session needs.

This is a planned improvement. It decides whether a writer can use the tool
without learning the app's session types.

**Success criteria (measurable)**

- [ ] `resume_without_questions == 1.0`: in a new Chat, "Let's continue with
      `<title>`" (title, slug or folder name, any capitalisation or accents)
      resolves the right workspace and answers with where the writer left off
      and the next step. The chat asks no setup question. Checked over a fixture
      registry with 3 works, one title with accents and one not registered: for
      that one, the answer lists the known works.
- [ ] `resume_tool_calls <= 2` from "Let's continue with `<title>`" to the
      first answer. Counted on a recorded transcript.
- [ ] `chapter_jump_wall_s <= 8` (median of 5) from "take me to chapter 7"
      to Word at the chapter, in a plain Chat. This is one model turn with one
      tool call that drives Word itself.
- [ ] `places_render_as_buttons == 1.0`: a reply that lists places shows
      doc-control's `live_places` buttons in the Chat tab, and a click moves
      Word with no new chat message.
- [ ] `writer_setup_actions <= 3` to turn it on, for a writer who already has
      the desktop app, Word and the novel: run one setup step, restart the app,
      allow the tools on first use. Counted on a scripted walkthrough.
- [ ] `config_entries_clobbered == 0`: the setup step adds or updates only the
      literary-critic entry in `claude_desktop_config.json`. Every other key is
      left byte-for-byte the same, a backup is kept, and the result is valid
      JSON. Tested on fixture configs, including one with doc-control and
      unknown keys.
- [ ] `server_runtime_deps == {stdlib, doc-control}` (rule 9), checked by the
      existing import test.
- [ ] No session type to choose. The walkthrough for the writer never names
      threads, projects, Cowork or the Code tab. This is judged by reading the
      setup prompt and the walkthrough.
- [ ] The writer channel's rules still hold: novel content stays out of the
      repo, the writer approves every manuscript change, and the writer writes.
      Judged by the existing guard and prompt tests, which pass unchanged.

## 2. Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `src/litcritic/` new `mcp` module | Primary | stdio MCP server: `lc mcp` | Yes | New entry point; tools wrap existing commands | Med |
| `src/litcritic/workspace.py` registry | Primary | Finds a novel's working folder from a title | Yes | Lookup by title, slug or folder name; folders registered at setup and on every `lc init` | Med |
| `lc` CLI (`cli.py`, `docx_cli.py`, `word_live.py`) | Dependent | The commands the tools call | Small | Unchanged behaviour; maybe a `resume` summary command | Low |
| Setup step (new `lc desktop` or `lc doctor --fix`) | Primary | Writes the config entry | Yes | Edits a file of the desktop app, outside the repo and workspace | High |
| `prompts/` (00-guide, 05-setup, 80-live-word), `.claude/skills/litcritic/SKILL.md` | Dependent | The guide the chat follows | Yes | Delivered as server instructions/resources; one path for "plain Chat" | Med |
| doc-control (≥ 0.6.3) | Dependent | Live Word engine, `live_places` buttons; `doc_control.api.run` as stable Python entry | No | lc writes its own server (D-4); doc-control's `mcp.py` is the reference | Low |
| `claude_desktop_config.json` | Infrastructure | Lists local MCP servers for the Chat tab | Yes (by setup) | A broken file stops all the writer's local servers | High |
| Packaging (PyPI `literary-critic`, `uvx`) | Infrastructure | How the server reaches the writer's PC | Yes | 0.1.0 is not published; the entry needs a stable command | Med |
| Writer's working folder (`<novel>/literary-critic/`, chat D-10) | Data | All state | No | Read and written exactly as today | Low |
| Cowork / Code-tab threads, Skill zip | UI | Today's paths | No | Remain as alternatives; no longer the main path on Windows desktop | Low |

**Risk of inaction**: every session starts with "which chat do I use?". A
plain Chat cannot see the novel. Writers who are not developers stop at
setup, which is the very audience the chat workspace targets.

## 3. Options

Every option keeps chat D-10 (state in `<novel>/literary-critic/`), install
D-1 (live engine first, then computer use, then the plain locator) and install
D-3 (doc-control owns the live engine's packaging).

### Option A: doc-control only, with a remembered folder (Conservative)

- **Description**: Add nothing on the literary-critic side. Claude's memory or
  a custom instruction stores the novel's folder, and the cloud sandbox runs
  the kit. In a plain Chat, doc-control's tools (`live_select`, `live_places`,
  `outline`, `find`) work on the open `.docx` directly. Codex state, metrics and
  rounds come from a workspace zip that the writer uploads.
- **Scope**: `prompts/05-setup.md` and `80-live-word.md` text only.
- **Effort**: Small
- **Tradeoffs**: Nothing to install. But the sandbox still cannot read the PC
  folder, so there is no resume without an upload, and that breaks the "Let's
  continue" criterion. The paragraph anchors that `lc` computes
  (`c07.s2.p4`) are unavailable, so jumps fall back to Word's search text.
- **Compatibility**: Fully compatible.

### Option B: literary-critic as a local MCP server beside doc-control (Recommended)

- **Description**: `lc mcp` serves a small set of tools on stdio (MCP over
  newline-delimited JSON-RPC, standard library only). It runs from the Chat
  tab's config, as doc-control does, on the writer's PC:
  - `works` lists the registered works (title, folder, last activity).
  - `resume(work)` returns the work's state: the current draft, the open
    round and the next step.
  - `locate(work, target, go)` and `places(work, targets)` cover the
    existing `lc docx locate --go` and `lc docx places`.
  - `show`, `find` and codex `ask` let the chat read the novel.
  - `run(work, command)` runs any other `lc` subcommand in that work's
    folder, from an allow-list.

  The server's `instructions` carry the short guide: the two channels, the
  hard rules for writers, "Let's continue with X" means `resume`, and a
  jump is one `locate` call and then "Done." The prompts are served as
  resources, so the chat reads a part only when it needs it.

  A setup step (`lc desktop install`) adds the entry to
  `claude_desktop_config.json`. It keeps a backup, validates the result and
  merges, so it never overwrites. It also registers the novel's folder. The
  chat calls doc-control's `live_places` itself with the arguments that
  `places` returns, because the buttons belong to doc-control's server.
- **Scope**:
  - New `src/litcritic/mcp.py` and a `mcp` subcommand.
  - Registry lookup by title in `workspace.py`.
  - The setup command.
  - Prompts and SKILL.md: plain Chat becomes the main path on Windows desktop.
  - Packaging: publish to PyPI so the entry is `uvx literary-critic mcp`, or
    point it at an installed `lc`.
  - Tests: a JSON-RPC transcript test, the config-merge fixtures and the
    registry lookup.
- **Effort**: Medium
- **Tradeoffs**:
  - One plain chat does everything, and resume is local and instant.
  - Jumps keep their speed: one tool call drives Word through the same
    `word_live` path that reached 2 s.
  - The writer adds a second local server: one setup step and one
    permission prompt on first use.
  - Tools run with the writer's permissions on their own files. Keeping
    the tool set small and allow-listed keeps the risk bounded.
  - It depends on the desktop app passing server `instructions` to the
    model. If the app ignores them, a one-line custom instruction ("for
    novels, use literary-critic's tools") is the fallback. That is open
    question Q-2.
- **Compatibility**: Additive. Every CLI command, the Skill zip and the thread
  paths still work.

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
    chat, which is the very confusion reported.
  - Threads relaying through a project measured about 2 minutes per turn.
  - `live_places` buttons in threads are still unconfirmed.
- **Compatibility**: Fully compatible.

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Small | Medium | Small |
| Risk | Low (no code) | Medium (edits the app's config; new server) | Low |
| Completeness | Low: no local resume, no anchors | High: every criterion | Partial: fails "no session type to choose" |
| Compatibility | Full | Additive | Full |
| Maintenance | None | One server module plus its tests; follows MCP revisions | Follows the app's UI changes |

## 4. Recommendation

**Recommended option**: Option B. It is the only option that meets "one
plain chat" and "resume without questions". It reuses every fast path that
already exists (`locate --go`, `places`, the registry). It also follows the
same shape the writer already runs successfully: doc-control as a local server
in the Chat tab.

**Immediate next action**: answer Q-2 with a probe server on the owner's PC,
then write the plan, with
the JSON-RPC transcript test and the config-merge fixtures as the first
gates.

**Open questions**:
- [x] Q-1: Should lc reuse doc-control's `mcp` module? Answered by doc-control:
      no. Its `handle`/`serve` and the registry hooks are internal and may change
      in any release, so lc writes its own small stdlib server (D-4), using
      doc-control 0.6.3's `mcp.py` as a reference. If lc ever serves its own
      app page, that page's buttons can call only lc's tools. lc would then
      proxy Word moves through `doc_control.api.run("live.select", …)`, which
      is doc-control's stable Python entry point.
- [ ] Q-2: Does the desktop app's Chat tab give the model a server's
      `instructions`? To be checked on the owner's PC with a probe server
      before the guide relies on it.
- [ ] Q-3: How does the entry start the server: publish `literary-critic` to
      PyPI and use `uvx`, the same way as doc-control, or install it once
      and point at that? The owner decides. Publishing also needs the
      `repo-housekeeping` metadata.
- [ ] Q-4: Should the setup step be a new `lc desktop install`, or part of
      `lc doctor --fix`? The proposal is a separate command, because it edits a
      file outside the workspace and should be explicit.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| chat D-10 | Working files in `<novel>/literary-critic/` | agreed (kept) | 2026-10-11 |
| install D-1 | "Take me there" tries the live engine first, then computer use, then the plain locator | agreed (kept) | 2026-10-14 |
| install D-3 | Packaging the live engine for writers belongs to doc-control | agreed (kept) | 2026-10-14 |
| install D-4 | A returning writer resumes from the existing working folder, without setup questions | agreed (kept; this spec makes it work in a plain Chat) | 2026-10-14 |
| D-1 | The main path on a Windows PC with the desktop app is a plain Chat with two local servers (doc-control, literary-critic); threads and projects become alternatives | proposed | 2026-10-14 |
| D-2 | `live_places` buttons stay doc-control's; literary-critic returns the call's arguments and the chat makes the call | proposed | 2026-10-14 |
| D-3 | The setup step merges into the desktop config (backup, validate, never overwrite other entries) | proposed | 2026-10-14 |
| D-4 | lc has its own stdlib MCP server and does not import doc-control's `mcp` module, which is internal (doc-control's answer to Q-1) | agreed | 2026-10-14 |

---

> Sections 5–6 (contracts, risks) are appended by `design`.
