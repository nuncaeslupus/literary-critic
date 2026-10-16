"""Pack the desktop extension: ``literary-critic-X.Y.Z.mcpb`` from this checkout.

Stdlib only, so CI and a writer's machine need no Node to pack. The bundle is the server
type ``uv`` (release D-1): the app installs uv, which builds the project from the bundled
``pyproject.toml`` and ``uv.lock``. So the bundle carries no venv, and its
``pyproject.toml`` turns off the dev group, which ``uv run`` would otherwise install.

    python scripts/pack_mcpb.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
# What the server reads at run time (``repo_root()`` is the bundle's root).
CONTENT = ("src/litcritic", "schemas", "checklist", "prompts", "docs/codex")
TOP = ("uv.lock", "README.md", "LICENSE", "NOTICE")
NO_DEV = "\n[tool.uv]\ndefault-groups = []  # the app's uv run installs no dev tools\n"


class PackError(Exception):
    """The bundle cannot be packed from this checkout."""


def version(root: Path = ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as f:
        return str(tomllib.load(f)["project"]["version"])


def manifest(root: Path = ROOT) -> dict[str, object]:
    """The manifest with the version from ``pyproject.toml``; a stamped version that
    differs is refused, so the two never drift."""
    data: dict[str, object] = json.loads(
        (root / "extension" / "manifest.json").read_text(encoding="utf-8")
    )
    want = version(root)
    if data.get("version") not in ("0.0.0", want):
        raise PackError(f"manifest version {data.get('version')} is not pyproject's {want}")
    data["version"] = want
    return data


def bundle_pyproject(root: Path = ROOT) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if re.search(r"^\[tool\.uv\]", text, re.M):
        raise PackError("pyproject.toml has a [tool.uv] table: merge default-groups into it")
    return text.rstrip("\n") + "\n" + NO_DEV


def files(root: Path = ROOT) -> dict[str, Path]:
    """Name in the bundle -> source, for every file copied as is."""
    out: dict[str, Path] = {}
    for top in CONTENT:
        for p in sorted((root / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                out[p.relative_to(root).as_posix()] = p
    for name in TOP:
        out[name] = root / name
    for p in sorted((root / "extension").iterdir()):
        if p.is_file() and p.name != "manifest.json":
            out[p.name] = p
    missing = [name for name, p in out.items() if not p.is_file()]
    if missing:
        raise PackError(f"missing from the checkout: {', '.join(missing)}")
    return out


def pack(out_dir: Path, root: Path = ROOT) -> Path:
    data = manifest(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"literary-critic-{data['version']}.mcpb"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        z.writestr("pyproject.toml", bundle_pyproject(root))
        for name, src in files(root).items():
            z.write(src, name)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=ROOT / "dist", help="folder for the .mcpb")
    args = p.parse_args(argv)
    try:
        print(pack(args.out))
    except PackError as e:
        print(f"pack_mcpb: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
