import statistics
from pathlib import Path

import pytest

from litcritic import corpus, query
from litcritic.cli import main


@pytest.fixture(scope="module")
def ws(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ws")
    (root / "work.toml").write_text('slug = "ws"\nlanguage = "es"\n', encoding="utf-8")
    assert main(["ingest", str(corpus.get("marianela").path), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0
    return root


def _queries(ix: query.Index) -> list[str]:
    out = [query.toc(ix)]
    for c in ix.chapters:
        out.append(query.show(ix, c["id"]))
        for s in c["scenes"][:2]:
            out.append(query.show(ix, s["id"]))
    for word in ("Pablo", "ojos", "Nela", "luz", "madre", '"la mina"', "zzzz"):
        out.append(query.find(ix, word))
    for i in range(0, len(ix.anchors), 40):
        out.append(query.context(ix, ix.anchors[i]))
    return out


def test_context_respects_budget(ws: Path) -> None:
    ix = query.load(ws)
    for budget in (150, 600, 2000):
        for anchor in ix.anchors[::97]:
            assert query.estimate_tokens(query.context(ix, anchor, budget)) <= budget
        assert query.estimate_tokens(query.show(ix, "c02", budget)) <= budget
        assert query.estimate_tokens(query.find(ix, "Nela", budget)) <= budget
        assert query.estimate_tokens(query.toc(ix, budget)) <= budget


def test_index_query_tokens_p95(ws: Path) -> None:
    ix = query.load(ws)
    sizes = sorted(query.estimate_tokens(t) for t in _queries(ix))
    p95 = sizes[int(0.95 * (len(sizes) - 1))]
    assert p95 <= 2500
    assert statistics.mean(sizes) > 200  # the queries return real content


def test_show_find_context_content(ws: Path) -> None:
    ix = query.load(ws)
    toc = query.toc(ix)
    assert "c01 | 1776 | 1 | -I-" in toc
    text = query.show(ix, "c01", budget=400)
    assert text.splitlines()[0].startswith("[c01.s0.p1] -I-")
    assert "continue: lc show c01.s1.p" in text.splitlines()[-1]
    nxt = text.splitlines()[-1].split("lc show ")[1]
    assert query.show_from(ix, nxt).startswith(f"[{nxt.rstrip('-')}]")
    found = query.find(ix, "PABLO", budget=300)
    assert found.splitlines()[0].endswith("match 'PABLO'") and "[c" in found
    assert query.find(ix, "zzzz").splitlines()[0].startswith("0 paragraphs")
    ctx = query.context(ix, "c05.s1.p3", budget=1500)
    lines = ctx.splitlines()
    target = next(k for k, line in enumerate(lines) if line.startswith(">>> [c05.s1.p3]"))
    assert lines[target - 1].startswith("[c05.s1.p2]") and lines[target + 1].startswith(
        "[c05.s1.p4]"
    )
    with pytest.raises(KeyError):
        query.show(ix, "c99")


def test_cli_queries(ws: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["show", "--workspace", str(ws), "--budget", "300"]) == 0
    assert "chapter | words" in capsys.readouterr().out
    assert main(["find", "Nela", "--workspace", str(ws), "--in", "c02"]) == 0
    assert "[c02." in capsys.readouterr().out
    assert main(["context", "c02.s1.p3", "--workspace", str(ws)]) == 0
    assert main(["show", "c77", "--workspace", str(ws)]) == 2


def test_review_regressions(ws: Path) -> None:
    ix = query.load(ws)
    # A paragraph longer than the budget is shown cut, and the hint moves on.
    long_ix = query.Index(["x " * 3000, "next one"], ["c01.s1.p1", "c01.s1.p2"], ["a", "b"], [])
    text = query.show(long_ix, "c01", budget=200)
    assert text.startswith("[c01.s1.p1] x x") and "lc show c01.s1.p2-" in text
    assert query.estimate_tokens(text) <= 200
    with pytest.raises(ValueError, match="empty"):
        query.find(ix, "  ")
    with pytest.raises(ValueError, match="at least"):
        query.toc(ix, budget=10)
