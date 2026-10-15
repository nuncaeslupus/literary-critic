import json
import os
import random
import tomllib
from pathlib import Path

import pytest
from docgen import docx

from litcritic import corpus, dc, ingest, settings, setup, word_live, workspace
from litcritic.cli import main


def _paras(name: str, n: int) -> list[tuple[str, bool]]:
    draft = ingest.read(corpus.get(name).path)
    return [(p.text, bool(p.heading)) for p in draft.paragraphs[:n]]


def _revise(paras: list[tuple[str, bool]], seed: int) -> list[tuple[str, bool]]:
    """Another draft: some paragraphs dropped, some words changed."""
    rng = random.Random(seed)
    out = []
    for text, heading in paras:
        if not heading and rng.random() < 0.1:
            continue
        words = text.split()
        if not heading and words and rng.random() < 0.3:
            words[rng.randrange(len(words))] = "cambiado"
        out.append((" ".join(words), heading))
    return out


def _put(folder: Path, name: str, data: bytes | str, day: int) -> Path:
    f = folder / name
    if isinstance(data, str):
        f.write_text(data, encoding="utf-8")
    else:
        f.write_bytes(data)
    ts = 1_760_000_000 + day * 86_400
    os.utime(f, (ts, ts))
    return f


def _novel_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "MyNovel"
    folder.mkdir()
    base = _paras("marianela", 220)
    _put(folder, "MyNovel_v1.docx", docx(_revise(base[:150], 1), seed=1), 1)
    _put(folder, "MyNovel_v2.docx", docx(_revise(base[:190], 2), seed=2), 5)
    v3 = docx(base, seed=3)
    _put(folder, "MyNovel_v3.docx", v3, 9)
    _put(folder, "Copy of MyNovel_v3.docx", v3, 10)
    _put(folder, "MyNovel_v3 (1).docx", v3, 11)
    _put(folder, "MyNovel backup.docx", docx(base[:200], seed=4), 12)
    md = "\n\n".join(t for t, _ in base)
    _put(folder, "MyNovel_v3.md", md, 13)  # an export: the .docx stays the manuscript
    _put(folder, "notes.docx", docx(_paras("jekyll-hyde", 60), seed=5), 14)
    _put(folder, "letter to agent.txt", "Dear agent,\n\nPlease find attached my novel.\n", 15)
    _put(folder, "~$MyNovel_v3.docx", b"lock", 15)
    return folder


EXPECTED = {
    "manuscript": "MyNovel_v3.docx",
    "versions": [
        "MyNovel_v3.md",
        "MyNovel backup.docx",
        "MyNovel_v3 (1).docx",
        "Copy of MyNovel_v3.docx",
        "MyNovel_v2.docx",
        "MyNovel_v1.docx",
    ],
    "others": ["letter to agent.txt", "notes.docx"],
}


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {str(f.relative_to(folder)): f.read_bytes() for f in folder.rglob("*") if f.is_file()}


def test_setup_picks_latest_draft_and_lists_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenarios = 0
    correct = 0
    # 1. drafts, copies, a backup, an export and unrelated documents
    folder = _novel_folder(tmp_path)
    assert main(["setup", "--folder", str(folder)]) == 0
    out = json.loads(capsys.readouterr().out)
    got = {
        "manuscript": out["manuscript"]["path"],
        "versions": [v["path"] for v in out["versions"]],
        "others": sorted(out["others"]),
    }
    scenarios += 1
    correct += got == EXPECTED
    assert got == EXPECTED
    assert out["status"] == "ready" and out["workspace"] == "literary-critic"
    assert out["language"] == "es" and out["version"] == "v001"
    assert out["environment"]["folder_writable"] and out["environment"]["word_lock"]
    assert (folder / "literary-critic" / "text" / "v001.txt").is_file()
    assert (folder / "literary-critic" / "index" / "v001" / "structure.json").is_file()
    # 2. drafts with no number: the newest one, whatever its name
    other = tmp_path / "Second"
    other.mkdir()
    base = _paras("jekyll-hyde", 120)
    _put(other, "final.docx", docx(_revise(base, 7), seed=7), 3)
    _put(other, "draft.docx", docx(base, seed=8), 4)
    found = setup.discover(other)
    scenarios += 1
    correct += found.manuscript.path.name == "draft.docx" and [
        f.path.name for f, _ in found.versions
    ] == ["final.docx"]
    # 3. only copies: the newest copy is the manuscript
    third = tmp_path / "Third"
    third.mkdir()
    _put(third, "Copy of Book.docx", docx(base, seed=9), 1)
    _put(third, "Book (1).docx", docx(base, seed=9), 2)
    found = setup.discover(third)
    scenarios += 1
    correct += found.manuscript.path.name == "Book (1).docx" and not found.others
    # 4. an excerpt sent to an agent is newer, a later draft has a new opening,
    #    and the folder holds a long unrelated book: none of them misleads
    fourth = tmp_path / "The Old Mill"
    fourth.mkdir()
    mill = _paras("marianela", 400)
    _put(fourth, "The Old Mill v2.docx", docx(_revise(mill[:380], 11), seed=11), 1)
    _put(fourth, "The Old Mill v3.docx", docx(mill[:380], seed=12), 2)
    prologue = [(f"Prólogo nuevo, línea {k} de una apertura reescrita.", False) for k in range(80)]
    _put(fourth, "The Old Mill v4.docx", docx(prologue + mill[60:380], seed=13), 3)
    _put(fourth, "first chapters for agent.docx", docx(mill[:40], seed=14), 4)
    _put(fourth, "research.docx", docx(_paras("jekyll-hyde", 2000), seed=15), 5)
    found = setup.discover(fourth)
    scenarios += 1
    correct += (
        found.manuscript.path.name == "The Old Mill v4.docx"
        and [f.path.name for f in found.others] == ["research.docx"]
        and setup._title(found.manuscript.path) == "The Old Mill"
    )
    # 5. the writer moved to Markdown: a newer draft with other text wins
    fifth = tmp_path / "Catch-22"
    fifth.mkdir()
    _put(fifth, "Catch-22.docx", docx(base, seed=16), 1)
    _put(fifth, "Catch-22.md", "\n\n".join(t for t, _ in _revise(base, 17)), 2)
    found = setup.discover(fifth)
    scenarios += 1
    correct += found.manuscript.path.name == "Catch-22.md"
    correct += setup._title(found.manuscript.path) == "Catch-22"
    scenarios += 1
    novel_discovery_accuracy = correct / scenarios
    assert novel_discovery_accuracy == 1.0


def test_setup_reuses_existing_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _novel_folder(tmp_path)
    assert main(["setup", "--folder", str(folder)]) == 0
    first = json.loads(capsys.readouterr().out)
    before = _snapshot(folder)
    assert main(["setup", "--folder", str(folder)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second == first
    assert _snapshot(folder) == before
    # The writer saves a new draft: it is ingested into the same workspace.
    _put(folder, "MyNovel_v4.docx", docx(_revise(_paras("marianela", 220), 9), seed=6), 20)
    assert main(["setup", "--folder", str(folder)]) == 0
    third = json.loads(capsys.readouterr().out)
    assert third["manuscript"]["path"] == "MyNovel_v4.docx"
    assert third["version"] == "v002" and third["workspace"] == first["workspace"]


def test_setup_without_documents_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["setup", "--folder", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_prose_suggestions_off_until_notice_acknowledged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _novel_folder(tmp_path)
    ws = folder / "literary-critic"
    profile = ws / "analysis" / "profile.toml"
    assert main(["setup", "--folder", str(folder)]) == 0
    off_by_default = json.loads(capsys.readouterr().out)["settings"]["prose_suggestions"] is False
    profile.write_text('mode = "revision"\nlanguage = "es"\n\n[weights]\npacing = 2\n')
    before = profile.read_bytes()
    # On without the acknowledgement: refused, the notice printed, nothing changed.
    assert main(["setup", "--folder", str(folder), "--prose-suggestions", "on"]) == 1
    out = json.loads(capsys.readouterr().out)
    refused = out["reason"] == "ai_notice" and "IA" in out["notice"]
    refused = refused and profile.read_bytes() == before
    assert settings.load(ws)["prose_suggestions"] is False
    # Acknowledged: on, with the time recorded and the rest of the profile kept.
    argv = ["setup", "--folder", str(folder), "--prose-suggestions", "on", "--ack-ai-notice"]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["settings"]["prose_suggestions"] is True
    now = settings.load(ws)
    profile_data = tomllib.loads(profile.read_text())
    assert now["prose_suggestions"] and now["ai_notice_ack"].endswith("Z")
    assert profile_data["weights"] == {"pacing": 2} and profile_data["mode"] == "revision"
    # Off again: the acknowledgement goes with it, so turning on asks again.
    assert main(["setup", "--folder", str(folder), "--prose-suggestions", "off"]) == 0
    capsys.readouterr()
    assert settings.load(ws) == {
        "prose_suggestions": False,
        "ai_notice_ack": "",
        "edit_in_place": None,
    }
    # A profile edited by hand never turns it on without the acknowledgement.
    for text in ("prose_suggestions = true\n", 'prose_suggestions = "false"\n'):
        profile.write_text('mode = "revision"\nlanguage = "es"\n' + text)
        hand_off = settings.load(ws)["prose_suggestions"] is False
        refused = refused and hand_off
    # A profile this tool cannot edit safely is left alone.
    tricky = 'mode = "revision"\nlanguage = "es"\nnote = """\n[not a table]\n"""\n'
    profile.write_text(tricky)
    assert main([*argv]) == 2
    capsys.readouterr()
    refused = refused and profile.read_text() == tricky
    # A broken profile does not stop setup.
    profile.write_text("mode = \n")
    assert main(["setup", "--folder", str(folder)]) == 0
    out = json.loads(capsys.readouterr().out)
    refused = refused and out["settings"]["prose_suggestions"] is False
    refused = refused and "profile_error" in out["settings"]
    # The acknowledgement alone is a usage error.
    assert main(["setup", "--folder", str(folder), "--ack-ai-notice"]) == 2
    capsys.readouterr()
    prose_suggestions_default_off = int(off_by_default and refused)
    assert prose_suggestions_default_off == 1
    assert "watermark" in settings.notice("en") and settings.notice("fr") == settings.notice("en")


def test_notice_on_a_new_folder_and_new_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _novel_folder(tmp_path)
    argv = ["setup", "--folder", str(folder), "--prose-suggestions", "on"]
    assert main([*argv, "--language", "en"]) == 1
    assert "watermark" in json.loads(capsys.readouterr().out)["notice"]
    assert not (folder / "literary-critic").exists()  # nothing was created
    assert main([*argv, "--ack-ai-notice"]) == 0
    capsys.readouterr()
    profile = tomllib.loads((folder / "literary-critic" / "analysis" / "profile.toml").read_text())
    assert profile["mode"] == "revision" and profile["language"] == "es"
    assert profile["prose_suggestions"] is True
    assert main(["validate", "profile", str(folder / "literary-critic/analysis/profile.toml")]) == 0


def test_who_writes_has_three_answers_and_help_needs_the_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "Who writes?": the writer (off, recommended), small fixes (minor) or suggested
    wording (on). The notice comes with the question, and both kinds of help need it read."""
    folder = _novel_folder(tmp_path)
    ws = folder / "literary-critic"
    profile = ws / "analysis" / "profile.toml"
    assert main(["setup", "--folder", str(folder)]) == 0
    asked = "IA" in json.loads(capsys.readouterr().out)["ai_notice"]  # shown before choosing
    argv = ["setup", "--folder", str(folder), "--prose-suggestions", "minor"]
    assert main(argv) == 1
    asked = asked and json.loads(capsys.readouterr().out)["reason"] == "ai_notice"
    assert main([*argv, "--ack-ai-notice"]) == 0
    out = json.loads(capsys.readouterr().out)
    minor = out["settings"]["prose_suggestions"] == "minor" and "ai_notice" not in out
    minor = minor and tomllib.loads(profile.read_text())["prose_suggestions"] == "minor"
    assert main(["validate", "profile", str(profile)]) == 0
    capsys.readouterr()
    # From small fixes to full suggestions and back to the writer alone.
    on = ["setup", "--folder", str(folder), "--prose-suggestions", "on", "--ack-ai-notice"]
    assert main(on) == 0
    minor = minor and json.loads(capsys.readouterr().out)["settings"]["prose_suggestions"] is True
    assert main(["setup", "--folder", str(folder), "--prose-suggestions", "off"]) == 0
    off = json.loads(capsys.readouterr().out)["settings"]["prose_suggestions"] is False
    # "minor" written by hand, without the acknowledgement, stays off.
    profile.write_text('mode = "revision"\nlanguage = "es"\nprose_suggestions = "minor"\n')
    off = off and settings.load(ws)["prose_suggestions"] is False
    # The notice says what is at stake, and that it is not legal advice.
    en = settings.notice("en")
    told = all(w in en for w in ("copyright", "watermark", "disclose", "not legal advice"))
    who_writes_ok = int(asked and minor and off and told)
    assert who_writes_ok == 1


def test_writer_choice_of_manuscript_and_edit_answer_are_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _novel_folder(tmp_path)
    ws = folder / "literary-critic"
    argv = ["setup", "--folder", str(folder)]
    assert main([*argv, "--manuscript", "MyNovel_v2.docx", "--edit-in-place", "yes"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["manuscript"]["path"] == "MyNovel_v2.docx"
    assert "MyNovel_v3.docx" in [v["path"] for v in out["versions"]]
    assert out["settings"]["edit_in_place"] is True and out["workspace_path"] == str(ws)
    # A later run (turning a setting on, say) keeps the writer's choice...
    assert main(argv) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["manuscript"]["path"] == "MyNovel_v2.docx" and again["version"] == "v001"
    assert again["settings"]["edit_in_place"] is True
    # ...until the writer saves a newer draft.
    _put(folder, "MyNovel_v4.docx", docx(_revise(_paras("marianela", 220), 9), seed=6), 10**5)
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["manuscript"]["path"] == "MyNovel_v4.docx"
    assert main([*argv, "--manuscript", "missing.docx"]) == 2


def test_a_workspace_still_works_when_the_novel_folder_moves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The workspace records the manuscript relative to the novel's folder, so it keeps
    working when that folder is reached by another path (a sandbox's copy of it, the
    writer's computer, a later conversation)."""
    folder = _novel_folder(tmp_path)
    assert main(["setup", "--folder", str(folder), "--manuscript", "MyNovel_v2.docx"]) == 0
    capsys.readouterr()
    ws = folder / "literary-critic"
    choice = json.loads((ws / setup.CHOICE).read_text(encoding="utf-8"))
    reads = json.loads((ws / "state" / "documents.json").read_text(encoding="utf-8"))
    assert choice["manuscript"] == "MyNovel_v2.docx"
    assert (
        list(reads) == ["MyNovel_v2.docx"] and reads["MyNovel_v2.docx"]["path"] == "MyNovel_v2.docx"
    )

    moved = tmp_path / "elsewhere" / "MyNovel"
    moved.parent.mkdir()
    folder.rename(moved)
    assert main(["setup", "--folder", str(moved)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["manuscript"]["path"] == "MyNovel_v2.docx" and out["version"] == "v001"
    doc = moved / "MyNovel_v2.docx"
    assert ingest.last_read(moved / "literary-critic", doc) == reads["MyNovel_v2.docx"]["sha256"]
    assert ingest.known_documents(moved / "literary-critic") == [doc.resolve()]


def test_absolute_paths_recorded_elsewhere_are_found_in_the_novel_folder(tmp_path: Path) -> None:
    """Workspaces from before kept absolute paths; one recorded where the folder had
    another path (Cowork's sandbox) is found again under the novel's folder."""
    folder = tmp_path / "MyNovel"
    (folder / "drafts").mkdir(parents=True)
    ws = folder / "literary-critic"
    (ws / "state").mkdir(parents=True)
    doc = folder / "drafts" / "MyNovel.docx"
    doc.write_bytes(docx(_paras("marianela", 5), seed=1))
    gone = "/tmp/claude-0/mnt/MyNovel/drafts/MyNovel.docx"
    rows = {gone: {"path": gone, "sha256": "old", "seq": 1}}
    (ws / "state" / "documents.json").write_text(json.dumps(rows), encoding="utf-8")
    assert ingest.recorded_path(ws, gone) == doc.resolve()
    assert ingest.last_read(ws, doc) == "old"
    ingest.record_read(ws, doc)
    rows = json.loads((ws / "state" / "documents.json").read_text(encoding="utf-8"))
    assert list(rows) == ["drafts/MyNovel.docx"] and rows["drafts/MyNovel.docx"]["seq"] == 2
    outside = tmp_path / "other.docx"
    assert ingest.stored_path(ws, outside) == str(outside.resolve())
    assert ingest.recorded_path(ws, str(outside)) == outside


def test_from_word_lists_the_open_documents_setup_can_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The writer need not find the file: the documents open in Word, with their folders."""
    known = tmp_path / "Known"
    (known / setup.WORKSPACE_DIR).mkdir(parents=True)
    (known / setup.WORKSPACE_DIR / workspace.MANIFEST).write_text("", encoding="utf-8")
    docs = [
        {"app": "word", "path": str(tmp_path / "New" / "Novel.docx"), "name": "Novel.docx"},
        {"app": "word", "path": str(known / "Other.docx"), "name": "Other.docx"},
        {"app": "word", "path": str(tmp_path / "chart.xlsx"), "name": "chart.xlsx"},
    ]
    calls = []

    def run(op: str, request: dict[str, object]) -> dict[str, object]:
        calls.append((op, request))
        return {"apps": ["word"], "documents": docs}

    monkeypatch.setattr(dc, "run", run)
    assert main(["setup", "--from-word"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert calls == [("live.status", {})]
    assert out["status"] == "open_in_word"
    assert [(d["name"], d["folder"], d["set_up"]) for d in out["documents"]] == [
        ("Novel.docx", str(tmp_path / "New"), False),
        ("Other.docx", str(known), True),
    ]


def test_from_word_is_empty_when_word_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(op: str, request: dict[str, object]) -> dict[str, object]:
        raise dc.DocError("ENGINE_UNAVAILABLE", "no Word")

    monkeypatch.setattr(dc, "run", run)
    assert word_live.open_documents() == []
    assert setup.open_in_word()["documents"] == []


def test_setup_needs_a_folder_or_word(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["setup"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
