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


def read_terms(files: list[Path]) -> list[str]:
    terms: set[str] = set()
    for f in files:
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


def staged_changes(repo: Path) -> dict[str, str]:
    """Added lines per staged file (binary files map to '')."""
    names = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    result: dict[str, str] = {}
    for name in names:
        diff = subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "-U0", "--", name],
            capture_output=True,
            text=True,
            errors="replace",
            check=True,
        ).stdout
        added = [
            ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")
        ]
        result[name] = "\n".join(added)
    return result


def tracked_files(repo: Path) -> dict[str, str]:
    """Full text of every tracked file (for CI / full scans)."""
    names = subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    result: dict[str, str] = {}
    for name in names:
        p = repo / name
        try:
            result[name] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            result[name] = ""
    return result
