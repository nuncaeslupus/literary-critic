from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest
from codex_fixture import build

from litcritic import codex, query, questions, view
from litcritic.cli import main
from litcritic.textstats import WORD

SAMPLE = {"character": "Nela", "expression": "la mina"}


@pytest.fixture(scope="module")
def work(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("marianela")
    return root, build(root)


@pytest.fixture(scope="module")
def v(work: tuple[Path, dict[str, str]]) -> view.View:
    return view.View(work[0])


def _ask(v: view.View, qid: str, **given: object) -> list[tuple[object, ...]]:
    return questions.ask(v, questions.load()[qid], dict(given))[1]


def test_every_named_question_runs_on_fixture(v: view.View) -> None:
    qs = questions.load()
    assert len(qs) >= 20
    for q in qs.values():
        given = {k: SAMPLE[k] for k in q.params if k in SAMPLE}
        cols, _ = questions.ask(v, q, given)
        assert cols, q.id


def test_example_question_families_on_fixture(
    work: tuple[Path, dict[str, str]], v: view.View
) -> None:
    root, ids = work
    cx = codex.Codex(root)
    ix = query.load(root, "v001")
    para = {a: i for i, a in enumerate(ix.anchors)}

    # 1. In how many chapters does a character speak?
    nela_chapters = {
        query.chapter_key(d.spans[0].start.para)
        for d in cx.of_type("dialogue")
        if d.fields["speaker"] == ids["nela"]
    }
    assert _ask(v, "speech-chapters", character="Nela")[0][0] == len(nela_chapters) > 3

    # 2. Am I overusing an expression? Uses per chapter.
    expected: Counter[str] = Counter()
    for i, p in enumerate(ix.paragraphs):
        forms = [view.norm(w) for w in WORD.findall(p)]
        hits = sum(forms[k : k + 2] == ["los", "ojos"] for k in range(len(forms)))
        if hits:
            expected[query.chapter_key(ix.anchors[i])] += hits
    got = {str(c): int(str(n)) for c, n in _ask(v, "expression-use", expression="Los  OJOS")}
    assert got == dict(expected) and sum(got.values()) > 5

    # 3. Which character matters most to another?
    assert _ask(v, "relevance", character="Nela")[0][0] == "Pablo"

    # 4. Is a storyline told continuously, or are there gaps?
    words = [len(WORD.findall(p)) for p in ix.paragraphs]
    start = [sum(words[:i]) for i in range(len(words))]
    cure = sorted(para[s.start.para] for s in cx.get(ids["cure"]).spans)
    gaps = sorted(
        (start[b] - (start[a] + words[a]) for a, b in pairwise(cure)),
        reverse=True,
    )
    rows = _ask(v, "thread-gaps", min_words=1)
    got_gaps = [int(str(r[3])) for r in rows if r[0] == "cure"]
    assert got_gaps == [g for g in gaps if g >= 1] and got_gaps[0] > 1000


def test_progress_questions_on_fixture(work: tuple[Path, dict[str, str]], v: view.View) -> None:
    _, ids = work
    assert [r[0] for r in _ask(v, "setups-without-payoff")] == [ids["open-setup"]]
    rejected = _ask(v, "rejected")
    assert rejected == [(ids["rejected-issue"], "Slow opening.", "intended pace")]
    open_issues = {(r[0], r[1]): r[2] for r in _ask(v, "open-issues")}
    assert open_issues == {("line", "low"): 1, ("scene", "low"): 1}  # accepted != done


def test_question_params_validated(v: view.View) -> None:
    q = questions.load()["speech-chapters"]
    with pytest.raises(questions.QuestionError, match="needs character"):
        questions.ask(v, q, {})
    with pytest.raises(questions.QuestionError, match="unknown parameter"):
        questions.ask(v, q, {"character": "Nela", "chapter": "c01"})
    with pytest.raises(questions.QuestionError, match="declares"):
        questions.parse('-- id = "x"\n-- title = "t"\n-- family = "f"\nSELECT :a', "x.sql")


def test_ask_and_questions_cli(
    work: tuple[Path, dict[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = work
    assert main(["codex", "questions"]) == 0
    assert "speech-chapters [characters]" in capsys.readouterr().out
    w = ["--workspace", str(root)]
    assert main(["codex", "ask", "relevance", "--param", "character=Nela", *w]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("Which characters") and out[2].startswith("Pablo |")
    assert main(["codex", "ask", "relevance", *w]) == 2
    assert "needs character" in capsys.readouterr().err


def test_question_lookups_ignore_case_and_accents(v: view.View) -> None:
    assert int(str(_ask(v, "speech-chapters", character="SOFIA")[0][0])) > 0
    assert _ask(v, "relevance", character="celipin")


def test_question_limits_answer_with_an_error_row(v: view.View) -> None:
    assert str(_ask(v, "top-phrases", n=5, min_uses=1)[0][0]).startswith("error")
    rows = _ask(v, "expression-use", expression="uno dos tres cuatro cinco")
    assert str(rows[0][0]).startswith("error")
    hyphen = _ask(v, "expression-use", expression="los-ojos,")
    assert hyphen == _ask(v, "expression-use", expression="los ojos")


def test_absences_include_characters_who_never_return(v: view.View) -> None:
    kinds = {r[1] for r in _ask(v, "character-absences", min_words=1)}
    assert {"before first", "after last", "between"} <= kinds
