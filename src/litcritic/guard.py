"""Content guard: keep working-novel material out of the tool repo.

Two checks on the files about to be committed:
1. Manuscript-like file types are allowed only under ``corpus/``.
2. No term from any workspace's ``guard-terms.txt`` (or the local, git-ignored
   ``.litcritic-guard-terms``) may appear in a path or in added text.
Matching ignores case and accents and respects word boundaries.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from litcritic import workspace

MANUSCRIPT_SUFFIXES = {".docx", ".doc", ".odt", ".rtf", ".pdf", ".epub", ".pages", ".gdoc"}
ALLOWED_MANUSCRIPT_DIRS = ("corpus/",)
LOCAL_TERMS_FILE = ".litcritic-guard-terms"


@dataclass(frozen=True)
class Violation:
    path: str
    reason: str


def fold(text: str) -> str:
    """Lowercase and strip accents so 'Ángel' matches 'angel'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def read_terms(files: list[Path], required: list[Path] | None = None) -> list[str]:
    """Terms from the given files; missing ``files`` are skipped, missing ``required`` raise."""
    for f in required or []:
        if not f.is_file():
            raise FileNotFoundError(f"terms file not found: {f}")
    terms: set[str] = set()
    for f in [*files, *(required or [])]:
        if not f.is_file():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.add(line)
    return sorted(terms)


def default_term_files(repo: Path) -> list[Path]:
    files = [ws.guard_terms_file for ws in workspace.all_workspaces()]
    files.append(repo / LOCAL_TERMS_FILE)
    return files


def compile_terms(terms: list[str]) -> re.Pattern[str] | None:
    folded = [re.escape(fold(t)) for t in terms if len(t.strip()) >= 3]
    if not folded:
        return None
    return re.compile(r"(?<!\w)(" + "|".join(folded) + r")(?!\w)")


def check(files: dict[str, str], terms: list[str]) -> list[Violation]:
    """Check {path: added_text} against the rules."""
    pattern = compile_terms(terms)
    out: list[Violation] = []
    for path, text in sorted(files.items()):
        suffix = Path(path).suffix.lower()
        if suffix in MANUSCRIPT_SUFFIXES and not path.startswith(ALLOWED_MANUSCRIPT_DIRS):
            out.append(Violation(path, f"manuscript file type {suffix} outside corpus/"))
        if pattern is None:
            continue
        for target, label in ((path, "path"), (text, "content")):
            m = pattern.search(fold(target))
            if m:
                out.append(Violation(path, f"guarded term in {label}: {m.group(1)!r}"))
    return out


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def _added_lines(diff: str) -> str:
    """Added lines of a unified diff, skipping the file header."""
    added: list[str] = []
    in_hunk = False
    for ln in diff.splitlines():
        if ln.startswith("@@"):
            in_hunk = True
        elif in_hunk and ln.startswith("+"):
            added.append(ln[1:])
    return "\n".join(added)


def staged_changes(repo: Path) -> dict[str, str]:
    """Added lines per staged file (binary files map to '')."""
    out = _git(repo, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    names = [n for n in out.split("\0") if n]
    return {n: _added_lines(_git(repo, "diff", "--cached", "-U0", "--", n)) for n in names}


def tracked_files(repo: Path) -> dict[str, str]:
    """Full text of every tracked file (for CI / full scans)."""
    names = [n for n in _git(repo, "ls-files", "-z").split("\0") if n]
    result: dict[str, str] = {}
    for name in names:
        try:
            result[name] = (repo / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            result[name] = ""
    return result
