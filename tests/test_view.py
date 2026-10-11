import json
import os
import shutil
import time
from pathlib import Path

import pytest

from litcritic import codex, corpus, query, view
from litcritic import spans as spanlib
from litcritic.cli import main


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("work")
    (root / "work.toml").write_text('slug = "w"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    codex.Codex.init(root, "v001")
    return root


@pytest.fixture
def work(base: Path, tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(base, root)
    return root


def _text(root: Path) -> spanlib.Text:
    ix = query.load(root, "v001")
    return spanlib.Text(ix.paragraphs, ix.anchors, "v001")


def test_view_rejects_writes(work: Path) -> None:
    v = view.View(work)
    for sql in (
        "INSERT INTO items(id) VALUES ('x')",
        "DELETE FROM paragraphs",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA query_only = OFF",
        "CREATE TABLE t(x)",
    ):
        with pytest.raises(view.ViewError):
            v.run(sql)
    assert v.run("SELECT COUNT(*) FROM paragraphs")[1][0][0] > 100


def test_view_tables_and_typed_views(work: Path) -> None:
    cx = codex.Codex(work)
    text = _text(work)
    nela = cx.add(
        "entity", "Heroine.", {"kind": "character", "name": "Nela", "aliases": ["Marianela"]}
    )
    pablo = cx.add("entity", "Blind boy.", {"kind": "character", "name": "Pablo"})
    i = next(k for k, p in enumerate(text.paragraphs) if "Nela" in p)
    span = spanlib.make(text, "v001", text.anchors[i], 0, text.anchors[i], 20)
    cx.add("dialogue", "Speaks.", {"speaker": nela.id, "addressee": pablo.id}, [span])
    v = view.View(work, cx)
    _, rows = v.run("SELECT speaker, addressee, para_idx, words FROM v_dialogue")
    assert rows == [(nela.id, pablo.id, i, rows[0][3])] and rows[0][3] > 0
    assert v.built == set()
    _, n = v.run("SELECT COUNT(*) FROM mentions WHERE entity_id = :e", {"e": nela.id})
    assert n[0][0] > 50 and "mentions" in v.built
    _, pairs = v.run("SELECT COUNT(DISTINCT scene) FROM copresence WHERE a < b")
    assert pairs[0][0] > 0
    _, grams = v.run(
        "SELECT norm, COUNT(*) c FROM ngrams WHERE n = 2 GROUP BY norm ORDER BY c DESC"
    )
    assert grams[0][1] > 20 and {"tokens", "ngrams"} <= v.built
    assert "v_dialogue(id, status, text, speaker, addressee, para_idx, words)" in v.schema()
    assert "mentions(entity_id, para_idx, off, form)" in v.schema()


def test_view_stops_runaway_queries(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view, "TIMEOUT", 0.2)
    v = view.View(work)
    with pytest.raises(view.ViewError, match="stopped"):
        v.run(
            "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT COUNT(*) FROM r"
        )


def test_view_load_time_20k_items(work: Path) -> None:
    text = _text(work)
    k = next(i for i, p in enumerate(text.paragraphs) if len(p) > 40)
    span = spanlib.make(text, "v001", text.anchors[k], 0, text.anchors[k], 10).as_json()
    rows = []
    for n in range(20_000):
        rows.append(
            json.dumps(
                {
                    "id": f"fa-{n:08x}",
                    "type": "fact",
                    "text": f"Fact {n}.",
                    "spans": [span],
                    "links": [],
                    "fields": {"claim": f"claim {n}"},
                }
            )
        )
    (work / "codex" / "items" / "fact.jsonl").write_text("\n".join(rows) + "\n")
    times = []
    for _ in range(2):
        start = time.perf_counter()
        v = view.View(work)
        times.append(time.perf_counter() - start)
    assert v.run("SELECT COUNT(*) FROM v_fact")[1][0][0] == 20_000
    # Gate: 1 s on a laptop-class machine; slow shared runners may scale it.
    limit = 1.0 * float(os.environ.get("LITCRITIC_PERF_FACTOR", "1"))
    assert min(times) <= limit, times


def test_codex_sql_cli(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    w = ["--workspace", str(work)]
    assert main(["codex", "sql", "--schema", *w]) == 0
    assert "paragraphs(idx, anchor" in capsys.readouterr().out
    assert main(["codex", "sql", "SELECT COUNT(*) AS n FROM chapters", "--json", *w]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["columns"] == ["n"] and data["rows"][0][0] > 10 and data["more"] is False
    assert main(["codex", "sql", "SELECT text FROM paragraphs", "--json", *w]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["more"] is True and len(json.dumps(data)) < 3.5 * 2100
    sql = "SELECT idx FROM paragraphs WHERE idx + 0 = :i"
    assert main(["codex", "sql", sql, "--param", "i=12", *w]) == 0
    assert capsys.readouterr().out.splitlines()[1] == "12"
    assert main(["codex", "sql", "DELETE FROM items", *w]) == 2
    out = capsys.readouterr()
    assert "error" in out.err
    assert main(["codex", "sql", "SELECT anchor FROM paragraphs", "--budget", "100", *w]) == 0
    assert "more rows" in capsys.readouterr().out
    long = "SELECT text FROM paragraphs ORDER BY length(text) DESC LIMIT 1"
    assert main(["codex", "sql", long, "--budget", "100", *w]) == 0
    assert "[…]" in capsys.readouterr().out


def test_view_cached_build_statements_cannot_write(work: Path) -> None:
    v = view.View(work)
    with pytest.raises(view.ViewError):
        v.run("INSERT INTO links VALUES (?,?,?)", ("a", "rel", "b"))
    v.run("SELECT COUNT(*) FROM tokens")
    with pytest.raises(view.ViewError):
        v.run("INSERT INTO tokens VALUES (?,?,?,?,?)", (0, 0, "x", "x", 1))
    assert v.run("SELECT COUNT(*) FROM links")[1][0][0] == 0


def test_view_computed_tables_only_built_when_used(work: Path) -> None:
    v = view.View(work)
    v.run("SELECT COUNT(*) AS mentions FROM paragraphs WHERE text LIKE '%tokens%'")
    assert v.built == set()
    _, rows = v.run(
        "SELECT g.norm, t.norm FROM ngrams g JOIN tokens t"
        " ON t.para_idx = g.para_idx AND t.pos = g.pos WHERE g.n = 2 LIMIT 200"
    )
    assert all(g.split()[0] == t for g, t in rows)


def test_documented_query_schema_names_every_table(work: Path) -> None:
    doc = (Path(__file__).parents[1] / "docs" / "codex" / "README.md").read_text(encoding="utf-8")
    v = view.View(work)
    for line in v.schema().splitlines()[1:]:
        name = line.split("(", 1)[0]
        assert f"`{'v_<type>' if name.startswith('v_') else name}`" in doc or (
            name in ("chapters", "scenes") and "`chapters`, `scenes`" in doc
        ), name


def test_changes_table_reads_the_log(work: Path) -> None:
    cx = codex.Codex(work)
    item = cx.add("entity", "Someone.", {"kind": "character", "name": "Someone"})
    cx.retire(item.id)
    sql = "SELECT op, type, text FROM changes WHERE item = ? ORDER BY rowid"
    rows = view.View(work).run(sql, [item.id])[1]
    assert rows == [("add", "entity", "Someone."), ("update", "entity", "Someone.")]
