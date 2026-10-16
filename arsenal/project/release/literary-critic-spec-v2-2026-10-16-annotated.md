# Literary Critic — Specification (annotated edition)

> Generated 2026-10-16. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Spec

## Preamble & scope

**Date**: 2026-10-16
**Ticket / PR**: workspace `release`
**Author**: Claude (with the owner)
**Revision**: 2
**Status**: draft
**Revision log**:
- r2 — applied the owner's answers given in chat (2026-10-16), no notes
  export. Option C chosen. Q-1: working state stays beside the novel, so it is
  on OneDrive when the novel is (D-3 rewritten, chat D-10 kept). Q-2: "Update
  automatically" can be turned off, and is on by default. Q-3: the installed
  extension is the only version, with no dev entry (D-11). Q-4: no signing for
  now. Added the app's per-tool approval questions (§3 B.7, Q-7). Corrected
  §2: Controlled folder access is off by default.
- r1 — first draft. Sources: the owner's request ("I want to install it and
  forget it. And if it can be autoupdated or at least say so when it is
  outdated, much better"), the `desktop` and `install` specs, doc-control's
  `PACKAGE` spec, the MCPB documentation and a reading of the installed Claude
  desktop app (2026-10-16).

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

The `desktop` workspace built `lc mcp`, the server behind a literary-critic
desktop extension (`works`, `resume`, `locate`, `places`, `change_card` and the
rest). It planned the extension's packaging as T8 but never built it, so
nothing installs the tool on a writer's PC today. The Claude desktop app
starts the server from the developer's clone with
`uv run --directory <clone> lc mcp <folder>`, under the name
`literary-critic-dev`. literary-critic has no package, release, tag or
installer, and its version has been 0.1.0 since the start.

doc-control, the generic Word tool literary-critic imports as a library
(pinned `>=0.8.3,<0.9` in `pyproject.toml` and `uv.lock`), ships its own
PyInstaller exe, installer and `.mcpb`. On the owner's PC that route ran into
permission errors and antivirus threat detections.

A writer has no technical skills. They need to:

- install one file once, with no Python, terminal, config file or security
  exception;
- then forget it: either the tool updates itself, or the chat tells them in
  plain words when a newer version exists and how to get it in a click or two.

The tool must also not trip Windows Security. Two parts of it can:

- **Controlled folder access** ("ransomware protection") is off by default.
  When the writer or whoever set up the PC turns it on, it blocks unknown
  programs from writing in Documents, Desktop and similar folders, and novels
  usually live in Documents.
- **Defender and SmartScreen** flag unsigned executables, as they did with
  doc-control's.

Using the tool must not mean a stream of questions either. Today the app asks
the writer to approve each tool the first time the chat calls it, and those
questions are technical ("literary-critic wants to use `locate`").

A planned improvement. Without it the tool exists only on the developer's PC.

**Success criteria (measurable)**

The clean PC below is Windows 11 with default Windows Security plus
Controlled folder access turned on, Word, and the Claude desktop app signed in.
It has never had Python, uv, doc-control or literary-critic on it. Windows
Sandbox or a fresh user account counts.

- [ ] `install_actions_clean_pc <= 3`: click the download link, drag the
  `.mcpb` onto the app's window, press Install. Accepting the folder picker's
  default is inside the third action. A security exception, a config file, a
  terminal or a separate Python, uv or doc-control install fails the criterion;
  it is not counted as an action. Each install warning the writer must accept
  counts as one more action (desktop Q-8). Counted on a recorded test run.
- [ ] `security_detections == 0`: zero Defender detections, zero SmartScreen
  prompts and zero Controlled folder access blocks on the clean PC. Counted
  over download, install, first start and a scripted session: set up a novel
  kept in Documents, ingest, write Codex entries, approve a change with the
  document open in Word, approve one with it closed, and write the comments
  copy. Read from Windows Security's protection history.
- [ ] `virustotal_detections_mcpb == 0` for every released `.mcpb`, recorded
  in the release's evidence (gated only on the first release; later releases
  are recorded, and a detection opens an issue).
- [ ] `manuscript_file_writes_by_server == 0`: the server process never writes
  the manuscript `.docx` or a file beside it. Every approved change reaches the
  manuscript through Word, via the live engine. Tested by a fake that records
  every write path, plus the clean-PC session above.
- [ ] `state_beside_novel == 1.0`: a work's working state is in
  `<novel>/literary-critic/`, so it is on OneDrive whenever the novel
  is, in every case where Windows lets the tool write there. Tested over the
  layouts `Documents`, `OneDrive\Documents`, `OneDrive\<other>` and a folder
  outside both.
- [ ] `cfa_fallback_correct == 1.0`: when Controlled folder access is on and
  the novel's folder is protected, the tool never tries to write there (so
  Windows shows no "unauthorized changes blocked" notice). It uses
  `%OneDrive%\literary-critic\<work>\` when OneDrive is set up, otherwise
  `%USERPROFILE%\literary-critic\<work>\`, and the chat says where, once.
  Backups, logs and caches never go under a protected folder. Tested by unit
  tests with Controlled folder access faked on and off over the same layouts.
- [ ] `update_notice_hours <= 24`: after a release is published, the
  writer's first conversation more than 24 h later tells them a newer version
  exists. With auto-update (Option C) the measure is
  `auto_update_applied_restarts <= 1` instead: the new version runs after at
  most one restart of the app, with no writer action.
- [ ] `update_false_alarms == 0` over the scripted cases: installed version
  older, equal and newer than the latest release; offline; a source checkout
  (tests only, since there is no dev entry); a release that has no `.mcpb`
  asset.
- [ ] `update_check_added_ms <= 100` on any tool call. The check runs in the
  background, at most one network request a day, and says nothing on any
  failure. Measured with the network mocked slow (10 s) and refused.
- [ ] `writer_update_actions <= 3` when the writer updates by hand: click the
  link the chat gives, drag the file onto the window, press Install. The
  folders, the settings and every work's state are still there afterwards
  (`state_kept_after_update == 1.0`).
- [ ] `update_notice_plain == 1` (install D-2 kept): at most 40 words, no
  version numbers, file names or commands unless the writer asks with
  `[[...]]`, once per conversation, never while a change is being applied.
  Judged on the test run.
- [ ] `bundle_lock_exact == 1`: in the installed extension, the versions of
  doc-control, pywin32 and every other package equal the ones in the
  release's `uv.lock`. CI checks `uv lock --check`, and the release smoke test
  compares the installed versions with the lock.
- [ ] `live_engine_ready == 1`: on the clean PC, pywin32 imports in the
  installed environment and doc-control's `live.status` answers with Word
  open.
- [ ] `release_on_tag == 1`: a `vX.Y.Z` tag whose version matches
  `pyproject.toml` produces a GitHub Release. It carries
  `literary-critic-X.Y.Z.mcpb` and `SHA256SUMS`, and it is built and
  smoke-tested by CI with no human step. `mcpb validate` reports 0 errors.
- [ ] `doccontrol_release_to_bump_pr_days <= 1`: a new doc-control release
  inside the pinned range opens a bump PR within a day. A release outside the
  range opens an issue instead.
- [ ] `standalone_doccontrol_reported == 1.0`: when the doc-control extension
  or a doc-control entry in the app's config is present, `resume` reports it
  once, and the chat tells the writer in one plain sentence how to remove it.
  Fixtures: extension enabled, extension disabled, config entry, none. A
  disabled extension is not reported.
- [ ] `fix_to_owner_hours <= 24`: with no dev entry (D-11), a fix merged to
  `main` that touches what the extension runs is released, and runs on the
  owner's PC after at most one restart of the app, within a day of the merge.
  When the owner asks the chat to update, the check runs at once, ignoring the
  daily limit (`update_now_restarts <= 1`).
- [ ] `approval_questions_after_setup == 0`: after the first session, the app
  asks no per-tool approval question in an ordinary session (open a work,
  locate, approve two changes, show places). The first session asks at most
  one question per group the app offers, or one per tool if it offers no
  groups, and the chat tells the writer beforehand, in plain words, which
  answer to pick. Counted on the clean-PC test run (Q-7).

<!-- -->

> **✎ Notes** · `SPEC §1`
> _(your notes here — replace this line)_

## §2 Systems & Impact

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `extension/` (new): `manifest.json`, icon, the bundle's `pyproject.toml` | Primary | What the app installs | Yes | Server type `uv`; one `directory` setting; the version stamped from the tag | High |
| `scripts/pack_mcpb.py` (new) | Primary | Builds the `.mcpb` (stdlib `zipfile`) | Yes | Source, `prompts/`, `src/litcritic/ui/`, `uv.lock` and a `VERSION` stamp; no venv | Med |
| `.github/workflows/release.yml` (new), `ci.yml` | Infrastructure | Builds, validates and smoke-tests the bundle; publishes the Release | Yes | Release on tag; manifest check and pack on every PR | Med |
| `src/litcritic/kit.py` (`version_info`, `update_check`) | Primary | Version and update check | Yes | Source `mcpb`; reads the latest GitHub Release and its `.mcpb` asset, not tags; runs in the background | Med |
| `src/litcritic/mcp.py` (`works`, `resume`, tool list) | Primary | Tells the chat about updates and a standalone doc-control; describes the tools to the app | Yes | Additive fields; the guide gains the update, doc-control and approval sentences; every tool gets read-only or write annotations | Med |
| `src/litcritic/folders.py`, `workspace.py` | Primary | Where state and working folders live | Yes | Working state stays beside the novel; a fallback place when Controlled folder access protects that folder | Med |
| `src/litcritic/docx_cli.py` (`apply_edits`) | Primary | The one write path for approved changes | Yes | With the document closed, open it in Word and apply live instead of writing the file | Med |
| `src/litcritic/winblock.py` | Dependent | Explains a Windows refusal | Small | Stays as the last resort; should no longer fire | Low |
| doc-control (PyPI, `>=0.8.3,<0.9`) | External dependency | Word engines, `live.*`, backup store | No (validation) | Used as published; `DOC_CONTROL_STORE=appdata` for any file write that remains | Med |
| Claude desktop app | Host | Installs `.mcpb`, provides uv, runs the server | No (outside our control) | Its uv-type behaviour is undocumented in part (§2 facts) | High |
| GitHub Releases of this repo | Shared resource | "Latest version" and the download | Yes | First release ever; the repo is public, so the unauthenticated API works | Med |
| Owner's `claude_desktop_config.json` | Infrastructure | `literary-critic-dev` entry | Yes (D-11) | Removed once the extension is installed; `folders.json` is shared, so nothing is lost | Low |
| `desktop` plan tasks T1, T8, T10 | Dependent | Probes, packaging, test run | Yes | T8 is replaced by this spec's tasks; T1's probes and T10's test run happen on the released bundle | Med |

**Facts this rests on** (checked 2026-10-16). Items marked *[app]* come from
reading the installed app's code (`app.asar`, version 2.42304). They are
verified but undocumented, and may change in any app release.

- **Server types.** The MCPB manifest
  ([MANIFEST.md](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md))
  has four server types:
  - `node`: Node.js ships with the app.
  - `python`: every dependency is bundled under `server/lib` or `server/venv`,
    and the user's own Python runs it.
  - `binary`: self-contained.
  - `uv` (manifest 0.4 and later): the bundle carries `pyproject.toml`, must
    not carry a venv, and "the host manages execution".
- **The `uv` type on Windows** *[app]*: at install the app downloads uv 0.9.7
  from uv's GitHub releases (with a pinned checksum) and runs `uv sync` in the
  unpacked extension folder. uv fetches a managed Python unless a feature flag
  says to use the system one. The install dialog says it needs "to fetch a few
  dependencies". So the writer needs internet at install, and nothing else.
  This answers the documentation half of desktop Q-3. The clean-PC run (desktop
  T1) is still the proof.
- **The `python` type** *[app]* needs a system Python matching
  `compatibility.runtimes.python`. Otherwise it reports "no-python-installed".
  So it costs the writer a Python install.
- **pywin32.** Under `uv` it installs as a normal wheel into a real venv, and
  its `.pth` start-up file sets up its DLLs. Under `python` with `server/lib` on
  `PYTHONPATH`, that file is not processed (inferred from how Python handles
  `.pth` files), so it would need hand-made DLL set-up.
- **Updates.** "Extensions from the official directory update automatically
  by default"; a privately distributed `.mcpb` is updated by installing the
  newer file
  ([help article](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)).
  The manifest has no update URL and no private registry field. The directory
  no longer accepts local-server extensions (desktop r5, doc-control D-P5). An
  organisation owner can "Upload new version" of a custom extension for the
  organisation, which does not apply to a writer on a personal plan.
- **Reinstall** *[app]*: extensions are stored by id
  (`local.mcpb.<author>.<name>`), with their settings in a separate file,
  `Claude Extensions Settings\<id>.json`. A newer `.mcpb` with the same `name`
  should replace the old one and keep its settings. That is inferred, to be
  confirmed on the clean PC.
- **Where it unpacks** *[app]*: `%APPDATA%\Claude\Claude Extensions\<id>\`.
  On the packaged (MSIX) app, every `%APPDATA%` and `%LOCALAPPDATA%` write by
  the app and its child processes goes to
  `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\…`
  ([claude-code#27041](https://github.com/anthropics/claude-code/issues/27041)).
  The owner's `mcp.log` lives there too. Windows deletes that folder when the
  app is uninstalled or reset, so it must never hold the writer's work.
- **Signing.** `mcpb sign` appends a PKCS#7 signature
  ([CLI.md](https://github.com/modelcontextprotocol/mcpb/blob/main/CLI.md))
  and needs the certificate's private key as a PEM file. The app records each
  bundle as `signed`, `self-signed` or `unsigned` *[app]*, and refuses an
  unsigned one only under an organisation policy. The owner saw several
  warnings when installing an unsigned probe (desktop r4). The documentation
  does not say which ones signing removes. Since 2023, public code-signing
  keys must live on hardware or a cloud HSM, so a PEM key for a CA-issued
  certificate is not normally obtainable (inferred).
- **Antivirus.** PyInstaller executables are a common source of Defender
  machine-learning false positives (unsigned bootloader). Onedir and signing
  reduce them but do not remove them. doc-control hit this on the owner's PC.
  The `uv` type runs no executable of ours, only uv's and the python.org-built
  standalone Python, both widely deployed.
- **Controlled folder access** is off by default on Windows 11; the writer,
  or whoever manages the PC, turns it on in Windows Security. When on, it
  blocks writes by programs it does not trust in Documents, Desktop, Pictures,
  Videos, Music and Favorites, and in any folder added to its list. With
  OneDrive backing up Documents, that includes `OneDrive\Documents`. The
  OneDrive folder itself (`%OneDrive%`) is not on the default list, so it is
  both backed up and writable. Whether it is on, and which folders it
  protects, is in Defender's settings (`Get-MpPreference`, or the registry
  under `Windows Defender Exploit Guard\Controlled Folder Access`); whether a
  normal user can read them is a probe (Q-8). An allowed program
  is identified by its full path. Under the `uv` type that path is the
  uv-managed `python.exe`, which changes with each Python update, so an
  exception would have to be granted again and again. Word is trusted, so
  Word's own saves are never blocked.
- **What literary-critic writes today:**

  | Write | Where | Protected when the novel is in Documents? |
  |---|---|---|
  | Working state: Codex, index, rounds, `log/edits.jsonl`, `.cache` | `<novel>/literary-critic/` (chat D-10) | yes |
  | Comments copy | `<novel>/literary-critic/revisions/round-NN/` | yes |
  | An approved change, document open in Word | Word, through `live.*`; Word saves | no (Word is trusted) |
  | An approved change, document closed | the `.docx` itself, by doc-control's file engine | yes |
  | doc-control's backup of that change | `<novel>/.doc-control/` (doc-control's default "adjacent" store) | yes |
  | `folders.json`, `mcp.log` | `%APPDATA%\literary-critic\` (virtualised under MSIX) | no |
  | Update cache | the temp folder | no |

- **Approval questions** (not verifiable from the app's local code, since the
  chat screen is web code it loads; to confirm in Q-7). The app asks before a
  chat uses a local tool for the first time, with "Allow once" and "Always
  allow". Its connector settings list each server's tools, grouped as
  read-only or write tools by the annotations the server declares
  (`readOnlyHint`, `destructiveHint`), and can set a whole group to "Always
  allow". A server cannot grant itself permission; the manifest has no field
  for it. The app's code does hold per-tool policies (`always_allow`,
  `always_ask`, `always_deny`) *[app]*. literary-critic declares no
  annotations today, so every tool counts as a write tool.

**Risk of inaction**: the tool runs only on the developer's PC. A writer who
gets a copy some other way runs it without updates. On a PC with Controlled
folder access on, its first write into Documents is blocked.

<!-- -->

> **✎ Notes** · `SPEC §2`
> _(your notes here — replace this line)_

## §3 Options

Every option keeps:

- desktop D-5 and D-13: one `.mcpb`, installed by dragging it onto the app's
  window;
- desktop D-6: doc-control bundled as a library, so the writer installs
  nothing else;
- install D-2: the update check is a script, silent when it does not know;
- the change card (#227) as the only way to change the manuscript.

<!-- -->

> **✎ Notes** · `SPEC §3`
> _(your notes here — replace this line)_

### Option A: a uv bundle with an update notice (Conservative)

- **Description**:
  - The `.mcpb` uses server type `uv`. It carries the source, `prompts/`,
    the places page, `pyproject.toml` with `doc-control[live]` on Windows, and
    `uv.lock`, so the app's `uv sync` installs exactly the locked versions.
  - A tag builds and publishes it (the release flow below).
  - `kit.update_check` learns the `mcpb` source and reads the latest GitHub
    Release. When a newer `.mcpb` exists, `resume` says so, and the chat gives
    the writer the download link and "drag it onto this window".
  - Working folders stay beside the novel. When Windows blocks a write,
    `winblock` explains how to allow the program.
  - Every tool still asks for approval the first time.
- **Scope**: `extension/`, `scripts/pack_mcpb.py`, `release.yml`, `kit.py`,
  `mcp.py`.
- **Effort**: Medium
- **Tradeoffs**: Smallest change, no exe, nothing to sign. But it fails
  `security_detections == 0` on any PC with Controlled folder access on: the
  first write into Documents is blocked. The fix it offers is an exception for a `python.exe`
  path that changes with updates, and that is the kind of step the writer
  cannot take. It also leaves updates manual.
- **Compatibility**: Additive.

<!-- -->

> **✎ Notes** · `SPEC › Option A: a uv bundle with an update notice (Conservative)`
> _(your notes here — replace this line)_

### Option B: Option A, plus no security exception and a pinned release flow (Recommended baseline)

- **Description**: Option A, and:
  1. **Working state beside the novel, never blocked** (Q-1 answered).
     - The working state stays in `<novel>/literary-critic/` (chat
       D-10), so it is on OneDrive whenever the novel is, and backed up with
       it.
     - Before the first write for a work, the tool asks Defender whether
       Controlled folder access is on and whether the novel's folder is
       protected. If both, it never tries that folder (no Windows notice) and
       uses `%OneDrive%\literary-critic\<work>\` when OneDrive is set up,
       otherwise `%USERPROFILE%\literary-critic\<work>\`. Both survive
       uninstalling the Claude app. The chat says once, in plain words, where
       the work's files are. If Defender's settings cannot be read, the tool
       tries the novel's folder, and a refused write moves the work to the
       same fallback without a second attempt.
     - The choice is recorded per work in `folders.json`, so `works` and
       `resume` find the work by its manuscript wherever its state is. If the
       writer later turns Controlled folder access off, the work stays where
       it is.
     - The comments copy goes with the working state.
  2. **The manuscript is changed only by Word.** When an approved change
     targets a document that is not open, `apply_edits` asks the live engine
     to open it in Word, applies the change there, and lets the writer save
     it, which needs no exception. The file engine never writes the
     manuscript. If Word is missing, the change card says what to change and
     where, and the writer types it.
  3. **Backups away from the novel.** The server starts doc-control with
     `DOC_CONTROL_STORE=appdata`, so no `.doc-control/` folder appears beside
     the manuscript. Live changes have no file backup anyway; Word's undo
     takes them back.
  4. **A standalone doc-control is reported.** `resume` reads the app's
     `extensions-installations.json` and `claude_desktop_config.json` and adds
     `other_doc_control: {kind, name}`. The guide turns it into one
     sentence: "You also have a separate doc-control extension. This tool
     already includes it; please remove it in Settings → Extensions so every
     change goes through your approval." A server cannot stop the chat from
     calling another server, so this is a report, not a block.
  5. **Release flow.**
     - With no dev entry (D-11), every fix reaches the owner through a
       release. So each merged PR that changes what the extension runs
       (`src/`, `prompts/`, `pyproject.toml`, `uv.lock`, `extension/`) is
       followed the same day by a patch release.
     - Merging a PR that bumps `pyproject.toml`'s version tags `vX.Y.Z`.
     - The tag runs `release.yml` on `windows-latest`:
       - `uv lock --check`;
       - pack and `mcpb validate`;
       - a smoke test that unpacks the bundle, runs uv 0.9.7's `uv sync` with
         no system Python, and drives `initialize`, `tools/list` and `works`
         over JSON-RPC;
       - the installed versions compared with `uv.lock`;
       - the Release published with the `.mcpb` and `SHA256SUMS`, and release
         notes in plain words.
     - A daily workflow watches doc-control on PyPI. A new version inside the
       range runs `uv lock --upgrade-package doc-control` and opens a bump PR
       that also bumps the patch version, so merging it releases. A version
       outside the range opens an issue (the range is a code decision).
  6. **The update notice, made dependable.**
     - The check runs in a background thread when the server starts, at most
       once a day, and adds nothing to any tool call.
     - It reads `releases/latest` and needs a `.mcpb` asset, so a tag without
       a published bundle is never announced.
     - `resume` and `works` return `update: {available, url}`. `url` is the
       Release page, which one click opens in the browser; it is not a
       direct download.
     - Kept from install D-2: one plain sentence, once a conversation.
     - "Update now": when the writer or the owner asks the chat to update,
       `works` with `check_update: true` checks at once, ignoring the daily
       limit.
  7. **Few approval questions.**
     - Every tool declares MCP annotations: `readOnlyHint: true` on tools
       that only read (`works`, `resume`, `locate`, `find`, `show`, `places`,
       `ask`), and `destructiveHint: false` on the ones that write only the
       tool's own state. `change_card` is a write tool; its card is the
       writer's real approval of each change.
     - At setup the chat warns, in plain words, that the app will ask
       permission for the tool and that "Always allow" stops it asking
       again, and says where the setting is in case the writer picked
       "Allow once".
     - No new tool is added for anything an existing one can carry as a
       field.
- **Scope**: Option A, plus `folders.py`, `workspace.py` (the fallback place),
  a Controlled-folder-access reader beside `winblock.py`,
  `docx_cli.apply_edits`, the doc-control environment and tool annotations in
  `mcp.py`, a detection module, `.github/workflows/doccontrol-bump.yml`, the
  guide in `prompts/01-chat-guide.md`, and tests for each.
- **Effort**: Medium–Large
- **Tradeoffs**:
  - It meets every criterion except auto-update: an update costs the writer
    three actions each time.
  - The working state stays beside the novel except on a PC that protects
    the novel's folder; there it goes to OneDrive's root, which is backed up
    and not protected. A writer who has no OneDrive and protects Documents
    gets a folder with no backup, and the chat says where it is.
  - A closed document is opened in Word to apply a change, and the writer
    sees Word open. That is visible but honest: the writer saves it.
- **Compatibility**: Additive for the server's tools. Existing working
  folders stay where they are.

<!-- -->

> **✎ Notes** · `SPEC › Option B: Option A, plus no security exception and a pinned release flow (Recommended baseline)`
> _(your notes here — replace this line)_

### Option C: Option B, plus self-update (Chosen, in two phases)

- **Description**: Option B is phase 1. Phase 2 adds automatic updates of the
  tool's code. The app cannot do that for a privately distributed extension
  (§2), so the extension does it itself:
  - **Launcher.** The bundle's entry point is a small standard-library
    launcher, `extension/launch.py`. It starts the newest healthy runtime: the
    one the app installed, or a newer one the extension staged earlier.
  - **Staging.** After start, at most once a day, the server checks the
    latest Release. If it is newer and does not set `reinstall: true`, it
    builds a fresh environment with the uv that runs it (the `UV` variable uv
    sets for its children; to be confirmed, Q-5) in
    `%LOCALAPPDATA%\literary-critic\runtime\<X.Y.Z>\`. That environment is
    installed from the Release's pinned requirements, with hashes: the
    literary-critic wheel attached to the Release, and doc-control and
    pywin32 from PyPI. It then runs a self-test (`initialize` and
    `tools/list`) and only then marks the environment ready. Nothing changes
    in the running server.
  - **Switching.** The next time the app starts the server, the launcher
    runs the ready runtime. If it fails to start twice, the launcher marks it
    bad and goes back to the previous one. Two runtimes are kept.
  - **What it cannot update.** A release that changes the manifest (settings,
    server type, the launcher itself) sets `reinstall: true`, and the
    phase-1 notice asks the writer to install the `.mcpb`.
  - **The writer's control** (Q-2 answered). An "Update automatically"
    checkbox (a boolean `user_config` setting) shows in the install dialog and
    in the extension's settings. It is ticked by default, and the writer can
    untick it; then phase 1's notice applies. When an update was applied, the
    chat says so once, afterwards, in plain words.
  - **Update now.** When the writer or the owner asks the chat to update,
    staging runs at once instead of waiting for the daily check, and the chat
    says to restart the app when the new version is ready. This is the
    owner's path from a merged fix to testing it in a chat (D-11).
- **Scope**: Option B, plus `extension/launch.py`, a staging module, release
  assets (wheel plus a hashed requirements file), and tests for staging,
  switching and rollback with fakes.
- **Effort**: Large (phase 2 alone is Medium)
- **Tradeoffs**:
  - It is the only option that gives "install it and forget it":
    `auto_update_applied_restarts <= 1` with no writer action.
  - It runs code the install dialog never showed. That is the same trust as
    the manual path, since the writer would install whatever the Release
    holds, but nobody looks first. A broken release reaches every writer at
    their next restart, so the self-test and rollback are what limits the
    damage.
  - The staged runtimes live in the app's virtualised data, which is
    disposable. Losing them falls back to the bundled runtime.
  - It depends on undocumented app behaviour (uv in the environment). An
    extension that updates its own code would also likely be refused by any
    future directory listing (inferred).
- **Compatibility**: Phase 1 releases can be updated to phase 2 only by
  reinstalling once. Every release after that updates itself.

<!-- -->

> **✎ Notes** · `SPEC › Option C: Option B, plus self-update (Chosen, in two phases)`
> _(your notes here — replace this line)_

### Rejected: a frozen exe (binary type, like doc-control's packaging)

Every option avoids it. It would bring the Defender false positives the owner
already met with doc-control. Removing them needs Authenticode signing:
Azure Trusted Signing at about $10 a month after identity validation, or an
OV or EV certificate at a few hundred dollars a year with the key on a
hardware token or cloud HSM (doc-control `PACKAGE` §3). Even signed, a new
file builds SmartScreen reputation only over time. The `uv` type needs none of
this, because no executable of ours runs.

<!-- -->

> **✎ Notes** · `SPEC › Rejected: a frozen exe (binary type, like doc-control's packaging)`
> _(your notes here — replace this line)_

### Comparison

| | Option A | Option B | Option C |
|---|---|---|---|
| Effort | Medium | Medium–Large | Large (B + Medium) |
| Risk | High usability risk (Windows blocks writes wherever Controlled folder access is on) | Medium (fallback place on protected PCs; Word opens for a closed document) | Medium–High (self-update depends on undocumented uv behaviour; a bad release spreads by itself) |
| Completeness | Install and notice only; fails `security_detections` | Every criterion; updates take 3 writer actions | Every criterion; updates take 0 actions after phase 2 |
| Compatibility | Additive | Additive; state stays beside the novel (chat D-10 kept) | As B; one manual reinstall into phase 2 |
| Maintenance | Release workflow | + bump workflow, detection, tool annotations | + launcher, staging, rollback, extra release assets |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Chosen option** (owner, 2026-10-16): Option C, built in two phases. Phase 1
is Option B and is worth shipping alone:

- one drag installs everything, with no exe and nothing to sign;
- nothing trips Windows Security, and the app stops asking for approval after
  the first session;
- doc-control stays pinned;
- the writer is told about every release within a day.

Phase 2 adds what the owner asked for first, the tool updating itself. It goes
after phase 1 because its launcher has to be in the bundle the writer installs
once, and it rests on app behaviour (Q-5) that the clean-PC run checks first.

With no dev entry (D-11), phase 2 matters for the owner too: until it ships,
every fix the owner tests in a chat costs a manual reinstall. So the plan
keeps phase 1 short and starts phase 2 right after it.

**Immediate next action**: the owner approves this revision, then `design`
plans both phases. Its first task packs the bundle in CI and runs the
`desktop` T1 probe on the clean PC with that bundle. That gives desktop Q-3
(no uv, no Python), desktop Q-8 (the install warnings), Q-5, Q-6, Q-7 and Q-8
in one run.

**Open questions**:
- [x] **Q-1 (owner):** where does the working state live? Answered: beside
  the novel, so on OneDrive when the novel is. A fallback place only where
  Controlled folder access protects the novel's folder (§3 B.1, D-3).
- [x] **Q-2 (owner):** is "Update automatically" on by default? Answered: it
  can be turned off, and is on by default (D-8).
- [x] **Q-3 (owner):** keep a developer entry? Answered: no. The installed
  extension is the only version; feedback is gathered, fixed and tested in
  chats (D-11).
- [x] **Q-4 (owner):** sign the `.mcpb`? Answered: not yet (D-12). Revisit
  only if the clean-PC run shows that signing removes a warning the writer
  must accept.
- [ ] **Q-5 (probe):** does the server's process see the uv the app
  installed (the `UV` variable, or a known path), so that phase 2 can build an
  environment without downloading uv again? If not, phase 2 downloads uv into
  its own runtime folder, with a pinned checksum, as the app does.
- [ ] **Q-6 (probe):** does installing a newer `.mcpb` over the old one keep
  the folder setting, the "Update automatically" choice and the extension
  enabled? Inferred yes (§2). If not, the update instructions add the missing
  step, and `writer_update_actions` is re-counted.
- [ ] **Q-7 (probe):** which approval questions does the app ask for a local
  extension's tools: per tool or per group, per chat or for good, and does
  "Always allow" in the connector settings cover a whole group? The setup
  sentence and `approval_questions_after_setup` follow what the probe shows.
- [ ] **Q-8 (probe):** can a normal user's process read whether Controlled
  folder access is on and which folders it protects? If not, the tool tries
  the novel's folder once and falls back on refusal, and Windows shows its
  notice that one time; `cfa_fallback_correct` then allows that single notice.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| chat D-10 | Working files in `<novel>/literary-critic/` | agreed (kept by D-3) | 2026-10-11 |
| install D-2 | The update check is a script, silent when it does not know; one plain sentence, never mid-change | agreed (kept; now reads Releases and runs in the background) | 2026-10-14 |
| desktop D-5, D-13 | One `.mcpb`, installed by dragging it onto the app's window | agreed (kept) | 2026-10-14 |
| desktop D-6 | doc-control is bundled as a library | agreed (kept) | 2026-10-14 |
| doc-control D-P3 | doc-control ships its own exe unsigned | noted; literary-critic ships no exe (D-1) | 2026-10-14 |
| D-1 | Server type `uv`; no executable of ours, so nothing for Authenticode to sign | agreed | 2026-10-16 |
| D-2 | `uv.lock` ships in the bundle; CI fails when it does not match `pyproject.toml` | agreed | 2026-10-16 |
| D-3 | Working state beside the novel (on OneDrive when the novel is); where Controlled folder access protects that folder, `%OneDrive%\literary-critic\<work>` or else `%USERPROFILE%\literary-critic\<work>`, chosen before any write | agreed (r2; replaces r1's per-user folder) | 2026-10-16 |
| D-4 | The manuscript is changed only through Word (live engine); the file engine never writes it | agreed | 2026-10-16 |
| D-5 | A Release is cut by merging a version bump; a tag publishes the `.mcpb` and `SHA256SUMS` from CI; a merged fix to what the extension runs is released the same day | agreed | 2026-10-16 |
| D-6 | A doc-control release inside the range reaches writers through an automatic bump PR and a patch release | agreed | 2026-10-16 |
| D-7 | A standalone doc-control is reported once, in plain words; it is not blocked | agreed | 2026-10-16 |
| D-8 | Self-update (phase 2): staged, self-tested, applied on the next start, with rollback; a manifest change still needs a reinstall; an "Update automatically" checkbox, ticked by default | agreed | 2026-10-16 |
| D-9 | This workspace replaces `desktop` T8; `desktop` T1 and T10 run on the released bundle | agreed | 2026-10-16 |
| D-10 | Option C chosen, in two phases | agreed | 2026-10-16 |
| D-11 | No developer entry: the installed extension is the only version on every PC, the owner's included; the `literary-critic-dev` config entry is removed once the extension is installed | agreed | 2026-10-16 |
| D-12 | The `.mcpb` is not signed for now | agreed | 2026-10-16 |
| D-13 | Tools declare read-only or write annotations, and the setup guide tells the writer to answer "Always allow" once | proposed (r2) | 2026-10-16 |


> Sections 5–6 (contracts, risks) are appended by `design`.

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

