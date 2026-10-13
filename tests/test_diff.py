import json
import re
from pathlib import Path

import pytest

from litcritic import corpus, diff, synth
from litcritic.cli import main


def _measure(slug: str, seed: int, rate: float = 0.08) -> tuple[float, float, float]:
    text = corpus.get(slug).read()
    old = synth.paragraphs(text)
    draft = synth.generate(text, seed, rate)
    al = diff.align(old, draft.paragraphs)
    keep = [i for i, e in enumerate(draft.old) if e["kind"] == "unchanged"]
    mapping = al.mapping()
    stability = sum(mapping.get(i) == draft.old[i]["new"][0] for i in keep) / len(keep)  # type: ignore[index]
    truth: set[object] = {i for i, e in enumerate(draft.old) if e["kind"] != "unchanged"}
    truth |= {("new", j) for j, e in enumerate(draft.new) if e["kind"] == "inserted"}
    got: set[object] = {i for i, e in enumerate(al.old) if e["status"] != "unchanged"}
    got |= {("new", j) for j, e in enumerate(al.new) if e["status"] == "inserted"}
    tp = len(truth & got)
    return stability, tp / len(truth), tp / len(got)


@pytest.mark.parametrize("slug", ["marianela", "jekyll-hyde"])
def test_alignment_survives_synthetic_edits(slug: str) -> None:
    for seed in range(3):
        stability, recall, precision = _measure(slug, seed)
        assert stability >= 0.99
        assert recall >= 0.98
        assert precision >= 0.95


def test_statuses_on_small_example() -> None:
    old = [
        "Alpha one two three four.",
        "Beta five six seven eight nine ten.",
        "Gamma eleven twelve. Delta thirteen fourteen.",
        "Epsilon fifteen sixteen seventeen.",
        "Zeta eighteen.",
        "Eta nineteen twenty.",
        "Theta a b c d e f g h.",
        "Iota i j k l m.",
        "Kappa n o p q r.",
    ]
    new = [
        "Alpha one two three four.",
        "Beta five six seven eight nine eleven.",
        "Gamma eleven twelve.",
        "Delta thirteen fourteen.",
        "Epsilon fifteen sixteen seventeen. Zeta eighteen.",
        "Brand new words here.",
        "Iota i j k l m.",
        "Kappa n o p q r.",
        "Theta a b c d e f g h.",
    ]
    al = diff.align(old, new)
    assert [e["status"] for e in al.old] == [
        "unchanged",
        "modified",
        "split",
        "merged",
        "merged",
        "deleted",
        "moved",
        "unchanged",
        "unchanged",
    ]
    assert al.old[2]["new"] == [2, 3] and al.new[4]["old"] == [3, 4]
    assert al.new[5]["status"] == "inserted" and al.old[6]["new"] == [8]


def test_identical_drafts() -> None:
    paras = synth.paragraphs(corpus.get("jekyll-hyde").read())
    al = diff.align(paras, list(paras))
    assert al.counts == {"inserted": 0, "unchanged": len(paras)}


def test_cli_diff(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "work.toml").write_text('slug = "ws"\n', encoding="utf-8")
    text = corpus.get("jekyll-hyde").read()
    (tmp_path / "a.txt").write_text(text, encoding="utf-8")
    # Plain text marks a heading by the gaps around it; keep them in the new draft.
    headings = "|".join(re.escape(h) for h in re.findall(r"\n\n\n\n([^\n]+)\n", text))
    edited = re.sub(rf"\n\n((?:{headings})\n)\n", r"\n\n\n\n\1\n\n", synth.generate(text, 5).text)
    (tmp_path / "b.txt").write_text(edited, encoding="utf-8")
    for name in ("a", "b"):
        assert main(["ingest", str(tmp_path / f"{name}.txt"), "--workspace", str(ws)]) == 0
    assert main(["diff", "v001", "v002", "--workspace", str(ws)]) == 2  # no structure yet
    for v in ("v001", "v002"):
        assert main(["anchor", "--workspace", str(ws), "--version", v]) == 0
    assert main(["diff", "v001", "v002", "--workspace", str(ws)]) == 0
    data = json.loads((ws / "index" / "v002" / "alignment.json").read_text(encoding="utf-8"))
    assert data["counts"]["unchanged"] > 300 and data["stale_scenes"]
    assert data["old"][2]["a"] == "c01.s0.p1" and data["old"][2]["new"] == ["c01.s0.p1"]


def test_review_regressions() -> None:
    a, b, c = "Alpha one two three.", "Beta four five six.", "Gamma seven eight nine."
    # Repeated scene-break lines pair with their own copies.
    al = diff.align([a, "* * *", b, "* * *", c], ["* * *", a, "* * *", b, "* * *", c])
    assert [e["status"] for e in al.old] == ["unchanged"] * 5
    assert al.old[1]["new"] == [2] and al.new[0]["status"] == "inserted"
    # Unrelated drafts stay fast and pair nothing.
    import random
    import time

    rng = random.Random(1)
    vocab = [f"w{k}" for k in range(3000)]
    old = [" ".join(rng.choices(vocab, k=30)) for _ in range(1500)]
    new = [" ".join(rng.choices(vocab, k=30)) for _ in range(1500)]
    start = time.monotonic()
    al = diff.align(old, new)
    assert time.monotonic() - start < 15
    assert al.counts == {"deleted": 1500, "inserted": 1500}


def test_alignment_reads_doc_control_address_map() -> None:
    """Every old paragraph that kept its text maps through doc-control's address map."""
    paras = synth.paragraphs(corpus.get("jekyll-hyde").read())
    new = [*paras[:10], "An inserted paragraph of several plain words.", *paras[10:]]
    al = diff.align(paras, new)
    assert len(al.address_map) == len(paras)
    assert al.mapping() == {i: i + (i >= 10) for i in range(len(paras))}
    assert all(al.address_map[al.old_at[i]] == al.new_at[j] for i, j in al.mapping().items())
    assert al.new[10] == {"status": "inserted", "old": []}


def test_from_diff_skips_blank_paragraphs() -> None:
    """Blank document paragraphs (no workspace paragraph) drop out of every record."""
    result = {
        "changes": [
            {"kind": "unchanged", "old": ["p3#cc"], "new": ["p2#cc"]},
            {"kind": "deleted", "old": ["p2#00"], "new": []},  # a blank line
            {"kind": "modified", "old": ["p4#dd"], "new": ["p3#ee"], "similarity": 0.9},
            {"kind": "inserted", "old": [], "new": ["p4#ff"]},
        ],
        "address_map": {"p3#cc": "p2#cc", "p2#00": None, "p4#dd": "p3#ee"},
    }
    al = diff.from_diff(result, ["p1#aa", "p3#cc", "p4#dd"], ["p1#aa", "p2#cc", "p3#ee", "p4#ff"])
    assert [e["status"] for e in al.old] == ["unchanged", "unchanged", "modified"]
    assert [e["new"] for e in al.old] == [[0], [1], [2]] and al.old[2]["ratio"] == 0.9
    assert al.new[3] == {"status": "inserted", "old": []}
    assert al.counts == {"inserted": 1, "modified": 1, "unchanged": 2}
    assert al.mapping() == {0: 0, 1: 1}
