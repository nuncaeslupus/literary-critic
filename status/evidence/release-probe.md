# Clean-PC probe of the released bundle (owner, 2026-10-17)

Plan: `arsenal/project/release/plan.md` T3. Bundle: the v0.1.1 Release asset
`literary-critic-0.1.1.mcpb` (sha256 `a41bfa453f1536b6d6b63e59056ff672fd3535e0503a76b2163c43b26c193a09`,
checked against `SHA256SUMS`). PC: Windows Sandbox (8 GB, vGPU off; the first run
with 4 GB and the default vGPU closed itself while the app installed), Claude
desktop app installed from claude.ai/download, Spanish UI. No `python`, `py`,
`uv` or `uvx` on the machine. Defender does not run in Sandbox, so Controlled
folder access was read on the host instead (Q-8).

## Desktop Q-8: the install path and its warnings

**Answer: yes**, the bundle installs, with one red warning and one confirmation.

- Dragging the `.mcpb` onto a chat **attaches it to the conversation**; it does
  not install. Double-clicking it opens Windows' "choose an app" dialog: the app
  registers no `.mcpb` association. The route that works is Settings →
  Extensions, then dropping the file on that page.
- Install card: the manifest's name and description, "Requisitos: Todos los
  requisitos cumplidos" (with no Python and no uv), and one red warning,
  verbatim: "La instalación otorgará a esta extensión acceso a todo lo que hay
  en tu computadora. La información del desarrollador que se muestra no ha sido
  verificada por Anthropic. Asegúrate de confiar en la fuente de esta extensión
  antes de instalarla." Button: Instalar.
- Then a native dialog: "¿Instalar extensión?" / "¿Desea instalar Literary
  Critic?" / "Esta extensión de escritorio se instalará en su computadora. Para
  instalar esta extensión, necesitamos descargar algunas dependencias. Esto
  puede tomar algunos minutos." [Instalar] [Cancelar].
- "Instalando… 20.8 MB / 20.8 MB", done in about one minute; the extension
  shows "Habilitada".
- Writer actions from a downloaded file: open Settings, open Extensions, drop
  the file, Instalar, Instalar — five, not the three the spec counts.
- The app records the bundle as `signatureInfo.status: "unsigned"`, `source:
  "local"`. No SmartScreen or Defender prompt (Defender off in Sandbox).

## Desktop Q-3: does the server start with no Python and no uv?

**Answer: yes.** `mcp.log` logged the start two seconds after the install:
literary-critic 0.1.1, doc-control 0.8.3, Python from the extension's `.venv`
(a uv-managed CPython 3.14.0 under the app's Roaming folder). `works` answered
the versions in a chat. `win32com.client` and `pywintypes` import from that
environment (Word itself is not in Sandbox).

- The app started the server **twice** (two start lines, two `uv` and two
  `python` processes) for one install, and again for the update.

## Q-5: does the server see the app's uv?

**Answer: yes.** The server's environment has
`UV=%APPDATA%\Claude\uv-runtime\uv-0.9.7-win32-x64\uv.exe` (under MSIX
virtualisation); `uv` is not on `PATH`.

## Q-6: does a reinstall keep the settings?

**Answer: yes.** A newer bundle (a local 0.1.2 build, never published) dropped
on Settings → Extensions over 0.1.1 opens the installed extension's card with
an **Actualizar** button and the same red warning, then the same native
"¿Instalar extensión?" dialog. After it:

- The novels' folder was kept, the extension stayed "Habilitada", and the
  tools allowed with "Permitir siempre" (Resume, Works) stayed allowed, now
  shown as such on the settings page. The app's settings file keeps
  `userConfig` (`novels_folder`, `auto_update`) beside `isEnabled`.
- The running server was replaced within a second: `mcp.log` logged 0.1.2
  starting with the folder, with no app restart. Writer actions: open
  Settings, open Extensions, drop the file, Actualizar, Instalar.
- "Update automatically" was left on, so keeping an "off" choice was not seen;
  it lives in the same `userConfig` as the folder that was kept.
- Saving the settings restarts the server once, with the new folder.
- Dropping the **same** file again opens the card with no update button and
  installs nothing.

- The settings are on the extension's page (Settings → Extensions → Literary
  Critic): "Your novels' folder" with an "Agregar directory" button, and
  "Update automatically" (on), then Guardar. The install card asks for neither,
  so the server starts with no folder. The button label is the app's own, half
  translated ("Agregar directory" for the manifest's `directory` type); the
  manifest cannot change it.

## Q-7: which approval questions does the app ask?

**Answer: yes**, per tool, and "always" lasts beyond the chat.

- Settings → Extensions → Literary Critic → "Permisos de herramientas": groups
  "Herramientas interactivas" (2), "Otras herramientas" (11) and "App-only
  tools" (4, with no control). Each tool and each group can be set to allow,
  ask or block; everything starts at "Requiere aprobación".
- First call of a tool in a chat, verbatim: "Claude quiere usar [tool] de
  [Literary Critic]" with [Rechazar Esc] [Permitir siempre Ctrl Shift ⏎]
  [Permitir una vez Ctrl ⏎].
- "Permitir siempre" covers that tool only: the next tool asked again. A new
  chat called the allowed tool with no question, and so did a chat after the
  update. The settings page showed the change only after a reopen.
- So the setup sentence can tell the writer to set the group to allow once on
  the extension's page, or to answer "Permitir siempre" once per tool.

## Q-8: can a normal user read Controlled folder access?

**Answer: yes.** On the host, a medium-integrity (non-admin) PowerShell reads
`Get-MpPreference`: `EnableControlledFolderAccess = 1`; the
`ControlledFolderAccessProtectedFolders` list is empty because the default
protected folders (Documents, Desktop, …) are not listed there. Sandbox cannot
run Defender (`0x800106ba`), so the fallback itself needs a fresh account on a
real PC.

## VirusTotal

0 / 65 for `literary-critic-0.1.1.mcpb` (same sha256 as above), 2026-10-17.
VirusTotal scans the zip but not its members (it holds more than one file).

## Other findings

- **The update check is always "unknown" on a fresh Windows.** The extension's
  Python (OpenSSL 3.5.4) fails `CERTIFICATE_VERIFY_FAILED: unable to get local
  issuer certificate` on `api.github.com`: CPython reads only the roots already
  in the Windows store, and Windows adds a root only when its own TLS asks for
  it, which the Electron app never does. One `Invoke-WebRequest` to the same
  URL (Windows' TLS) installed the root; Python's check then answered `latest
  0.1.1`, `update_available: no`. Phase 2's self-update depends on this.
- Asked "which version?", the model called `resume`, which carries no versions,
  and said it could not tell (in two chats); `works` does carry
  them.
- The model mixed in the account's memory from another PC and described novels
  this PC does not have, although `resume` listed no folders.
