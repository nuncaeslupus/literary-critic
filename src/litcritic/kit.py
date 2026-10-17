"""The chat kit: everything an assistant with code execution needs, in one zip.

The kit holds the stdlib-only package, its data, the schemas, the checklist,
the prompts, ``START_HERE.md`` and an ``lc.py`` launcher. The ``doc_control``
package (the one runtime dependency, stdlib only) is copied in beside
``litcritic`` so the kit runs with no pip and no network. ``doctor`` checks a
platform by running a tiny pipeline in a temporary folder.
"""

from __future__ import annotations

import base64
import contextlib
import importlib.util
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import __version__
from litcritic.workspace import repo_root


class KitError(Exception):
    """The kit cannot be built from here."""


MIN_PYTHON = (3, 11)  # keep in step with requires-python in pyproject.toml
CONTENT = ("src/litcritic", "schemas", "checklist", "prompts", "docs/codex")
LAUNCHER = '''"""Run the literary-critic tool from an unpacked kit: python lc.py <command> ..."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ needed, found {sys.version.split()[0]}")

sys.dont_write_bytecode = True  # the kit's folder may be read-only (an installed Skill)

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from litcritic.cli import main  # noqa: E402

raise SystemExit(main())
'''


VERSION_FILE = "VERSION"  # in a kit or Skill zip: {"version", "built", "source"}


def _stamp(source: str) -> str:
    built = datetime.now(UTC).strftime("%Y-%m-%d")
    return json.dumps({"version": __version__, "built": built, "source": source}) + "\n"


def version_info(root: Path | None = None) -> dict[str, Any]:
    """This copy's version, build date and where it came from: ``kit`` or ``skill``
    (a zip's ``VERSION`` stamp), ``checkout`` (a git work tree) or ``package``."""
    root = root or repo_root()
    stamp = root / VERSION_FILE
    if stamp.is_file():
        with contextlib.suppress(ValueError, OSError):
            d = json.loads(stamp.read_text(encoding="utf-8"))
            return {"version": str(d["version"]), "built": d.get("built"), "source": d["source"]}
    source = "checkout" if (root / ".git").exists() else "package"
    return {"version": __version__, "built": None, "source": source}


RELEASE_URL = "https://api.github.com/repos/nuncaeslupus/literary-critic/releases/latest"
RELEASES_PAGE = "https://github.com/nuncaeslupus/literary-critic/releases/latest"
TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
UPDATE_TIMEOUT = 5.0  # seconds; past it the check says nothing
CACHE: Path | None = None  # tests; else update.json beside folders.json
CACHE_SECONDS = 24 * 3600  # one network read a day


def _cache_file() -> Path:
    if CACHE is not None:
        return CACHE
    from litcritic.folders import state_file  # folders imports mcp, which imports kit

    return state_file().parent / "update.json"


def _cert_unverified(exc: BaseException) -> bool:
    """urlopen's failure was the server certificate (urllib wraps it in ``URLError``)."""
    return isinstance(exc, ssl.SSLCertVerificationError) or isinstance(
        getattr(exc, "reason", None), ssl.SSLCertVerificationError
    )


# Windows PowerShell 5.1 fetches through SChannel; base64 keeps stdout free of codepages.
WINDOWS_FETCH = (
    "$ProgressPreference='SilentlyContinue';"
    "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;"
    "$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec {secs} -Uri '{url}'"
    " -Headers @{{'User-Agent'='literary-critic'}};"
    "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($r.Content))"
)


def _windows_fetch(url: str, timeout: float) -> bytes | None:
    """``url``'s body read through Windows' own TLS, or None. On a fresh Windows the store
    lacks roots that Windows installs only when its own TLS asks; CPython reads the store
    but never asks, so this one fetch also lets later urllib calls verify."""
    if sys.platform != "win32" or timeout <= 1:
        return None
    exe = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    exe = exe / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    script = WINDOWS_FETCH.format(secs=max(1, int(timeout) - 1), url=url)
    try:
        done = subprocess.run(
            [str(exe), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (
            base64.b64decode(done.stdout.strip(), validate=True) if done.returncode == 0 else None
        )
    except Exception:  # missing, blocked or slow: the check stays "unknown"
        return None


def _fetch_release(timeout: float) -> dict[str, Any] | None:
    """The newest published Release (``tag_name``, ``html_url``, ``assets``), or None on
    any failure (offline, slow, refused, no release). A certificate Python cannot verify
    on Windows is retried once through Windows' own TLS, within the same ``timeout``."""
    started = time.monotonic()
    req = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "literary-critic"})
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except Exception as exc:
            if not _cert_unverified(exc):
                return None
            fallback = _windows_fetch(RELEASE_URL, timeout - (time.monotonic() - started))
            if fallback is None:
                return None
            body = fallback
        got = json.loads(body.decode("utf-8"))
        return got if isinstance(got, dict) else None
    except Exception:  # any failure means "unknown", never an error for the writer
        return None


def _parse(version: str) -> tuple[int, ...] | None:
    m = TAG.fullmatch("v" + version.lstrip("v"))
    return tuple(int(n) for n in m.groups()) if m else None


def _released(release: dict[str, Any]) -> str | None:
    """The release's version, only when it carries its ``.mcpb``: a tag without a
    published bundle is never announced."""
    tag = str(release.get("tag_name") or "")
    if not TAG.fullmatch(tag):
        return None
    names = {str(a.get("name")) for a in release.get("assets") or [] if isinstance(a, dict)}
    return tag[1:] if f"literary-critic-{tag[1:]}.mcpb" in names else None


def _latest(force: bool = False) -> tuple[str, str] | None:
    """``(version, page)`` of the newest release with a bundle, read at most once a day
    unless ``force``."""
    cache = _cache_file()
    if not force:
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - float(cached["at"]) < CACHE_SECONDS:
                return (str(cached["latest"]), str(cached["url"])) if cached["latest"] else None
    release = _fetch_release(UPDATE_TIMEOUT)
    if release is None:
        return None
    latest = _released(release)
    url = str(release.get("html_url") or RELEASES_PAGE)
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"at": time.time(), "latest": latest, "url": url}), "utf-8")
    return (latest, url) if latest else None


def update_check(info: dict[str, Any], network: bool = True, force: bool = False) -> dict[str, Any]:
    """``latest``, ``url`` and ``update_available`` (``yes``, ``no`` or ``unknown``) for a
    copy described by ``version_info``. ``yes`` only when its version is older than the
    newest release with a bundle; a source checkout, no network or any failure is
    ``unknown``."""
    found = _latest(force) if network and info.get("source") != "checkout" else None
    mine = _parse(str(info.get("version", "")))
    newest = _parse(found[0]) if found else None
    if info.get("source") == "checkout" or mine is None or newest is None:
        state = "unknown"
    else:
        state = "yes" if mine < newest else "no"
    latest, url = found or (None, RELEASES_PAGE)
    return {"latest": latest, "url": url, "update_available": state}


SKILL = Path(".claude") / "skills" / "litcritic" / "SKILL.md"
SKILL_NAME = "litcritic"
SKILL_MAX_BYTES = 30 * 1024 * 1024


def _doc_control_files() -> dict[str, Path]:
    """The installed ``doc_control`` package (and its licence) under ``src/``."""
    spec = importlib.util.find_spec(
        "doc_control"
    )  # find, never import: kit.py stays dependency-free
    if spec is None or not spec.submodule_search_locations:
        raise KitError("doc-control is not installed (pip install doc-control); the kit needs it")
    out: dict[str, Path] = {}
    for location in spec.submodule_search_locations:
        base = Path(location)
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                out["src/doc_control/" + p.relative_to(base).as_posix()] = p
        for dist in sorted(base.parent.glob("doc_control-*.dist-info")):
            for lic in sorted(dist.glob("licenses/LICENSE*")) + sorted(dist.glob("LICENSE*")):
                out.setdefault("src/doc_control/LICENSE", lic)
    return out


def _files(root: Path) -> dict[str, Path]:
    """The kit's files from the checkout: name in the zip -> source."""
    out: dict[str, Path] = {}
    for top in CONTENT:
        for p in sorted((root / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                out[p.relative_to(root).as_posix()] = p
    out.update(_doc_control_files())
    out["START_HERE.md"] = root / "kit" / "START_HERE.md"
    out["LICENSE"] = root / "LICENSE"
    return out


def _build(
    out: Path, files: dict[str, Path], generated: dict[str, str], prefix: str = "", limit: int = 0
) -> int:
    """Write the zip beside ``out`` and move it into place only when complete (and,
    with ``limit``, small enough): a failed build never removes the previous one."""
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, src in files.items():
                zf.write(src, prefix + name)
            for name, text in generated.items():
                zf.writestr(prefix + name, text)
        if limit and partial.stat().st_size > limit:
            raise KitError(f"the zip would be over {limit // 2**20} MB")
        os.replace(partial, out)
    finally:
        partial.unlink(missing_ok=True)
    return len(files) + len(generated)


def _checkout(*extra: Path) -> Path:
    root = repo_root()
    needed = [root / top for top in CONTENT] + [root / "kit" / "START_HERE.md", root / "LICENSE"]
    needed += [root / e for e in extra]
    missing = [p.relative_to(root).as_posix() for p in needed if not p.exists()]
    if missing:
        raise KitError(f"not a source checkout of the tool (missing {', '.join(missing)})")
    return root


def build(out: Path | None = None) -> tuple[Path, int]:
    """Write ``literary-critic-kit-<version>.zip``; returns its path and file count."""
    root = _checkout()
    out = (out or root / "dist" / f"literary-critic-kit-{__version__}.zip").resolve()
    return out, _build(out, _files(root), {"lc.py": LAUNCHER, VERSION_FILE: _stamp("kit")})


def build_skill(out: Path | None = None) -> tuple[Path, int]:
    """Write ``litcritic-skill-<version>.zip``: the ``litcritic/`` Skill folder (its
    SKILL.md at the top) with the whole kit inside, ready to upload to Claude."""
    root = _checkout(SKILL)
    out = (out or root / "dist" / f"litcritic-skill-{__version__}.zip").resolve()
    files = {"SKILL.md": root / SKILL, **_files(root)}
    generated = {"lc.py": LAUNCHER, VERSION_FILE: _stamp("skill")}
    count = _build(out, files, generated, f"{SKILL_NAME}/", SKILL_MAX_BYTES)
    return out, count


def _tiny_docx() -> bytes:
    """A three-paragraph ``.docx``, built by ``convert`` (the one module that writes parts)."""
    from litcritic import convert
    from litcritic.ingest import Draft, Para

    return convert.draft_to_docx(Draft([Para(t) for t in ("Uno.", "Dos.", "Tres.")], "docx"))


def doctor(home: Path | None = None) -> list[str]:
    """Problems found on this platform (empty when everything works).

    ``home`` is where the writer's workspaces will live (``./home`` in a kit);
    it is checked against the location rule, without writing anything there.
    """
    problems = []
    if sys.version_info < MIN_PYTHON:  # the launcher stops earlier; this covers `lc doctor`
        problems.append(
            f"Python {'.'.join(map(str, MIN_PYTHON))}+ needed, found {sys.version.split()[0]}"
        )
        return problems
    from litcritic import dc, ingest, metrics, pack, query, structure, workspace

    try:
        if dc.run("server.capabilities", {}).get("api") is None:
            problems.append("doc-control answered without its API version")
    except Exception as exc:  # DocError, or anything doc-control raises
        problems.append(f"doc-control: {type(exc).__name__}: {exc}")

    if home is not None:
        try:
            workspace.check_location(home / "check")
        except workspace.WorkspaceError as exc:
            problems.append(f"workspaces cannot live in {home}: {exc}")

    text = (
        "CAPÍTULO 1\n\n" + "La noche cayó sobre el valle. " * 40 + "\n\n—¿Vienes? —preguntó.\n\n"
        "CAPÍTULO 2\n\n" + "Al día siguiente llovió sin parar. " * 40 + "\n\n"
        "CAPÍTULO 3\n\n" + "Nadie volvió a hablar de aquello. " * 40 + "\n"
    )
    saved = os.environ.get(workspace.REGISTRY_ENV)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[workspace.REGISTRY_ENV] = str(Path(tmp) / "registry.txt")  # leave no trace
            home = Path(tmp) / "home"
            ws = workspace.create("check", "Check", "es", home)
            src = Path(tmp) / "draft.txt"
            src.write_text(text, encoding="utf-8")
            ingest.ingest(src, ws.root)
            _, s, _ = structure.build(ws.root)
            if len([c for c in s.chapters if c.reason != "front"]) != 3:
                problems.append("structure detection gave an unexpected result")
            ctx = metrics.context_for(ws.root, "v001", "es")
            if (
                metrics.compute(ctx, ["readability_fernandez_huerta"])[
                    "readability_fernandez_huerta"
                ].get("book")
                is None
            ):
                problems.append("metrics did not run")
            if "c02" not in query.toc(query.load(ws.root)):
                problems.append("queries did not run")
            pack.pack(ws.root, Path(tmp) / "check.zip")
            tiny = Path(tmp) / "tiny.docx"
            tiny.write_bytes(_tiny_docx())
            if len(ingest.read(tiny).paragraphs) != 3:
                problems.append("Word (.docx) reading gave an unexpected result")
    except Exception as exc:  # report, never crash: this is a diagnostic
        problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        if saved is None:
            os.environ.pop(workspace.REGISTRY_ENV, None)
        else:
            os.environ[workspace.REGISTRY_ENV] = saved
    return problems
