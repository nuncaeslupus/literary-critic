"""Measuring the literary index: cost, agreement with a gold list, agreement between tiers.

- ``cost`` reads ``plan.json``: input tokens per packet (the rendered packet, characters
  / 4), output tokens recorded by ``lc index import``, calls (planned: one print and one
  import per packet, or one fewer per packet chaining ``import --next``; recorded: what
  was actually printed and imported), and wall time from the ``started``/``finished``
  timestamps the commands record.
- ``evaluate`` scores the Codex entities against a gold list (``tests/fixtures/gold``
  format): entity precision, recall and F1, alias-merge errors and reference recall.
- ``compare`` sets two answers to the same packet side by side (a cheaper tier against
  a stronger reference) and returns agreement numbers only: the D-4 check that keeps a
  step on a cheaper tier only where it agrees at least ``AGREEMENT`` with the strong one.

Entity forms are compared the way ``prepass.score`` compares them: casefolded words with
honorifics, articles and connectors dropped.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from litcritic import packets, prepass, view
from litcritic.codex import Codex

AGREEMENT = 0.9  # D-4: a cheaper tier stays only where it agrees this much
WORD = re.compile(r"\w+")


class EvalError(Exception):
    """The evaluation cannot run on what it was given."""


def _ratio(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


def _f1(p: float, r: float) -> float:
    return round(2 * p * r / (p + r), 4) if p + r else 0.0


# --- cost --------------------------------------------------------------------------


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _text_tokens(ws_root: Path, version: str) -> int:
    pre = packets.work_dir(ws_root) / "prepass.json"
    if pre.is_file():
        st = json.loads(pre.read_text(encoding="utf-8")).get("stats", {})
        if st.get("version") == version and "text_tokens" in st:
            return int(st["text_tokens"])
    text = ws_root / "text" / f"{version}.txt"
    return prepass.estimate_tokens(text.read_text(encoding="utf-8")) if text.is_file() else 0


def cost(ws_root: Path) -> dict[str, Any]:
    """Per packet and in total: tokens in and out, calls, wall time."""
    doc = packets.load_plan(ws_root)
    rows: list[dict[str, Any]] = []
    spans: list[tuple[datetime, datetime]] = []
    for p in doc["packets"]:
        units = {u["scene"] for u in p["inputs"].get("units", [])}
        row: dict[str, Any] = {
            "id": p["id"],
            "kind": p["kind"],
            "tier": p.get("tier", ""),
            "status": p["status"],
            "scenes": len(units),
            "in_tokens": p["tokens"],
            "out_tokens": p.get("out_tokens"),
            "calls": p.get("prints", 0) + p.get("imports", 0),
            "seconds": None,
        }
        a, b = _ts(p.get("started")), _ts(p.get("finished"))
        if a and b and b >= a:
            row["seconds"] = round((b - a).total_seconds(), 1)
            spans.append((a, b))
        rows.append(row)
    text_tokens = _text_tokens(ws_root, doc["draft"])
    scenes = int(doc.get("stats", {}).get("scenes", 0))
    n = len(rows)
    done = [r for r in rows if r["status"] == "done"]
    in_all = sum(r["in_tokens"] for r in rows)
    out_done = sum(r["out_tokens"] or 0 for r in done)
    scene_done = [r for r in done if r["kind"] == "scenes"]
    out_scenes = sum(r["out_tokens"] or 0 for r in scene_done)
    answered = sum(r["scenes"] for r in scene_done)
    calls = sum(r["calls"] for r in rows)
    chained = n + 1 if n else 0
    timed = [r["seconds"] for r in rows if r["seconds"] is not None]
    total = {
        "draft": doc["draft"],
        "text_tokens": text_tokens,
        "scenes": scenes,
        "packets": n,
        "packets_done": len(done),
        "in_tokens": in_all,
        "in_tokens_done": sum(r["in_tokens"] for r in done),
        "in_tokens_per_1k_text_tokens": round(1000 * in_all / text_tokens, 1)
        if text_tokens
        else 0.0,
        "peak_packet_tokens": max((r["in_tokens"] for r in rows), default=0),
        "out_tokens": out_done,
        "out_tokens_per_scene": round(out_scenes / answered, 1) if answered else None,
        "out_tokens_per_scene_all": round(out_done / scenes, 1) if scenes and done else None,
        "calls_planned": 2 * n,
        "calls_planned_chained": chained,
        "calls_recorded": calls,
        "calls_per_scene": _ratio(2 * n, scenes),
        "calls_per_scene_chained": _ratio(chained, scenes),
        "calls_recorded_per_scene": _ratio(calls, scenes),
        "timed_packets": len(timed),
        "wall_seconds_sum": round(sum(timed), 1) if timed else None,
        "wall_seconds_span": round(
            (max(b for _, b in spans) - min(a for a, _ in spans)).total_seconds(), 1
        )
        if spans
        else None,
    }
    return {"packets": rows, "total": total}


def cost_lines(rep: dict[str, Any]) -> list[str]:
    out = []
    for r in rep["packets"]:
        line = (
            f"{r['id']} {r['kind']} {r['tier']} {r['status']}: in ~{r['in_tokens']}"
            f", out {'~' + str(r['out_tokens']) if r['out_tokens'] is not None else '-'}"
            f", {r['calls']} calls"
        )
        if r["seconds"] is not None:
            line += f", {r['seconds']} s"
        out.append(line)
    t = rep["total"]
    out.append(
        f"total: {t['packets']} packets ({t['packets_done']} done) for {t['scenes']} scenes, "
        f"text ~{t['text_tokens']} tokens"
    )
    out.append(
        f"in ~{t['in_tokens']} tokens ({t['in_tokens_per_1k_text_tokens']} per 1k text tokens), "
        f"largest packet ~{t['peak_packet_tokens']}"
    )
    per = t["out_tokens_per_scene"]
    out.append(
        f"out ~{t['out_tokens']} tokens recorded"
        + (f" ({per} per scene answered)" if per is not None else "")
    )
    out.append(
        f"calls: {t['calls_planned']} planned ({t['calls_per_scene']} per scene), "
        f"{t['calls_planned_chained']} chaining `import --next` "
        f"({t['calls_per_scene_chained']} per scene), {t['calls_recorded']} recorded"
    )
    if t["wall_seconds_sum"] is not None:
        out.append(
            f"wall time: {t['wall_seconds_sum']} s over {t['timed_packets']} packet(s), "
            f"{t['wall_seconds_span']} s from first print to last import"
        )
    return out


# --- entities against a gold list --------------------------------------------------


def _raw(e: dict[str, Any]) -> list[str]:
    return [f for f in [e.get("name", ""), *e.get("aliases", []), *e.get("titles", [])] if f]


def _forms(e: dict[str, Any]) -> set[tuple[str, ...]]:
    return {n for n in map(prepass._norm, _raw(e)) if n}


def _exact(e: dict[str, Any]) -> set[str]:
    return {" ".join(f.casefold().split()) for f in _raw(e)}


def _match(
    ents: list[dict[str, Any]], refs: list[dict[str, Any]]
) -> tuple[list[list[int]], list[list[int]]]:
    """For each entity, the reference entities sharing a normalised form; and the
    reverse. Forms equal before normalisation take precedence: an entity sharing an
    exact form with some reference entities matches only those, so two references the
    normalisation makes alike ("señor Centeno", "la señora de Centeno") stay apart."""
    ref_forms = [_forms(r) for r in refs]
    ref_exact = [_exact(r) for r in refs]
    hits = []
    for e in ents:
        ex = _exact(e)
        same = [j for j, rx in enumerate(ref_exact) if ex & rx]
        hits.append(same or [j for j, rf in enumerate(ref_forms) if _forms(e) & rf])
    back: list[list[int]] = [[] for _ in refs]
    for i, hs in enumerate(hits):
        for j in hs:
            back[j].append(i)
    return hits, back


def _codex_entities(cx: Codex) -> list[dict[str, Any]]:
    return [{"id": it.id, **it.fields} for it in cx.live("entity")]


def entity_scores(ents: list[dict[str, Any]], gold: dict[str, Any]) -> dict[str, Any]:
    """Precision, recall and F1 of entities against a gold list, and alias-merge errors.

    An entity is a hit when any of its forms (name, aliases, titles) equals a form of a
    gold entity after normalisation; one matching only a ``minor`` gold entry (equal or
    inside it) is neutral, neither hit nor false positive. Entities of a kind the gold
    list never uses (motifs, rules) are out of scope. A gold entity reached by two
    entities is a split, an entity reaching two gold entities a merge: each extra one
    is an alias-merge error.
    """
    gents = gold["entities"]
    minor = [prepass._norm(m["name"]) for m in gold.get("minor", [])]
    kinds = {e["kind"] for e in gents} | {m.get("kind", "") for m in gold.get("minor", [])}
    scoped = [e for e in ents if e.get("kind") in kinds]
    out_of_scope = [e.get("name", "") for e in ents if e.get("kind") not in kinds]
    hits, back = _match(scoped, gents)
    true: list[int] = []
    false: list[int] = []
    neutral: list[int] = []
    for i, e in enumerate(scoped):
        if hits[i]:
            true.append(i)
        elif any(f == m or prepass._inside(f, m) for f in _forms(e) for m in minor):
            neutral.append(i)
        else:
            false.append(i)
    reached = [j for j, b in enumerate(back) if b]
    precision = _ratio(len(true), len(true) + len(false))
    recall = _ratio(len(reached), len(gents))
    splits = [
        {"gold": gents[j]["name"], "entities": sorted(scoped[i]["name"] for i in b)}
        for j, b in enumerate(back)
        if len(b) > 1
    ]
    merges = [
        {"entity": scoped[i]["name"], "gold": [gents[j]["name"] for j in hits[i]]}
        for i in true
        if len(hits[i]) > 1
    ]
    kind_errors = [
        {"entity": scoped[i]["name"], "kind": scoped[i]["kind"]}
        for i in true
        if all(gents[j]["kind"] != scoped[i]["kind"] for j in hits[i])
    ]
    return {
        "gold_entities": len(gents),
        "reached": len(reached),
        "recall": recall,
        "entities": len(ents),
        "scored": len(scoped),
        "true": len(true),
        "false": len(false),
        "neutral": len(neutral),
        "precision": precision,
        "f1": _f1(precision, recall),
        "alias_merge_errors": sum(len(s["entities"]) - 1 for s in splits)
        + sum(len(m["gold"]) - 1 for m in merges),
        "splits": splits,
        "merges": merges,
        "kind_errors": kind_errors,
        "missed": [g["name"] for j, g in enumerate(gents) if not back[j]],
        "false_positives": [scoped[i]["name"] for i in false],
        "out_of_scope": out_of_scope,
        "_back": back,
        "_scoped": scoped,
    }


def reference_recall(
    ws_root: Path, cx: Codex, gold: dict[str, Any], back: list[list[int]], scoped: list[Any]
) -> dict[str, Any]:
    """T3's method on the Codex entities: for each gold entity, the distinct mentions of
    the entities matching it, capped at its gold occurrences, over all gold occurrences."""
    draft = packets.load_draft(ws_root, cx.draft)
    scenes = [a.rsplit(".p", 1)[0] for a in draft.anchors]
    rows = view.mention_rows(draft.paragraphs, scenes, cx.live("entity"))
    at: dict[str, set[tuple[int, int]]] = {}
    for eid, para, off, *_ in rows:
        at.setdefault(eid, set()).add((para, off))
    occ = [int(g.get("occurrences", 0)) for g in gold["entities"]]
    hits = 0
    for j, n in enumerate(occ):
        pos: set[tuple[int, int]] = set()
        for i in back[j]:
            pos |= at.get(scoped[i]["id"], set())
        hits += min(len(pos), n)
    return {
        "recall": _ratio(hits, sum(occ)),
        "hits": hits,
        "gold": sum(occ),
        "mentions": len(rows),
    }


def evaluate(ws_root: Path, gold: dict[str, Any], references: bool = True) -> dict[str, Any]:
    """The Codex entities of a workspace scored against a gold list."""
    if not gold.get("entities"):
        raise EvalError("the gold list has no entities")
    cx = Codex(ws_root)
    ents = _codex_entities(cx)
    rep = entity_scores(ents, gold)
    back, scoped = rep.pop("_back"), rep.pop("_scoped")
    if references and any("occurrences" in g for g in gold["entities"]):
        rep["reference_recall"] = reference_recall(ws_root, cx, gold, back, scoped)
    return rep


def eval_lines(rep: dict[str, Any]) -> list[str]:
    out = [
        f"entities: precision {rep['precision']} ({rep['true']} hits, {rep['false']} false, "
        f"{rep['neutral']} neutral of {rep['scored']} scored), recall {rep['recall']} "
        f"({rep['reached']}/{rep['gold_entities']} gold), F1 {rep['f1']}",
        f"alias-merge errors: {rep['alias_merge_errors']} ({len(rep['splits'])} split, "
        f"{len(rep['merges'])} merged); kind errors: {len(rep['kind_errors'])}",
    ]
    if "reference_recall" in rep:
        r = rep["reference_recall"]
        out.append(f"reference recall {r['recall']} ({r['hits']}/{r['gold']} gold occurrences)")
    for key, label in (
        ("missed", "missed"),
        ("false_positives", "false"),
        ("out_of_scope", "out of scope"),
    ):
        if rep[key]:
            out.append(f"{label}: {', '.join(rep[key])}")
    for s in rep["splits"]:
        out.append(f"split: {s['gold']} -> {' | '.join(s['entities'])}")
    for m in rep["merges"]:
        out.append(f"merged: {m['entity']} -> {' | '.join(m['gold'])}")
    return out


# --- two tiers on the same packet --------------------------------------------------


def _field(s: Any) -> tuple[str, ...]:
    """A pov, location or time for exact matching: words casefolded, articles,
    honorifics and connectors dropped, accents removed."""
    words = [w.casefold() for w in WORD.findall(str(s or ""))]
    kept = [w for w in words if w not in prepass._strip_words()] or words
    return tuple(
        "".join(c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c))
        for w in kept
    )


def _mean(xs: Iterable[float]) -> float | None:
    v = list(xs)
    return round(sum(v) / len(v), 1) if v else None


def _kind_of(ans: dict[str, Any]) -> str:
    for k in ("entities", "scenes"):
        if isinstance(ans.get(k), list) and (k == "scenes" or "scenes" not in ans):
            return k
    raise EvalError("not a packet answer: expected an object with entities or scenes")


def compare(ans: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    """Agreement of an answer with a reference answer to the same packet (numbers only)."""
    kind = _kind_of(ans)
    if _kind_of(ref) != kind:
        raise EvalError("the two answers are of different kinds")
    if kind == "entities":
        a, r = ans["entities"], ref["entities"]
        hits, back = _match(a, r)
        matched = [i for i, h in enumerate(hits) if h]
        recall = _ratio(sum(1 for b in back if b), len(r))
        precision = _ratio(len(matched), len(a))
        same_kind = sum(1 for i in matched if any(r[j]["kind"] == a[i]["kind"] for j in hits[i]))
        kind_agreement = _ratio(same_kind, len(matched))
        out: dict[str, Any] = {
            "kind": "entities",
            "entities": len(a),
            "reference_entities": len(r),
            "recall": recall,
            "precision": precision,
            "f1": _f1(precision, recall),
            "kind_agreement": kind_agreement,
            "splits": sum(len(b) - 1 for b in back if len(b) > 1),
            "merges": sum(len(h) - 1 for h in hits if len(h) > 1),
        }
        out["min_agreement"] = min(recall, precision, kind_agreement)
    else:
        a_sc = {s["scene"]: s for s in ans["scenes"]}
        r_sc = {s["scene"]: s for s in ref["scenes"]}
        common = [k for k in r_sc if k in a_sc]
        out = {
            "kind": "scenes",
            "scenes": len(a_sc),
            "reference_scenes": len(r_sc),
            "common_scenes": len(common),
        }
        rates = []
        for f in ("pov", "location", "time"):
            same = sum(1 for k in common if _field(a_sc[k].get(f)) == _field(r_sc[k].get(f)))
            out[f"{f}_agreement"] = _ratio(same, len(common))
            rates.append(out[f"{f}_agreement"])

        def side(sc: dict[str, Any], which: str) -> int:
            return sum(1 for su in sc.get("setups", []) if su.get("side") == which)

        for label, src in (("answer", a_sc), ("reference", r_sc)):
            out[f"summary_words_{label}"] = _mean(
                len(str(src[k].get("summary", "")).split()) for k in common
            )
            out[f"setups_{label}"] = sum(side(src[k], "setup") for k in common)
            out[f"payoffs_{label}"] = sum(side(src[k], "payoff") for k in common)
            out[f"new_entities_{label}"] = sum(len(src[k].get("entities", [])) for k in common)
        out["out_tokens_per_scene_answer"] = packets.output_tokens_per_scene(ans)
        out["out_tokens_per_scene_reference"] = packets.output_tokens_per_scene(ref)
        out["min_agreement"] = min([_ratio(len(common), len(r_sc)), *rates])
    out["threshold"] = AGREEMENT
    out["agrees"] = out["min_agreement"] >= AGREEMENT
    return out


def compare_lines(rep: dict[str, Any]) -> list[str]:
    keys = [k for k in rep if k not in ("kind", "agrees", "threshold")]
    out = [f"{rep['kind']}: " + ", ".join(f"{k} {rep[k]}" for k in keys)]
    verdict = "agrees" if rep["agrees"] else "does not agree"
    out.append(
        f"{verdict} with the reference (lowest agreement {rep['min_agreement']}, "
        f"threshold {rep['threshold']})"
    )
    return out
