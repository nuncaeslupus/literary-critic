"""Bounded LLM packets for the literary index: plan, render, import.

The LLM never reads the novel through ad hoc calls. ``plan`` splits the work
into packets of bounded size and writes ``<ws>/index/work/plan.json``:

- **entities** packets: the pre-pass candidate list (most frequent names first),
  cut into self-contained packets of at most ``ENTITY_CAP`` tokens;
- **scenes** packets: consecutive scenes up to ``SCENE_TEXT_CAP`` tokens of text,
  never splitting a scene; a scene over the cap gets a packet of its own, and one
  over ``SPLIT_AT`` is cut at paragraph boundaries into parts.

``render`` prints one packet: short instructions, the closed JSON answer schema
(``schemas/index-<kind>-answer.schema.json``) and the inputs, nothing else.
``import_answer`` validates an answer, anchors every quote exactly (a quote
missing or ambiguous in its scene refuses the answer, naming the field) and
writes all of the packet's items in one Codex batch, all or nothing. Raw answers
are kept under ``index/work/answers/`` for audit.

Tokens are estimated as characters / 4, like the pre-pass.
"""

from __future__ import annotations

import bisect
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from litcritic import prepass, query, structure, validate, view
from litcritic import spans as spanlib
from litcritic.codex import Codex, CodexError, Item, _write_atomic

PLAN_SCHEMA = 1
ENTITY_CAP = 6000  # tokens per rendered entity packet
SCENE_TEXT_CAP = 8000  # tokens of scene text per scene packet
SPLIT_AT = 11000  # a scene above this many tokens is cut at paragraph boundaries
PACKET_MAX = 12000  # no rendered packet exceeds this
KNOWN_CAP = 300  # tokens for the names an entity packet shares with the others
KNOWN_LINES_CAP = 1500  # tokens for the known entities listed under the scenes of a packet
SETUP_LINES_CAP = 300  # tokens for the open setups listed in a scene packet
SCENES_PER_PACKET = 40  # the answer schema allows 60
FACT_NAMES = 12  # names and speakers listed per scene
STATUSES = ("todo", "done", "failed")
KIND_SCHEMA = {"entities": "index-entities-answer", "scenes": "index-scenes-answer"}
# Model tier per packet kind, named, never a model id (spec, open question 1): cheap
# (Haiku-class), standard (Sonnet-class), strong (the session's best). Entity resolution
# needs the strong tier: a cheap model agreed only 0.73 recall / 0.69 precision with a
# strong one on a real manuscript (D-4). Scene packets need the standard tier: against a
# strong reference on a real manuscript the cheap tier left pov out in first-person
# scenes (5/18 right) and missed half the setups; the standard tier agreed on >= 17/18
# scenes per field once told to always give pov.
TIERS = ("cheap", "standard", "strong")
TIER = {"entities": "strong", "scenes": "standard"}

INSTRUCTIONS = {
    "entities": (
        "Task: decide which candidates are characters, places, objects, groups or motifs "
        "of the novel; put the rest in rejects. One entry per entity: name = its fullest "
        "usual name; aliases = its other names and nicknames below; titles = role phrases "
        'the text uses as a name for it ("the doctor"), apart from aliases. A generic role '
        "phrase (the doctor, the man, the girl) is a reject unless the text consistently "
        "uses it for one character. One person under two names the text keeps apart (a "
        "double identity) is two entities: give the second same_as = the first's name. "
        "If a candidate is another form of a name under Other names, give that exact name "
        "with your forms as aliases. quote (optional) = exact words of the text naming it, "
        "for a name that is not a candidate."
    ),
    "scenes": (
        "Task: one entry per scene below; facts only, never prose for the novel. "
        "pov: always; whose eyes the scene is told through; first person: "
        '"narrator (first person)", plus the name if the text gives it. '
        "location: where the scene happens, not where someone comes from. "
        'time: as precise as the text allows, else "unspecified". '
        "summary: what happens and what changes, who does what to whom (check who is who "
        "against known and speakers), no interpretation. "
        "setups: only details planted for a later scene, never one resolved in the same "
        "scene, never a theme. side payoff only in the scene that resolves a setup, "
        "pays_off = that setup's label or id (Open setups lists earlier ones). "
        "entities: only people, places or things missing from known. Every quote: exact "
        "words copied from that scene, enough to occur only once in it."
    ),
}


class PacketError(Exception):
    """The packet engine cannot do what was asked."""


class Refused(Exception):
    """An answer is refused; ``path`` names the field."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path, self.reason = path, reason


tokens = prepass.estimate_tokens


def work_dir(ws_root: Path) -> Path:
    return ws_root / "index" / "work"


def plan_path(ws_root: Path) -> Path:
    return work_dir(ws_root) / "plan.json"


# --- the draft -------------------------------------------------------------------


@dataclass
class Draft:
    version: str
    paragraphs: list[str]
    anchors: list[str]
    scenes: list[dict[str, Any]]  # {id, start, end, words}
    pre: dict[str, Any]  # the pre-pass document

    def text(self) -> spanlib.Text:
        return spanlib.Text(self.paragraphs, self.anchors, self.version)


def load_draft(ws_root: Path, version: str | None = None, fresh: bool = False) -> Draft:
    """A draft with its scenes and pre-pass (run and written when ``fresh`` or missing)."""
    version = version or structure.latest_version(ws_root)
    ix = query.load(ws_root, version, codex=False)
    pre_file = work_dir(ws_root) / "prepass.json"
    pre: dict[str, Any] | None = None
    if not fresh and pre_file.is_file():
        pre = json.loads(pre_file.read_text(encoding="utf-8"))
        if pre.get("stats", {}).get("version") != version:
            pre = None
    if pre is None:
        pre = prepass.run(ws_root, version)
        prepass.write(ws_root, pre)
    scenes = prepass._scene_list(ix.chapters, len(ix.paragraphs))
    return Draft(version, ix.paragraphs, ix.anchors, scenes, pre)


# --- planning --------------------------------------------------------------------


def _render_params(pre: dict[str, Any]) -> tuple[list[int], int]:
    """Contexts per candidate and words per side, as the pre-pass budget left them."""
    cands = pre["candidates"]
    r = pre.get("render", {})
    nsnip = [len(c["snippets"]) for c in cands]
    left = int(r.get("one_context", 0))
    for i, c in enumerate(cands):
        if left <= 0:
            break
        if nsnip[i] == 2 and c["count"] >= 2:
            nsnip[i] = 1
            left -= 1
    return nsnip, int(r.get("side_words", prepass.SNIPPET_SIDE))


def _candidate_cost(c: dict[str, Any], k: int, side: int) -> int:
    """Characters a candidate adds to the rendered list."""
    if c["count"] < 2:
        return len(c["name"]) + 2
    return len(prepass._render_lines([c], [k], side)) - len(prepass._render_lines([], [], side))


def entity_groups(pre: dict[str, Any], cap: int = ENTITY_CAP) -> list[tuple[int, int]]:
    """Ranges of the (frequency-sorted) candidates, one per entity packet, each
    rendering to at most ``cap`` tokens; sizes are balanced, frequent names first."""
    cands = pre["candidates"]
    if not cands:
        return []
    nsnip, side = _render_params(pre)
    costs = [_candidate_cost(c, k, side) for c, k in zip(cands, nsnip, strict=True)]
    fixed = len(_entity_frame("e00", 9, 9, "v000", "")) + len(prepass._render_lines([], [], side))
    known = KNOWN_CAP * 4 + 20
    room = cap * 4 - fixed
    total = sum(costs)
    if total <= room:
        return [(0, len(cands))]
    room -= known  # several packets: each lists the names of the others
    cum = [0]
    for c in costs:
        cum.append(cum[-1] + c)
    n = max(2, math.ceil(total / room))
    while n < len(cands):
        cuts = [0]
        for k in range(1, n):
            at = bisect.bisect_left(cum, total * k / n, lo=cuts[-1] + 1, hi=len(cands))
            if at > cuts[-1] + 1 and abs(cum[at - 1] - total * k / n) <= abs(
                cum[at] - total * k / n
            ):
                at -= 1
            cuts.append(at)
        cuts.append(len(cands))
        groups = [(cuts[k], cuts[k + 1]) for k in range(n) if cuts[k + 1] > cuts[k]]
        if all(cum[b] - cum[a] <= room for a, b in groups):
            return groups
        n += 1
    return [(i, i + 1) for i in range(len(cands))]


def scene_units(draft: Draft, only: set[str] | None = None) -> list[dict[str, Any]]:
    """Scenes as packet units ``{scene, paras: [lo, hi], tokens, words[, part: [k, n]]}``;
    a scene over ``SPLIT_AT`` tokens becomes parts cut at paragraph boundaries."""
    out: list[dict[str, Any]] = []
    paras = draft.paragraphs
    for sc in draft.scenes:
        if only is not None and sc["id"] not in only:
            continue
        lo, hi = sc["start"], min(sc["end"], len(paras) - 1)
        if hi < lo:
            continue
        size = [len(paras[i]) + 1 for i in range(lo, hi + 1)]
        words = draft.pre["scenes"].get(sc["id"], {}).get("words", 0)
        toks = tokens("\n".join(paras[lo : hi + 1]))
        if toks <= SPLIT_AT or hi == lo:
            out.append({"scene": sc["id"], "paras": [lo, hi], "tokens": toks, "words": words})
            continue
        n = math.ceil(toks / SCENE_TEXT_CAP)
        total = sum(size)
        cuts = [lo]
        acc = 0
        for i in range(lo, hi + 1):
            acc += size[i - lo]
            if len(cuts) < n and acc >= total * len(cuts) / n and i < hi:
                cuts.append(i + 1)
        bounds = [*cuts, hi + 1]
        parts = [(bounds[k], bounds[k + 1] - 1) for k in range(len(cuts))]
        for k, (a, b) in enumerate(parts, 1):
            out.append(
                {
                    "scene": sc["id"],
                    "paras": [a, b],
                    "tokens": tokens("\n".join(paras[a : b + 1])),
                    "words": sum(len(p.split()) for p in paras[a : b + 1]),
                    "part": [k, len(parts)],
                }
            )
    return out


def scene_groups(units: list[dict[str, Any]], cap: int = SCENE_TEXT_CAP) -> list[list[int]]:
    """Consecutive units grouped up to ``cap`` text tokens; a part or an oversized
    scene stands alone."""
    groups: list[list[int]] = []
    acc = 0
    for i, u in enumerate(units):
        cur = groups[-1] if groups else None
        alone = "part" in u or (cur is not None and "part" in units[cur[0]])
        if cur is None or alone or acc + u["tokens"] > cap or len(cur) >= SCENES_PER_PACKET:
            groups.append([i])
            acc = u["tokens"]
        else:
            cur.append(i)
            acc += u["tokens"]
    return groups


def changed_scenes(ws_root: Path, draft: Draft) -> set[str]:
    """Scenes holding the spans of items the last ``lc codex sync`` asks to re-read."""
    cx = Codex(ws_root)
    queue = cx.root / "reread.jsonl"
    if not queue.is_file():
        raise PacketError("no sync data: run `lc codex sync` after ingesting the new draft")
    ids = [json.loads(line)["item"] for line in queue.read_text("utf-8").splitlines() if line]
    pos = {a: i for i, a in enumerate(draft.anchors)}
    scene_of: dict[int, str] = {}
    for sc in draft.scenes:
        for i in range(sc["start"], sc["end"] + 1):
            scene_of[i] = sc["id"]
    out: set[str] = set()
    for item_id in ids:
        item = cx.items.get(item_id)
        if item is None:
            continue
        for s in item.spans:
            if s.draft != draft.version:
                continue
            i0, i1 = pos.get(s.start.para), pos.get(s.end.para)
            if i0 is None or i1 is None:
                continue
            out.update(scene_of[i] for i in range(i0, i1 + 1) if i in scene_of)
    return out


def plan(ws_root: Path, changed: bool = False, version: str | None = None) -> dict[str, Any]:
    """Run the pre-pass, split the work into packets and write ``plan.json``."""
    draft = load_draft(ws_root, version, fresh=True)
    try:
        cx = Codex(ws_root)
    except CodexError:
        if changed:
            raise PacketError("no Codex yet: run `lc index plan` without --changed") from None
        cx = Codex.init(ws_root, draft.version)
    if cx.draft != draft.version:
        raise PacketError(
            f"the Codex is synced to {cx.draft}, the latest draft is {draft.version}; "
            "run `lc codex sync` first"
        )
    packets: list[dict[str, Any]] = []
    only = changed_scenes(ws_root, draft) if changed else None
    if not changed:
        for k, (a, b) in enumerate(entity_groups(draft.pre), 1):
            packets.append(
                {
                    "id": f"e{k}",
                    "kind": "entities",
                    "tier": TIER["entities"],
                    "inputs": {"candidates": [a, b]},
                }
            )
    units = scene_units(draft, only)
    groups = scene_groups(units)
    width = max(3, len(str(len(groups))))
    for k, g in enumerate(groups, 1):
        packets.append(
            {
                "id": f"s{k:0{width}d}",
                "kind": "scenes",
                "tier": TIER["scenes"],
                "inputs": {"units": [units[i] for i in g]},
            }
        )
    old: dict[str, dict[str, Any]] = {}
    path = plan_path(ws_root)
    if path.is_file():
        prev = json.loads(path.read_text(encoding="utf-8"))
        if prev.get("draft") == draft.version:
            old = {p["id"]: p for p in prev.get("packets", [])}
    doc: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "draft": draft.version,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "changed_only": changed,
        "packets": packets,
    }
    for p in packets:
        p["status"] = "todo"
        was = old.get(p["id"])
        if was and was.get("kind") == p["kind"] and was.get("inputs") == p["inputs"]:
            for key in ("status", "items", "error"):
                if key in was:
                    p[key] = was[key]
        p["tokens"] = tokens(render(ws_root, doc, p["id"], draft, cx))
    doc["stats"] = plan_stats(doc, len(draft.scenes) if not changed else len(only or ()))
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return doc


def plan_stats(doc: dict[str, Any], scenes: int) -> dict[str, Any]:
    ps = doc["packets"]
    calls = 2 * len(ps)  # one `lc index packet` and one `lc index import` per packet
    chained = len(ps) + 1 if ps else 0  # sequential: `lc index import --next` prints the next
    return {
        "scenes": scenes,
        "entity_packets": sum(p["kind"] == "entities" for p in ps),
        "scene_packets": sum(p["kind"] == "scenes" for p in ps),
        "max_packet_tokens": max((p["tokens"] for p in ps), default=0),
        "total_packet_tokens": sum(p["tokens"] for p in ps),
        "tool_calls": calls,
        "tool_calls_per_scene": round(calls / scenes, 3) if scenes else 0.0,
        "tool_calls_chained": chained,
        "tool_calls_per_scene_chained": round(chained / scenes, 3) if scenes else 0.0,
    }


def load_plan(ws_root: Path) -> dict[str, Any]:
    path = plan_path(ws_root)
    if not path.is_file():
        raise PacketError("no plan yet: run `lc index plan`")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc


def _packet(doc: dict[str, Any], packet_id: str) -> dict[str, Any]:
    for p in doc["packets"]:
        if p["id"] == packet_id:
            out: dict[str, Any] = p
            return out
    raise PacketError(f"no packet {packet_id!r} in the plan (see `lc index status`)")


# --- rendering -------------------------------------------------------------------


def _schema_text(kind: str) -> str:
    schema = validate.load_schema(KIND_SCHEMA[kind])
    slim = {k: v for k, v in schema.items() if k not in ("$schema", "title")}
    return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))


def _frame(head: str, kind: str) -> str:
    return (
        f"{head}\n{INSTRUCTIONS[kind]}\n"
        f"Answer with JSON only, valid against this schema:\n{_schema_text(kind)}\n"
    )


def _entity_frame(pid: str, k: int, n: int, version: str, known: str) -> str:
    out = _frame(
        f"packet {pid} · entities {k}/{n} · tier {TIER['entities']} · draft {version}", "entities"
    )
    if known:
        out += f"Other names: {known}\n"
    return out + "Candidates:\n"


def _cap_join(names: list[str], cap_tokens: int) -> str:
    out: list[str] = []
    used = 0
    for name in names:
        cost = len(name) + 2
        if used + cost > cap_tokens * 4:
            break
        out.append(name)
        used += cost
    return "; ".join(out)


def _codex_entities(cx: Codex | None) -> list[Item]:
    return cx.live("entity") if cx is not None else []


def render(
    ws_root: Path,
    doc: dict[str, Any],
    packet_id: str,
    draft: Draft | None = None,
    cx: Codex | None = None,
) -> str:
    """The text of one packet: instructions, the answer schema, the inputs."""
    p = _packet(doc, packet_id)
    draft = draft or load_draft(ws_root, doc["draft"])
    if cx is None:
        try:
            cx = Codex(ws_root)
        except CodexError:
            cx = None
    if p["kind"] == "entities":
        return _render_entities(doc, p, draft, cx)
    return _render_scenes(p, draft, cx)


def _render_entities(doc: dict[str, Any], p: dict[str, Any], draft: Draft, cx: Codex | None) -> str:
    cands = draft.pre["candidates"]
    nsnip, side = _render_params(draft.pre)
    a, b = p["inputs"]["candidates"]
    ent = [x for x in doc["packets"] if x["kind"] == "entities"]
    k = next(i for i, x in enumerate(ent, 1) if x["id"] == p["id"])
    names = [i.fields.get("name", "") for i in _codex_entities(cx)]
    if len(ent) > 1:
        names += [
            c["name"]
            for x in ent
            if x is not p
            for c in cands[x["inputs"]["candidates"][0] : x["inputs"]["candidates"][1]]
            if c["count"] >= 2
        ]
    uniq: dict[str, str] = {}
    for name in names:
        if name:
            uniq.setdefault(name.casefold(), name)
    known = _cap_join(list(uniq.values()), KNOWN_CAP)
    head = _entity_frame(p["id"], k, len(ent), draft.version, known)
    body = prepass._render_lines(cands[a:b], nsnip[a:b], side)
    return head + body


def _known(units: list[dict[str, Any]], draft: Draft, cx: Codex | None) -> list[list[str]]:
    """Per unit, the Codex entities the reference index finds in it, most mentioned
    first: ``Name [id]``, plus the other forms (aliases, titles) the unit uses."""
    ents = _codex_entities(cx)
    out: list[list[str]] = [[] for _ in units]
    if not ents:
        return out
    paras: list[str] = []
    owner: list[str] = []
    for k, u in enumerate(units):
        lo, hi = u["paras"]
        paras += draft.paragraphs[lo : hi + 1]
        owner += [str(k)] * (hi - lo + 1)
    by_id = {e.id: e for e in ents}
    count: list[Counter[str]] = [Counter() for _ in units]
    forms: list[dict[str, dict[str, str]]] = [{} for _ in units]
    for eid, _, _, form, scene, _ in view.mention_rows(paras, owner, ents):
        k = int(scene)
        count[k][eid] += 1
        name = by_id[eid].fields.get("name", "")
        if form.casefold() != name.casefold():
            forms[k].setdefault(eid, {}).setdefault(form.casefold(), form)
    for k in range(len(units)):
        for eid, _ in count[k].most_common():
            line = f"{by_id[eid].fields.get('name', '')} [{eid}]"
            seen = list(forms[k].get(eid, {}).values())
            if seen:
                line += f" ({' / '.join(seen[:4])})"
            out[k].append(line)
    return out


def _scene_facts(unit: dict[str, Any], draft: Draft, known: list[str]) -> list[str]:
    pre_sc = draft.pre["scenes"].get(unit["scene"], {})
    lines = []
    if known:
        lines.append("known: " + "; ".join(known))
    told = {w.casefold() for w in prepass.TOKEN.findall(" ".join(known))}
    names = [
        n
        for n in pre_sc.get("names", [])
        if not all(w.casefold() in told for w in prepass.TOKEN.findall(n))
    ][:FACT_NAMES]
    if names:
        lines.append("other names: " + ", ".join(names))
    lo, hi = unit["paras"]
    span = set(draft.anchors[lo : hi + 1])
    who = Counter(
        s["who"] for s in draft.pre["speakers"].get(unit["scene"], []) if s["para"] in span
    )
    if who:
        lines.append("speakers: " + ", ".join(f"{w} {n}" for w, n in who.most_common(FACT_NAMES)))
    return lines


def _open_setups(units: list[dict[str, Any]], draft: Draft, cx: Codex | None) -> str:
    """Setups placed before the packet and not paid off yet, nearest first."""
    if cx is None:
        return ""
    paid = {
        x["to"]
        for it in cx.live("setup")
        for x in it.links
        if x["rel"] == "pays_off" and it.fields.get("side") == "payoff"
    }
    pos = {a: i for i, a in enumerate(draft.anchors)}
    lo = units[0]["paras"][0]
    found: list[tuple[int, str]] = []
    for it in cx.live("setup"):
        if it.fields.get("side") != "setup" or it.id in paid or not it.spans:
            continue
        at = pos.get(it.spans[0].start.para)
        if at is not None and at < lo:
            found.append((at, f"{it.fields.get('label', '')} [{it.id}]"))
    found.sort(reverse=True)
    return _cap_join([x for _, x in found], SETUP_LINES_CAP)


def _render_scenes(p: dict[str, Any], draft: Draft, cx: Codex | None) -> str:
    units = p["inputs"]["units"]
    first, last = units[0]["scene"], units[-1]["scene"]
    span = first if first == last else f"{first}..{last}"
    head = _frame(
        f"packet {p['id']} · scenes {span} · tier {TIER['scenes']} · draft {draft.version}",
        "scenes",
    )
    opened = _open_setups(units, draft, cx)
    if opened:
        head += f"Open setups: {opened}\n"
    known = _known(units, draft, cx)
    bodies = ["\n".join(draft.paragraphs[u["paras"][0] : u["paras"][1] + 1]) for u in units]
    room = min(KNOWN_LINES_CAP * 4, PACKET_MAX * 4 - len(head) - sum(map(len, bodies)) - 2000)
    k = max((len(x) for x in known), default=0)
    while k > 0 and sum(len("; ".join(x[:k])) + 9 for x in known if x) > room:
        k -= 1
    blocks = []
    for u, body, kn in zip(units, bodies, known, strict=True):
        title = f"## {u['scene']}"
        if "part" in u:
            title += f" part {u['part'][0]}/{u['part'][1]} (answer for this part only)"
        title += f" ({u['words']} words)"
        blocks.append("\n".join([title, *_scene_facts(u, draft, kn[:k]), body]))
    return head + "\n".join(blocks) + "\n"


# --- importing -------------------------------------------------------------------


def _hits(text: spanlib.Text, quote: str, lo: int, hi: int) -> list[int]:
    """Global offsets of every occurrence of ``quote`` in paragraphs lo..hi."""
    g0 = text.starts[lo]
    g1 = text.starts[hi] + len(text.paragraphs[hi])
    hits = []
    g = text.joined.find(quote, g0, g1)
    while g != -1 and g + len(quote) <= g1:
        hits.append(g)
        g = text.joined.find(quote, g + 1, g1)
    return hits


def _span_at(text: spanlib.Text, g: int, length: int) -> spanlib.Span:
    a, b = text.local(g), text.local(g + length)
    return spanlib.make(text, text.draft, a.para, a.off, b.para, b.off)


def _anchor(
    text: spanlib.Text, quote: str, lo: int, hi: int, path: str, scope: str
) -> spanlib.Span:
    hits = _hits(text, quote, lo, hi)
    if not hits:
        raise Refused(path, f"not found in {scope} (copy the words exactly)")
    if len(hits) > 1:
        raise Refused(path, f"found {len(hits)} times in {scope}; quote more words")
    return _span_at(text, hits[0], len(quote))


def _forms(cx: Codex) -> dict[str, str]:
    """Casefolded name and aliases of every live entity -> its id (titles never
    identify an entity: they are role phrases)."""
    out: dict[str, str] = {}
    for item in cx.live("entity"):
        for f in [item.fields.get("name", ""), *item.fields.get("aliases", [])]:
            if f:
                out.setdefault(f.casefold(), item.id)
    return out


@dataclass
class EntityImport:
    items: list[Item]
    fallbacks: int  # quotes anchored by a fallback (ambiguous or not found)
    unlinked: int  # same_as names matching no entity yet


def _entity_items(ans: dict[str, Any], cx: Codex, draft: Draft, text: spanlib.Text) -> EntityImport:
    known = _forms(cx)
    by_form: dict[str, dict[str, Any]] = {}
    pos = {a: i for i, a in enumerate(draft.anchors)}
    for c in draft.pre["candidates"]:
        for f in [c["name"], *c["forms"]]:
            have = by_form.get(f.casefold())
            if have is None or pos.get(c["first"]["para"], 0) < pos.get(have["first"]["para"], 0):
                by_form[f.casefold()] = c
    owner: dict[str, int] = {}
    items: dict[str, Item] = {}
    taken: set[str] = set()
    fallbacks = 0
    same: list[tuple[str, str, str]] = []  # item id, target name, path
    for i, e in enumerate(ans["entities"]):
        path = f"$.entities[{i}]"
        forms = [e["name"], *e.get("aliases", [])]
        for j, f in enumerate(forms):
            where = f"{path}.name" if j == 0 else f"{path}.aliases[{j - 1}]"
            other = owner.get(f.casefold())
            if other is not None and other != i:
                raise Refused(where, f"{f!r} is already in $.entities[{other}]")
            owner[f.casefold()] = i
        low = {f.casefold() for f in forms}
        titles = [t for t in dict.fromkeys(e.get("titles", [])) if t.casefold() not in low]
        hits = sorted({known[f.casefold()] for f in forms if f.casefold() in known})
        if len(hits) > 1:
            raise Refused(path, f"matches {len(hits)} known entities ({', '.join(hits)})")
        if hits:
            base = items.get(hits[0]) or Item.from_json(cx.get(hits[0]).as_json())
            current = [base.fields.get("name", ""), *base.fields.get("aliases", [])]
            owned = {h.casefold() for h in current}
            new = [f for f in forms if f.casefold() not in owned]
            old_titles = base.fields.get("titles", [])
            owned |= {t.casefold() for t in old_titles} | {f.casefold() for f in new}
            more = [t for t in titles if t.casefold() not in owned]
            if new:
                base.fields["aliases"] = [*base.fields.get("aliases", []), *new]
            if more:
                base.fields["titles"] = [*old_titles, *more]
            if new or more:
                items[base.id] = base
            for f in new:
                known[f.casefold()] = base.id
            item_id = base.id
        else:
            span, fell = _entity_span(e, forms, titles, by_form, text, path)
            fallbacks += fell
            fields: dict[str, Any] = {"kind": e["kind"], "name": e["name"]}
            if e.get("aliases"):
                fields["aliases"] = list(e["aliases"])
            if titles:
                fields["titles"] = titles
            item_id = cx.new_id("entity", taken)
            taken.add(item_id)
            items[item_id] = Item(
                id=item_id,
                type="entity",
                text=f"{e['name']} ({e['kind']})",
                spans=[span],
                fields=fields,
            )
            for f in forms:
                known[f.casefold()] = item_id
        if e.get("same_as"):
            same.append((item_id, e["same_as"], f"{path}.same_as"))
    unlinked = 0
    for item_id, target, where in same:
        to = known.get(target.casefold())
        if to is None:
            unlinked += 1
            continue
        if to == item_id:
            raise Refused(where, "names this entity itself; same_as joins two entities")
        it = items.get(item_id) or Item.from_json(cx.get(item_id).as_json())
        if not any(x["rel"] == "same_as" and x["to"] == to for x in it.links):
            it.links.append({"rel": "same_as", "to": to})
            items[item_id] = it
    return EntityImport(list(items.values()), fallbacks, unlinked)


def _entity_span(
    e: dict[str, Any],
    forms: list[str],
    titles: list[str],
    by_form: dict[str, dict[str, Any]],
    text: spanlib.Text,
    path: str,
) -> tuple[spanlib.Span, int]:
    """Where a new entity is anchored, and 1 when a fallback placed it.

    A quote found once anchors there. An entity's quote often names it in a few words
    that recur, so an ambiguous quote anchors on its first occurrence inside the
    candidate's first paragraph, else on its first occurrence in the draft; a quote not
    found falls back to the candidate's first occurrence. Scene quotes stay strict.
    """
    last = len(text.paragraphs) - 1
    pos = text.index
    cands = [by_form[f.casefold()] for f in forms if f.casefold() in by_form]
    cands = cands or [by_form[t.casefold()] for t in titles if t.casefold() in by_form]
    c = min(cands, key=lambda c: pos.get(c["first"]["para"], last + 1)) if cands else None
    quote = e.get("quote")
    if quote:
        hits = _hits(text, quote, 0, last)
        if len(hits) == 1:
            return _span_at(text, hits[0], len(quote)), 0
        if hits:
            g = hits[0]
            i = pos.get(c["first"]["para"]) if c else None
            if i is not None:
                g0, g1 = text.starts[i], text.starts[i] + len(text.paragraphs[i])
                g = next((h for h in hits if g0 <= h < g1), g)
            return _span_at(text, g, len(quote)), 1
        if c is None:
            raise Refused(f"{path}.quote", "not found in the draft (copy the words exactly)")
        return _candidate_span(c, text, path), 1
    if c is None:
        raise Refused(f"{path}.name", "not a candidate name; add a quote naming it")
    return _candidate_span(c, text, path), 0


def _candidate_span(c: dict[str, Any], text: spanlib.Text, path: str) -> spanlib.Span:
    """The candidate's first occurrence, narrowed to its longest form."""
    i = text.index.get(c["first"]["para"])
    if i is None:
        raise Refused(f"{path}.name", "the pre-pass is out of date; run `lc index plan`")
    par, q = text.paragraphs[i], c["first"]["quote"]
    at = par.find(q)
    if at < 0:
        raise Refused(f"{path}.name", "the pre-pass is out of date; run `lc index plan`")
    for f in sorted(c["forms"], key=len, reverse=True):
        k = q.find(f)
        if k >= 0:
            return spanlib.make(
                text, text.draft, text.anchors[i], at + k, text.anchors[i], at + k + len(f)
            )
    return spanlib.make(text, text.draft, text.anchors[i], at, text.anchors[i], at + len(q))


@dataclass
class SceneImport:
    items: list[Item]
    unlinked: int  # payoffs matching no setup label or id yet
    same_scene: int  # payoffs linked to a setup planted in the same scene


def _scene_items(
    ans: dict[str, Any], p: dict[str, Any], cx: Codex, draft: Draft, text: spanlib.Text
) -> SceneImport:
    units = {u["scene"]: u for u in p["inputs"]["units"]}
    seen: dict[str, int] = {}
    for i, s in enumerate(ans["scenes"]):
        if s["scene"] not in units:
            raise Refused(f"$.scenes[{i}].scene", f"{s['scene']!r} is not in this packet")
        if s["scene"] in seen:
            raise Refused(
                f"$.scenes[{i}].scene", f"{s['scene']!r} also in $.scenes[{seen[s['scene']]}]"
            )
        seen[s["scene"]] = i
    missing = [u for u in units if u not in seen]
    if missing:
        raise Refused("$.scenes", f"missing {', '.join(missing)}")
    known = _forms(cx)
    existing = cx.scenes_by_unit(draft.anchors)
    setups = {
        it.fields["label"].casefold(): it.id
        for it in cx.live("setup")
        if it.fields.get("side") == "setup"
    }
    setup_ids = {it.id for it in cx.live("setup") if it.fields.get("side") == "setup"}
    planted: dict[str, str] = {}  # setup id -> scene, for setups of this answer
    items: list[Item] = []
    taken: set[str] = set()
    unlinked = 0

    def new(type_name: str) -> str:
        item_id = cx.new_id(type_name, taken)
        taken.add(item_id)
        return item_id

    pending: list[tuple[Item, str, str]] = []  # payoff item, setup label or id, scene
    for i, s in enumerate(ans["scenes"]):
        u = units[s["scene"]]
        lo, hi = u["paras"]
        path = f"$.scenes[{i}]"
        scope = s["scene"] + (f" part {u['part'][0]}" if "part" in u else "")
        span = spanlib.make(
            text, draft.version, draft.anchors[lo], 0, draft.anchors[hi], len(draft.paragraphs[hi])
        )
        fields = {k: s[k] for k in ("summary", "pov", "location", "time") if k in s}
        label = s["scene"] + (f" (part {u['part'][0]}/{u['part'][1]})" if "part" in u else "")
        head = " ".join(s["summary"].split()[:12])
        line = f"{label}: {head}" + ("…" if len(s["summary"].split()) > 12 else "")
        old = existing.get(s["scene"]) if "part" not in u else None
        if old is not None and [(x.start.para, x.end.para) for x in old.spans] == [
            (span.start.para, span.end.para)
        ]:
            item = Item.from_json(old.as_json())
            item.text, item.fields, item.spans, item.status = line, fields, [span], "active"
        else:
            item = Item(id=new("scene"), type="scene", text=line, spans=[span], fields=fields)
        items.append(item)
        for j, e in enumerate(s.get("entities", [])):
            if e["name"].casefold() in known:
                continue
            espan = _anchor(text, e["quote"], lo, hi, f"{path}.entities[{j}].quote", scope)
            eid = new("entity")
            known[e["name"].casefold()] = eid
            items.append(
                Item(
                    id=eid,
                    type="entity",
                    text=f"{e['name']} ({e['kind']})",
                    spans=[espan],
                    fields={"kind": e["kind"], "name": e["name"]},
                )
            )
        for j, su in enumerate(s.get("setups", [])):
            spath = f"{path}.setups[{j}]"
            sspan = _anchor(text, su["quote"], lo, hi, f"{spath}.quote", scope)
            if "pays_off" in su and su["side"] != "payoff":
                raise Refused(f"{spath}.pays_off", "only a payoff pays something off")
            it = Item(
                id=new("setup"),
                type="setup",
                text=f"{su['side']}: {su['label']}",
                spans=[sspan],
                fields={"label": su["label"], "side": su["side"]},
            )
            items.append(it)
            if su["side"] == "setup":
                setups[su["label"].casefold()] = it.id
                planted[it.id] = s["scene"]
            else:  # linked by pays_off (a setup's label or id), else by its own label
                pending.append((it, su.get("pays_off", su["label"]), s["scene"]))
    same_scene = 0
    for it, target, scene in pending:
        to = setups.get(target.casefold()) or (target if target in setup_ids else None)
        if to is None:
            unlinked += 1
            continue
        it.links.append({"rel": "pays_off", "to": to})
        same_scene += planted.get(to) == scene
    return SceneImport(items, unlinked, same_scene)


def import_answer(ws_root: Path, packet_id: str, raw: str) -> str:
    """Validate and import one answer; returns the one-line result.

    ``ok <id>: N items`` on success; ``error <id>: <path>: <reason>`` when refused,
    in which case nothing is written to the Codex and the packet is marked failed.
    Environment problems (no plan, unknown packet) raise PacketError.
    """
    doc = load_plan(ws_root)
    p = _packet(doc, packet_id)
    if p["status"] == "done":
        return f"error {packet_id}: $: packet already imported"
    answers = work_dir(ws_root) / "answers"
    answers.mkdir(parents=True, exist_ok=True)
    (answers / f"{packet_id}.json").write_text(raw, encoding="utf-8")
    try:
        try:
            ans = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Refused("$", f"not valid JSON ({exc.msg}, line {exc.lineno})") from None
        kind = KIND_SCHEMA[p["kind"]]
        schema = validate.load_schema(kind)
        errs = validate.check(ans, schema, schema)
        if errs:
            path, _, reason = errs[0].partition(": ")
            more = f" (+{len(errs) - 1} more)" if len(errs) > 1 else ""
            raise Refused(path, reason + more)
        draft = load_draft(ws_root, doc["draft"])
        cx = Codex(ws_root)
        if cx.draft != doc["draft"]:
            raise PacketError(f"the Codex is synced to {cx.draft}, the plan to {doc['draft']}")
        text = draft.text()
        notes: list[str] = []
        if p["kind"] == "entities":
            got = _entity_items(ans, cx, draft, text)
            items = got.items
            if got.fallbacks:
                notes.append(f"{got.fallbacks} quote fallback{'s' * (got.fallbacks > 1)}")
            if got.unlinked:
                notes.append(f"{got.unlinked} same_as left unlinked: no entity with that name yet")
        else:
            got_s = _scene_items(ans, p, cx, draft, text)
            items = got_s.items
            if got_s.unlinked:
                notes.append(
                    f"{got_s.unlinked} payoff(s) left unlinked: no setup with that label yet"
                )
            if got_s.same_scene:
                notes.append(f"{got_s.same_scene} payoff(s) in the scene of their setup")
        try:
            cx.add_many(items, by="llm", batch=f"index:{doc['draft']}:{packet_id}")
        except CodexError as exc:
            raise Refused("$", str(exc)) from None
    except Refused as exc:
        p["status"], p["error"] = "failed", str(exc)
        _save_plan(ws_root, doc)
        return f"error {packet_id}: {exc}"
    p["status"], p["items"] = "done", len(items)
    if p["kind"] == "scenes":
        p["out_tokens"] = tokens(_compact(ans))
    p.pop("error", None)
    _save_plan(ws_root, doc)
    note = f" ({'; '.join(notes)})" if notes else ""
    return f"ok {packet_id}: {len(items)} items{note}"


def _compact(ans: Any) -> str:
    return json.dumps(ans, ensure_ascii=False, separators=(",", ":"))


def output_tokens_per_scene(ans: dict[str, Any]) -> float:
    """Estimated output tokens of a scene answer (compact JSON) per scene in it."""
    n = len(ans.get("scenes", [])) or 1
    return round(tokens(_compact(ans)) / n, 1)


def _save_plan(ws_root: Path, doc: dict[str, Any]) -> None:
    _write_atomic(plan_path(ws_root), json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


# --- status ----------------------------------------------------------------------


def status_lines(doc: dict[str, Any]) -> list[str]:
    out = []
    for p in doc["packets"]:
        if p["kind"] == "entities":
            a, b = p["inputs"]["candidates"]
            what = f"candidates {a + 1}-{b}"
        else:
            us = p["inputs"]["units"]
            what = us[0]["scene"] if len(us) == 1 else f"{us[0]['scene']}..{us[-1]['scene']}"
            if "part" in us[0]:
                what += f" part {us[0]['part'][0]}/{us[0]['part'][1]}"
        line = f"{p['id']} {p['kind']} {p['status']} ~{p['tokens']} tokens {what}"
        if p["status"] == "done":
            out_tok = ""
            if p.get("out_tokens"):
                per = round(p["out_tokens"] / len(p["inputs"]["units"]), 1)
                out_tok = f", ~{per} out tokens/scene"
            line += f" ({p.get('items', 0)} items{out_tok})"
        elif p["status"] == "failed":
            line += f": {p.get('error', '')}"
        out.append(line)
    n = Counter(p["status"] for p in doc["packets"])
    out.append(
        f"{len(doc['packets'])} packets, draft {doc['draft']}: "
        + ", ".join(f"{n[s]} {s}" for s in STATUSES)
    )
    return out
