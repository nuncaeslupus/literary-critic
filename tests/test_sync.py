import json
import os
import random
import shutil
import time
from pathlib import Path

import pytest
from codex_fixture import build

from litcritic import codex, corpus, query, sync, synth, view
from litcritic import spans as spanlib
from litcritic.cli import main


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("marianela")
    return root, build(root)


@pytest.fixture
def work(base: tuple[Path, dict[str, str]], tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "w"
    shutil.copytree(base[0], root)
    return root, base[1]


def _new_draft(root: Path, paragraphs: list[str], tmp: Path) -> None:
    src = tmp / "draft.txt"
    src.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")
    assert main(["ingest", str(src), "--workspace", str(root)]) == 0
    assert main(["anchor", "--workspace", str(root)]) == 0


def _old(root: Path) -> list[str]:
    return query.load(root, "v001").paragraphs


def test_sync_single_edit_flags_only_reached_items(
    work: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    root, _ = work
    cx = codex.Codex(root)
    paras = _old(root)
    target = next(d for d in cx.of_type("dialogue") if len(d.spans) == 1)
    i = query.load(root, "v001").anchors.index(target.spans[0].start.para)
    edited = [*paras[:i], paras[i].replace(" ", "  muy ", 1), *paras[i + 1 :]]
    _new_draft(root, edited, tmp_path)
    old_text = spanlib.Text(paras, query.load(root, "v001").anchors, "v001")
    reached = {it.id for it in cx.covering(old_text, {old_text.anchors[i]})}
    reached |= {src.id for r in list(reached) for src, rel in cx.linked_to(r) if rel in sync.HOP}
    report = sync.sync(root)
    assert target.id in report.flagged
    assert len(report.flagged) / len(reached) <= 1.5
    after = codex.Codex(root)
    assert after.draft == "v002" and after.check() == []
    queue = [json.loads(x) for x in (root / "codex" / "reread.jsonl").read_text().splitlines()]
    assert {q["item"] for q in queue} == set(report.flagged)


def test_sync_rename_keeps_entity_id(work: tuple[Path, dict[str, str]], tmp_path: Path) -> None:
    root, ids = work
    before = view.View(root).run(
        "SELECT COUNT(*) FROM mentions WHERE entity_id = ?", (ids["celipin"],)
    )[1][0][0]
    _new_draft(root, [p.replace("Celipín", "Celipino") for p in _old(root)], tmp_path)
    report = sync.sync(root)
    assert (ids["celipin"], "Celipín", "Celipino") in report.renamed
    ent = codex.Codex(root).get(ids["celipin"])
    assert ent.fields["name"] == "Celipino" and "Celipín" in ent.fields["aliases"]
    assert codex.Codex(root).check() == []
    after = view.View(root).run(
        "SELECT COUNT(*) FROM mentions WHERE entity_id = ?", (ids["celipin"],)
    )[1][0][0]
    assert after == before > 10


def test_sync_deleted_paragraph_flags_dependents(
    work: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    root, _ = work
    cx = codex.Codex(root)
    ix = query.load(root, "v001")
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    i = next(k for k, p in enumerate(ix.paragraphs) if len(p) > 200 and k > 300)
    fact = cx.add(
        "fact",
        "Event here.",
        {"claim": "x"},
        [spanlib.make(text, "v001", ix.anchors[i], 0, ix.anchors[i], 40)],
    )
    later = cx.add(
        "fact",
        "Refers back.",
        {"claim": "y"},
        [spanlib.make(text, "v001", ix.anchors[i + 5], 0, ix.anchors[i + 5], 10)],
        [{"rel": "depends_on", "to": fact.id}],
    )
    _new_draft(root, ix.paragraphs[:i] + ix.paragraphs[i + 1 :], tmp_path)
    report = sync.sync(root)
    assert fact.id in report.lost and later.id in report.dependents
    after = codex.Codex(root)
    assert after.get(later.id).status == "needs_reread"
    assert after.get(later.id).spans[0].state in ("ok", "moved")
    assert after.check() == []


def test_sync_100k_words_under_5s(tmp_path: Path) -> None:
    root = tmp_path / "big"
    root.mkdir()
    (root / "work.toml").write_text('slug = "big"\nlanguage = "es"\n', encoding="utf-8")
    text = corpus.get("marianela").read()
    big = synth.paragraphs(text) * 2
    _new_draft(root, big, tmp_path)
    codex.Codex.init(root, "v001")
    ix = query.load(root, "v001")
    t = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    rng = random.Random(7)
    usable = [k for k, p in enumerate(ix.paragraphs) if len(p) > 30]
    rows = []
    for n in range(20_000):
        k = rng.choice(usable)
        span = spanlib.make(t, "v001", ix.anchors[k], 0, ix.anchors[k], 25).as_json()
        rows.append(
            json.dumps(
                {
                    "id": f"fa-{n:08x}",
                    "type": "fact",
                    "text": "x",
                    "spans": [span],
                    "links": [],
                    "fields": {"claim": "c"},
                }
            )
        )
    (root / "codex" / "items" / "fact.jsonl").write_text("\n".join(rows) + "\n")
    words = sum(len(p.split()) for p in ix.paragraphs)
    assert words > 90_000
    _new_draft(root, synth.generate("\n\n".join(big), 3, 0.05).paragraphs, tmp_path)
    start = time.perf_counter()
    report = sync.sync(root, cx=codex.Codex(root))
    elapsed = time.perf_counter() - start
    assert report.new == "v002"
    limit = 5.0 * float(os.environ.get("LITCRITIC_PERF_FACTOR", "1"))
    assert elapsed <= limit, elapsed


def test_sync_rename_with_spans_keeps_relocation_and_queue(
    work: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    root, ids = work
    cx = codex.Codex(root)
    ix = query.load(root, "v001")
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    i = next(k for k, p in enumerate(ix.paragraphs) if "Celipín" in p and k > 50)
    off = ix.paragraphs[i].index("Celipín")
    span = spanlib.make(text, "v001", ix.anchors[i], off, ix.anchors[i], off + 7)
    cx.update(ids["celipin"], spans=[span])
    cx.update(ids["pablo"], status="needs_reread")
    _new_draft(root, [p.replace("Celipín", "Celipino") for p in ix.paragraphs], tmp_path)
    report = sync.sync(root)
    after = codex.Codex(root)
    ent = after.get(ids["celipin"])
    assert ent.fields["name"] == "Celipino" and ent.status == "needs_reread"
    assert ent.spans[0].draft == "v002" and ids["celipin"] in report.changed
    queue = {
        json.loads(x)["item"]: json.loads(x)["reason"]
        for x in (root / "codex" / "reread.jsonl").read_text().splitlines()
    }
    assert queue[ids["pablo"]] == "earlier" and queue[ids["celipin"]] == "changed"
    assert after.check() == []


def test_sync_refuses_going_back(work: tuple[Path, dict[str, str]], tmp_path: Path) -> None:
    root, _ = work
    _new_draft(root, _old(root), tmp_path)
    sync.sync(root)
    with pytest.raises(codex.CodexError, match="does not go back"):
        sync.sync(root, "v001")
