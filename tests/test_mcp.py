import io
import json
import re
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
    p1 = "It was a cold afternoon and nobody left the house."
    ws, _doc = _workspace(tmp_path, _plain(p1, "The street stayed empty."))
    if propose:
        change.propose(ws, "cold", "bitter", by="writer", why="stronger word")
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
    assert "hostCapabilities" in html  # ui/message only when the host advertises it

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
    # the id only: the work and the change, never text to write
    schema = tools["change_approve"]["inputSchema"]
    assert set(schema["properties"]) == {"work", "change"}
    assert schema["required"] == ["work", "change"]

    ran: list[list[str]] = []

    def fake_run(grant: Any, work: str, argv: list[str]) -> dict[str, Any]:
        ran.append(argv)
        return {"status": "ok"}

    monkeypatch.setattr(mcp, "_json_run", fake_run)
    res = _call_raw(server, "change_approve", {"work": "mynovel", "change": "C1"})
    out = _text(res)
    assert not res["isError"], out
    assert out["status"] == "applied" and out["locate"]["target"] == "bitter"
    assert ran == [["docx", "locate", "--quote", "bitter", "--go"]]

    again = _call_raw(server, "change_approve", {"work": "mynovel", "change": "C1"})
    assert again["isError"] and _text(again)["error"] == "not_proposed"

    change.propose(ws, "street", "road", by="writer")
    dismissed = _call_raw(server, "change_dismiss", {"work": "mynovel", "change": "C2"})
    assert _text(dismissed)["status"] == "dismissed"


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
    block = re.search(r"const SETTLED = \{(.*?)\};", html, re.S)
    assert block, "the page names every settled status"
    words = dict(re.findall(r"(\w+): \"([^\"]+)\"", block.group(1)))
    # every status a change can reach that is no longer actionable, and none that is
    assert set(words) == {"approved", "applied", "typed_by_writer", "dismissed", "undone"}
    assert not set(words) & {"proposed", *change.LIVE}
    assert words["applied"].startswith("✓") and words["dismissed"] == "Dismissed"
    assert "✗" not in "".join(words.values())
    # a refusal for a settled change shows the settled state, not the red error
    assert 'why.code === "not_proposed" && settle(await liveStatus())' in html
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
        exc.winerror = 5  # type: ignore[misc]  # only Windows sets it
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
