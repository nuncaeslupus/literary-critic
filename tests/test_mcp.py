import io
import json
from pathlib import Path
from typing import Any

import pytest

from litcritic import folders, mcp
from litcritic.cli import build_parser

FIXTURES = Path(__file__).parent / "fixtures" / "mcp"


def _crash(args: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("boom")


def _refuse(args: dict[str, Any]) -> dict[str, Any]:
    raise mcp.ToolError("outside_granted_folders", path="x")


def _server() -> mcp.Server:
    return mcp.Server(
        [
            mcp.Tool(
                "echo",
                "Echo the word back.",
                lambda a: {"word": a["word"]},
                {"word": {"type": "string"}},
                ("word",),
            ),
            mcp.Tool("refuse", "Always refused.", _refuse),
            mcp.Tool("crash", "Always crashes.", _crash),
        ],
        instructions="test guide",
        version="0.0.0-test",
    )


def _replay(server: mcp.Server, sends: list[Any]) -> list[Any]:
    stdin = io.StringIO("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sends))
    stdout = io.StringIO()
    server.serve(stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_mcp_transcript_initialize_list_call_matches() -> None:
    rows = [
        json.loads(line) for line in (FIXTURES / "transcript.jsonl").read_text("utf-8").splitlines()
    ]
    got = _replay(_server(), [r["send"] for r in rows])
    assert got == [r["expect"] for r in rows if r["expect"] is not None]


def test_mcp_initialize_without_version_answers_default() -> None:
    got = _replay(_server(), [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
    assert got[0]["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION


def test_mcp_bad_lines_answer_errors_and_keep_serving() -> None:
    server = _server()
    stdin = io.StringIO(
        'not json\n\n{"id": 1, "method": "ping"}\n{"jsonrpc": "2.0", "id": 2, "method": "ping"}\n'
    )
    stdout = io.StringIO()
    server.serve(stdin, stdout)
    codes = [
        json.loads(line).get("error", {}).get("code") for line in stdout.getvalue().splitlines()
    ]
    assert codes == [-32700, -32600, None]


def test_mcp_subcommand_registered() -> None:
    args = build_parser().parse_args(["mcp", "C:/novels"])
    assert args.folders == ["C:/novels"]


def _novel(base: Path, folder: str, title: str, draft: bool = True) -> Path:
    root = base / folder / "literary-critic"
    root.mkdir(parents=True)
    slug = folder.lower().replace(" ", "-")
    (root / "work.toml").write_text(
        f'id = "{slug}-abc123"\nslug = "{slug}"\ntitle = "{title}"\nlanguage = "es"\n',
        encoding="utf-8",
    )
    if draft:
        (root / "text").mkdir()
        (root / "text" / "v001.txt").write_text("Uno.\n", encoding="utf-8")
    return root


def _call(server: mcp.Server, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """The result object of one tools/call on a fresh session."""
    sends = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    ]
    reply = _replay(server, sends)[-1]["result"]
    assert not reply["isError"], reply
    out: dict[str, Any] = json.loads(reply["content"][0]["text"])
    return out


def test_resume_named_work_returns_state_and_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    novels = tmp_path / "Novels"
    _novel(novels, "Epoca", "Época de lluvias")
    _novel(novels, "Second", "Second", draft=False)
    server = mcp.Server(mcp.tools(folders.Grant([str(novels)])))
    names = [
        t["name"]
        for t in _replay(server, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])[0][
            "result"
        ]["tools"]
    ]
    assert {"works", "resume"} <= set(names)

    out = _call(server, "resume", {"work": "epoca de LLUVIAS"})  # resume_tool_calls == 1
    work = out["work"]
    assert work["title"] == "Época de lluvias"
    assert work["draft"] == "v001"
    assert work["next_step"]["step"] == "index"
    assert work["prose_suggestions"] is False
    assert len(out["guide"].split()) <= 400
    assert "[[...]]" in out["guide"]

    second = _call(server, "resume", {"work": "second"})
    assert second["work"]["next_step"]["step"] == "setup"
    listed = _call(server, "works", {})
    assert listed["works"][0]["title"] == "Second"  # most recent first

    missing = _call(server, "resume", {"work": "Unknown Book"})
    assert missing["not_found"] == "Unknown Book"
    assert {w["title"] for w in missing["works"]} == {"Época de lluvias", "Second"}
    assert "add_folder" in missing["hint"]

    several = _call(server, "resume", {})
    assert len(several["choose"]) == 2


def test_resume_without_name_opens_the_only_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    _novel(tmp_path, "Only", "Only")
    out = _call(mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Only")]))), "resume", {})
    assert out["work"]["title"] == "Only"
