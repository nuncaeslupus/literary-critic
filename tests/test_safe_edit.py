import json
from pathlib import Path

import pytest
from docgen import docx

from litcritic import docx_edit, safe_edit


def _setup(tmp_path: Path) -> tuple[Path, Path, bytes]:
    folder = tmp_path / "MyNovel"
    folder.mkdir()
    doc = folder / "MyNovel_v3.docx"
    data = docx([("Capítulo 1", True), ("Ya voy —dijo Pablo con voz cansada.", False)], seed=2)
    doc.write_bytes(data)
    return folder / "literary-critic", doc, data


def _edit(data: bytes) -> tuple[bytes, object]:
    return docx_edit.apply(data, [docx_edit.Edit("A1", "dijo Pablo", "susurró Pablo")])


def test_failure_at_each_step_restores_original(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path)
    restored = 0
    for step in safe_edit.STEPS:
        with pytest.raises(safe_edit.SafeEditError, match="put back"):
            safe_edit.write(ws, doc, _edit, _fail_at=step)
        restored += doc.read_bytes() == data and not list(doc.parent.glob(".~lc-*"))
    # A transform whose result is not a valid package is caught at verification.
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc, lambda d: (b"not a zip", None))
    assert exc.value.reason == "verify"
    restored += doc.read_bytes() == data

    # So is one that changes more than intended.
    def expect(old: bytes, new: bytes) -> None:
        raise safe_edit.SafeEditError("verify", "unexpected change")

    with pytest.raises(safe_edit.SafeEditError, match="unexpected"):
        safe_edit.write(ws, doc, _edit, expect=expect)
    restored += doc.read_bytes() == data
    assert restored / (len(safe_edit.STEPS) + 2) == 1.0
    assert len(safe_edit.backups(ws, doc)) == len(safe_edit.STEPS) + 2


def test_locked_or_changed_document_is_refused(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path)
    for lock in ("~$" + doc.name[2:], "~$" + doc.name, f".~lock.{doc.name}#"):
        (doc.parent / lock).write_text("x")
        assert safe_edit.status(ws, doc).locked
        with pytest.raises(safe_edit.SafeEditError) as exc:
            safe_edit.write(ws, doc, _edit)
        assert exc.value.reason == "locked"
        (doc.parent / lock).unlink()
    assert doc.read_bytes() == data and not safe_edit.backups(ws, doc)
    safe_edit.record_read(ws, doc)
    doc.write_bytes(data + b"")  # same bytes: not a change
    assert not safe_edit.status(ws, doc).changed_on_disk
    changed = docx([("Otro texto.", False)], seed=5)
    doc.write_bytes(changed)  # the writer saved in Word meanwhile
    assert safe_edit.status(ws, doc).changed_on_disk
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc, _edit)
    assert exc.value.reason == "changed"
    assert doc.read_bytes() == changed


def test_successful_write_records_logs_and_keeps_twenty_backups(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path)
    backup, _ = safe_edit.write(ws, doc, _edit, log={"edit_ids": ["A1"]})
    assert backup.read_bytes() == data
    assert docx_edit.texts(doc.read_bytes())[-1] == "Ya voy —susurró Pablo con voz cansada."
    st = safe_edit.status(ws, doc)
    assert not st.changed_on_disk and st.last_read_sha256 == safe_edit.sha256(doc.read_bytes())
    entry = json.loads((ws / "log" / "edits.jsonl").read_text().splitlines()[-1])
    assert entry["edit_ids"] == ["A1"] and entry["backup"] == str(backup)
    for _ in range(25):
        safe_edit.write(ws, doc, lambda d: (d, None))
    assert len(safe_edit.backups(ws, doc)) == safe_edit.KEEP_BACKUPS
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc.with_name("missing.docx"), _edit)
    assert exc.value.reason == "missing"
