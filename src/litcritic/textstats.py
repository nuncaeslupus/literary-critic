"""Language-aware text primitives: words, sentences, syllables, dialogue spans.

Rules are deliberately simple and documented; they are used for relative
comparisons between chapters, not as linguistic ground truth.
"""

from __future__ import annotations

import re
import unicodedata

WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
DASHES = "—–"
SINGLE_LETTER_WORDS = {"I", "A", "O", "Y", "E", "U"}  # words, not initials
ABBREVIATIONS = {
    "es": {
        "sr",
        "sra",
        "srta",
        "dr",
        "dra",
        "d",
        "dña",
        "ud",
        "uds",
        "vd",
        "etc",
        "pág",
        "núm",
        "st",
    },
    "en": {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc", "mt", "prof", "rev"},
}


def words(text: str) -> list[str]:
    return WORD.findall(text)


def sentences(text: str, lang: str = "en") -> list[str]:
    """Split a paragraph into sentences.

    A ``.``, ``!``, ``?`` or ``…`` ends a sentence when the next real character
    (after closing quotes, spaces and dialogue dashes) is upper case, a digit, an
    opening ``¿``/``¡``, or the end of the paragraph. Known abbreviations and
    single initials do not end sentences.
    """
    abbr = ABBREVIATIONS.get(lang, ABBREVIATIONS["en"])
    out: list[str] = []
    start = 0
    for m in re.finditer(r"[.!?…]+[\"'»”’)\]]*", text):
        end = m.end()
        rest = text[end:]
        nxt = re.match(rf"[\s{DASHES}\"'«“‘(]*(.)", rest)
        if nxt is None:
            continue  # paragraph end: handled after the loop
        if not (nxt.group(1).isupper() or nxt.group(1).isdigit() or nxt.group(1) in "¿¡"):
            continue
        if m.group().startswith(".") and len(m.group()) == 1:
            prev = re.search(r"([^\W\d_]+)$", text[start : m.start()])
            word = prev.group(1) if prev else ""
            initial = len(word) == 1 and word.isupper() and word not in SINGLE_LETTER_WORDS
            if word.casefold() in abbr or initial:
                continue
        piece = text[start:end].strip()
        if words(piece):
            out.append(piece)
        start = end
    tail = text[start:].strip()
    if words(tail):
        out.append(tail)
    return out


# --- syllables ---------------------------------------------------------------------

_ES_STRONG = set("aeoáéó")
_ES_ACCENTED_WEAK = set("íú")
_ES_VOWELS = set("aeiouáéíóúü")


def syllables_es(word: str) -> int:
    """Spanish syllables: vowel nuclei with diphthongs, hiatus and silent u."""
    w = word.casefold()
    w = re.sub(r"(?<=[qg])u(?=[eiéí])", "", w)  # que, qui, gue, gui: u is silent
    w = re.sub(r"(?<=[aeiouáéíóú])y$", "i", w)  # hoy, muy, rey
    if w == "y":
        return 1
    count = 0
    prev = ""
    for c in w:
        if c not in _ES_VOWELS:
            prev = ""
            continue
        if not prev:
            count += 1
        elif (
            (prev in _ES_STRONG and c in _ES_STRONG)
            or prev in _ES_ACCENTED_WEAK
            or (c in _ES_ACCENTED_WEAK)
        ):
            count += 1  # hiatus
        prev = c
    return max(count, 1)


def syllables_en(word: str) -> int:
    """English syllables: vowel groups, minus a silent final e, at least one."""
    w = re.sub(r"[^a-z]", "", word.casefold())
    if not w:
        return 1
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    groups = re.findall(r"[aeiouy]{1,2}", w)
    return max(len(groups), 1)


def syllables(word: str, lang: str) -> int:
    return syllables_es(word) if lang == "es" else syllables_en(word)


# --- dialogue ----------------------------------------------------------------------


def dialogue_spans(text: str) -> list[str]:
    """Speech segments of a paragraph.

    Dash-led paragraphs (Spanish and other conventions) alternate speech and
    narrator inserts at each dash that follows a space or precedes punctuation:
    ``—Ven —dijo ella—. Ahora.`` → ``Ven``, ``Ahora.``. Text between quotes or
    guillemets is speech too.
    """
    spans: list[str] = []
    stripped = text.replace("--", "—").lstrip()  # "--" is the plain-text em dash
    if stripped[:1] in DASHES or stripped.startswith("- "):
        body = stripped.lstrip(DASHES + "- ")
        parts = re.split(rf"\s[{DASHES}]|[{DASHES}](?=[\s.,;:])", body)
        spans.extend(p for k, p in enumerate(parts) if k % 2 == 0 and words(p))
        return spans
    for pattern in (r"«([^»]*)»", r"“([^”]*)”", r'"([^"]*)"'):
        spans.extend(m.group(1) for m in re.finditer(pattern, text) if words(m.group(1)))
    if not spans and continues_speech(text):
        spans.append(stripped.lstrip('«»“"'))
    return spans


def continues_speech(text: str) -> bool:
    """A speech running over paragraphs: opened and not closed, or a » continuation."""
    t = text.lstrip()
    if t.startswith("»"):
        return True
    for open_, close in (("«", "»"), ("“", "”")):
        if t.startswith(open_) and t.count(close) < t.count(open_):
            return True
    return t.startswith('"') and t.count('"') % 2 == 1


def is_dialogue(text: str) -> bool:
    return bool(dialogue_spans(text))


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
