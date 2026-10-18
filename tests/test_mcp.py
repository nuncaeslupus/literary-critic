import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from litcritic import __version__, claude_app, folders, mcp
from litcritic.cli import build_parser

FIXTURES = Path(__file__).parent / "fixtures" / "mcp"
COLD = "It was a cold afternoon and nobody left the house."


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
    assert out["versions"] == mcp.versions()  # "which version?" answered from resume too

    second = _call(server, "resume", {"work": "second"})
    assert second["work"]["next_step"]["step"] == "setup"
    listed = _call(server, "works", {})
    assert listed["works"][0]["title"] == "Second"  # most recent first
    assert listed["versions"]["literary-critic"] == __version__
    assert listed["versions"]["doc-control"]  # installed in the test environment

    missing = _call(server, "resume", {"work": "Unknown Book"})
    assert missing["not_found"] == "Unknown Book"
    assert {w["title"] for w in missing["works"]} == {"Época de lluvias", "Second"}
    assert "add_folder" in missing["hint"]

    several = _call(server, "resume", {})
    assert len(several["choose"]) == 2
    assert (
        several["versions"]["literary-critic"]
        == __version__
        == missing["versions"]["literary-critic"]
    )
    tool = next(
        t
        for t in _replay(server, [{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])[0][
            "result"
        ]["tools"]
        if t["name"] == "resume"
    )
    assert "which version?" in tool["description"]


def test_resume_without_name_opens_the_only_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    _novel(tmp_path, "Only", "Only")
    out = _call(mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Only")]))), "resume", {})
    assert out["work"]["title"] == "Only"


@pytest.fixture
def jekyll(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> mcp.Server:
    """A granted folder with one real work: the start of the corpus novel, set up."""
    from litcritic import setup

    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    novel = tmp_path / "Novels" / "Jekyll"
    novel.mkdir(parents=True)
    text = (Path(__file__).parents[1] / "corpus" / "jekyll-hyde" / "text.txt").read_text("utf-8")
    (novel / "jekyll.txt").write_text(text[:20000], encoding="utf-8")
    setup.setup(novel)
    return mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Novels")])))


def _call_raw(server: mcp.Server, name: str, args: dict[str, Any]) -> dict[str, Any]:
    send = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
    reply = _replay(server, [{**send, "params": {"name": name, "arguments": args}}])[0]
    result: dict[str, Any] = reply["result"]
    return result


def test_run_refuses_commands_outside_allow_list(jekyll: mcp.Server, tmp_path: Path) -> None:
    refused = [
        ["guard", "--all"],
        ["init", "x"],
        ["kit"],
        "round status; rm -rf ~",  # a shell string
        ["show", "--workspace", str(tmp_path)],
        ["find", "x", "--in", str(tmp_path.parent / "elsewhere.txt")],
    ]
    for command in refused:
        res = _call_raw(jekyll, "run", {"work": "jekyll", "command": command})
        assert res["isError"], command
        error = json.loads(res["content"][0]["text"])["error"]
        assert error in ("not_allowed", "outside_granted_folders"), command
    ok = _call_raw(jekyll, "run", {"work": "jekyll", "command": ["round", "status"]})
    assert not ok["isError"]
    assert "exit" in json.loads(ok["content"][0]["text"])


def test_guide_reads_the_guides_and_the_checklist_only() -> None:
    """A chat without the repo reads the guides the next steps name, and nothing else."""
    got = mcp.read_guide("20-codex-items.md")
    assert got["name"] == "prompts/20-codex-items.md" and got["text"].startswith("# ")
    assert mcp.read_guide("checklist/traits.toml")["name"] == "checklist/traits.toml"
    for bad in ("../pyproject.toml", "prompts/../AGENTS.md", "nope.md", ""):
        with pytest.raises(mcp.ToolError) as err:
            mcp.read_guide(bad)
        assert "prompts/40-checks.md" in err.value.payload["guides"], bad


def test_show_find_ask_read_the_work(jekyll: mcp.Server) -> None:
    toc = json.loads(_call_raw(jekyll, "show", {"work": "Jekyll"})["content"][0]["text"])
    assert toc["exit"] == 0 and toc["output"].strip()
    hit = json.loads(
        _call_raw(jekyll, "find", {"work": "jekyll", "query": "Utterson"})["content"][0]["text"]
    )
    assert hit["exit"] == 0 and "Utterson" in hit["output"]
    asked = _call_raw(jekyll, "ask", {"work": "jekyll", "question": "chapter-lengths"})
    assert not asked["isError"]
    missing = json.loads(_call_raw(jekyll, "show", {"work": "nope"})["content"][0]["text"])
    assert missing["not_found"] == "nope"


def test_places_result_carries_ui_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from test_docx_cli import _corpus_docx, _workspace

    from litcritic import dc

    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    _ws, doc = _workspace(tmp_path, _corpus_docx(120), anchor=True)
    server = mcp.Server(mcp.tools(folders.Grant([str(tmp_path)])))

    listed = _replay(server, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])[0]
    tool = next(t for t in listed["result"]["tools"] if t["name"] == "places")
    assert tool["_meta"]["ui"]["resourceUri"] == mcp.PLACES_URI == "ui://literary-critic/places"

    res = _call_raw(server, "places", {"work": "mynovel", "targets": ["c01", "c02", "c03"]})
    assert not res["isError"], res
    assert res["_meta"]["ui"]["resourceUri"] == mcp.PLACES_URI
    shown = res["structuredContent"]
    assert shown["doc"] == doc.name and len(shown["places"]) == 3
    assert all(p["label"] and (p.get("at") or p.get("find_phrase")) for p in shown["places"])

    page = _replay(
        server,
        [
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/read",
                "params": {"uri": mcp.PLACES_URI},
            }
        ],
    )[0]["result"]["contents"][0]
    assert page["mimeType"] == mcp.UI_MIME
    assert 'name: "select"' in page["text"]  # each button calls this server's select
    assert "doc-control 0.6.3" in page["text"]  # the version the page was adapted from

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_run(op: str, request: dict[str, Any]) -> dict[str, Any]:
        calls.append((op, request))
        return {"at": request.get("at"), "selected": True}

    monkeypatch.setattr(dc, "run", fake_run)
    place = shown["places"][0]
    args = {"doc": shown["doc"], "mode": "cursor", "front": True, "at": place.get("at", "")}
    picked = json.loads(_call_raw(server, "select", args)["content"][0]["text"])
    assert picked["ok"] and calls == [("live.select", args)]
    refused = _call_raw(server, "select", {"doc": str(doc)})
    assert refused["isError"]


def _change_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, propose: bool = True
) -> tuple[mcp.Server, Path]:
    from test_docx_cli import _plain, _workspace

    from litcritic import change

    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    p1 = COLD
    ws, _doc = _workspace(tmp_path, _plain(p1, "The street stayed empty."))
    if propose:
        change.propose(ws, "cold", "bitter", by="writer", why="stronger word")
    # No Word here: the file engine stands in for it (word-only is test_docx_cli's).
    approve = change.approve
    monkeypatch.setattr(
        change, "approve", lambda root, cid, **kw: approve(root, cid, **{**kw, "word_only": False})
    )
    return mcp.Server(mcp.tools(folders.Grant([str(tmp_path)]))), ws


def _listed(server: mcp.Server) -> dict[str, Any]:
    reply = _replay(server, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])[0]
    return {t["name"]: t for t in reply["result"]["tools"]}


def _text(res: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(res["content"][0]["text"])
    return out


def test_change_card_result_links_ui_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _ws = _change_work(tmp_path, monkeypatch)
    tool = _listed(server)["change_card"]
    assert tool["_meta"]["ui"]["resourceUri"] == mcp.CHANGE_URI == "ui://literary-critic/change"

    res = _call_raw(server, "change_card", {"work": "mynovel", "change": "C1"})
    assert not res["isError"], res
    assert res["_meta"]["ui"]["resourceUri"] == mcp.CHANGE_URI
    shown = res["structuredContent"]
    assert shown["id"] == "C1" and shown["work"] == "mynovel"
    assert "cold" in shown["card"]["text"] and "bitter" in shown["card"]["text"]

    msg = {"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": mcp.CHANGE_URI}}
    page = _replay(server, [msg])[0]["result"]["contents"][0]
    assert page["mimeType"] == mcp.UI_MIME
    html = page["text"]
    assert html.count("<button") == 2
    assert ">Approve</button>" in html and ">Dismiss</button>" in html
    assert '"change_approve"' in html and '"change_dismiss"' in html
    assert "ui/message" not in html  # one click approves: no chat message to send
    assert "updateModelContext" in html  # the outcome reaches the model only when the host takes it

    assert _call_raw(server, "change_card", {"work": "mynovel", "change": "C9"})["isError"]


def test_change_approve_tool_is_app_only_and_locates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import change

    server, ws = _change_work(tmp_path, monkeypatch)
    tools = _listed(server)
    for name in ("change_approve", "change_dismiss"):
        assert tools[name]["_meta"]["ui"]["visibility"] == ["app"]
        assert "resourceUri" not in tools[name]["_meta"]["ui"]
    assert tools["change_card"]["_meta"]["ui"]["visibility"] == ["model", "app"]
    # the id only: the work and the change (and whether Word goes there), never text
    schema = tools["change_approve"]["inputSchema"]
    assert set(schema["properties"]) == {"work", "change", "go"}
    assert schema["required"] == ["work", "change"]

    ran: list[list[str]] = []

    def fake_run(grant: Any, work: str, argv: list[str]) -> dict[str, Any]:
        ran.append(argv)
        return {"status": "ok"}

    monkeypatch.setattr(mcp, "_json_run", fake_run)
    res = _call_raw(server, "change_approve", {"work": "mynovel", "change": "C1"})
    out = _text(res)
    assert not res["isError"], out
    # Word goes to the new wording between the words pinned around it (here, all of it).
    bitter = COLD.replace("cold", "bitter")
    assert out["status"] == "applied" and out["locate"]["target"] == bitter
    assert ran == [["docx", "locate", "--quote", bitter, "--go"]]

    again = _call_raw(server, "change_approve", {"work": "mynovel", "change": "C1"})
    assert again["isError"] and _text(again)["error"] == "not_proposed"

    change.propose(ws, "street", "road", by="writer")
    dismissed = _call_raw(server, "change_dismiss", {"work": "mynovel", "change": "C2"})
    assert _text(dismissed)["status"] == "dismissed"


def test_change_card_proposes_inline_and_shows_a_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _ws = _change_work(tmp_path, monkeypatch, propose=False)
    made = _call_raw(
        server,
        "change_card",
        {"work": "mynovel", "quote": "cold", "replace": "bitter", "why": "x", "by": "writer"},
    )
    assert not made["isError"], made
    shown = made["structuredContent"]
    assert shown["id"] == "C1" and shown["status"] == "proposed"
    assert [c["id"] for c in shown["changes"]] == ["C1"]
    buttons = set(shown["card"]["buttons"])
    assert {"approve", "dismiss", "go", "approved", "dismissed", "undone"} <= buttons
    assert {"applying", "dismissing"} <= buttons  # said in words while a click runs
    assert {"approve_all", "dismiss_all"} <= buttons  # a batch: each change, or all at once

    _call_raw(server, "change_card", {"work": "mynovel", "quote": "street", "replace": "road"})
    both = _call_raw(server, "change_card", {"work": "mynovel", "changes": ["C1", "C2"]})
    assert [c["id"] for c in both["structuredContent"]["changes"]] == ["C1", "C2"]
    assert "road" in both["structuredContent"]["changes"][1]["card"]["text"]

    nothing = _call_raw(server, "change_card", {"work": "mynovel"})
    assert nothing["isError"] and _text(nothing)["error"] == "missing_arguments"
    refused = _call_raw(server, "change_card", {"work": "mynovel", "quote": "x", "replace": "x"})
    assert refused["isError"] and _text(refused)["error"] == "invalid"


def test_change_card_proposes_several_edits_in_one_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Several changes are one call and one box, never a box each and then the batch; an
    edit that cannot be proposed is said, the others still shown."""
    server, _ws = _change_work(tmp_path, monkeypatch, propose=False)
    edits = [
        {"quote": "cold", "replace": "bitter", "why": "stronger"},
        {"quote": "street", "replace": "road", "why": "plainer"},
        {"quote": "no such words", "replace": "x"},
    ]
    res = _call_raw(server, "change_card", {"work": "mynovel", "edits": edits, "by": "writer"})
    assert not res["isError"], res
    shown = res["structuredContent"]
    assert [c["id"] for c in shown["changes"]] == ["C1", "C2"]
    assert [n["quote"] for n in shown["not_proposed"]] == ["no such words"]
    none = _call_raw(server, "change_card", {"work": "mynovel", "edits": edits[2:] * 2})
    assert none["isError"] and _text(none)["error"] == "not_proposed"
    described = _listed(server)["change_card"]["description"]
    assert "edits" in described and "never say card" in described.replace("\n", " ")


def test_change_go_takes_word_to_the_change_before_and_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _ws = _change_work(tmp_path, monkeypatch)
    tool = _listed(server)["change_go"]
    assert tool["_meta"]["ui"]["visibility"] == ["app"]
    ran: list[list[str]] = []

    def fake_run(grant: Any, work: str, argv: list[str]) -> dict[str, Any]:
        ran.append(argv)
        return {"status": "done"}

    monkeypatch.setattr(mcp, "_json_run", fake_run)
    went = _text(_call_raw(server, "change_go", {"work": "mynovel", "change": "C1"}))
    assert went["went"]["status"] == "done"
    batch = {"work": "mynovel", "change": "C1", "go": False}
    assert "went" not in _text(_call_raw(server, "change_approve", batch))  # a batch goes once
    _call_raw(server, "change_go", {"work": "mynovel", "change": "C1"})
    assert ran == [
        ["docx", "locate", "--quote", COLD, "--go"],  # the old wording before approval
        ["docx", "locate", "--quote", COLD.replace("cold", "bitter"), "--go"],  # the new
    ]
    # Word did not move: the card is told, in the novel's language, not a silent "ok".
    monkeypatch.setattr(mcp, "_json_run", lambda *a: {"status": "refused"})
    lost = _call_raw(server, "change_go", {"work": "mynovel", "change": "C1"})
    assert lost["isError"] and _text(lost)["error"] == "not_found"
    assert "Word" in _text(lost)["message"]
    unknown = _call_raw(server, "change_go", {"work": "mynovel", "change": "C9"})
    assert unknown["isError"] and _text(unknown)["error"] == "unknown_change"


def test_change_go_finds_an_unsaved_edit_in_the_open_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import word_live

    server, _ws = _change_work(tmp_path, monkeypatch)
    went: list[tuple[Path, str]] = []
    monkeypatch.setattr(word_live, "is_open", lambda doc: True)

    def go(doc: Path, phrase: str, at: str = "") -> dict[str, str]:
        went.append((doc, phrase))
        return {"status": "done"}

    monkeypatch.setattr(word_live, "go", go)
    monkeypatch.setattr(mcp, "_json_run", lambda *a: pytest.fail("the file is not read"))
    out = _text(_call_raw(server, "change_go", {"work": "mynovel", "change": "C1"}))
    assert out["went"]["status"] == "done"
    assert went[0][1] == COLD and went[0][0].is_file()


def test_select_opens_the_document_word_does_not_have_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import dc, word_live

    server, ws = _change_work(tmp_path, monkeypatch, propose=False)
    opened: list[Path] = []
    tries: list[dict[str, Any]] = []

    def run(op: str, request: dict[str, Any]) -> dict[str, Any]:
        tries.append(request)
        if not opened:
            raise dc.DocError("DOC_NOT_OPEN", "not open")
        return {"selected": True}

    monkeypatch.setattr(word_live, "run", run)

    def open_if_closed(doc: Path) -> bool:
        opened.append(doc)
        return True

    monkeypatch.setattr(word_live, "open_if_closed", open_if_closed)
    args = {"doc": "MyNovel_v3.docx", "find_phrase": "cold", "mode": "cursor"}
    out = _text(_call_raw(server, "select", {**args, "work": "mynovel"}))
    assert out["ok"] and out["opened"] and opened == [ws.parent / "MyNovel_v3.docx"]
    assert tries == [args, args]  # the work picks the file; Word gets the name alone

    opened.clear()
    monkeypatch.setattr(word_live, "open_if_closed", lambda doc: False)
    out = _text(_call_raw(server, "select", {**args, "work": "mynovel"}))
    assert not out["ok"] and out["error"]["code"] == "DOC_NOT_OPEN"
    out = _text(_call_raw(server, "select", args))  # without the work: nothing to open
    assert not out["ok"]


def test_run_help_answers_with_the_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server, _ws = _change_work(tmp_path, monkeypatch, propose=False)
    for argv in (["change", "propose", "--help"], ["change", "-h"]):
        res = _call_raw(server, "run", {"work": "mynovel", "command": argv})
        out = _text(res)
        assert not res["isError"] and out["exit"] == 0, out
        assert "usage:" in out["output"] and "propose" in out["output"]
    bad = _call_raw(server, "run", {"work": "mynovel", "command": ["change", "nope"]})
    assert bad["isError"] and _text(bad)["error"] == "bad_command"


def test_change_status_tool_is_app_only_and_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import change

    server, ws = _change_work(tmp_path, monkeypatch)
    tool = _listed(server)["change_status"]
    assert tool["_meta"]["ui"]["visibility"] == ["app"]
    assert set(tool["inputSchema"]["properties"]) == {"work", "change"}

    def status(cid: str) -> str:
        res = _call_raw(server, "change_status", {"work": "mynovel", "change": cid})
        assert not res["isError"], res
        out = _text(res)
        assert out["id"] == cid and out["work"] == "mynovel"
        return str(out["status"])

    # the card's own result stays "proposed"; the status tool follows the log
    card = _call_raw(server, "change_card", {"work": "mynovel", "change": "C1"})
    assert card["structuredContent"]["status"] == "proposed" == status("C1")
    monkeypatch.setattr(mcp, "_json_run", lambda *a: {"status": "ok"})
    assert not _call_raw(server, "change_approve", {"work": "mynovel", "change": "C1"})["isError"]
    assert status("C1") == "applied"
    assert change.mark_undone(ws, ["C1"], "op1") == "C1"
    assert status("C1") == "undone"
    change.propose(ws, "street", "road", by="writer")
    change.dismiss(ws, "C2")
    assert status("C2") == "dismissed"

    unknown = _call_raw(server, "change_status", {"work": "mynovel", "change": "C9"})
    assert unknown["isError"] and _text(unknown)["error"] == "unknown_change"


def test_change_page_renders_settled_changes_as_settled() -> None:
    from litcritic import change

    html = (Path(mcp.__file__).parent / "ui" / "change.html").read_text(encoding="utf-8")
    assert '"change_status"' in html  # asked on load, the tool result may be stale
    block = re.search(r"const SETTLED = \(\) => \(\{(.*?)\}\);", html, re.S)
    assert block, "the page names every settled status"
    keys = dict(re.findall(r"(\w+): labels\.(\w+)", block.group(1)))
    # every status a change can reach that is no longer actionable, and none that is
    assert set(keys) == {"approved", "applied", "typed_by_writer", "dismissed", "undone"}
    assert not set(keys) & {"proposed", *change.LIVE}
    # the words come from the card, in the novel's language, with English in the page
    for lang in ("en", "es"):
        words = {status: change._BUTTONS[lang][key] for status, key in keys.items()}
        assert words["applied"].startswith("✓") and not words["dismissed"].startswith("✓")
        assert "✗" not in "".join(words.values())
        assert all(f'{key}: "{change._BUTTONS["en"][key]}"' in html for key in keys.values())
    # a refusal for a settled change shows the settled state, not the red error
    assert 'why.code === "not_proposed" && settle(row, await liveStatus(row))' in html
    assert '$("buttons").hidden = true' in html


def test_state_includes_plan_active_and_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from litcritic import plan

    server, ws = _change_work(tmp_path, monkeypatch, propose=False)
    assert _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]["plan"] is None

    state, _ev = plan.init(ws, "iterative")
    ids = [p["id"] for p in state["parts"]][:3]
    for pid in ids:
        plan.transition(ws, "accept", pid, "writer")
    plan.transition(ws, "start", ids[0], "writer")

    shown = _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]
    assert shown["plan"]["active"]["id"] == ids[0]
    assert [p["id"] for p in shown["plan"]["next"]] == ids[1:3]
    assert 0 < len(shown["plan"]["timeline"]) <= 5
    assert shown["next_step"]["step"] == "index"  # indexing still comes before the plan
    monkeypatch.setattr(mcp, "_index_state", lambda root: {"packets": 1, "todo": 0})
    done = _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]
    assert done["next_step"]["step"] == "plan"

    tool = _text(_call_raw(server, "plan", {"work": "mynovel"}))
    assert tool["status"] == "ok" and tool["active"]["id"] == ids[0]


def test_a_novel_never_set_up_is_found_and_set_up_from_the_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    novel = tmp_path / "Novelas" / "Señora, Ñúñez"  # a comma and accents survive
    novel.mkdir(parents=True)
    text = (Path(__file__).parents[1] / "corpus" / "jekyll-hyde" / "text.txt").read_text("utf-8")
    (novel / "Ruiseñor.txt").write_text(text[:20000], encoding="utf-8")
    (novel / "~$iseñor.docx").write_text("lock", encoding="utf-8")
    server = mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Novelas")])))

    missing = _call(server, "resume", {"work": "ruisenor"})
    assert missing["not_set_up"][0] == {
        "name": "Señora, Ñúñez",
        "folder": str(novel),
        "named": "yes",
    }
    assert "setup" in missing["hint"]

    ready = _call(server, "setup", {"folder": str(novel)})
    assert ready["status"] == "ready" and ready["manuscript"]["path"] == "Ruiseñor.txt"
    assert "ai_notice" in ready and "resume" in ready["say"]
    refused = _call(server, "setup", {"folder": str(novel), "prose_suggestions": "minor"})
    assert refused["reason"] == "ai_notice" and refused["notice"]
    chosen = _call(server, "setup", {"folder": str(novel), "edit_in_place": False})
    assert chosen["settings"]["edit_in_place"] is False

    found = _call(server, "resume", {"work": "Señora, Ñúñez"})
    assert found["work"]["draft"] == "v001"
    assert _call(server, "resume", {"work": "x"}).get("not_set_up") is None


def test_setup_refuses_a_folder_outside_the_grant(tmp_path: Path) -> None:
    server = mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Granted")])))
    (tmp_path / "Granted").mkdir()
    res = _call_raw(server, "setup", {"folder": str(tmp_path)})
    assert res["isError"]
    assert json.loads(res["content"][0]["text"])["error"] == "outside_granted_folders"


def test_run_explains_a_windows_block_only_when_the_command_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed save comes back with the clicks to fix it; novel text quoting it does not."""
    import argparse

    server, _ws = _change_work(tmp_path, monkeypatch, propose=False)

    def blocked(args: Any) -> int:
        exc = PermissionError(13, "Access is denied", r"C:\Users\w\Documents\n\x.json")
        setattr(exc, "winerror", 5)  # noqa: B010  # only Windows defines it
        raise exc

    def open_in_word(args: Any) -> int:
        message = r"[WinError 32] being used by another process: 'C:\n\draft.docx'"
        print(json.dumps({"status": "error", "message": message}))
        return 2

    def quoted(args: Any) -> int:
        print("Access is denied, she said.")
        return 0

    def full_disk(args: Any) -> int:
        raise OSError(28, "No space left on device")

    def run(func: Any) -> dict[str, Any]:
        monkeypatch.setattr(mcp, "_parse", lambda argv: argparse.Namespace(func=func))
        return _call_raw(server, "run", {"work": "mynovel", "command": ["round", "status"]})

    out = _text(run(blocked))
    assert out["exit"] == 2 and out["windows_block"]["kind"] == "blocked"
    assert out["windows_block"]["protected_folder"] is True
    assert _text(run(open_in_word))["windows_block"]["kind"] == "open"
    assert "windows_block" not in _text(run(quoted))
    failed = run(full_disk)
    assert failed["isError"] and _text(failed)["error"] == "internal"


def test_resume_returns_the_saved_overview_and_moves_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved overview reaches the next chat; it proposes the plan instead of reading again."""
    server, ws = _change_work(tmp_path, monkeypatch, propose=False)
    monkeypatch.setattr(mcp, "_index_state", lambda root: {"packets": 1, "todo": 0})
    first = _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]
    assert first["overview"] is None and first["next_step"]["step"] == "overview"
    assert "lc overview save" in first["next_step"]["say"]

    saved = _call_raw(
        server,
        "run",
        {"work": "mynovel", "command": ["overview", "save", "--text", "Works. P1.", "--partial"]},
    )
    assert _text(saved)["exit"] == 0
    shown = _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]
    assert shown["overview"]["text"] == "Works. P1." and shown["overview"]["partial"] is True
    assert shown["next_step"]["step"] == "propose_plan"

    draft = shown["draft"]
    nxt = f"v{int(draft[1:]) + 1:03d}"
    (ws / "text" / f"{nxt}.txt").write_text("New draft.\n", encoding="utf-8")
    stale = _text(_call_raw(server, "resume", {"work": "mynovel"}))["work"]
    assert stale["overview"]["stale"] is True
    assert stale["next_step"]["step"] == "overview_stale"


def test_a_failed_call_is_logged_with_its_arguments_and_answer(tmp_path: Path) -> None:
    def fails(a: dict[str, Any]) -> Any:
        raise mcp.ToolError("changed", detail="read it again first")

    log = io.StringIO()
    server = mcp.Server([mcp.Tool("approve", "", fails)], log=log)
    _call_raw(server, "approve", {"card": "C1"})
    line = log.getvalue().strip()
    assert re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d call approve error \d+\.\ds ", line)
    assert '"C1"' in line and "read it again first" in line


def test_the_log_says_whether_the_host_draws_cards_and_fetches_them() -> None:
    log = io.StringIO()
    server = mcp.Server([], log=log)
    ext = {"extensions": {mcp.UI_EXTENSION: {"mimeTypes": [mcp.UI_MIME]}}}
    init = {"clientInfo": {"name": "host"}, "capabilities": ext}
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init})
    server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
    read = {"uri": mcp.PLACES_URI}
    server.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": read})
    lines = log.getvalue().splitlines()
    assert lines[0].endswith(" ui") and '"host"' in lines[0]
    assert lines[1].endswith(" no-ui")
    assert lines[2].endswith("page " + mcp.PLACES_URI)


def test_the_log_file_keeps_one_old_log_once_too_big(tmp_path: Path) -> None:
    state = tmp_path / "lc" / "folders.json"
    path = mcp.log_file(state)
    path.write_text("x" * (mcp.LOG_LIMIT + 1), encoding="utf-8")
    assert mcp.log_file(state) == path
    assert not path.exists() and path.with_name("mcp.log.1").exists()


@pytest.mark.parametrize(
    ("files", "kind"),
    [
        (
            {
                "extensions-installations.json": {
                    "extensions": {
                        "local.mcpb.someone.doc-control": {"manifest": {"name": "doc-control"}}
                    }
                },
                "Claude Extensions Settings/local.mcpb.someone.doc-control.json": {
                    "isEnabled": True
                },
            },
            "extension",
        ),
        (
            {
                "extensions-installations.json": {
                    "extensions": {
                        "local.mcpb.someone.doc-control": {"manifest": {"name": "doc-control"}}
                    }
                },
                "Claude Extensions Settings/local.mcpb.someone.doc-control.json": {
                    "isEnabled": False
                },
            },
            None,
        ),
        (
            {
                "claude_desktop_config.json": {
                    "mcpServers": {
                        "docs": {"command": "uvx", "args": ["--from", "doc-control[live]", "x"]},
                        "literary-critic-dev": {"command": "lc", "args": ["mcp", "doc-control"]},
                    }
                }
            },
            "config",
        ),
        ({"claude_desktop_config.json": {"mcpServers": {}}}, None),
    ],
    ids=["extension-enabled", "extension-disabled", "config-entry", "none"],
)
def test_resume_reports_standalone_doccontrol_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, Any], kind: str | None
) -> None:
    app = tmp_path / "Claude"
    for name, data in files.items():
        (app / name).parent.mkdir(parents=True, exist_ok=True)
        (app / name).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv(claude_app.APP_DIR_ENV, str(app))
    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    _novel(tmp_path, "Only", "Only")
    server = mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Only")])))

    first = _call(server, "resume", {})
    second = _call(server, "resume", {})
    if kind is None:
        assert "other_doc_control" not in first
    else:
        assert first["other_doc_control"]["kind"] == kind
        assert "Settings → Extensions" in first["other_doc_control"]["say"]
        assert "other_doc_control" not in second  # standalone_doccontrol_reported: once
    assert "other_doc_control" in first["guide"]


def test_update_check_slow_network_adds_under_100ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time

    from litcritic import kit

    monkeypatch.setenv(folders.FOLDERS_ENV, str(tmp_path / "folders.json"))
    monkeypatch.setenv("LC_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("LC_AUTO_UPDATE", raising=False)
    monkeypatch.setattr(kit, "CACHE", tmp_path / "update.json")
    monkeypatch.setattr(kit, "version_info", lambda: {"version": "0.1.0", "source": "package"})
    monkeypatch.setattr(mcp, "UPDATE", {"available": "unknown", "url": kit.RELEASES_PAGE})
    release = threading.Event()

    def slow(timeout: float) -> dict[str, Any]:
        release.wait(10)  # a 10 s network
        name = "literary-critic-0.2.0.mcpb"
        return {"tag_name": "v0.2.0", "html_url": "page", "assets": [{"name": name}]}

    monkeypatch.setattr(kit, "_fetch_release", slow)
    # read this morning, before the release: a start reads it again all the same
    (tmp_path / "update.json").write_text(
        json.dumps({"at": time.time(), "latest": "0.1.0", "url": "page"}), "utf-8"
    )
    _novel(tmp_path, "Only", "Only")
    server = mcp.Server(mcp.tools(folders.Grant([str(tmp_path / "Only")])))
    thread = mcp.start_update_check()
    started = time.perf_counter()
    out = _call(server, "resume", {})
    assert time.perf_counter() - started < 0.1  # the check adds nothing to the call
    assert out["update"]["available"] == "unknown"
    release.set()
    thread.join(5)
    resumed = _call(server, "resume", {})["update"]
    assert resumed == {
        "available": "yes",
        "url": "page",
        "staging": "off",  # LC_AUTO_UPDATE unset: the chat can say why nothing is ready
        "applied": False,
        "restart_needed": False,
    }
    listed = _call(server, "works", {"check_update": True})  # "update now": no daily limit
    assert listed["update"]["available"] == "yes"


def test_tools_list_declares_annotations() -> None:
    """Every tool says whether it only reads, so the app can group it for "Always allow"."""
    listing = [t.listing() for t in mcp.tools(None)]
    read_only = {t["name"] for t in listing if t["annotations"] == {"readOnlyHint": True}}
    assert read_only == {"works", "resume", "locate", "find", "show", "places", "ask", "guide"}
    for tool in listing:
        if tool["name"] not in read_only:
            assert tool["annotations"] == {"readOnlyHint": False, "destructiveHint": False}
