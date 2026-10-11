"""The chat kit: everything an assistant with code execution needs, in one zip.

The kit holds the stdlib-only package, its data, the schemas, the checklist,
the prompts, ``START_HERE.md`` and an ``lc.py`` launcher. ``doctor`` checks a
platform by running a tiny pipeline in a temporary folder.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from litcritic import __version__
from litcritic.workspace import repo_root


class KitError(Exception):
    """The kit cannot be built from here."""


MIN_PYTHON = (3, 12)  # keep in step with requires-python in pyproject.toml
CONTENT = ("src/litcritic", "schemas", "checklist", "prompts")
LAUNCHER = '''"""Run the literary-critic tool from an unpacked kit: python lc.py <command> ..."""

import sys
from pathlib import Path

if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ needed, found {sys.version.split()[0]}")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from litcritic.cli import main  # noqa: E402

raise SystemExit(main())
'''


def build(out: Path | None = None) -> tuple[Path, int]:
    """Write ``literary-critic-kit-<version>.zip``; returns its path and file count."""
    root = repo_root()
    needed = [root / top for top in CONTENT] + [root / "kit" / "START_HERE.md", root / "LICENSE"]
    missing = [p.relative_to(root).as_posix() for p in needed if not p.exists()]
    if missing:
        raise KitError(f"not a source checkout of the tool (missing {', '.join(missing)})")
    out = (out or root / "dist" / f"literary-critic-kit-{__version__}.zip").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    count = 0
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as zf:
            for top in CONTENT:
                for p in sorted((root / top).rglob("*")):
                    if p.resolve() in (out, partial) or not p.is_file():
                        continue
                    if "__pycache__" not in p.parts and p.suffix != ".pyc":
                        zf.write(p, p.relative_to(root).as_posix())
                        count += 1
            zf.write(root / "kit" / "START_HERE.md", "START_HERE.md")
            zf.writestr("lc.py", LAUNCHER)
            zf.write(root / "LICENSE", "LICENSE")
            count += 3
        os.replace(partial, out)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    return out, count


def _tiny_docx() -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paras = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in ("Uno.", "Dos.", "Tres."))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{paras}</w:body></w:document>'
        )
    return buf.getvalue()


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
    from litcritic import ingest, metrics, pack, query, structure, workspace

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
            if len(ingest.read_docx(_tiny_docx()).paragraphs) != 3:
                problems.append("Word (.docx) reading gave an unexpected result")
    except Exception as exc:  # report, never crash: this is a diagnostic
        problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        if saved is None:
            os.environ.pop(workspace.REGISTRY_ENV, None)
        else:
            os.environ[workspace.REGISTRY_ENV] = saved
    return problems
