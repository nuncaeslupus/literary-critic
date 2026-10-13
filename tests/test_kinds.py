from pathlib import Path

import pytest

from litcritic import codex, kinds, query, structure, view, workspace
from litcritic import spans as spanlib
from litcritic.cli import main

# Invented placeholder poems (no real work).
POEMS = """Poems, collected.

A note on the poems that follow.

First Light

The kettle hums before the sun
the window learns its grey.

A bird repeats the only word
it found along the way

Harbour

Ropes complain against the posts,
the boats rehearse their names.

The tide comes back with nothing new
and leaves it all the same.

Late Train

Faces lean on folded coats,
the stations count us down.
"""
CORE = ("codex", "view", "structure", "sync", "spans", "questions", "workspace", "diff")


def test_poem_kind_plugs_in_without_core_change(tmp_path: Path) -> None:
    assert {"novel", "poem"} <= set(kinds.available())
    ws = workspace.create("poems", "Poems", "en", tmp_path / "home", kind="poem")
    src = tmp_path / "poems.txt"
    src.write_text(POEMS, encoding="utf-8")
    assert main(["ingest", str(src), "--workspace", str(ws.root)]) == 0
    assert main(["anchor", "--workspace", str(ws.root)]) == 0
    ix = query.load(ws.root)
    titles = [c["title"] for c in ix.chapters]
    assert titles == ["", "First Light", "Harbour", "Late Train"]
    cx = codex.Codex.init(ws.root, "v001")
    text = spanlib.Text(ix.paragraphs, ix.anchors, "v001")
    stanza = spanlib.from_quote(text, "v001", "The tide comes back")
    cx.add("stanza_form", "Quatrain.", {"lines": 2, "rhyme": "xa"}, [stanza])
    cx.add("motif", "Return.", {"name": "return"}, [stanza])
    v = view.View(ws.root)
    _, rows = v.run("SELECT lines, rhyme FROM v_stanza_form")
    assert rows == [(2, "xa")]
    assert v.run("SELECT COUNT(*) FROM chapters WHERE id != 'c00'")[1][0][0] == 3
    for name in CORE:
        src_text = (Path(codex.__file__).parent / f"{name}.py").read_text(encoding="utf-8")
        assert "poem" not in src_text.lower(), name


def test_novel_is_the_default_kind(tmp_path: Path) -> None:
    assert kinds.of_work(tmp_path).NAME == "novel"
    with pytest.raises(kinds.KindError):
        kinds.get("opera")


def test_poem_titles_need_a_block_of_their_own() -> None:
    from litcritic.kinds import poem

    lines = ["Harbour", "Ropes complain against the posts", "the boats rehearse their names"]
    meta = [{}, {"blank_before": 1}, {}]
    assert poem.chapter_starts(lines, meta) == [0]
    assert poem.chapter_starts(lines, []) == []
    s = structure.detect(lines, meta, kind="poem")
    assert [(c.title, c.reason) for c in s.chapters] == [("Harbour", "override")]


def test_unknown_kind_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "work.toml").write_text('kind = "poems"\n', encoding="utf-8")
    with pytest.raises(kinds.KindError, match="unknown kind"):
        kinds.of_work(tmp_path)
    with pytest.raises(SystemExit):
        main(["init", "x", "--title", "X", "--language", "en", "--kind", "opera"])
