"""Gate prompts_reference_valid_commands: every lc call in the procedures runs.

Full commands (`lc <command> ...` with arguments) are parsed by the real CLI
parser, so unknown commands, flags, invalid choices and missing required
options all fail. A bare mention such as `lc show` only has to name a command.
Placeholders like <slug> stand for any value.
"""

import argparse
import contextlib
import io
import re
import shlex
from pathlib import Path

from litcritic.cli import build_parser
from litcritic.workspace import repo_root

SPAN = re.compile(r"`([^`]*)`")
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)


def _documents() -> list[Path]:
    root = repo_root()
    docs = sorted((root / "prompts").glob("*.md"))
    docs += sorted((root / ".claude" / "skills").glob("litcritic*/SKILL.md"))
    return docs


def _commands(text: str) -> list[str]:
    """Every `lc ...` command in inline code and fenced blocks, split at && ; |."""
    chunks = [m.group(1) for m in FENCE.finditer(text)]
    chunks += [m.group(1) for m in SPAN.finditer(FENCE.sub("", text))]
    out = []
    for chunk in chunks:
        for line in chunk.splitlines():
            for part in re.split(r"&&|;|\|", line):
                part = part.strip()
                if part.startswith("lc "):
                    out.append(part)
    return out


def _subcommands() -> set[str]:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def check(command: str) -> str:
    """'' when the command is valid, else the reason."""
    tokens = shlex.split(re.sub(r"<[^>]*>", "x", command))[1:]
    if len(tokens) == 1:  # a mention of the command, not a call
        return "" if tokens[0] in _subcommands() else f"no command {tokens[0]!r}"
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            build_parser().parse_args(tokens)
    except SystemExit:
        return err.getvalue().strip().splitlines()[-1]
    return ""


def references_valid() -> tuple[int, int, list[str]]:
    total = 0
    bad = []
    docs = _documents()
    for doc in docs:
        for command in _commands(doc.read_text(encoding="utf-8")):
            total += 1
            problem = check(command)
            if problem:
                bad.append(f"{doc.name}: {command} -> {problem}")
    return total, len(docs), bad


def test_prompts_only_reference_existing_commands() -> None:
    total, _, bad = references_valid()
    assert total >= 30  # the prompts really use the tool
    assert bad == []


def test_checker_catches_bad_references() -> None:
    assert check("lc show c01 --workspace x --budget 900") == ""
    assert check("lc show") == ""
    assert check("lc frobnicate") != ""
    assert "required" in check("lc show c05.s1")
    assert "invalid choice" in check("lc validate scenecard file.json")
    assert "unrecognized" in check("lc show c01 --workspace x --bogus")
    assert _commands("run `lc show c01 --fp && lc frobnicate --x`") == [
        "lc show c01 --fp",
        "lc frobnicate --x",
    ]


def test_every_prompt_is_listed_in_readme() -> None:
    readme = (repo_root() / "prompts" / "README.md").read_text(encoding="utf-8")
    for doc in (repo_root() / "prompts").glob("[0-9]*.md"):
        assert f"`{doc.name}`" in readme
