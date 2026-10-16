# Literary Critic — Specification (annotated edition)

> Generated 2026-10-16. This is the document with a **note slot** after every section that has text of its own. Read it in any Markdown app. To annotate, replace the `_(your notes…)_` placeholder under any section. When done, send the file back — notes are acted on.

---

# Spec

## Preamble & scope

**Date**: 2026-10-16
**Ticket / PR**: workspace `release`
**Author**: Claude (with the owner)
**Revision**: 1
**Status**: draft
**Revision log**:
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

The tool must also not trip Windows Security on a normal writer's PC. Two
parts of it do:

- **Controlled folder access** ("ransomware protection") blocks unknown
  programs from writing in Documents, Desktop and similar folders, and novels
  usually live in Documents.
- **Defender and SmartScreen** flag unsigned executables, as they did with
  doc-control's.

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
- [ ] `writer_files_in_protected_folders == 0`: the tool's own files (working
  state, backups, logs, caches) never go under a folder Controlled folder access
  protects by default (`winblock.PROTECTED`). Tested by a unit test over every
  path the tool resolves, with `Documents` and `OneDrive\Documents` layouts.
- [ ] `update_notice_hours <= 24`: after a release is published, the
  writer's first conversation more than 24 h later tells them a newer version
  exists. With auto-update (Option C) the measure is
  `auto_update_applied_restarts <= 1` instead: the new version runs after at
  most one restart of the app, with no writer action.
- [ ] `update_false_alarms == 0` over the scripted cases: installed version
  older, equal and newer than the latest release; offline; a source checkout
  (the dev entry); a release that has no `.mcpb` asset.
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
- [ ] `dev_entry_silent == 1`: the developer's `literary-critic-dev` entry
  never shows an update notice and is told apart from the installed extension
  in `works` (`source: checkout` against `source: mcpb`). Judged on the
  owner's PC.

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
| `src/litcritic/mcp.py` (`works`, `resume`) | Primary | Tells the chat about updates and a standalone doc-control | Yes | Additive fields; the guide gains the update and doc-control sentences | Med |
| `src/litcritic/folders.py`, `workspace.py` | Primary | Where state and working folders live | Yes | Working state moves out of protected folders (Q-1); existing folders are copied once | High |
| `src/litcritic/docx_cli.py` (`apply_edits`) | Primary | The one write path for approved changes | Yes | With the document closed, open it in Word and apply live instead of writing the file | Med |
| `src/litcritic/winblock.py` | Dependent | Explains a Windows refusal | Small | Stays as the last resort; should no longer fire | Low |
| doc-control (PyPI, `>=0.8.3,<0.9`) | External dependency | Word engines, `live.*`, backup store | No (validation) | Used as published; `DOC_CONTROL_STORE=appdata` for any file write that remains | Med |
| Claude desktop app | Host | Installs `.mcpb`, provides uv, runs the server | No (outside our control) | Its uv-type behaviour is undocumented in part (§2 facts) | High |
| GitHub Releases of this repo | Shared resource | "Latest version" and the download | Yes | First release ever; the repo is public, so the unauthenticated API works | Med |
| Owner's `claude_desktop_config.json` | Infrastructure | `literary-critic-dev` entry | Owner's choice (Q-3) | Kept beside the extension or not | Low |
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
- **Controlled folder access** blocks writes by programs it does not trust in
  Documents, Desktop, Pictures, Videos, Music and Favorites. With OneDrive
  backing up Documents, that includes `OneDrive\Documents`. An allowed program
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

**Risk of inaction**: the tool runs only on the developer's PC. A writer who
gets a copy some other way runs it without updates. On most writers' PCs its
first write into Documents is blocked once Controlled folder access is on.

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
- **Scope**: `extension/`, `scripts/pack_mcpb.py`, `release.yml`, `kit.py`,
  `mcp.py`.
- **Effort**: Medium
- **Tradeoffs**: Smallest change, no exe, nothing to sign. But it fails
  `security_detections == 0` on most writer PCs: the first write into
  Documents is blocked. The fix it offers is an exception for a `python.exe`
  path that changes with updates, and that is the kind of step the writer
  cannot take. It also leaves updates manual.
- **Compatibility**: Additive.

<!-- -->

> **✎ Notes** · `SPEC › Option A: a uv bundle with an update notice (Conservative)`
> _(your notes here — replace this line)_

### Option B: Option A, plus no security exception and a pinned release flow (Recommended baseline)

- **Description**: Option A, and:
  1. **Nothing of ours in protected folders.**
     - Working state moves to a per-user folder outside every protected
       folder and outside the app's virtualised data (Q-1). The proposal is
       `%USERPROFILE%\literary-critic\works\<work>\`, which survives
       uninstalling the Claude app.
     - A work is still found by its manuscript, so `works` and `resume` are
       unchanged for the writer.
     - An existing `<novel>/literary-critic/` folder is copied there once,
       on first use, and left where it was.
     - The comments copy goes to the working state, and the chat tells the
       writer where it is.
  2. **The manuscript is changed only by Word.** When an approved change
     targets a document that is not open, `apply_edits` asks the live engine
     to open it in Word, applies the change there, and lets the writer save
     it, which needs no exception. The file engine never writes the
     manuscript. If Word is missing, the change card says what to change and
     where, and the writer types it.
  3. **Backups away from the novel.** The server starts doc-control with
     `DOC_CONTROL_STORE=appdata`, so no `.doc-control/` folder appears beside
     the manuscript.
  4. **A standalone doc-control is reported.** `resume` reads the app's
     `extensions-installations.json` and `claude_desktop_config.json` and adds
     `other_doc_control: {kind, name}`. The guide turns it into one
     sentence: "You also have a separate doc-control extension. This tool
     already includes it; please remove it in Settings → Extensions so every
     change goes through your approval." A server cannot stop the chat from
     calling another server, so this is a report, not a block.
  5. **Release flow.**
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
- **Scope**: Option A, plus `folders.py`, `workspace.py` (with a one-time
  copy), `docx_cli.apply_edits`, the doc-control environment in `mcp.py`, a
  detection module, `.github/workflows/doccontrol-bump.yml`, the guide in
  `prompts/01-chat-guide.md`, and tests for each.
- **Effort**: Medium–Large
- **Tradeoffs**:
  - It meets every criterion except auto-update: an update costs the writer
    three actions each time.
  - It moves state away from the novel. That supersedes chat D-10. The
    working state also loses OneDrive's backup unless Q-1 picks a backed-up
    place that is not protected, and on Windows none is both by default.
  - A closed document is opened in Word to apply a change, and the writer
    sees Word open. That is visible but honest: the writer saves it.
- **Compatibility**: Additive for the server's tools. Old working folders are
  copied, not moved, so a downgrade still finds them.

<!-- -->

> **✎ Notes** · `SPEC › Option B: Option A, plus no security exception and a pinned release flow (Recommended baseline)`
> _(your notes here — replace this line)_

### Option C: Option B, plus self-update (Recommended, in two phases)

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
  - **The writer's control.** An "Update automatically" setting in the
    install dialog (Q-2). When it is on, the chat says once, afterwards, that
    the tool was updated, in plain words.
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

> **✎ Notes** · `SPEC › Option C: Option B, plus self-update (Recommended, in two phases)`
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
| Risk | High usability risk (Windows blocks on most PCs) | Medium (moved state; Word opens for a closed document) | Medium–High (self-update depends on undocumented uv behaviour; a bad release spreads by itself) |
| Completeness | Install and notice only; fails `security_detections` | Every criterion; updates take 3 writer actions | Every criterion; updates take 0 actions after phase 2 |
| Compatibility | Additive | Additive; state copied once (supersedes chat D-10) | As B; one manual reinstall into phase 2 |
| Maintenance | Release workflow | + bump workflow, detection | + launcher, staging, rollback, extra release assets |

<!-- -->

> **✎ Notes** · `SPEC › Comparison`
> _(your notes here — replace this line)_

## §4 Recommendation

**Recommended option**: Option C, built in two phases. Phase 1 is Option B and
is worth shipping alone:

- one drag installs everything, with no exe and nothing to sign;
- nothing trips Windows Security;
- doc-control stays pinned;
- the writer is told about every release within a day.

Phase 2 adds what the owner asked for first, the tool updating itself. It goes
after phase 1 because its launcher has to be in the bundle the writer installs
once, and it rests on app behaviour (Q-5) that the clean-PC run checks first.

**Immediate next action**: the owner answers Q-1 to Q-4, then `design` plans
phase 1. Its first task packs the bundle in CI and runs the `desktop` T1 probe
on the clean PC with that bundle. That gives Q-3 (no uv, no Python), desktop
Q-8 (the install warnings), the reinstall check (settings kept) and Q-5 (uv
reachable from the server) in one run.

**Open questions**:
- [ ] **Q-1 (owner):** where does the working state live?
  - Recommended: `%USERPROFILE%\literary-critic\` (survives uninstalling the
    app; not protected; not backed up by OneDrive).
  - `%LOCALAPPDATA%`: lost when the Claude app is uninstalled or reset, under
    MSIX.
  - Beside the novel, as today (needs an exception on most PCs).

  Whichever is chosen, the chat can tell the writer where it is, and
  `lc pack` makes a backup zip on request.
- [ ] **Q-2 (owner):** in phase 2, is "Update automatically" on by default?
  Recommended: on, as the owner's wording asks, with the setting in the
  install dialog.
- [ ] **Q-3 (owner):** the developer's own entry. Recommended:
  - Keep `literary-critic-dev` (`uv run --directory <clone> lc mcp <folder>`)
    beside the installed extension, so the dev PC also runs what writers run.
  - Turn the extension off in Settings → Extensions while developing; two
    servers with the same tools in one chat confuse the model.
  - Turn it back on, and remove or rename the dev entry, for a test run.
  - Give the dev entry its own state file (`LITCRITIC_FOLDERS`), so the two do
    not share `folders.json`.
  - The dev entry reports `source: checkout` and never sees an update notice.
- [ ] **Q-4 (owner):** sign the `.mcpb`? Recommended: no, for now. A
  self-signed signature changes nothing for a writer. A CA-issued signature
  needs a private key the CA will not hand out as a file (§2). Revisit only if
  the clean-PC run shows that signing removes a warning the writer must accept.
- [ ] **Q-5 (probe):** does the server's process see the uv the app
  installed (the `UV` variable, or a known path), so that phase 2 can build an
  environment without downloading uv again? If not, phase 2 downloads uv into
  its own runtime folder, with a pinned checksum, as the app does.
- [ ] **Q-6 (probe):** does installing a newer `.mcpb` over the old one keep
  the folder setting and the extension enabled? Inferred yes (§2). If not,
  the update instructions add the folder step, and `writer_update_actions` is
  re-counted.

**Decisions log**:

| ID | Decision | Status | Date |
|----|----------|--------|------|
| chat D-10 | Working files in `<novel>/literary-critic/` | superseded by D-3, if approved | 2026-10-11 |
| install D-2 | The update check is a script, silent when it does not know; one plain sentence, never mid-change | agreed (kept; now reads Releases and runs in the background) | 2026-10-14 |
| desktop D-5, D-13 | One `.mcpb`, installed by dragging it onto the app's window | agreed (kept) | 2026-10-14 |
| desktop D-6 | doc-control is bundled as a library | agreed (kept) | 2026-10-14 |
| doc-control D-P3 | doc-control ships its own exe unsigned | noted; literary-critic ships no exe (D-1) | 2026-10-14 |
| D-1 | Server type `uv`; no executable of ours, so nothing for Authenticode to sign | proposed | 2026-10-16 |
| D-2 | `uv.lock` ships in the bundle; CI fails when it does not match `pyproject.toml` | proposed | 2026-10-16 |
| D-3 | No tool file under a protected folder; working state in a per-user folder (Q-1), copied once from the old place | proposed | 2026-10-16 |
| D-4 | The manuscript is changed only through Word (live engine); the file engine never writes it | proposed | 2026-10-16 |
| D-5 | A Release is cut by merging a version bump; a tag publishes the `.mcpb` and `SHA256SUMS` from CI | proposed | 2026-10-16 |
| D-6 | A doc-control release inside the range reaches writers through an automatic bump PR and a patch release | proposed | 2026-10-16 |
| D-7 | A standalone doc-control is reported once, in plain words; it is not blocked | proposed | 2026-10-16 |
| D-8 | Self-update (phase 2): staged, self-tested, applied on the next start, with rollback; a manifest change still needs a reinstall | proposed | 2026-10-16 |
| D-9 | This workspace replaces `desktop` T8; `desktop` T1 and T10 run on the released bundle | proposed | 2026-10-16 |


> Sections 5–6 (contracts, risks) are appended by `design`.

<!-- -->

> **✎ Notes** · `SPEC §4`
> _(your notes here — replace this line)_

