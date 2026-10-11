import json
import shutil
from pathlib import Path

import pytest

from litcritic import codex, corpus, query
from litcritic import spans as spanlib
from litcritic.cli import main


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("work")
    (root / "work.toml").write_text('slug = "w"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(base, root)
    codex.Codex.init(root, "v001")
    return root


def _text(root: Path) -> spanlib.Text:
    ix = query.load(root, "v001")
    return spanlib.Text(ix.paragraphs, ix.anchors, "v001")


def _span(root: Path, quote: str = "Nela") -> spanlib.Span:
    text = _text(root)
    i = next(k for k, p in enumerate(text.paragraphs) if quote in p)
    off = text.paragraphs[i].index(quote)
    a = text.anchors[i]
    return spanlib.make(text, "v001", a, off, a, off + len(quote))


def test_codex_items_round_trip_and_reload(work: Path) -> None:
    cx = codex.Codex(work)
    nela = cx.add("entity", "Main character.", {"kind": "character", "name": "Nela"})
    scene = cx.add("scene", "Opening.", {"summary": "Someone gets lost."}, [_span(work)])
    cx.update(scene.id, links=[{"rel": "about", "to": nela.id}])
    again = codex.Codex(work)
    assert again.get(scene.id).links == [{"rel": "about", "to": nela.id}]
    assert again.get(scene.id).rev == 2
    assert next(i for i, _ in again.linked_to(nela.id)).id == scene.id
    text = _text(work)
    assert again.covering(text, {again.get(scene.id).spans[0].start.para})[0].id == scene.id
    log = (work / "codex" / "changes.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["op"] for x in log] == ["add", "add", "update"]
    assert again.check() == []


def test_codex_rejects_bad_items(work: Path) -> None:
    cx = codex.Codex(work)
    with pytest.raises(codex.CodexError, match="kind"):
        cx.add("entity", "x", {"kind": "planet", "name": "X"})
    with pytest.raises(codex.CodexError, match="needs at least one span"):
        cx.add("scene", "x", {"summary": "y"})
    with pytest.raises(codex.CodexError, match="unknown item"):
        cx.add("thread", "x", {"name": "y"}, links=[{"rel": "about", "to": "en-00000000"}])
    with pytest.raises(codex.CodexError, match="unknown item type"):
        cx.add("spaceship", "x")


def test_check_finds_every_injected_defect(work: Path) -> None:
    cx = codex.Codex(work)
    ent = cx.add("entity", "A place.", {"kind": "place", "name": "Mine"})
    fact = cx.add("fact", "Something happens.", {"claim": "x"}, [_span(work)])
    target = cx.add("thread", "A subplot.", {"name": "t"})
    linker = cx.add("thread", "Another.", {"name": "u"}, links=[{"rel": "about", "to": target.id}])
    items = work / "codex" / "items"
    rows = {
        "dead": {
            **cx.get(linker.id).as_json(),
            "id": "th-deadbeef",
            "links": [{"rel": "about", "to": "en-00000000"}],
        },
        "orphan": {**cx.get(fact.id).as_json(), "id": "fa-0ddba11a", "spans": [], "links": []},
        "stale": {**cx.get(fact.id).as_json(), "id": "fa-5ca1ab1e"},
        "schema": {**cx.get(ent.id).as_json(), "id": "en-badf00d0", "fields": {"name": "X"}},
    }
    rows["stale"]["spans"][0]["state"] = "changed"
    with (items / "thread.jsonl").open("a") as fh:
        fh.write(json.dumps(rows["dead"]) + "\n")
    with (items / "fact.jsonl").open("a") as fh:
        fh.write(json.dumps(rows["orphan"]) + "\n" + json.dumps(rows["stale"]) + "\n")
    with (items / "entity.jsonl").open("a") as fh:
        fh.write(json.dumps(rows["schema"]) + "\n" + json.dumps(cx.get(ent.id).as_json()) + "\n")
    problems = "\n".join(codex.Codex(work).check())
    expected = {
        "dead link": "th-deadbeef: dead link",
        "orphan": "fa-0ddba11a: orphan",
        "stale span": "fa-5ca1ab1e: stale span",
        "duplicate id": f"duplicate id {ent.id}",
        "schema failure": "en-badf00d0.fields",
    }
    missing = [k for k, v in expected.items() if v not in problems]
    assert missing == [], problems


def test_new_type_needs_no_core_change(work: Path, tmp_path: Path) -> None:
    extra = tmp_path / "types"
    extra.mkdir()
    (extra / "motif.toml").write_text(
        'type = "motif"\nprefix = "mo"\nlinks = ["about"]\ncolumns = ["name"]\n'
        'spans_required = true\n\n[schema]\ntype = "object"\nrequired = ["name"]\n'
        '[schema.properties.name]\ntype = "string"\n',
        encoding="utf-8",
    )
    types = codex.load_types(extra)
    cx = codex.Codex(work, types)
    item = cx.add("motif", "Recurring light.", {"name": "light"}, [_span(work)])
    assert codex.Codex(work, types).get(item.id).fields == {"name": "light"}
    assert item.id.startswith("mo-")


def test_codex_write_is_atomic(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cx = codex.Codex(work)
    cx.add("entity", "First.", {"kind": "character", "name": "A"})
    before = (work / "codex" / "items" / "entity.jsonl").read_text(encoding="utf-8")

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("litcritic.codex.os.replace", boom)
    with pytest.raises(OSError):
        cx.add("entity", "Second.", {"kind": "character", "name": "B"})
    assert (work / "codex" / "items" / "entity.jsonl").read_text(encoding="utf-8") == before


def test_codex_cli_add_show_find_check(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(work)]
    assert (
        main(
            [
                "codex",
                "add",
                "entity",
                "--text",
                "Heroine.",
                "--fields",
                '{"kind": "character", "name": "Nela"}',
                *w,
            ]
        )
        == 0
    )
    ent = capsys.readouterr().out.strip()
    assert (
        main(
            [
                "codex",
                "add",
                "dialogue",
                "--text",
                "She speaks.",
                "--fields",
                json.dumps({"speaker": ent}),
                "--quote",
                _span(work).exact,
                "--within",
                _span(work).start.para,
                "--link",
                f"about:{ent}",
                *w,
            ]
        )
        == 0
    )
    dl = capsys.readouterr().out.strip()
    assert main(["codex", "show", ent, *w]) == 0
    assert f"<- about {dl}" in capsys.readouterr().out
    assert main(["codex", "find", "heroine", *w]) == 0
    assert ent in capsys.readouterr().out
    assert main(["codex", "check", *w]) == 0
    assert main(["codex", "retire", ent, *w]) == 0
    capsys.readouterr()
    assert main(["codex", "check", *w]) == 1
    assert "links to retired" in capsys.readouterr().out


def test_codex_covering_finds_spans_running_through(work: Path) -> None:
    cx = codex.Codex(work)
    text = _text(work)
    scene = cx.add(
        "scene",
        "Long.",
        {"summary": "x"},
        [spanlib.make(text, "v001", text.anchors[2], 0, text.anchors[6], 3)],
    )
    assert [i.id for i in cx.covering(text, {text.anchors[4]})] == [scene.id]
    assert cx.covering(text, {text.anchors[8]}) == []


def test_codex_never_rewrites_a_damaged_file(work: Path) -> None:
    cx = codex.Codex(work)
    cx.add("entity", "One.", {"kind": "character", "name": "A"})
    path = work / "codex" / "items" / "entity.jsonl"
    path.write_text(path.read_text() + "null\n" + '{"id": "en-1", "links": [{"rel": "x"}]}\n')
    damaged = codex.Codex(work)
    assert len(damaged.load_errors) == 2
    with pytest.raises(codex.CodexError, match="could not be read"):
        damaged.add("entity", "Two.", {"kind": "character", "name": "B"})
    assert path.read_text().count("\n") == 3


def test_codex_meta_keeps_other_keys_and_rejects_bad_drafts(work: Path) -> None:
    cx = codex.Codex(work)
    cx.set_meta(last_sync="2026-10-11")
    cx.set_meta(synced_draft="v001")
    assert codex.Codex(work).meta["last_sync"] == "2026-10-11"
    with pytest.raises(codex.CodexError):
        cx.set_meta(synced_draft='v"1')
    with pytest.raises(codex.CodexError, match="not been ingested"):
        cx.set_meta(synced_draft="v999")


def test_codex_replace_all_validates_and_bumps_rev(work: Path) -> None:
    cx = codex.Codex(work)
    ent = cx.add("entity", "One.", {"kind": "character", "name": "A"})
    changed = codex.Item.from_json({**ent.as_json(), "status": "needs_reread"})
    cx.replace_all([changed])
    assert codex.Codex(work).get(ent.id).rev == 2
    broken = codex.Item.from_json({**ent.as_json(), "links": [{"rel": "knows", "to": "en-0"}]})
    with pytest.raises(codex.CodexError, match="unknown item"):
        cx.replace_all([broken])
