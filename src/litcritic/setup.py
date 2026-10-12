"""`lc setup`: find the writer's novel in a folder and prepare the workspace.

The writer points at the folder that holds the novel (say ``MyNovel/``). Setup:

1. looks at every document there (``.docx``, ``.odt``, ``.md``, ``.txt``);
2. groups the drafts of the novel: documents whose opening text overlaps the
   longest one, so notes, letters and other books stay apart;
3. takes the newest draft as the manuscript; files named as copies or backups
   ("Copy of", "(1)", "backup", "copia") are listed but never chosen while a
   real draft exists, and ``.docx`` is preferred, as the only format edited in place;
4. creates (or reuses) the workspace ``MyNovel/literary-critic/``, ingests the
   manuscript and anchors it.

A second run with nothing changed writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import ingest, metrics, safe_edit, structure, workspace

WORKSPACE_DIR = "literary-critic"
SAMPLE_WORDS = 3000
SHINGLE = 5
SAME_NOVEL = 0.3  # share of the shorter opening found in the other one
FORMAT_RANK = {".docx": 0, ".odt": 1, ".md": 2, ".txt": 3}
COPY = re.compile(
    r"(^|[\s_.-])(copy|copia|backup|respaldo|bak|old|antiguo|recovered|recuperado)"
    r"([\s_.-]|$)|^(copy|copia) (of|de) |\(\d+\)$|-\s*copy$",
    re.I,
)


class SetupError(Exception):
    """Nothing to set up (no folder, no documents)."""


@dataclass
class Found:
    path: Path
    modified: float
    words: int
    shingles: set[tuple[str, ...]]
    marked_copy: bool

    def as_json(self, folder: Path, similarity: float | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"path": _rel(folder, self.path), "modified": _iso(self.modified)}
        if similarity is not None:
            out["similarity"] = round(similarity, 2)
        return out


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(folder: Path, path: Path) -> str:
    return str(path.relative_to(folder.parent)) if path.is_relative_to(folder.parent) else str(path)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())


def _shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + SHINGLE]) for i in range(max(0, len(words) - SHINGLE + 1))}


def similarity(a: Found, b: Found) -> float:
    if not a.shingles or not b.shingles:
        return 0.0
    return len(a.shingles & b.shingles) / min(len(a.shingles), len(b.shingles))


def _documents(folder: Path) -> list[Path]:
    out = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in FORMAT_RANK:
            continue
        if f.name.startswith(("~$", ".~lock.", ".")):
            continue  # Word / LibreOffice lock files, hidden files
        out.append(f)
    return out


def _read(path: Path) -> Found | None:
    try:
        draft = ingest.read(path)
    except (ingest.IngestError, OSError, ValueError):
        return None
    words = _words(" ".join(p.text for p in draft.paragraphs))
    return Found(
        path,
        path.stat().st_mtime,
        len(words),
        _shingles(words[:SAMPLE_WORDS]),
        bool(COPY.search(path.stem)),
    )


def _version_number(path: Path) -> int:
    nums = re.findall(r"\d+", path.stem)
    return int(nums[-1]) if nums else 0


@dataclass
class Discovery:
    manuscript: Found
    versions: list[tuple[Found, float]]
    others: list[Found]


def discover(folder: Path) -> Discovery:
    """The latest draft, its other versions (newest first) and unrelated documents."""
    found = [f for f in (_read(p) for p in _documents(folder)) if f and f.words]
    if not found:
        raise SetupError(f"no document with text in {folder} (.docx, .odt, .md or .txt)")
    seed = max(found, key=lambda f: (not f.marked_copy, f.words))
    novel = [f for f in found if f is seed or similarity(f, seed) >= SAME_NOVEL]
    real = [f for f in novel if not f.marked_copy] or novel
    best = min(FORMAT_RANK[f.path.suffix.lower()] for f in real)
    manuscript = max(
        (f for f in real if FORMAT_RANK[f.path.suffix.lower()] == best),
        key=lambda f: (f.modified, _version_number(f.path)),
    )
    versions = sorted(
        ((f, similarity(f, manuscript)) for f in novel if f is not manuscript),
        key=lambda v: -v[0].modified,
    )
    others = [f for f in found if f not in novel]
    return Discovery(manuscript, versions, others)


def detect_language(path: Path) -> str:
    """The lexicon language whose stopwords are most frequent in the opening."""
    draft = ingest.read(path)
    words = _words(" ".join(p.text for p in draft.paragraphs[:400]))[:SAMPLE_WORDS]
    scores = {}
    for lex in sorted(metrics.DATA.glob("lexicon_*.toml")):
        lang = lex.stem.removeprefix("lexicon_")
        stop = set(metrics.lexicon(lang).get("stopwords", []))
        scores[lang] = sum(w in stop for w in words)
    return max(scores, key=lambda k: scores[k]) if scores else "en"


def _slug(name: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or "novel"


def _title(path: Path) -> str:
    stem = re.sub(r"[\s_-]*(v(ersion)?|draft|borrador)?[\s_-]*\d+$", "", path.stem, flags=re.I)
    return " ".join(re.sub(r"[_]+", " ", stem).split()) or path.stem


def environment(folder: Path, manuscript: Path) -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "os": sys.platform,
        "folder_writable": os.access(folder, os.W_OK),
        "word_lock": bool(safe_edit.lock_files(manuscript)),
    }


def setup(folder: Path) -> dict[str, Any]:
    """Run discovery, create or reuse the workspace, ingest and anchor."""
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise SetupError(f"{folder} is not a folder")
    found = discover(folder)
    doc = found.manuscript.path
    root = folder / WORKSPACE_DIR
    if (root / workspace.MANIFEST).is_file():
        ws = workspace.resolve(str(root))
    else:
        ws = workspace.create(
            _slug(folder.name), _title(doc), detect_language(doc), base=folder, folder=WORKSPACE_DIR
        )
    result = ingest.ingest(doc, ws.root)
    structure_file = ws.root / "index" / result.version / "structure.json"
    if not result.unchanged or not structure_file.is_file():
        structure.build(ws.root, result.version)
    return {
        "status": "ready",
        "workspace": _rel(folder, ws.root),
        "manuscript": found.manuscript.as_json(folder),
        "version": result.version,
        "versions": [f.as_json(folder, sim) for f, sim in found.versions],
        "others": [_rel(folder, f.path) for f in found.others],
        "environment": environment(folder, doc),
        "language": str(ws.manifest.get("language", "")),
    }


def _cmd(args: argparse.Namespace) -> int:
    try:
        out = setup(args.folder)
    except (SetupError, workspace.WorkspaceError, ingest.IngestError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("setup", help="find the novel in a folder and prepare its workspace")
    p.add_argument("--folder", type=Path, required=True, help="the folder holding the novel")
    p.set_defaults(func=_cmd)
