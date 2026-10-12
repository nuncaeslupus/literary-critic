import io
import random
import re
import zipfile

import pytest
from docgen import docx

from litcritic import corpus, docx_edit, ingest

AUTHOR = docx_edit.AUTHOR


def _members(data: bytes) -> dict[str, bytes]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    return {n: zf.read(n) for n in zf.namelist()}


def _corpus_paragraphs(n: int = 80) -> list[tuple[str, bool]]:
    text = corpus.get("marianela").path.read_text(encoding="utf-8")
    paras = [ingest.clean(p) for p in text.split("\n\n") if len(ingest.clean(p)) > 60]
    return [(p, False) for p in paras[:n]]


def _reject_all(data: bytes) -> list[str]:
    """What Word shows after "Reject all changes": insertions gone, deletions back."""
    xml = _members(data)["word/document.xml"].decode("utf-8")
    xml = re.sub(r"<w:ins\b[^>]*>.*?</w:ins>", "", xml, flags=re.S)
    xml = re.sub(
        r"<w:del\b[^>]*\bw:author=\"literary-critic\"[^>]*>(.*?)</w:del>", r"\1", xml, flags=re.S
    )
    xml = xml.replace("w:delText", "w:t")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, payload in _members(data).items():
            zf.writestr(name, xml.encode("utf-8") if name == "word/document.xml" else payload)
    return [p.text for p in ingest.read_docx(out.getvalue()).paragraphs]


def _plan(data: bytes, rng: random.Random, k: int) -> list[tuple[docx_edit.Edit, int, str]]:
    """k edits on distinct paragraphs, each quote unique in the document."""
    texts = docx_edit.texts(data)
    plans: list[tuple[docx_edit.Edit, int, str]] = []
    for ordinal in rng.sample(range(len(texts)), len(texts)):
        words = texts[ordinal].split()
        if len(words) < 8:
            continue
        a = rng.randrange(0, len(words) - 4)
        quote = " ".join(words[a : a + 4])
        if len(docx_edit.find(data, quote)) != 1:
            continue
        repl = quote.upper() + " <&> nuevo"
        try:  # passages across a note mark or an old tracked change are refused, by design
            docx_edit.apply(data, [docx_edit.Edit("probe", quote, repl)])
        except docx_edit.EditError:
            continue
        expected = " ".join(texts[ordinal].split()).replace(quote, repl, 1)
        plans.append((docx_edit.Edit(f"E{len(plans)}", quote, repl), ordinal, expected))
        if len(plans) == k:
            break
    return plans


def test_edits_change_only_target_text() -> None:
    unintended = 0
    for seed in range(8):
        data = docx(_corpus_paragraphs(), seed=seed)
        before = docx_edit.texts(data)
        plans = _plan(data, random.Random(seed), 6)
        assert len(plans) == 6
        out, matches = docx_edit.apply(data, [e for e, _, _ in plans], date="2026-10-12T00:00:00Z")
        after = docx_edit.texts(out)
        edited = {o: exp for _, o, exp in plans}
        for k, (old, new) in enumerate(zip(before, after, strict=True)):
            want = edited.get(k, old)
            unintended += " ".join(new.split()) != " ".join(want.split())
        a, b = _members(data), _members(out)
        assert a.keys() == b.keys()
        unintended += sum(a[n] != b[n] for n in a if n != "word/document.xml")

        # Outside the edited paragraphs, document.xml is byte-identical.
        def outside(xml: str, edited: dict[int, str] = edited) -> str:
            spans = docx_edit.paragraph_spans(xml, "w")
            for o in sorted(edited, reverse=True):
                s, e = spans[o]
                xml = xml[:s] + xml[e:]
            return xml

        unintended += outside(a["word/document.xml"].decode()) != outside(
            b["word/document.xml"].decode()
        )
        assert sorted(m.para for m in matches) == sorted(edited)
    assert unintended == 0


def test_edits_are_tracked_revisions() -> None:
    data = docx(_corpus_paragraphs(), seed=11)
    plans = _plan(data, random.Random(11), 5)
    out, _ = docx_edit.apply(data, [e for e, _, _ in plans])
    xml = _members(out)["word/document.xml"].decode()
    assert len(re.findall(rf'<w:ins\b[^>]*w:author="{AUTHOR}"', xml)) == 5
    assert len(re.findall(rf'<w:del\b[^>]*w:author="{AUTHOR}"', xml)) >= 5
    ids = re.findall(r'<w:(?:ins|del)\b[^>]*\bw:id="(\d+)"', xml)
    assert len(ids) == len(set(ids))  # every revision has its own id
    assert _reject_all(out) == [p.text for p in ingest.read_docx(data).paragraphs]


def test_edit_refused_when_ambiguous_missing_or_overlapping() -> None:
    data = docx([("Pablo dijo hola. Pablo dijo adiós.", False), ("Otra cosa.", False)])
    with pytest.raises(docx_edit.EditError) as exc:
        docx_edit.apply(data, [docx_edit.Edit("A", "Pablo dijo", "Él dijo")])
    assert "2 times" in exc.value.problems["A"]
    with pytest.raises(docx_edit.EditError, match="not found"):
        docx_edit.apply(data, [docx_edit.Edit("B", "nada de esto", "x")])
    with pytest.raises(docx_edit.EditError, match="overlap"):
        docx_edit.apply(
            data,
            [docx_edit.Edit("C", "dijo hola", "x"), docx_edit.Edit("D", "hola. Pablo", "y")],
        )
    # Context picks the occurrence; whitespace in the quote is tolerated.
    out, m = docx_edit.apply(
        data, [docx_edit.Edit("E", "Pablo  dijo", "Él dijo", prefix="hola.", suffix="adiós")]
    )
    assert docx_edit.texts(out)[0] == "Pablo dijo hola. Él dijo adiós."
    assert m[0].start == 17


def test_edit_refused_inside_existing_revision_or_field() -> None:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    doc = (
        f"<w:document {w}><w:body>"
        '<w:p><w:r><w:t>Antes </w:t></w:r><w:ins w:id="1" w:author="x"><w:r><w:t>insertado'
        "</w:t></w:r></w:ins><w:r><w:t> después</w:t></w:r></w:p>"
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> PAGE '
        '</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>12</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "<w:r><w:t> páginas</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", doc)
    data = buf.getvalue()
    assert docx_edit.texts(data) == ["Antes insertado después", "12 páginas"]
    with pytest.raises(docx_edit.EditError, match="by hand"):
        docx_edit.apply(data, [docx_edit.Edit("A", "insertado", "x")])
    with pytest.raises(docx_edit.EditError):
        docx_edit.apply(data, [docx_edit.Edit("B", "12 pág", "x")])
    out, _ = docx_edit.apply(data, [docx_edit.Edit("C", "páginas", "hojas")])
    assert docx_edit.texts(out)[1] == "12 hojas"


def test_rename_whole_words_keeps_case() -> None:
    data = docx(
        [("Pablo y Pablito vieron a PABLO.", False), ("pablo no vino; Pablo sí.", False)], seed=4
    )
    assert [m.text for m in docx_edit.rename_matches(data, "Pablo", case_sensitive=False)] == [
        "Pablo",
        "PABLO",
        "pablo",
        "Pablo",
    ]
    assert len(docx_edit.rename_matches(data, "Pablo")) == 2
    out, found, skipped = docx_edit.rename(data, "pablo", "pedro", case_sensitive=False)
    assert skipped == []
    assert len(found) == 4
    assert docx_edit.texts(out) == ["Pedro y Pablito vieron a PEDRO.", "pedro no vino; Pedro sí."]
    with pytest.raises(docx_edit.EditError, match="does not appear"):
        docx_edit.rename(data, "Ana", "Eva")


def test_not_a_docx_is_an_edit_error() -> None:
    with pytest.raises(docx_edit.EditError, match="not a readable"):
        docx_edit.texts(b"plain text")


def _raw(body: str) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", f"<w:document {w}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


def test_review_regressions_note_marks_fields_context_and_case() -> None:
    # A footnote mark between the words would move: refused.
    data = _raw(
        '<w:p><w:r><w:t>end.</w:t></w:r><w:r><w:footnoteReference w:id="1"/></w:r>'
        '<w:r><w:t xml:space="preserve"> Next</w:t></w:r></w:p>'
    )
    with pytest.raises(docx_edit.EditError, match="note mark"):
        docx_edit.apply(data, [docx_edit.Edit("a", "end. Next", "end; next")])
    # A field that spans paragraphs (a table of contents) is not editable inside.
    toc = _raw(
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>TOC</w:instrText>'
        '</w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>'
        "<w:p><w:r><w:t>Chapter two</w:t></w:r></w:p>"
        '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "<w:p><w:r><w:t>Chapter two</w:t></w:r></w:p>"
    )
    with pytest.raises(docx_edit.EditError):
        docx_edit.apply(toc, [docx_edit.Edit("b", "Chapter two", "X", prefix="TOC")])
    # Context can reach into the previous paragraph, and a wrong one excludes.
    two = _raw(
        "<w:p><w:r><w:t>He said yes</w:t></w:r></w:p><w:p><w:r><w:t>Then He said yes</w:t>"
        "</w:r></w:p>"
    )
    assert [m.para for m in docx_edit.find(two, "He said", prefix="Then")] == [1]
    assert [m.para for m in docx_edit.find(two, "He said", prefix="yes Then")] == [1]
    # Every problem is reported at once, the empty quote included.
    with pytest.raises(docx_edit.EditError) as exc:
        docx_edit.apply(two, [docx_edit.Edit("e", " ", "x"), docx_edit.Edit("f", "zzz", "x")])
    assert set(exc.value.problems) == {"e", "f"}
    # An author name with quotes still gives well-formed XML.
    out, _ = docx_edit.apply(
        two, [docx_edit.Edit("g", "yes", "no", prefix="Then He said")], author='Ana "N"'
    )
    xml_out = _members(out)["word/document.xml"].decode()
    assert 'w:author="Ana &quot;N&quot;"' in xml_out
    # Renaming is case-sensitive by default: the verb survives the name.
    will = _raw("<w:p><w:r><w:t>Will said she will go.</w:t></w:r></w:p>")
    out, _, _ = docx_edit.rename(will, "Will", "Bill")
    assert docx_edit.texts(out) == ["Bill said she will go."]
    with pytest.raises(docx_edit.EditError, match="empty"):
        docx_edit.rename(will, "  ", "x")


def test_rendered_page_mark_run_is_editable_and_kept() -> None:
    data = _raw("<w:p><w:r><w:lastRenderedPageBreak/><w:t>Top of the page here.</w:t></w:r></w:p>")
    out, _ = docx_edit.apply(data, [docx_edit.Edit("a", "Top of", "Head of")])
    xml = _members(out)["word/document.xml"].decode()
    assert docx_edit.texts(out) == ["Head of the page here."]
    assert xml.index("lastRenderedPageBreak") < xml.index("<w:del ")


def test_rename_across_a_long_book_is_fast() -> None:
    import time

    paras = [(f"Párrafo {k}: Nela llegó tarde y Nela se fue pronto.", False) for k in range(3000)]
    data = docx(paras, seed=1)
    t0 = time.perf_counter()
    out, found, skipped = docx_edit.rename(data, "Nela", "Marta")
    assert len(found) + len(skipped) == 6000 and len(found) > 5000
    assert all("by hand" in why for _, why in skipped)
    assert time.perf_counter() - t0 < 30
    assert docx_edit.texts(out)[5].count("Marta") == 2
