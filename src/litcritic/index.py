"""Build the derived registers of a draft from its LLM-written scene cards.

Input: ``index/vNNN/scene_cards.json`` (a list of scene cards, schema
``scene-card``). Output: ``index/vNNN/registers/{characters,locations,timeline,
setups}.json`` (schema ``register``). Cards are validated and their anchors
checked against ``structure.json`` first; nothing is written when they fail.

Names are merged when they differ only in case or accents. Setups and payoffs
pair when the card uses the same short label for both, which the
scene-card procedure asks for.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from litcritic import structure, validate
from litcritic.textstats import strip_accents


def _key(text: str) -> str:
    return " ".join(strip_accents(text).casefold().split())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _key(text)).strip("-") or "x"


def _entries(names: dict[str, list[str]], forms: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    out = []
    used: set[str] = set()
    for key, anchors in names.items():
        name = forms[key].most_common(1)[0][0]
        slug = _slug(name)
        while slug in used:
            slug += "-2"
        used.add(slug)
        entry: dict[str, Any] = {
            "id": slug,
            "name": name,
            "anchors": sorted(set(anchors), key=anchors.index),
        }
        others = sorted(f for f in forms[key] if f != name)
        if others:
            entry["aliases"] = others
        out.append(entry)
    return out


def registers_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    people: dict[str, list[str]] = defaultdict(list)
    people_forms: dict[str, Counter[str]] = defaultdict(Counter)
    places: dict[str, list[str]] = defaultdict(list)
    place_forms: dict[str, Counter[str]] = defaultdict(Counter)
    setups: dict[str, dict[str, Any]] = {}
    timeline = []
    for card in cards:
        a = card["anchor"]
        for person in card.get("characters", []):
            people[_key(person)].append(a)
            people_forms[_key(person)][person] += 1
        if card.get("location"):
            places[_key(card["location"])].append(a)
            place_forms[_key(card["location"])][card["location"]] += 1
        if card.get("story_time"):
            timeline.append({"id": a, "name": card["story_time"], "anchors": [a]})
        for label in card.get("setups", []):
            e = setups.setdefault(
                _key(label), {"id": _slug(label), "name": label, "anchors": [], "status": "open"}
            )
            e["anchors"].append(a)
        for label in card.get("payoffs", []):
            e = setups.setdefault(
                _key(label), {"id": _slug(label), "name": label, "anchors": [], "status": "open"}
            )
            e["anchors"].append(a)
            e["status"] = "paid_off" if len(e["anchors"]) > 1 else "open"
    return {
        "characters": {
            "schema_version": 1,
            "kind": "characters",
            "entries": _entries(people, people_forms),
        },
        "locations": {
            "schema_version": 1,
            "kind": "locations",
            "entries": _entries(places, place_forms),
        },
        "timeline": {"schema_version": 1, "kind": "timeline", "entries": timeline},
        "setups": {"schema_version": 1, "kind": "setups", "entries": list(setups.values())},
    }


def check_cards(cards: Any, scene_ids: set[str]) -> list[str]:
    errors = validate.validate("scene-card", cards)
    if not isinstance(cards, list):
        return errors or ["scene_cards.json must be a list of scene cards"]
    seen: set[str] = set()
    for k, card in enumerate(cards):
        a = card.get("anchor") if isinstance(card, dict) else None
        if not isinstance(a, str):
            continue
        if a not in scene_ids:
            errors.append(f"$[{k}].anchor: no scene {a!r} in structure.json")
        if a in seen:
            errors.append(f"$[{k}].anchor: {a!r} has two cards")
        seen.add(a)
    return errors


def build(ws_root: Path, version: str | None = None) -> tuple[list[Path], list[str]]:
    version = version or structure.latest_version(ws_root)
    base = ws_root / "index" / version
    struct_file = base / "structure.json"
    if not struct_file.is_file():
        raise FileNotFoundError(f"no structure for {version}; run `lc anchor` first")
    data = json.loads(struct_file.read_text(encoding="utf-8"))
    scene_ids = {re.sub(r"^p\d+\.", "", s["id"]) for c in data["chapters"] for s in c["scenes"]}
    scene_ids |= {s["id"] for c in data["chapters"] for s in c["scenes"]}
    cards_file = base / "scene_cards.json"
    if not cards_file.is_file():
        raise FileNotFoundError(
            f"no scene cards yet ({cards_file}); write them with the scene-card procedure"
        )
    cards = json.loads(cards_file.read_text(encoding="utf-8"))
    errors = check_cards(cards, scene_ids)
    if errors:
        return [], errors
    regs = registers_from_cards(cards)
    out_dir = base / "registers"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for kind, reg in regs.items():
        problems = validate.validate("register", reg)
        if problems:  # a bug here, not bad input: cards were already valid
            raise ValueError(f"{kind} register invalid: {problems[:3]}")
        path = out_dir / f"{kind}.json"
        path.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        written.append(path)
    return written, []
