"""Deterministic pre-pass for the literary index (no LLM).

From a draft's paragraphs and scenes it finds what the LLM would otherwise look
for by hand:

- **candidates** for entities: runs of capitalised words outside sentence starts
  (joined by connectors such as ``de``/``van`` only between proper parts),
  honorific + name (``Mr. Utterson``, ``don Teodoro``), article + name
  (``la Nela``) and repeated role titles (``the lawyer``, ``el médico``), each
  with its count, the surface forms seen, its first quote and up to two
  keyword-in-context snippets;
- **speakers**: speaker tags in dialogue (verb of saying + name, or name + verb);
- **scenes**: words, paragraph range and the candidates present in each scene;
- **render**: the candidate list as compact text for the entity packet, with its
  token estimate (characters / 4), trimmed to a budget.

Word lists live in ``data/prepass_<lang>.toml``. Merging aliases and rejecting
false candidates is the LLM's job; the pre-pass aims for recall at a bounded size.
"""

from __future__ import annotations

import json
import math
import re
import time
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from litcritic import structure, textstats

DATA = Path(__file__).parent / "data"
TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
POSSESSIVE = re.compile(r"['’]s?$")
OPENERS = "\"'“”‘’«»—–-(¿¡[_*"
ENDERS = ".!?…:;"
SNIPPET_SIDE = 12
QUOTE_SIDE = 8
DEFAULT_SHARE = 0.10  # default render budget: this share of the text's tokens
MIN_ROLE_WORD = 3


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


@dataclass(frozen=True)
class Lexicon:
    lang: str
    honorifics: frozenset[str]
    honorifics_lower: frozenset[str]
    articles: frozenset[str]
    plural_articles: frozenset[str]
    connectors: tuple[tuple[str, ...], ...]  # longest first
    place_preps: frozenset[str]
    role_articles: tuple[str, ...]
    role_nouns: frozenset[str]
    role_min: int
    say_verbs: tuple[str, ...]
    not_speakers: frozenset[str]
    stop: frozenset[str]  # lower case


@cache
def lexicon(lang: str) -> Lexicon:
    path = DATA / f"prepass_{lang}.toml"
    if not path.is_file():
        path = DATA / "prepass_en.toml"
        lang = "en"
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    conns = sorted({tuple(c.split()) for c in d["connectors"]}, key=lambda c: -len(c))
    return Lexicon(
        lang=lang,
        honorifics=frozenset(d["honorifics"]),
        honorifics_lower=frozenset(d["honorifics_lower"]),
        articles=frozenset(d["articles"]),
        plural_articles=frozenset(d["plural_articles"]),
        connectors=tuple(conns),
        place_preps=frozenset(d["place_preps"]),
        role_articles=tuple(d["role_articles"]),
        role_nouns=frozenset(d["role_nouns"]),
        role_min=int(d["role_min"]),
        say_verbs=tuple(sorted(d["say_verbs"], key=len, reverse=True)),
        not_speakers=frozenset(d["not_speakers"]),
        stop=frozenset(w.casefold() for w in d["stop"]),
    )


# --- tokens ------------------------------------------------------------------------


@dataclass(frozen=True)
class Tok:
    s: int
    e: int
    w: str


def tokens(par: str) -> list[Tok]:
    out = []
    for m in TOKEN.finditer(par):
        w = m.group()
        e = m.end()
        pm = POSSESSIVE.search(w)
        if pm and len(w) - len(pm.group()) >= 2 and w[0].isupper():
            w = w[: len(w) - len(pm.group())]
            e = m.start() + len(w)
        out.append(Tok(m.start(), e, w))
    return out


def is_cap(w: str) -> bool:
    """A capitalised word (not an all-caps heading word, not a lone letter)."""
    head = re.split(r"['’]", w, maxsplit=1)[0]
    return len(head) > 1 and w[0].isupper() and not w.isupper()


def is_initial(par: str, pos: int, lex: Lexicon) -> bool:
    """True when the word at ``pos`` opens a sentence (or a speech)."""
    j = pos - 1
    opener = False
    while j >= 0 and (par[j].isspace() or par[j] in OPENERS):
        opener = opener or par[j] in OPENERS
        j -= 1
    if j < 0 or opener:
        return True
    if par[j] not in ENDERS:
        return False
    if par[j] == ".":
        prev = re.search(r"([^\W\d_]+)$", par[:j])
        word = prev.group(1) if prev else ""
        abbr = textstats.ABBREVIATIONS.get(lex.lang, textstats.ABBREVIATIONS["en"])
        if word in lex.honorifics or word.casefold() in abbr or (len(word) == 1 and word.isupper()):
            return False
    return True


def _space(gap: str) -> bool:
    return bool(gap) and gap.isspace() and gap.count("\n") == 0


# --- runs --------------------------------------------------------------------------


@dataclass
class Run:
    para: int
    s: int  # start of the form (honorific included)
    e: int
    form: str  # surface, honorific included, article excluded
    bare: str  # surface without the honorific
    key: tuple[str, ...]
    hon: bool
    initial: bool
    art: str  # article right before, or ""
    prep: bool
    spans: tuple[tuple[int, int], ...] = ()  # each part when the run is plain words


@dataclass
class Stats:
    low: Counter[str] = field(default_factory=Counter)  # lower-case uses, by casefold
    capmid: Counter[str] = field(default_factory=Counter)  # capitalised mid-sentence uses

    def common(self, w: str, lex: Lexicon) -> bool:
        """A capitalised word that is an ordinary word (or a stop word) in this text."""
        return w.casefold() in lex.stop or self.low[w.casefold()] > self.capmid[w]


def _stats(paras: list[str], toks: list[list[Tok]], lex: Lexicon) -> Stats:
    st = Stats()
    for par, ts in zip(paras, toks, strict=True):
        for t in ts:
            if t.w[0].islower():
                st.low[t.w.casefold()] += 1
            elif is_cap(t.w) and not is_initial(par, t.s, lex):
                st.capmid[t.w] += 1
    return st


def _runs(i: int, par: str, ts: list[Tok], st: Stats, lex: Lexicon) -> list[Run]:
    out: list[Run] = []
    n = len(ts)

    def gap(a: int) -> str:
        return par[ts[a].e : ts[a + 1].s]

    k = 0
    while k < n:
        first = k
        hon = False
        while k + 1 < n:  # honorifics, chained ("Sr. D. Teodoro")
            w, nxt, g = ts[k].w, ts[k + 1].w, gap(k)
            if not (is_cap(nxt) or nxt in lex.honorifics):
                break
            lower = w in lex.honorifics_lower and _space(g) and nxt not in lex.honorifics
            upper = w in lex.honorifics and (_space(g) or (g[:1] == "." and _space(g[1:])))
            if not (lower or upper):
                break
            hon = True
            k += 1
        if not is_cap(ts[k].w):
            k = first + 1
            continue
        parts = [k]
        j = k
        while j + 1 < n:
            g = gap(j)
            nxt = ts[j + 1].w
            if (_space(g) or g == "-") and is_cap(nxt) and nxt.casefold() not in lex.stop:
                parts.append(j + 1)
                j += 1
                continue
            joined = False
            for conn in lex.connectors:
                m = len(conn)
                last = j + m + 1
                if last >= n or not _space(g):
                    continue
                words = tuple(ts[x].w for x in range(j + 1, j + m + 1))
                gaps_ok = all(_space(gap(x)) for x in range(j + 1, last))
                head = ts[last].w
                if words == conn and gaps_ok and is_cap(head) and not st.common(head, lex):
                    parts.extend(range(j + 1, last + 1))
                    j = last
                    joined = True
                    break
            if not joined:
                break
        initial = is_initial(par, ts[first].s, lex)
        # Drop leading ordinary or stop words ("Pero Teodoro", "Oh Pablo").
        if not hon:
            while parts and (
                (initial and st.common(ts[parts[0]].w, lex))
                or ts[parts[0]].w.casefold() in lex.stop
                or not is_cap(ts[parts[0]].w)
            ):
                parts.pop(0)
                initial = False
            if not parts:
                k = j + 1
                continue
        while parts and not is_cap(ts[parts[-1]].w):
            parts.pop()
        caps = [ts[p].w for p in parts if is_cap(ts[p].w)]
        if not caps or all(c.casefold() in lex.stop for c in caps):
            k = j + 1
            continue
        lead = first if hon else parts[0]
        before = par[: ts[lead].s]
        art = ""
        prep = False
        mb = re.search(r"(?:^|[\s(])([^\W\d_]+)\s+$", before)
        if mb:
            prev = mb.group(1)
            if prev in lex.articles:
                art = prev
                mb2 = re.search(r"(?:^|[\s(])([^\W\d_]+)\s+$", before[: mb.start(1)])
                prep = bool(mb2 and mb2.group(1).casefold() in lex.place_preps)
            else:
                prep = prev.casefold() in lex.place_preps
        s, e = ts[lead].s, ts[parts[-1]].e
        key = tuple(ts[p].w.casefold() for p in parts)
        bare_s = ts[parts[0]].s
        plain = not hon and not art and all(is_cap(ts[p].w) for p in parts)
        if mb and not hon and not art:  # "los esposos Centeno": a named group
            prev = mb.group(1)
            mg = re.search(r"(?:^|[\s(])([^\W\d_]+)\s+$", before[: mb.start(1)])
            if (
                mg
                and mg.group(1) in lex.plural_articles
                and prev[0].islower()
                and len(prev) >= MIN_ROLE_WORD
                and prev not in _lower_connectors(lex)
            ):
                s = bare_s = mb.start(1)
                key = (prev.casefold(), *key)
                art = mg.group(1)
                plain = False
        out.append(
            Run(
                para=i,
                s=s,
                e=e,
                form=re.sub(r"\s+", " ", par[s:e]),
                bare=re.sub(r"\s+", " ", par[bare_s:e]),
                key=key,
                hon=hon,
                initial=initial and not hon,
                art=art,
                prep=prep,
                spans=tuple((ts[p].s, ts[p].e) for p in parts) if plain else (),
            )
        )
        k = j + 1
    return out


# --- speakers and roles ------------------------------------------------------------


def _verb_re(lex: Lexicon) -> str:
    return "|".join(re.escape(v).replace(r"\ ", r"\s+") for v in lex.say_verbs)


def _speakers(
    i: int, par: str, runs: list[Run], lex: Lexicon
) -> list[tuple[str, Run | None, str, int]]:
    """(role or "", run or None, verb, position) for each speaker tag in a paragraph."""
    if not textstats.is_dialogue(par):
        return []
    verbs = _verb_re(lex)
    arts = "|".join(lex.role_articles)
    found: list[tuple[str, Run | None, str, int]] = []
    starts = {r.s: r for r in runs}
    for m in re.finditer(rf"(?<![\w])({verbs})\s+", par, re.IGNORECASE):
        at = m.end()
        if at in starts:
            found.append(("", starts[at], m.group(1), at))
            continue
        ma = re.match(rf"({arts})\s+", par[at:], re.IGNORECASE)
        if not ma:
            continue
        if at + ma.end() in starts:
            found.append(("", starts[at + ma.end()], m.group(1), at))
            continue
        mn = re.match(r"([^\W\d_]+)(?![\w])", par[at + ma.end() :])
        noun = mn.group(1) if mn else ""
        if noun[:1].islower() and len(noun) >= MIN_ROLE_WORD and noun not in lex.not_speakers:
            found.append((f"{ma.group(1).casefold()} {noun}", None, m.group(1), at))
    ends = {r.e: r for r in runs}
    for m in re.finditer(rf"\s*,?\s+({verbs})(?![\w])", par, re.IGNORECASE):
        r = ends.get(m.start())
        if r and not any(f[1] is r for f in found):
            found.append(("", r, m.group(1), r.s))
    for m in re.finditer(rf"(?<![\w])({arts})\s+([^\W\d_]+)\s*,?\s+({verbs})(?![\w])", par):
        if m.group(2)[0].islower() and m.group(2).casefold() in lex.role_nouns:
            role = f"{m.group(1).casefold()} {m.group(2)}"
            if not any(f[0] == role and abs(f[3] - m.start()) < 3 for f in found):
                found.append((role, None, m.group(3), m.start()))
    found.sort(key=lambda f: f[3])
    return found


def _role_count(paras: list[str], idx: list[int], phrase: str) -> list[tuple[int, int, int]]:
    art, noun = phrase.split(" ", 1)
    rx = re.compile(
        rf"(?<![\w])(?i:{re.escape(art)})\s+{re.escape(noun)}(?![\w])(?!\s+[A-ZÁÉÍÓÚÑÜ])"
    )
    return [(i, m.start(), m.end()) for i in idx for m in rx.finditer(paras[i])]


# --- snippets ----------------------------------------------------------------------


def snippet(par: str, s: int, e: int, side: int = SNIPPET_SIDE) -> str:
    """``side`` words each way around [s, e), the form in brackets."""
    return _trim(f"{par[:s]}[{par[s:e]}]{par[e:]}", side)


def quote(par: str, s: int, e: int, side: int = QUOTE_SIDE) -> str:
    """An exact substring of ``par`` around [s, e) with up to ``side`` words each way."""
    lefts = [m.start() for m in re.finditer(r"\S+", par[:s])]
    a = lefts[-side] if len(lefts) >= side else 0
    rights = [m.end() for m in re.finditer(r"\S+", par[e:])]
    b = e + rights[side - 1] if len(rights) >= side else len(par)
    return par[a:b].strip()


def _trim(snip: str, side: int) -> str:
    left, _, rest = snip.partition("[")
    form, _, right = rest.partition("]")
    lw = re.findall(r"\S+\s*", left)[-side:] if side else []
    rw = re.findall(r"\s*\S+", right)[:side] if side else []
    return re.sub(r"\s+", " ", "".join(lw) + f"[{form}]" + "".join(rw)).strip()


# --- extraction --------------------------------------------------------------------


def _scene_list(chapters: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    scenes = [s for c in chapters for s in c.get("scenes", [])]
    return scenes or [{"id": "all", "start": 0, "end": n - 1, "words": 0}]


def extract(
    paras: list[str], anchors: list[str], scenes: list[dict[str, Any]], lang: str
) -> dict[str, Any]:
    """Candidates, speakers and scenes for paragraphs grouped in ``scenes``."""
    lex = lexicon(lang)
    scene_of: dict[int, str] = {}
    for sc in scenes:
        for i in range(sc["start"], sc["end"] + 1):
            scene_of[i] = sc["id"]
    idx = sorted(i for i in scene_of if i < len(paras))
    toks = [tokens(p) if i in scene_of else [] for i, p in enumerate(paras)]
    st = _stats(paras, toks, lex)

    runs: list[Run] = []
    tags: list[tuple[int, str, Run | None, str]] = []
    for i in idx:
        rs = _runs(i, paras[i], toks[i], st, lex)
        runs.extend(rs)
        for role, run, verb, _ in _speakers(i, paras[i], rs, lex):
            tags.append((i, role, run, verb))

    runs = _split(runs, paras)
    by_key: dict[tuple[str, ...], list[Run]] = defaultdict(list)
    for r in runs:
        by_key[r.key].append(r)
    spoke = {id(r) for _, _, r, _ in tags if r is not None}

    cands: list[dict[str, Any]] = []
    key_name: dict[tuple[str, ...], str] = {}
    occ: dict[str, list[tuple[int, int, int]]] = {}
    for key, rs in by_key.items():
        n = len(rs)
        hon = sum(r.hon for r in rs)
        mid = sum(not r.initial for r in rs)
        art = sum(bool(r.art) and not r.initial for r in rs)
        speaker = any(id(r) in spoke for r in rs)
        caps = [w for w in key if w not in _lower_connectors(lex)]
        bare = Counter(r.bare for r in rs).most_common(1)[0][0]
        if len(caps) == 1:
            proper = not st.common(bare, lex)
            ok = hon > 0 or speaker or art >= 2 or (proper and mid >= 1)
        else:
            ok = hon > 0 or speaker or mid >= 1
        if not ok:
            continue
        plural = sum(r.art in lex.plural_articles for r in rs)
        prep = sum(r.prep for r in rs)
        if plural * 2 > n:
            hint: str | None = "group"
        elif hon or speaker:
            hint = "person-title"
        elif n >= 2 and prep * 5 >= n * 2:
            hint = "place-prep"
        elif art >= 2:
            hint = "article-name"
        else:
            hint = None
        forms = [f for f, _ in Counter(r.form for r in rs).most_common()]
        if bare not in forms:
            forms.append(bare)
        key_name[key] = bare
        occ[bare] = [(r.para, r.s, r.e) for r in rs]
        cands.append({"name": bare, "forms": forms, "count": n, "kind_hint": hint})

    # Role titles: listed nouns used often, and article + noun seen as a speaker.
    role_phrases: set[str] = set()
    for i in idx:
        for art_ in lex.role_articles:
            rx = rf"(?<![\w])(?i:{re.escape(art_)})\s+([^\W\d_]+)(?![\w])"
            for m in re.finditer(rx, paras[i]):
                if m.group(1) in lex.role_nouns:
                    role_phrases.add(f"{art_} {m.group(1)}")
    role_phrases |= {role for _, role, _, _ in tags if role}
    taken = {(p, s) for v in occ.values() for p, s, _ in v}
    for phrase in sorted(role_phrases):
        hits = [h for h in _role_count(paras, idx, phrase) if (h[0], h[1]) not in taken]
        if len(hits) >= lex.role_min and phrase not in occ:
            occ[phrase] = hits
            cands.append(
                {"name": phrase, "forms": [phrase], "count": len(hits), "kind_hint": "role"}
            )

    for c in cands:
        hits = sorted(occ[c["name"]])
        f = hits[0]
        picks = [f]
        if len(hits) > 1:
            later = [h for h in hits[len(hits) // 2 :] if h[0] != f[0]] or hits[len(hits) // 2 :]
            picks.append(later[0])
        c["first"] = {"para": anchors[f[0]], "quote": quote(paras[f[0]], f[1], f[2])}
        c["snippets"] = [snippet(paras[p], s, e) for p, s, e in picks]
        if c["kind_hint"] is None:
            del c["kind_hint"]
    cands.sort(key=lambda c: (-c["count"], c["name"]))

    speakers: dict[str, list[dict[str, str]]] = {sc["id"]: [] for sc in scenes}
    for i, role, run, verb in tags:
        who = role or (key_name.get(run.key, run.bare) if run else "")
        speakers[scene_of[i]].append({"para": anchors[i], "who": who, "verb": verb})

    present: dict[str, Counter[str]] = defaultdict(Counter)
    for c in cands:
        for p, _, _ in occ[c["name"]]:
            present[scene_of[p]][c["name"]] += 1
    scene_out = {}
    for sc in scenes:
        lo, hi = sc["start"], sc["end"]
        words = sc.get("words") or sum(len(textstats.words(paras[i])) for i in range(lo, hi + 1))
        scene_out[sc["id"]] = {
            "words": words,
            "paras": [lo, hi],
            "anchors": [anchors[lo], anchors[hi]],
            "names": [n for n, _ in present[sc["id"]].most_common()],
        }
    return {"candidates": cands, "speakers": speakers, "scenes": scene_out}


def _split(runs: list[Run], paras: list[str]) -> list[Run]:
    """Split rare runs of adjacent names ("Aldeacorba Golfín", "Inglaterra Ulises
    Bull") where the leading part, or the next word, is a name used on its own."""
    counts = Counter(r.key for r in runs)
    out: list[Run] = []
    for r in runs:
        if len(r.spans) < 2 or counts[r.key] > 2:
            out.append(r)
            continue
        cut = next((p for p in range(1, len(r.key)) if counts[r.key[:p]] > 0), 0)
        if not cut and counts[r.key[1:2]] > 0:  # "... Inglaterra Ulises Bull" with "Ulises"
            cut = 1
        if not cut:
            out.append(r)
            continue
        par = paras[r.para]
        for a, b in ((0, cut), (cut, len(r.spans))):
            s, e = r.spans[a][0], r.spans[b - 1][1]
            out.append(
                Run(
                    para=r.para,
                    s=s,
                    e=e,
                    form=par[s:e],
                    bare=par[s:e],
                    key=r.key[a:b],
                    hon=False,
                    initial=r.initial and a == 0,
                    art=r.art if a == 0 else "",
                    prep=r.prep and a == 0,
                    spans=r.spans[a:b],
                )
            )
    return out


@cache
def _lower_connectors(lex: Lexicon) -> frozenset[str]:
    return frozenset(w for c in lex.connectors for w in c)


# --- rendering ---------------------------------------------------------------------


def _render_lines(cands: list[dict[str, Any]], nsnip: list[int], side: int) -> str:
    lines = ["# name (count) [hint] = other forms; then up to 2 contexts, [the form]"]
    once = []
    for c, k in zip(cands, nsnip, strict=True):
        if c["count"] < 2:
            once.append(c["name"])
            continue
        head = f"{c['name']} ({c['count']})"
        if c.get("kind_hint"):
            head += f" [{c['kind_hint']}]"
        others = [f for f in c["forms"] if f != c["name"]]
        if others:
            head += " = " + " / ".join(others)
        lines.append(head)
        lines.extend("  " + _trim(s, side) for s in c["snippets"][:k])
    if once:
        lines.append("# seen once (contexts on request): " + "; ".join(once))
    return "\n".join(lines) + "\n"


def render(cands: list[dict[str, Any]], budget: int | None) -> dict[str, Any]:
    """The candidate list as text. Names seen once are listed without context; over
    ``budget`` tokens, the most frequent names keep one context, then contexts
    get shorter."""
    nsnip = [len(c["snippets"]) for c in cands]
    side = SNIPPET_SIDE
    text = _render_lines(cands, nsnip, side)
    trimmed = 0
    if budget is not None:
        chars = len(text)
        for i, c in enumerate(cands):  # most frequent first
            if math.ceil(chars / 4) <= budget:
                break
            if nsnip[i] == 2 and c["count"] >= 2:
                nsnip[i] = 1
                trimmed += 1
                chars -= len(_trim(c["snippets"][1], side)) + 3
        text = _render_lines(cands, nsnip, side)
        while estimate_tokens(text) > budget and side > 3:
            side -= 1
            text = _render_lines(cands, nsnip, side)
    return {
        "text": text,
        "tokens": estimate_tokens(text),
        "budget": budget,
        "one_context": trimmed,
        "side_words": side,
    }


# --- workspace entry point ---------------------------------------------------------


def run(ws_root: Path, version: str | None = None, budget: int | None = None) -> dict[str, Any]:
    """Run the pre-pass on a workspace draft; returns the prepass document (not written)."""
    t0 = time.perf_counter()
    version = version or structure.latest_version(ws_root)
    text_file = ws_root / "text" / f"{version}.txt"
    struct_file = ws_root / "index" / version / "structure.json"
    if not text_file.is_file():
        raise FileNotFoundError(f"no draft {version}; run `lc ingest` first")
    if not struct_file.is_file():
        raise FileNotFoundError(f"no structure for {version}; run `lc anchor` first")
    text = text_file.read_text(encoding="utf-8")
    paras = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")
    data = json.loads(struct_file.read_text(encoding="utf-8"))
    anchors = [a for a, _ in data["paragraphs"]]
    if len(anchors) != len(paras):
        raise ValueError(f"structure for {version} is out of date; run `lc anchor`")
    lang = "en"
    manifest = ws_root / "work.toml"
    if manifest.is_file():
        lang = str(tomllib.loads(manifest.read_text(encoding="utf-8")).get("language", "en"))
    meta_file = ws_root / "text" / f"{version}.meta.json"
    words = None
    if meta_file.is_file():
        words = json.loads(meta_file.read_text(encoding="utf-8")).get("words")
    out = extract(paras, anchors, _scene_list(data["chapters"], len(paras)), lang)
    text_tokens = estimate_tokens(text)
    if budget is None:
        budget = int(text_tokens * DEFAULT_SHARE)
    out["render"] = render(out["candidates"], budget)
    out["stats"] = {
        "version": version,
        "language": lexicon(lang).lang,
        "paragraphs": len(paras),
        "words": words or sum(s["words"] for s in out["scenes"].values()),
        "text_tokens": text_tokens,
        "candidates": len(out["candidates"]),
        "speaker_tags": sum(len(v) for v in out["speakers"].values()),
        "render_tokens": out["render"]["tokens"],
        "render_share": round(out["render"]["tokens"] / max(text_tokens, 1), 4),
        "seconds": round(time.perf_counter() - t0, 3),
    }
    return {"schema_version": 1, **out}


def write(ws_root: Path, doc: dict[str, Any]) -> Path:
    path = ws_root / "index" / "work" / "prepass.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


# --- scoring against a gold list ---------------------------------------------------


@cache
def _strip_words() -> frozenset[str]:
    out = {"the", "of"}
    for lang in ("en", "es"):
        lex = lexicon(lang)
        out |= {h.casefold() for h in lex.honorifics | lex.honorifics_lower}
        out |= set(lex.articles) | set(lex.role_articles) | _lower_connectors(lex)
    return frozenset(out)


def _norm(s: str) -> tuple[str, ...]:
    ws = tuple(w.casefold() for w in TOKEN.findall(s))
    kept = tuple(w for w in ws if w not in _strip_words())
    return kept or ws


def _inside(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    n = len(a)
    return any(b[i : i + n] == a for i in range(len(b) - n + 1))


def score(cands: list[dict[str, Any]], gold: dict[str, Any]) -> dict[str, Any]:
    """Recall of gold entities (some candidate form equals one of its aliases, after
    dropping honorifics and articles) and precision of candidates; a candidate that
    matches only a ``minor`` gold entry is neutral."""
    entities = [(e, {_norm(a) for a in [e["name"], *e["aliases"]]}) for e in gold["entities"]]
    minor = [_norm(m["name"]) for m in gold.get("minor", [])]
    reached: set[str] = set()
    tp = neutral = 0
    for c in cands:
        forms = {_norm(f) for f in [c["name"], *c.get("forms", [])]}
        hits = [e["name"] for e, al in entities if forms & al]
        if hits:
            tp += 1
            reached.update(hits)
        elif any(f == m or _inside(f, m) for f in forms for m in minor):
            neutral += 1
    n = len(cands)
    missed = [e["name"] for e, _ in entities if e["name"] not in reached]
    return {
        "entities": len(entities),
        "reached": len(entities) - len(missed),
        "recall": (len(entities) - len(missed)) / len(entities) if entities else 1.0,
        "missed": missed,
        "candidates": n,
        "true": tp,
        "neutral": neutral,
        "precision_strict": tp / n if n else 0.0,
        "precision_lenient": (tp + neutral) / n if n else 0.0,
    }
