"""Gate prompts_reference_valid_commands: every lc call in the procedures runs.

Full commands (`lc <command> ...` with arguments) are parsed by the real CLI
parser, so unknown commands, flags, invalid choices and missing required
options all fail. A bare mention such as `lc show` only has to name a command.
Placeholders like <slug> stand for any value.
"""

import argparse
import contextlib
import io
import json
import re
import shlex
from pathlib import Path

from litcritic import docx_cli, word_live
from litcritic.cli import build_parser
from litcritic.workspace import repo_root

SPAN = re.compile(r"`([^`]*)`")
FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)


def _documents() -> list[Path]:
    root = repo_root()
    docs = sorted((root / "prompts").glob("*.md"))
    docs += sorted((root / ".claude" / "skills").glob("litcritic*/SKILL.md"))
    docs.append(root / "kit" / "START_HERE.md")
    return docs


def _commands(text: str) -> list[str]:
    """Every `lc ...` command in inline code and fenced blocks, split at && ; |."""
    chunks = [m.group(1) for m in FENCE.finditer(text)]
    chunks += [m.group(1) for m in SPAN.finditer(FENCE.sub("", text))]
    out = []
    for chunk in chunks:
        for line in chunk.splitlines():
            for part in re.split(r"&&|;|\|", line):
                part = re.sub(r"^python3? lc\.py ", "lc ", part.strip())
                if part.startswith("lc "):
                    out.append(part)
    return out


def _choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """The subcommands of a parser (empty when it has none)."""
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            return dict(a.choices)
    return {}


def _subcommands() -> set[str]:
    return set(_choices(build_parser()))


def named(command: str) -> str:
    """'' when the command (and its subcommand, if it has them) exists, else the reason."""
    tokens = shlex.split(re.sub(r"<[^>]*>", "x", command))[1:]
    parser = build_parser()
    path = ["lc"]
    for token in tokens:
        choices = _choices(parser)
        if not choices or token.startswith("-"):
            break
        if token not in choices:
            return f"no command {' '.join([*path, token])!r}"
        parser = choices[token]
        path.append(token)
    return ""


def check(command: str) -> str:
    """'' when the command is valid, else the reason."""
    tokens = shlex.split(re.sub(r"<[^>]*>", "x", command))[1:]
    if len(tokens) == 1:  # a mention of the command, not a call
        return "" if tokens[0] in _subcommands() else f"no command {tokens[0]!r}"
    top = _choices(build_parser())
    if len(tokens) == 2 and tokens[0] in top and tokens[1] in _choices(top[tokens[0]]):
        return ""  # a mention of a subcommand (`lc index plan`), not a call
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


def _codex_commands() -> list[str]:
    return [
        c
        for doc in _documents()
        for c in _commands(doc.read_text(encoding="utf-8"))
        if c.startswith("lc codex")
    ]


def test_prompt_commands_parse(tmp_path: Path) -> None:
    """Gate skill_workshop_errors (prompt side): the procedures drive the Codex, and every
    `lc codex` call parses; every literal SQL query in them runs on a fixture Codex."""
    commands = _codex_commands()
    assert [c for c in commands if check(c)] == []
    used = {shlex.split(re.sub(r"<[^>]*>", "x", c))[2] for c in commands if len(c.split()) > 2}
    assert used >= {
        "init",
        "add",
        "update",
        "retire",
        "show",
        "find",
        "sql",
        "ask",
        "questions",
        "sync",
        "check",
    }
    # The chat flow (setup, editing the Word file, live Word) is in the procedures too.
    every = [c for doc in _documents() for c in _commands(doc.read_text(encoding="utf-8"))]
    calls = {" ".join(shlex.split(re.sub(r"<[^>]*>", "x", c))[1:3]) for c in every}
    calls |= {shlex.split(c)[1] for c in every}
    assert calls >= {"setup", "docx edits", "docx rename", "docx locate", "docx status", "word"}
    assert [c for c in every if check(c)] == []
    from codex_fixture import build

    from litcritic import view

    build(tmp_path)
    v = view.View(tmp_path)
    queries = []
    for c in commands:
        if c.startswith('lc codex sql "'):
            tokens = shlex.split(c)
            given = [tokens[i + 1] for i, t in enumerate(tokens) if t == "--param"]
            params = dict(g.split("=", 1) for g in given)
            if "<" not in tokens[3]:
                queries.append((tokens[3], params))
    assert queries
    for sql, params in queries:
        v.run(sql, params)


def _named_documents() -> list[Path]:
    root = repo_root()
    docs = sorted((root / "prompts").glob("*.md"))
    docs += sorted((root / ".claude" / "skills" / "litcritic").rglob("*.md"))
    return docs


def named_ratio() -> tuple[float, int, list[str]]:
    """Share of `lc <command> [<sub>]` references in the prompts and the litcritic skill
    whose command and subcommand exist in the CLI parser."""
    refs = [
        (doc.name, c)
        for doc in _named_documents()
        for c in _commands(doc.read_text(encoding="utf-8"))
    ]
    bad = [f"{name}: {c} -> {named(c)}" for name, c in refs if named(c)]
    return (len(refs) - len(bad)) / len(refs), len(refs), bad


RETIRED_DOC = "word-control" + "-interface"  # gave way to doc-control's live engine


def naming_retired_doc() -> list[str]:
    """Files of the tool (prompts, skill, docs, kit, README, code, tests) that name the
    retired live-Word interface doc. Plans and evidence keep their history."""
    root = repo_root()
    files = [root / "README.md", *_named_documents()]
    for folder in ("docs", "kit", "src", "tests", ".claude/skills"):
        files += [f for f in (root / folder).rglob("*") if f.suffix in (".md", ".py", ".txt")]
    retired = (RETIRED_DOC, "LITCRITIC_" + "WORD_CONTROL")  # the doc and its extension hook
    return sorted(
        str(f.relative_to(root))
        for f in set(files)
        if any(term in f.read_text(encoding="utf-8") for term in retired)
    )


def test_prompts_name_only_lc_commands() -> None:
    """Gate prompts_reference_valid_commands (index T7): every lc command and
    subcommand the procedures name exists, the `lc index` packet loop included.
    Gate docs_naming_word_control_interface (doccontrol T12): nothing names the
    retired live-Word interface doc; live Word goes through `lc` only."""
    ratio, total, bad = named_ratio()
    print(f"prompts_reference_valid_commands = {ratio} ({total} references)")
    assert bad == []
    assert ratio == 1.0
    assert not (repo_root() / "docs" / f"{RETIRED_DOC}.md").exists()
    naming = naming_retired_doc()
    print(f"docs_naming_word_control_interface = {len(naming)}")
    assert naming == []
    index = {
        shlex.split(re.sub(r"<[^>]*>", "x", c))[2]
        for doc in _named_documents()
        for c in _commands(doc.read_text(encoding="utf-8"))
        if c.startswith("lc index ")
    }
    assert index >= {"plan", "packet", "import", "status", "cost", "eval", "compare"}
    assert named("lc index frobnicate") != ""
    assert named("lc frobnicate") != ""
    assert named("lc index plan --changed --workspace x") == ""
    assert check("lc index plan") == ""
    assert check("lc index frobnicate") != ""


def test_mention_rule_matches_packet_instructions() -> None:
    """The prompt and the entity packet state the same rule for places and groups."""
    from litcritic import packets

    prompt = (repo_root() / "prompts" / "20-codex-items.md").read_text(encoding="utf-8")
    for text in (" ".join(prompt.split()), packets.INSTRUCTIONS["entities"]):
        assert "a scene happens there" in text
        assert "2 or more places" in text
        assert "passing mention is a" in text


def test_tool_talk_waits_for_the_tool_channel() -> None:
    """A writer hears about the novel: the tool is discussed only when asked with [[...]]."""
    guide = " ".join((repo_root() / "prompts" / "00-guide.md").read_text(encoding="utf-8").split())
    assert "Unasked, never describe the tool's faults" in guide
    for name in ("00-guide.md", "01-chat-guide.md"):
        text = " ".join((repo_root() / "prompts" / name).read_text(encoding="utf-8").split())
        assert re.search(r"never writ(e it|ten) to the writer", text), name  # [[...]] is the maintainer's
    for path in _documents():
        for sentence in re.split(r"(?<=[.:;])\s+", " ".join(path.read_text("utf-8").split())):
            if re.search(r"\bpropose\b", sentence) and "[[" in sentence:
                assert re.search(r"only (then|when asked)", sentence, re.I), (path.name, sentence)


def test_setup_prompt_update_notice_is_short() -> None:
    text = (repo_root() / "prompts" / "05-setup.md").read_text(encoding="utf-8")
    updates = text.split("### Updates", 1)[1].split("\n## ", 1)[0]
    (notice,) = [ln[2:] for ln in updates.splitlines() if ln.startswith("> ")]
    assert len(notice.split()) <= 40
    assert not re.search(r"`|\blc\b|\.md\b|\.json\b|\d+\.\d+", notice)  # no tool talk


def test_guide_prompt_names_channels_rules_and_done() -> None:
    """The chat guide `resume` returns: short, with both channels, the writer rules and
    the one-call jump ending in "Done."."""
    from litcritic import mcp

    guide = mcp.guide()
    assert len(guide.split()) <= 400
    assert "Plain messages" in guide and "`[[...]]`" in guide
    for rule in (
        "The writer writes",
        "Never edit the manuscript",
        "Plain language",
        "Locate everything",
        "One change per message",
    ):
        assert rule in guide, rule
    assert "one call" in guide and '"Done."' in guide
    names = {t.name for t in mcp.tools(None)}
    for tool in re.findall(r"`([a-z_]+)`", guide):
        fields = (
            "next_step",
            "prose_suggestions",
            "windows_block",
            "say",
            "other_doc_control",
            "update",
            "url",
            "yes",
            "applied",
            "restart_needed",
            "staging",
        )
        if tool in (*fields, "false", "true", "go"):
            continue
        assert tool in names, tool
    # no skill ships with the extension unless the guide loses (D-8): nothing to validate
    assert not list((repo_root() / "extension").glob("**/SKILL.md"))


def _prompt(name: str) -> str:
    return (repo_root() / "prompts" / name).read_text(encoding="utf-8")


def test_guide_tells_writer_moves_need_writer_word() -> None:
    guide = _prompt("00-guide.md")
    assert "The plan in the tool" in guide
    assert "--by tool" in guide
    assert "--by writer" in guide
    assert "only on" in guide and "their word" in guide
    assert "their reason" in guide
    assert "iterative mode" in guide and "report mode" in guide
    assert "lc plan next" in guide


def test_cards_prompt_respects_prose_setting() -> None:
    guide = _prompt("00-guide.md")
    chat = _prompt("01-chat-guide.md")
    rounds = _prompt("60-rounds.md")
    for text in (guide, chat):
        assert "change_card" in text
        assert "Approve C1" in text and "Dismiss C1" in text
        assert "yes or no" in text
        assert '"minor"' in text
    assert "Approve" in guide and "Dismiss" in guide
    assert "prose_suggestions" in guide
    assert "minor" in rounds and "off" in rounds
    assert 'only if `prose_suggestions` is `"minor"` or\non' in guide


TRACKED_WORDING = re.compile(r"tracked[- ]changes?|Word (?:also )?marks|as tracked", re.I)


def test_writer_texts_have_no_tracked_wording(tmp_path: Path) -> None:
    """Gate tracked_wording_in_writer_texts == 0: after the switch to plain writes, no
    prompt, help text or writer line says an approved change shows as a tracked change."""
    root = repo_root()
    texts = {d.name: d.read_text(encoding="utf-8") for d in _documents()}
    texts["README.md"] = (root / "README.md").read_text(encoding="utf-8")
    texts["architecture.md"] = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
    parser = build_parser()
    for cmd in (("docx",), ("docx", "edits"), ("docx", "rename"), ("setup",)):
        sub = parser
        for name in cmd:
            sub = _choices(sub)[name]
        texts["help " + " ".join(cmd)] = sub.format_help()
    texts["help lc"] = parser.format_help()
    texts["docx_cli docstring"] = docx_cli.__doc__ or ""
    steps = word_live.manual("apply_edits", {"document": str(tmp_path / "Novel.docx")})
    texts["word_live apply_edits"] = json.dumps(steps, ensure_ascii=False)
    tracked_wording_in_writer_texts = [
        name for name, text in texts.items() if TRACKED_WORDING.search(text)
    ]
    assert tracked_wording_in_writer_texts == []


def test_guide_names_always_allow() -> None:
    """The setup part gives the answer the clean-PC probe found (spec Q-7)."""
    from litcritic import mcp

    guide = " ".join(mcp.guide().split())
    assert '"Always allow"' in guide
    assert "Settings → Extensions → Literary Critic" in guide
