from litcritic import guard


def test_fold_strips_accents_and_case() -> None:
    assert guard.fold("Ángel ÑANDÚ") == "angel nandu"


def test_manuscript_outside_corpus_blocked() -> None:
    v = guard.check({"notes/draft.docx": "", "corpus/en/sample.docx": ""}, [])
    assert [x.path for x in v] == ["notes/draft.docx"]


def test_term_in_content_blocked_accent_insensitive() -> None:
    v = guard.check({"docs/a.md": "Then Ramón left."}, ["Ramon"])
    assert len(v) == 1 and "content" in v[0].reason


def test_term_in_path_blocked() -> None:
    v = guard.check({"docs/ramon-notes.md": ""}, ["Ramón"])
    assert len(v) == 1 and "path" in v[0].reason


def test_word_boundary_respected() -> None:
    assert guard.check({"a.md": "Annabel and Ana"}, ["Anabel"]) == []
    assert guard.check({"a.md": "the analysis"}, ["Ana"]) == []


def test_short_terms_ignored() -> None:
    assert guard.check({"a.md": "el yo"}, ["yo"]) == []


def test_read_terms_skips_comments(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "t.txt"
    f.write_text("# comment\nFoo\n\nBar\n", encoding="utf-8")
    assert guard.read_terms([f, tmp_path / "missing.txt"]) == ["Bar", "Foo"]
