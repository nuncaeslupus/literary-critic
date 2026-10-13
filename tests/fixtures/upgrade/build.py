"""Rebuild the old-format workspaces in this folder (``<slug>.zip``, ``manifest.json``).

Runs the release before doc-control read the manuscripts, commit 6eab457::

    git archive 6eab457 src | tar -x -C /tmp/old
    PYTHONPATH=/tmp/old/src .venv/bin/python tests/fixtures/upgrade/build.py /tmp/work

Each workspace gets two drafts (the corpus text, then a seeded synthetic
revision; Marianela as ``.docx``), overrides in the first shape, a Codex with
scene cards, facts, dialogue and spans across paragraphs on the first draft,
synced to the second with that release's ``lc codex sync``, and a few items on
the second. The manuscripts are left out of the zips: ``upgrade_fixture.unpack``
rebuilds them and checks them against ``manifest.json``.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
import zipfile
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTS))

import upgrade_fixture as uf  # noqa: E402

from litcritic import codex, query, structure  # noqa: E402
from litcritic import spans as spanlib  # noqa: E402
from litcritic.cli import main  # noqa: E402


def _text(ws: Path, v: str) -> spanlib.Text:
    ix = query.load(ws, v, codex=False)
    return spanlib.Text(ix.paragraphs, ix.anchors, v)


def _items(cx: codex.Codex, ws: Path, v: str, rng: random.Random, every: int) -> None:
    t = _text(ws, v)
    data = json.loads((ws / "index" / v / "structure.json").read_text(encoding="utf-8"))
    who = cx.add("entity", "A placeholder speaker.", {"kind": "character", "name": "Speaker"}).id
    if every == 1:  # first draft: one card per scene
        for ch in data["chapters"]:
            for sc in ch["scenes"]:
                a, b = t.anchors[sc["start"]], t.anchors[sc["end"]]
                span = spanlib.make(t, v, a, 0, b, len(t.paragraphs[sc["end"]]))
                cx.add("scene", "Scene card.", {"summary": "A scene."}, [span])
    heads = {ch["start"] for ch in data["chapters"]}
    for i, p in enumerate(t.paragraphs):
        if i in heads or len(p) < 80:
            continue
        roll = rng.random()
        a = t.anchors[i]
        if roll < 0.12 / every:  # a sentence inside the paragraph
            cut = p.find(". ")
            if 0 < cut < len(p) - 20:
                end = p.find(". ", cut + 2)
                end = len(p) if end == -1 else end + 1
                span = spanlib.make(t, v, a, cut + 2, a, end)
                cx.add("fact", "A fact.", {"claim": "Something happens.", "role": "event"}, [span])
        elif roll < 0.18 / every and p[0] in '-—«"“':  # a whole dialogue paragraph
            span = spanlib.make(t, v, a, 0, a, len(p))
            cx.add("dialogue", "Someone speaks.", {"speaker": who}, [span])
        elif roll < 0.21 / every and i + 1 < len(t.paragraphs):  # across two paragraphs
            b = t.anchors[i + 1]
            span = spanlib.make(t, v, a, len(p) - 30, b, min(30, len(t.paragraphs[i + 1])))
            cx.add("fact", "Across a break.", {"claim": "It goes on.", "role": "event"}, [span])


def build(slug: str, work: Path) -> None:
    ws = work / slug
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "analysis").mkdir(parents=True)
    (ws / "work.toml").write_text(uf.work_toml(slug), encoding="utf-8")
    drafts = uf.manuscripts(slug, work / f"{slug}-src")
    first = uf.override_targets(slug)
    (ws / "analysis" / "structure-overrides.json").write_text(
        json.dumps(
            {
                "scene_starts": [structure.fingerprint(first["scene_start"])],
                "not_chapter": [structure.fingerprint(first["not_chapter"])],
            }
        ),
        encoding="utf-8",
    )
    rng = random.Random(int(str(uf.RECIPES[slug]["seed"])))
    for n, path in enumerate(drafts, 1):
        v = f"v{n:03d}"
        assert main(["ingest", str(path), "--workspace", str(ws)]) == 0
        assert main(["anchor", "--workspace", str(ws)]) == 0, slug
        if n == 1:
            _items(codex.Codex.init(ws, v), ws, v, rng, 1)
        else:
            assert main(["diff", f"v{n - 1:03d}", v, "--workspace", str(ws)]) == 0
            assert main(["codex", "sync", "--workspace", str(ws)]) == 0
            _items(codex.Codex(ws), ws, v, rng, 3)
    shutil.rmtree(ws / "manuscript")  # rebuilt by the tests
    shutil.rmtree(ws / "state", ignore_errors=True)  # paths of this machine
    with zipfile.ZipFile(uf.HERE / f"{slug}.zip", "w") as zf:
        for f in sorted(ws.rglob("*")):
            if f.is_file():
                zi = zipfile.ZipInfo(f.relative_to(ws).as_posix(), (2026, 10, 13, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, f.read_bytes(), compresslevel=9)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    manifest = {}
    for name in uf.RECIPES:
        build(name, out)
        fmt = str(uf.RECIPES[name]["format"])
        manifest[name] = [uf.content_hash(b, fmt) for b in uf._bytes(name)]
    (uf.HERE / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
