import argparse
import re
from pathlib import Path

from litcritic.cli import build_parser
from litcritic.workspace import repo_root

CALL = re.compile(r"(?:^|[`\s(])lc ([a-z][a-z-]*)((?:[^`\n])*)")


def _subcommands() -> dict[str, set[str]]:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {
        name: {opt for act in p._actions for opt in act.option_strings}
        for name, p in sub.choices.items()
    }


def _documents() -> list[Path]:
    root = repo_root()
    docs = sorted((root / "prompts").glob("*.md"))
    docs += sorted((root / ".claude" / "skills").glob("litcritic*/SKILL.md"))
    return docs


def _calls(text: str) -> list[tuple[str, list[str]]]:
    return [(m.group(1), re.findall(r"--[a-z][a-z-]*", m.group(2))) for m in CALL.finditer(text)]


def references_valid() -> tuple[int, list[str]]:
    commands = _subcommands()
    total = 0
    bad = []
    for doc in _documents():
        for name, flags in _calls(doc.read_text(encoding="utf-8")):
            total += 1
            if name not in commands:
                bad.append(f"{doc.name}: lc {name} does not exist")
            for flag in flags:
                if flag not in commands.get(name, set()):
                    bad.append(f"{doc.name}: lc {name} has no {flag}")
    return total, bad


def test_prompts_only_reference_existing_commands() -> None:
    total, bad = references_valid()
    assert total >= 20  # the prompts really use the tool
    assert bad == []


def test_checker_catches_bad_references() -> None:
    assert _calls("run `lc show c01 --budget 9` then lc frobnicate --x") == [
        ("show", ["--budget"]),
        ("frobnicate", ["--x"]),
    ]


def test_every_prompt_is_listed_in_readme() -> None:
    readme = (repo_root() / "prompts" / "README.md").read_text(encoding="utf-8")
    for doc in (repo_root() / "prompts").glob("[0-9]*.md"):
        assert f"`{doc.name}`" in readme
