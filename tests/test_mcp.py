import io
import json
from pathlib import Path

from litcritic import mcp
from litcritic.cli import build_parser

FIXTURES = Path(__file__).parent / "fixtures" / "mcp"


def _crash(args: dict) -> dict:
    raise RuntimeError("boom")


def _refuse(args: dict) -> dict:
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


def _replay(server: mcp.Server, sends: list) -> list:
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
