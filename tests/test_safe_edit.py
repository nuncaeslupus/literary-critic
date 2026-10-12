import io
import json
import zipfile
from pathlib import Path

import pytest
from docgen import docx

from litcritic import docx_edit, safe_edit

ANY = safe_edit.only_paragraphs_changed(set(range(1000)))


def _setup(tmp_path: Path, read: bool = True) -> tuple[Path, Path, bytes]:
    folder = tmp_path / "MyNovel"
    folder.mkdir(exist_ok=True)
    doc = folder / "MyNovel_v3.docx"
    data = docx([("Capítulo 1", True), ("Ya voy —dijo Pablo con voz cansada.", False)], seed=2)
    doc.write_bytes(data)
    ws = folder / "literary-critic"
    if read:
        safe_edit.record_read(ws, doc)
    return ws, doc, data


def _edit(data: bytes) -> tuple[bytes, object]:
    return docx_edit.apply(data, [docx_edit.Edit("A1", "dijo Pablo", "susurró Pablo")])


ONLY_LAST = safe_edit.only_paragraphs_changed({2})


def test_failure_at_each_step_restores_original(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path)
    restored = 0
    for step in safe_edit.STEPS:
        with pytest.raises(safe_edit.SafeEditError, match="put back"):
            safe_edit.write(ws, doc, _edit, ONLY_LAST, _fail_at=step)
        restored += doc.read_bytes() == data and not list(doc.parent.glob(".~lc-*"))
    # A transform whose result is not a valid package is caught at verification.
    no_document = io.BytesIO()
    with zipfile.ZipFile(no_document, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
    for bad in (b"not a zip", no_document.getvalue()):

        def broken(d: bytes, bad: bytes = bad) -> tuple[bytes, object]:
            return bad, None

        with pytest.raises(safe_edit.SafeEditError) as exc:
            safe_edit.write(ws, doc, broken, ANY)
        assert exc.value.reason == "verify"
        restored += doc.read_bytes() == data
    # So is one that changes more than intended.
    with pytest.raises(safe_edit.SafeEditError, match="unexpected change"):
        safe_edit.write(ws, doc, _edit, safe_edit.only_paragraphs_changed({0}))
    restored += doc.read_bytes() == data
    assert restored / (len(safe_edit.STEPS) + 3) == 1.0
    assert len(safe_edit.backups(ws, doc)) == len(safe_edit.STEPS) + 3


def test_locked_or_changed_document_is_refused(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path, read=False)
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc, _edit, ONLY_LAST)
    assert exc.value.reason == "unread"
    safe_edit.record_read(ws, doc)
    for lock in ("~$" + doc.name[2:], "~$" + doc.name, f".~lock.{doc.name}#"):
        (doc.parent / lock).write_text("x")
        assert safe_edit.status(ws, doc).locked
        with pytest.raises(safe_edit.SafeEditError) as exc:
            safe_edit.write(ws, doc, _edit, ONLY_LAST)
        assert exc.value.reason == "locked"
        (doc.parent / lock).unlink()
    assert doc.read_bytes() == data and not safe_edit.backups(ws, doc)
    # Another document's owner file does not lock this one.
    (doc.parent / "~$herNovel.docx").write_text("x")
    assert not safe_edit.status(ws, doc).locked
    changed = docx([("Otro texto.", False)], seed=5)
    doc.write_bytes(changed)  # the writer saved in Word meanwhile
    assert safe_edit.status(ws, doc).changed_on_disk
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc, _edit, ONLY_LAST)
    assert exc.value.reason == "changed"
    assert doc.read_bytes() == changed


def test_writer_save_during_the_edit_is_never_overwritten(tmp_path: Path) -> None:
    ws, doc, _ = _setup(tmp_path)
    theirs = docx([("Lo que el escritor guardó.", False)], seed=9)

    def edit_while_writer_saves(d: bytes) -> tuple[bytes, object]:
        out = _edit(d)
        doc.write_bytes(theirs)  # Word saves while we are working
        return out

    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc, edit_while_writer_saves, ONLY_LAST)
    assert exc.value.reason == "changed"
    assert doc.read_bytes() == theirs


def test_successful_write_records_logs_and_keeps_twenty_backups(tmp_path: Path) -> None:
    ws, doc, data = _setup(tmp_path)
    backup, _ = safe_edit.write(ws, doc, _edit, ONLY_LAST, log={"edit_ids": ["A1"]})
    assert backup.read_bytes() == data
    assert docx_edit.texts(doc.read_bytes())[-1] == "Ya voy —susurró Pablo con voz cansada."
    st = safe_edit.status(ws, doc)
    assert not st.changed_on_disk and st.last_read_sha256 == safe_edit.sha256(doc.read_bytes())
    entry = json.loads((ws / "log" / "edits.jsonl").read_text().splitlines()[-1])
    assert entry["edit_ids"] == ["A1"] and entry["backup"] == str(backup)
    # A document whose name starts the same keeps its own backups.
    other = doc.with_name("MyNovel_v3-copy.docx")
    other.write_bytes(data)
    safe_edit.record_read(ws, other)
    for _ in range(25):
        safe_edit.write(ws, other, lambda d: (d, None), ANY)
    for _ in range(25):
        safe_edit.write(ws, doc, lambda d: (d, None), ANY)
    assert len(safe_edit.backups(ws, doc)) == safe_edit.KEEP_BACKUPS
    assert len(safe_edit.backups(ws, other)) == safe_edit.KEEP_BACKUPS
    with pytest.raises(safe_edit.SafeEditError) as exc:
        safe_edit.write(ws, doc.with_name("missing.docx"), _edit, ANY)
    assert exc.value.reason == "missing"
