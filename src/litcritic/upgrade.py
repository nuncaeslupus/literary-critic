"""Bring a workspace made by an older release onto doc-control's formats.

``lc upgrade`` runs once per workspace, in this order:

1. **Backup**: the whole workspace is copied to ``upgrade-backup/<stamp>/`` and
   the copy checked file by file; ``lc upgrade --restore`` puts it back. A
   failure at any later step restores it by itself.
2. **Re-read every draft** from its snapshot in ``manuscript/`` (never the
   writer's own file): ``text/vNNN.txt`` and a schema-2 meta with doc-control
   addresses. A ``.txt`` or ``.md`` draft read through a converted ``.docx`` copy
   (before doc-control read them itself; its meta has no ``source``) is read
   again too: its addresses may differ now (empty lines, raw text), so overrides
   naming a paragraph whose fingerprint changed are re-keyed to the new one.
3. **Migrate structure overrides** (spec D-7): each 12-hex fingerprint of the
   first shape is matched by paragraph text in the latest draft and rewritten
   in doc-control's shape; one that matches no paragraph, or several, is kept
   under ``unconfirmed`` and listed for the writer, never dropped silently.
4. **Rebuild** each draft's ``structure.json`` (and ``alignment.json`` where
   there was one).
5. **Re-anchor the Codex**: every span is moved from the old text and labels
   to the new ones with ``spans.relocate`` (exact only). A span that resolved
   before and does not now is flagged for re-reading and counted
   (``codex_spans_lost_on_upgrade``).
6. **Drop the old safe-edit state** (``backups/``, ``.safe-edit/``): doc-control
   keeps its own backups and undo log; the old files stay in the backup.
7. Write ``analysis/upgrade-report.md`` for the writer.

A workspace already in the new formats is left untouched (a second run is a
no-op).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import diff, ingest, structure
from litcritic import spans as spanlib
from litcritic.codex import Codex, Item, _write_atomic

BACKUP_DIR = "upgrade-backup"
BACKUP_MANIFEST = "backup.json"
REPORT = Path("analysis") / "upgrade-report.md"
OLD_STATE = ("backups", ".safe-edit")  # the safe-edit protocol's backups and state
RESOLVED = ("ok", "moved")
VERSION = re.compile(r"v\d{3,}")


class UpgradeError(Exception):
    """The workspace cannot be upgraded (it was restored from the backup)."""


@dataclass
class Unconfirmed:
    """An override of the first shape that matched no paragraph, or several."""

    key: str
    fp: str
    reason: str  # "missing" | "several"
    text: str = ""  # the paragraph it named in the old text, when known
    where: str = ""  # its old anchor

    def as_json(self) -> dict[str, str]:
        return {"key": self.key, "fp": self.fp, "reason": self.reason, "text": self.text}


@dataclass
class Flagged:
    """A Codex span that resolved before the upgrade and does not now."""

    item: str
    type: str
    state: str
    quote: str
    where: str  # anchor in the new text ("" when lost)


@dataclass
class Report:
    already: bool = False
    backup: Path | None = None
    versions: list[tuple[str, int, int]] = field(default_factory=list)  # (v, old, new) paragraphs
    readdressed: dict[str, int] = field(default_factory=dict)  # v -> paragraphs with a new `at`
    rekeyed: int = 0  # overrides moved to a paragraph's new fingerprint
    relabelled: dict[str, int] = field(default_factory=dict)  # v -> paragraphs with a new label
    spans: int = 0
    resolved_before: int = 0
    kept: int = 0
    flagged: list[Flagged] = field(default_factory=list)
    migrated: int = 0
    unconfirmed: list[Unconfirmed] = field(default_factory=list)
    override_errors: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    rebuilt: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def lost(self) -> int:
        """``codex_spans_lost_on_upgrade``: spans that resolved before and do not now."""
        return self.resolved_before - self.kept

    def lines(self) -> list[str]:
        if self.already:
            return ["already up to date: nothing to upgrade"]
        out = [
            f"backup: {self.backup}",
            *(
                f"{v}: re-read ({a} -> {b} paragraphs)"
                + (
                    f"; {self.readdressed[v]} paragraph addresses changed"
                    if self.readdressed.get(v)
                    else ""
                )
                for v, a, b in self.versions
            ),
            f"codex: {self.kept} of {self.resolved_before} resolved spans kept"
            f" ({self.spans} spans in all); lost on upgrade: {self.lost}",
            f"overrides: {self.migrated} migrated, {len(self.unconfirmed)} to re-confirm",
        ]
        if self.rekeyed:
            out.append(f"overrides: {self.rekeyed} moved to their paragraph's new address")
        out += [f"override rejected: {e}" for e in self.override_errors]
        out += [f"removed old state: {r}/" for r in self.removed]
        out += self.notes
        out.append(f"report: {REPORT.as_posix()} ({self.seconds:.1f} s)")
        return out


# --- what needs upgrading ------------------------------------------------------


def _read_json(f: Path) -> Any:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _versions(root: Path) -> list[str]:
    found = [f.stem for f in (root / "text").glob("v*.txt") if VERSION.fullmatch(f.stem)]
    return sorted(found, key=lambda v: int(v[1:]))


def needed(root: Path) -> list[str]:
    """What is still in an old format (empty when the workspace is up to date)."""
    out: list[str] = []
    for v in _versions(root):
        meta = _read_json(root / "text" / f"{v}.meta.json")
        rows = (meta or {}).get("paragraphs") or []
        if (
            not meta
            or meta.get("schema_version") != ingest.META_SCHEMA
            or not all(isinstance(r, dict) and r.get("at") for r in rows)
            or ingest.converted_text(meta)
        ):
            out.append(f"text/{v}.meta.json")
        s = root / "index" / v / "structure.json"
        if s.is_file() and (_read_json(s) or {}).get("schema_version") != 2:
            out.append(f"index/{v}/structure.json")
    ov = _read_json(root / "analysis" / "structure-overrides.json")
    if isinstance(ov, dict) and "overrides" not in ov:
        out.append("analysis/structure-overrides.json")
    out += [f"{d}/" for d in OLD_STATE if (root / d).exists()]
    return out


def _ats(root: Path, v: str) -> list[str]:
    rows = (_read_json(root / "text" / f"{v}.meta.json") or {}).get("paragraphs") or []
    return [str(r.get("at", "")) if isinstance(r, dict) else "" for r in rows]


# --- backup and restore ----------------------------------------------------------


def _sha(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest()


def _files(root: Path) -> list[Path]:
    """Every file of the workspace, the upgrade backups left out."""
    return sorted(
        f
        for f in root.rglob("*")
        if f.is_file() and f.relative_to(root).parts[0] != BACKUP_DIR and not f.is_symlink()
    )


def backup(root: Path) -> Path:
    """Copy the whole workspace to ``upgrade-backup/<stamp>/`` and check the copy."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = root / BACKUP_DIR / stamp
    n = 1
    while dest.exists():
        n += 1
        dest = root / BACKUP_DIR / f"{stamp}-{n}"
    dest.mkdir(parents=True)
    listing: dict[str, str] = {}
    for f in _files(root):
        rel = f.relative_to(root)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        digest = _sha(f)
        if _sha(target) != digest:
            raise UpgradeError(f"the backup copy of {rel.as_posix()} differs; nothing was changed")
        listing[rel.as_posix()] = digest
    (dest / BACKUP_MANIFEST).write_text(
        json.dumps({"made": stamp, "files": listing}, indent=1) + "\n", encoding="utf-8"
    )
    return dest


def backups(root: Path) -> list[Path]:
    """Upgrade backups, oldest first."""
    d = root / BACKUP_DIR
    found = [b for b in d.iterdir() if (b / BACKUP_MANIFEST).is_file()] if d.is_dir() else []
    return sorted(found, key=lambda b: b.name)


def restore(root: Path, source: Path | None = None) -> Path:
    """Put the workspace back as the backup ``source`` (default: the latest) holds it."""
    found = backups(root)
    source = source or (found[-1] if found else None)
    if source is None:
        raise UpgradeError(f"no upgrade backup in {root / BACKUP_DIR}")
    listing: dict[str, str] = json.loads((source / BACKUP_MANIFEST).read_text("utf-8"))["files"]
    for rel, digest in listing.items():  # check the whole backup before touching anything
        f = source / rel
        if not f.is_file() or _sha(f) != digest:
            raise UpgradeError(f"backup {source.name} is damaged at {rel}; nothing was restored")
    for entry in root.iterdir():
        if entry.name == BACKUP_DIR:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    for rel in listing:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, target)
    return source


# --- the old state, read before anything is rewritten -------------------------


@dataclass
class _Old:
    paragraphs: list[str]
    anchors: list[str]  # [] when the draft had no (usable) structure


def _lines(f: Path) -> list[str]:
    text = f.read_text(encoding="utf-8")
    return text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")


def _old_state(root: Path) -> tuple[dict[str, _Old], dict[str, str]]:
    old: dict[str, _Old] = {}
    names: dict[str, str] = {}
    for v in _versions(root):
        paras = _lines(root / "text" / f"{v}.txt")
        data = _read_json(root / "index" / v / "structure.json") or {}
        anchors = [str(a) for a, _ in data.get("paragraphs") or []]
        old[v] = _Old(paras, anchors if len(anchors) == len(paras) else [])
        meta = _read_json(root / "text" / f"{v}.meta.json") or {}
        names[v] = str(meta.get("source_name") or "")
    return old, names


# --- overrides (D-7) ---------------------------------------------------------------


def _migrate_overrides(root: Path, old: _Old | None, report: Report) -> None:
    f = root / "analysis" / "structure-overrides.json"
    data = _read_json(f)
    if not isinstance(data, dict) or "overrides" in data:
        return
    v = _versions(root)[-1]
    paras = _lines(root / "text" / f"{v}.txt")
    meta = _read_json(root / "text" / f"{v}.meta.json") or {}
    ats = [str(r["at"]) for r in meta["paragraphs"]]
    where: dict[str, list[int]] = {}
    for i, t in enumerate(paras):
        where.setdefault(structure.fingerprint(t), []).append(i)
    was: dict[str, tuple[str, str]] = {}  # old fingerprint -> (old text, old anchor)
    if old is not None:
        for i, t in enumerate(old.paragraphs):
            was.setdefault(structure.fingerprint(t), (t, old.anchors[i] if old.anchors else ""))
    migrated: list[dict[str, Any]] = []
    for key, value in data.items():
        if key not in structure.LEGACY_KEYS or not isinstance(value, list):
            report.notes.append(f"overrides: unknown entry {key!r} kept as it was")
            continue
        kind, action = structure.LEGACY_KEYS[key]
        for fp in map(str, value):
            hits = where.get(fp, [])
            if len(hits) == 1:
                o = structure._forced(ats, hits)[0]
                o.update(kind=kind, action=action)
                migrated.append(o)
                continue
            text, anchor = was.get(fp, ("", ""))
            reason = "several" if hits else "missing"
            report.unconfirmed.append(Unconfirmed(key, fp, reason, text, anchor))
    out: dict[str, Any] = {"schema_version": structure.OVERRIDES_SCHEMA, "overrides": migrated}
    if report.unconfirmed:
        out["unconfirmed"] = [u.as_json() for u in report.unconfirmed]
    leftovers = {k: v for k, v in data.items() if k not in structure.LEGACY_KEYS}
    if leftovers:
        out["unknown"] = leftovers
    _write_atomic(f, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    report.migrated = len(migrated)


def _rekey_overrides(root: Path, before: list[str], after: list[str], report: Report) -> None:
    """Overrides in doc-control's shape follow their paragraph to its new fingerprint.

    ``before`` and ``after`` are the latest draft's addresses before and after it was
    read again, paragraph for paragraph (same text); an override names a paragraph by
    fingerprint (and ``nth``), which changes when doc-control now sees other text.
    """
    f = root / "analysis" / "structure-overrides.json"
    data = _read_json(f)
    if not isinstance(data, dict) or not isinstance(data.get("overrides"), list):
        return
    old_fps = [a.partition("#")[2] for a in before]
    if len(before) != len(after) or old_fps == [a.partition("#")[2] for a in after]:
        return
    moved = 0
    for o in data["overrides"]:
        if not isinstance(o, dict) or not o.get("fp"):
            continue
        hits = [i for i, fp in enumerate(old_fps) if fp == o["fp"]]
        k = int(o.get("nth") or 1) - 1
        if not 0 <= k < len(hits):
            continue  # it named no paragraph before either: lc anchor reports it
        new = structure._forced(after, [hits[k]])[0]
        if (new["fp"], new.get("nth")) == (o["fp"], o.get("nth")):
            continue
        o["fp"] = new["fp"]
        o.pop("nth", None)
        if "nth" in new:
            o["nth"] = new["nth"]
        moved += 1
    if moved:
        _write_atomic(f, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    report.rekeyed = moved


# --- Codex ---------------------------------------------------------------------------


def _identity(n: int) -> diff.Alignment:
    """The alignment of a text with itself (no doc-control call needed)."""
    ats = [f"p{i + 1}#same" for i in range(n)]
    return diff.Alignment(
        [{"status": "unchanged", "new": [i]} for i in range(n)],
        [{"status": "unchanged", "old": [i]} for i in range(n)],
        {"unchanged": n},
        [],
        ats,
        list(ats),
        dict(zip(ats, ats, strict=True)),
    )


def _new_text(root: Path, v: str) -> spanlib.Text:
    data = json.loads((root / "index" / v / "structure.json").read_text(encoding="utf-8"))
    return spanlib.Text(_lines(root / "text" / f"{v}.txt"), [a for a, _ in data["paragraphs"]], v)


def _reanchor(root: Path, old: dict[str, _Old], report: Report) -> None:
    if not (root / "codex" / "codex.toml").is_file():
        return
    cx = Codex(root)
    if cx.damaged:
        report.notes.append(
            "codex: some rows could not be read; their spans were not moved (lc codex check)"
        )
    drafts = sorted({s.draft for it in cx.items.values() for s in it.spans if s.draft in old})
    moved: dict[str, list[spanlib.Span]] = {}
    for v in drafts:
        new = _new_text(root, v)
        o = old[v]
        if o.anchors:
            prev = spanlib.Text(o.paragraphs, o.anchors, v)
            same = o.paragraphs == new.paragraphs
            al = (
                _identity(len(new.paragraphs)) if same else diff.align(o.paragraphs, new.paragraphs)
            )
        else:  # no old labels: spans can only be searched for
            prev, al = spanlib.Text([], [], v), _identity(0)
        kept = al.mapping()
        with spanlib.Resolver(new) as rs:
            for item in cx.items.values():
                if item.type in cx.damaged:
                    continue
                for k, s in enumerate(item.spans):
                    if s.draft != v:
                        continue
                    out = spanlib.relocate(s, prev, new, al, v, kept, rs)
                    if s.state in RESOLVED and out.state in RESOLVED:
                        out.state = s.state  # a new label is not a move in the text
                    moved.setdefault(item.id, list(item.spans))[k] = out
    updates: list[Item] = []
    flagged_ids: dict[str, str] = {}
    for item in cx.items.values():
        for s in item.spans:
            report.spans += 1
            report.resolved_before += s.state in RESOLVED and s.draft in old
        if item.id not in moved:
            continue
        after = moved[item.id]
        status = item.status
        for before, now in zip(item.spans, after, strict=True):
            if before.state in RESOLVED and before.draft in old:
                if now.state in RESOLVED:
                    report.kept += 1
                    continue
                quote = before.exact or f"{before.head} … {before.tail}"
                where = now.start.para if now.state == "changed" else ""
                report.flagged.append(Flagged(item.id, item.type, now.state, quote, where))
                flagged_ids[item.id] = now.state
                if status != "retired":
                    status = "needs_reread"
        copy = Item.from_json({**item.as_json(), "status": status})
        copy.spans = after
        updates.append(copy)
    cx.replace_all(updates, op="upgrade", by="script", updated=cx.draft, draft=cx.draft)
    if flagged_ids:
        _requeue(cx, flagged_ids)


def _requeue(cx: Codex, flagged: dict[str, str]) -> None:
    """Add the items the upgrade flagged to ``codex/reread.jsonl``, keeping earlier reasons."""
    f = cx.root / "reread.jsonl"
    reasons: dict[str, str] = {}
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("item"):
                reasons[str(row["item"])] = str(row.get("reason", "earlier"))
    reasons.update({i: state for i, state in flagged.items() if i not in reasons})
    queue = [
        {"item": it.id, "reason": reasons.get(it.id, "earlier")}
        for it in sorted(cx.items.values(), key=lambda x: x.id)
        if it.status == "needs_reread"
    ]
    _write_atomic(f, "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queue))


# --- the run ----------------------------------------------------------------------------


def _language(root: Path) -> str:
    try:
        lang = tomllib.loads((root / "work.toml").read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError):
        lang = None
    return str(lang or "en")


def _steps(root: Path, report: Report) -> None:
    old, names = _old_state(root)
    versions = list(old)
    before = {v: _ats(root, v) for v in versions}
    for v in versions:
        result = ingest.reingest(root, v, names.get(v, ""))
        report.versions.append((v, len(old[v].paragraphs), result.paragraphs))
        after = _ats(root, v)
        if all(before[v]) and len(before[v]) == len(after):
            report.readdressed[v] = sum(a != b for a, b in zip(before[v], after, strict=True))
    if versions and old[versions[-1]].paragraphs == _lines(root / "text" / f"{versions[-1]}.txt"):
        _rekey_overrides(root, before[versions[-1]], _ats(root, versions[-1]), report)
    _migrate_overrides(root, old.get(versions[-1]) if versions else None, report)
    for v in versions:
        _, _, errors = structure.build(root, v)
        report.override_errors += [e for e in errors if e not in report.override_errors]
        prev, now = old[v], _new_text(root, v)
        if prev.anchors and prev.paragraphs == now.paragraphs:
            pairs = zip(prev.anchors, now.anchors, strict=True)
            report.relabelled[v] = sum(a != b for a, b in pairs)
    for v in versions:
        al = _read_json(root / "index" / v / "alignment.json")
        src = str((al or {}).get("from", ""))
        if src in old:
            diff.build(root, src, v)
            report.rebuilt.append(f"index/{v}/alignment.json")
    _reanchor(root, old, report)
    for d in OLD_STATE:
        if (root / d).exists():
            shutil.rmtree(root / d) if (root / d).is_dir() else (root / d).unlink()
            report.removed.append(d)
    if (root / "metrics").is_dir() and any((root / "metrics").glob("v*.json")):
        report.notes.append("metrics: measured on the old text; run `lc metrics` again")
    if (root / "index" / "work" / "plan.json").is_file():
        report.notes.append("index plan: made on the old labels; run `lc index plan` again")


def upgrade(root: Path) -> Report:
    """Upgrade the workspace at ``root``; a no-op report when it is up to date."""
    t0 = time.perf_counter()
    report = Report()
    if not needed(root):
        report.already = True
        return report
    if not _versions(root):
        raise UpgradeError("no ingested draft to upgrade")
    report.backup = backup(root)
    try:
        _steps(root, report)
    except Exception as exc:
        restore(root, report.backup)
        raise UpgradeError(
            f"upgrade stopped ({type(exc).__name__}: {exc}); the workspace was restored "
            f"from {report.backup}"
        ) from exc
    report.seconds = time.perf_counter() - t0
    (root / REPORT).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT).write_text(render(report, _language(root), root), encoding="utf-8")
    return report


# --- the writer's report ---------------------------------------------------------------

TEXT = {
    "en": {
        "title": "Workspace upgrade",
        "intro": (
            "The tool now reads your manuscript with doc-control. Every draft kept in this "
            "workspace was read again from its saved copy, and everything built on it was "
            "brought along. Your own manuscript file was not opened or changed."
        ),
        "backup": "Backup",
        "backup_text": (
            "A full copy of the workspace as it was is in `{path}`. To go back to it, ask "
            "for `lc upgrade --restore`."
        ),
        "drafts": "Drafts read again",
        "draft": "- Draft {v}: {b} paragraphs (before: {a})",
        "relabel": "; {n} paragraphs now sit in a different chapter or scene number",
        "notes": "Your notes on the novel",
        "kept": "{kept} of {total} marked passages are still in place.",
        "none_lost": "None was lost.",
        "flagged": (
            "These passages could not be found exactly as before. The notes on them are "
            "marked to be read again:"
        ),
        "flag_line": "- {where}: «{quote}»",
        "nowhere": "no longer in the text",
        "structure": "Chapter and scene corrections",
        "migrated": "{n} of your corrections were carried over.",
        "unconfirmed": (
            "These corrections name a paragraph that is no longer exactly the same, so they "
            "were not applied. Please say again whether each one is still wanted:"
        ),
        "missing": "the paragraph changed or is gone",
        "several": "several paragraphs now read the same",
        "corr": {
            "chapter_starts": "start a chapter at",
            "not_chapter": "no chapter at",
            "scene_starts": "start a scene at",
            "not_scene": "no scene at",
        },
        "unknown_par": "a paragraph the tool can no longer show",
        "cleanup": "Old files removed",
        "cleanup_text": (
            "The backups the previous version kept of your manuscript before each edit "
            "(`{dirs}`) were removed; doc-control keeps its own from now on. The old ones "
            "are still inside the backup above."
        ),
        "todo": "Still to do",
        "chapter": "chapter {n}",
        "front": "the opening pages",
        "para": "the paragraph that begins «{head}» and ends «{tail}»",
    },
    "es": {
        "title": "Actualización del espacio de trabajo",
        "intro": (
            "La herramienta lee ahora tu manuscrito con doc-control. Cada versión guardada "
            "en este espacio de trabajo se ha vuelto a leer desde su copia, y todo lo "
            "construido sobre ella se ha trasladado. Tu propio archivo no se ha abierto ni "
            "modificado."
        ),
        "backup": "Copia de seguridad",
        "backup_text": (
            "Hay una copia completa del espacio de trabajo tal como estaba en `{path}`. "
            "Para volver a ella, pide `lc upgrade --restore`."
        ),
        "drafts": "Versiones leídas de nuevo",
        "draft": "- Versión {v}: {b} párrafos (antes: {a})",
        "relabel": "; {n} párrafos quedan ahora en otro número de capítulo o escena",
        "notes": "Tus notas sobre la novela",
        "kept": "{kept} de {total} pasajes marcados siguen en su sitio.",
        "none_lost": "No se ha perdido ninguno.",
        "flagged": (
            "Estos pasajes no se han encontrado exactamente igual que antes. Las notas "
            "sobre ellos quedan marcadas para releerlas:"
        ),
        "flag_line": "- {where}: «{quote}»",
        "nowhere": "ya no está en el texto",
        "structure": "Correcciones de capítulos y escenas",
        "migrated": "Se han trasladado {n} de tus correcciones.",
        "unconfirmed": (
            "Estas correcciones señalan un párrafo que ya no es exactamente igual, así que "
            "no se han aplicado. Confirma de nuevo si cada una sigue haciendo falta:"
        ),
        "missing": "el párrafo cambió o ya no está",
        "several": "ahora hay varios párrafos iguales",
        "corr": {
            "chapter_starts": "empezar un capítulo en",
            "not_chapter": "no empezar capítulo en",
            "scene_starts": "empezar una escena en",
            "not_scene": "no empezar escena en",
        },
        "unknown_par": "un párrafo que la herramienta ya no puede mostrar",
        "cleanup": "Archivos antiguos eliminados",
        "cleanup_text": (
            "Se han eliminado las copias que la versión anterior guardaba de tu manuscrito "
            "antes de cada cambio (`{dirs}`); a partir de ahora doc-control guarda las suyas. "
            "Las antiguas siguen dentro de la copia de seguridad."
        ),
        "todo": "Pendiente",
        "chapter": "capítulo {n}",
        "front": "las páginas iniciales",
        "para": "el párrafo que empieza «{head}» y termina «{tail}»",
    },
}


def _ends(text: str, n: int = 5) -> tuple[str, str]:
    words = text.split()
    return " ".join(words[:n]), " ".join(words[-n:])


def _chapter(anchor: str, t: dict[str, Any]) -> str:
    m = re.search(r"c(\d+)", anchor)
    if not m:
        return ""
    n = int(m.group(1))
    return str(t["front"]) if n == 0 else str(t["chapter"]).format(n=n)


def _short(quote: str, n: int = 12) -> str:
    words = " ".join(quote.split()).split(" ")
    return (
        " ".join(words)
        if len(words) <= 2 * n
        else f"{' '.join(words[:n])} … {' '.join(words[-n:])}"
    )


def render(report: Report, lang: str, root: Path) -> str:
    t: dict[str, Any] = TEXT.get(lang, TEXT["en"])
    backup_path = report.backup.relative_to(root).as_posix() if report.backup else ""
    lines = [f"# {t['title']}", "", t["intro"], "", f"## {t['backup']}", ""]
    lines += [t["backup_text"].format(path=backup_path), "", f"## {t['drafts']}", ""]
    for v, a, b in report.versions:
        extra = t["relabel"].format(n=report.relabelled[v]) if report.relabelled.get(v) else ""
        lines.append(t["draft"].format(v=v, a=a, b=b) + extra)
    lines += ["", f"## {t['notes']}", ""]
    lines.append(t["kept"].format(kept=report.kept, total=report.resolved_before))
    if report.flagged:
        lines += ["", t["flagged"], ""]
        for f in report.flagged:
            where = _chapter(f.where, t) if f.where else t["nowhere"]
            lines.append(t["flag_line"].format(where=where, quote=_short(f.quote)))
    else:
        lines.append(t["none_lost"])
    if report.migrated or report.unconfirmed:
        lines += ["", f"## {t['structure']}", "", t["migrated"].format(n=report.migrated)]
        if report.unconfirmed:
            lines += ["", t["unconfirmed"], ""]
            for u in report.unconfirmed:
                if u.text:
                    head, tail = _ends(u.text)
                    par = t["para"].format(head=head, tail=tail)
                    chapter = _chapter(u.where, t)
                    par = f"{par} ({chapter})" if chapter else par
                else:
                    par = t["unknown_par"]
                lines.append(f"- {t['corr'][u.key]} {par}: {t[u.reason]}")
    if report.removed:
        dirs = ", ".join(f"{d}/" for d in report.removed)
        lines += ["", f"## {t['cleanup']}", "", t["cleanup_text"].format(dirs=dirs)]
    if report.notes or report.override_errors:
        lines += ["", f"## {t['todo']}", ""]
        lines += [f"- {n}" for n in [*report.override_errors, *report.notes]]
    return "\n".join(lines) + "\n"


# --- command line --------------------------------------------------------------------------


def _cmd(args: Any) -> int:
    import sys

    from litcritic import workspace

    try:
        ws = workspace.resolve(args.workspace, args.home)
        if args.restore:
            src = restore(ws.root)
            print(f"restored the workspace from {src}")
            return 0
        report = upgrade(ws.root)
    except (workspace.WorkspaceError, UpgradeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in report.lines():
        print(line)
    return 1 if report.lost or report.unconfirmed else 0


def register(sub: Any) -> None:
    p = sub.add_parser(
        "upgrade", help="move a workspace made by an older release onto the new formats"
    )
    p.add_argument("--workspace", required=True, help="workspace folder or slug")
    p.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p.add_argument(
        "--restore", action="store_true", help="put back the workspace from the latest backup"
    )
    p.set_defaults(func=_cmd)
