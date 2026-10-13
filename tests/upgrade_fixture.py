"""Old-format workspaces for the upgrade tests, on the public-domain corpus.

``tests/fixtures/upgrade/<slug>.zip`` holds a workspace built by the release
before doc-control read the manuscripts (commit 6eab457): schema-1 meta, the
old structure, overrides in the first shape (12-hex fingerprints), and a Codex
on two drafts, the second synced with that release's ``lc codex sync``. The
manuscript snapshots are left out of the zip: ``unpack`` rebuilds them from the
corpus with ``synth`` and ``docgen`` (seeded), checks them against
``manifest.json`` and adds a backup the old safe-edit protocol kept.

To rebuild the zips, run ``tests/fixtures/upgrade/build.py`` with the old
release (its docstring has the commands).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from docgen import docx

from litcritic import corpus, synth

HERE = Path(__file__).parent / "fixtures" / "upgrade"
GOLD = Path(__file__).parent / "fixtures" / "gold" / "chapters.json"
RECIPES: dict[str, dict[str, object]] = {
    "jekyll-hyde": {"language": "en", "format": "txt", "seed": 11},
    "marianela": {"language": "es", "format": "docx", "seed": 12},
}
SAFE_EDIT_BACKUP = "draft.1a2b3c4d.20261001T120000Z"  # how safe-edit named its backups


def work_toml(slug: str) -> str:
    lang = RECIPES[slug]["language"]
    return (
        f'id = "{slug}-0f0f0f"\nslug = "{slug}"\ntitle = "{slug}"\nauthor = ""\n'
        f'kind = "novel"\nseries = ""\ntags = []\nlanguage = "{lang}"\n'
        'mode = "revision"\nschema_version = 2\n'
    )


def _flat(paragraphs: list[str]) -> list[str]:
    return [" ".join(p.split()) for p in paragraphs]


def _drafts(slug: str) -> list[list[str]]:
    """Each draft's paragraphs: the corpus text, then a seeded synthetic revision."""
    text = corpus.get(slug).read()
    second = synth.generate(text, int(str(RECIPES[slug]["seed"])), rate=0.03)
    return [_flat(synth.paragraphs(text)), _flat(second.paragraphs)]


def _bytes(slug: str) -> list[bytes]:
    if RECIPES[slug]["format"] == "txt":
        text = corpus.get(slug).read()
        second = synth.generate(text, int(str(RECIPES[slug]["seed"])), rate=0.03)
        return [text.encode("utf-8"), second.text.encode("utf-8")]
    gold = set(json.loads(GOLD.read_text(encoding="utf-8"))[slug])
    return [docx([(p, p in gold) for p in d], seed=n) for n, d in enumerate(_drafts(slug))]


def content_hash(data: bytes, fmt: str) -> str:
    """The manuscript's text content (a .docx's document part: zip dates vary)."""
    if fmt == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            data = zf.read("word/document.xml")
    return hashlib.sha256(data).hexdigest()


def manuscripts(slug: str, folder: Path) -> list[Path]:
    """Write the drafts as ``folder/draft-N.<ext>``; returns their paths, oldest first."""
    folder.mkdir(parents=True, exist_ok=True)
    fmt = str(RECIPES[slug]["format"])
    out = []
    for n, data in enumerate(_bytes(slug), 1):
        path = folder / f"draft-{n}.{fmt}"
        path.write_bytes(data)
        out.append(path)
    return out


def override_targets(slug: str) -> dict[str, str]:
    """Two unique body paragraphs of the first draft: a forced scene start, a denied chapter."""
    paras = _drafts(slug)[0]
    seen: dict[str, int] = {}
    for p in paras:
        seen[p] = seen.get(p, 0) + 1
    unique = [i for i, p in enumerate(paras) if seen[p] == 1 and len(p.split()) > 20]
    a = next(i for i in unique if i > len(paras) * 2 // 5)
    b = next(i for i in unique if i > len(paras) * 3 // 5)
    return {"scene_start": paras[a], "not_chapter": paras[b]}


def unpack(slug: str, dest: Path) -> Path:
    """The old workspace in ``dest/slug``, manuscripts and a safe-edit backup included."""
    root = dest / slug
    with zipfile.ZipFile(HERE / f"{slug}.zip") as zf:
        zf.extractall(root)
    fmt = str(RECIPES[slug]["format"])
    expected = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))[slug]
    (root / "manuscript").mkdir(exist_ok=True)
    for n, data in enumerate(_bytes(slug), 1):
        if content_hash(data, fmt) != expected[n - 1]:
            raise AssertionError(f"{slug} draft {n} no longer matches the fixture; rebuild it")
        (root / "manuscript" / f"v{n:03d}.{fmt}").write_bytes(data)
    (root / "backups").mkdir(exist_ok=True)
    (root / "backups" / f"{SAFE_EDIT_BACKUP}.{fmt}").write_bytes(_bytes(slug)[0])
    return root
