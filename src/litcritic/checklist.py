"""Load, validate and select checks from the analysis catalogue (``checklist/``)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STAGES = ("orientation", "developmental", "scene", "line", "verification")
METHODS = ("script", "llm", "hybrid")
KINDS = ("diagnostic", "inventory", "strength")
ACTION_LEVELS = ("structural", "scene", "line", "none")
MODES = ("revision", "reader-report")
INPUTS = (
    "L0",
    "L1",
    "L2",
    "L3",
    "structure",
    "characters",
    "relationships",
    "timeline",
    "locations",
    "motifs",
    "ledger",
    "metrics",
    "findings",
    "backlog",
)
SEVERITIES = ("high", "medium", "low")
ID_RE = re.compile(r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)?$")
CHECK_REQUIRED = ("id", "title", "question", "look_for", "method", "inputs", "evidence")
AREA_REQUIRED = ("id", "title", "stage", "order", "purpose")


@dataclass(frozen=True)
class Check:
    id: str
    area: str
    stage: str
    order: int
    title: str
    question: str
    method: str
    kind: str
    action_level: str
    inputs: tuple[str, ...]
    metrics: tuple[str, ...]
    applies_when: tuple[str, ...]
    modes: tuple[str, ...]
    raw: dict[str, Any] = field(repr=False, compare=False)


@dataclass
class Catalogue:
    root: Path
    areas: dict[str, dict[str, Any]]
    checks: list[Check]
    traits: dict[str, str]
    metrics: dict[str, dict[str, Any]]
    errors: list[str]


def _load_toml(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"{path.name}: missing")
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"{path.name}: invalid TOML: {exc}")
        return {}


def _subset(
    name: str, values: object, allowed: tuple[str, ...] | set[str], errs: list[str]
) -> None:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        errs.append(f"{name}: must be a list of strings")
        return
    for v in values:
        if v not in allowed:
            errs.append(f"{name}: unknown value {v!r}")


def load(root: Path) -> Catalogue:
    """Load and validate the whole catalogue; problems go to ``Catalogue.errors``."""
    errors: list[str] = []
    traits_doc = _load_toml(root / "traits.toml", errors)
    traits = {
        k: str(v.get("description", "")) if isinstance(v, dict) else ""
        for k, v in traits_doc.get("trait", {}).items()
    }
    metrics_doc = _load_toml(root / "metrics.toml", errors)
    metrics: dict[str, dict[str, Any]] = dict(metrics_doc.get("metric", {}))
    for mid, m in metrics.items():
        if not isinstance(m, dict):
            errors.append(f"metrics.toml: metric {mid} must be a table")
            continue
        for key in ("description", "unit", "status"):
            if key not in m:
                errors.append(f"metrics.toml: metric {mid} missing {key}")

    areas: dict[str, dict[str, Any]] = {}
    checks: list[Check] = []
    seen: set[str] = set()
    orders: set[int] = set()
    for path in sorted((root / "areas").glob("*.toml")):
        doc = _load_toml(path, errors)
        where = path.name
        missing = [k for k in AREA_REQUIRED if k not in doc]
        if missing:
            errors.append(f"{where}: area missing {missing}")
            continue
        if not isinstance(doc["id"], str) or not isinstance(doc["order"], int):
            errors.append(f"{where}: area id must be a string and order an integer")
            continue
        aid = doc["id"]
        if aid in areas:
            errors.append(f"{where}: duplicate area id {aid}")
        if doc["stage"] not in STAGES:
            errors.append(f"{where}: unknown stage {doc['stage']!r}")
        if doc["order"] in orders:
            errors.append(f"{where}: duplicate area order {doc['order']}")
        orders.add(doc["order"])
        areas[aid] = doc
        area_checks = doc.get("check", [])
        if not area_checks:
            errors.append(f"{where}: area has no checks")
        if not isinstance(area_checks, list):
            errors.append(f"{where}: [[check]] must be an array of tables")
            continue
        for c in area_checks:
            if not isinstance(c, dict):
                errors.append(f"{where}: check entries must be tables")
                continue
            cid = str(c.get("id", "?"))
            ctx = f"{where}:{cid}"
            errs: list[str] = []
            for k in CHECK_REQUIRED:
                if not c.get(k):
                    errs.append(f"missing {k}")
            if not ID_RE.match(cid) or not cid.startswith(f"{aid}."):
                errs.append(f"id must be '{aid}.<slug>'")
            if cid in seen:
                errs.append("duplicate id")
            seen.add(cid)
            if c.get("method") not in METHODS:
                errs.append(f"method must be one of {METHODS}")
            if c.get("kind", "diagnostic") not in KINDS:
                errs.append(f"kind must be one of {KINDS}")
            if c.get("action_level", "scene") not in ACTION_LEVELS:
                errs.append(f"action_level must be one of {ACTION_LEVELS}")
            _subset("inputs", c.get("inputs", []), INPUTS, errs)
            _subset("metrics", c.get("metrics", []), set(metrics), errs)
            _subset("applies_when", c.get("applies_when", []), set(traits), errs)
            _subset("modes", c.get("modes", list(MODES)), MODES, errs)
            if c.get("method") in ("script", "hybrid") and not c.get("metrics"):
                errs.append("script/hybrid checks must name metrics")
            kind = c.get("kind", "diagnostic")
            sev = c.get("severity", {})
            if kind == "diagnostic" and (
                not isinstance(sev, dict) or sorted(sev) != sorted(SEVERITIES)
            ):
                errs.append("diagnostic checks need severity.high/medium/low")
            if not isinstance(c.get("look_for", []), list):
                errs.append("look_for must be a list")
            errors.extend(f"{ctx}: {e}" for e in errs)
            checks.append(
                Check(
                    id=cid,
                    area=aid,
                    stage=doc["stage"],
                    order=int(doc["order"]),
                    title=str(c.get("title", "")),
                    question=str(c.get("question", "")),
                    method=str(c.get("method", "")),
                    kind=str(kind),
                    action_level=str(c.get("action_level", "scene")),
                    inputs=tuple(c.get("inputs", [])),
                    metrics=tuple(c.get("metrics", [])),
                    applies_when=tuple(c.get("applies_when", [])),
                    modes=tuple(c.get("modes", list(MODES))),
                    raw=c,
                )
            )
    if not areas:
        errors.append("no areas found")
    return Catalogue(root, areas, checks, traits, metrics, errors)


def select(
    cat: Catalogue,
    traits: set[str],
    mode: str = "revision",
    disabled: set[str] | None = None,
) -> list[Check]:
    """Checks that apply to a novel profile, in working order (stage, area order)."""
    disabled = disabled or set()
    chosen = [
        c
        for c in cat.checks
        if mode in c.modes
        and c.id not in disabled
        and c.area not in disabled
        and (not c.applies_when or set(c.applies_when) & traits)
    ]
    return sorted(chosen, key=lambda c: (STAGES.index(c.stage), c.order))


def stats(cat: Catalogue) -> dict[str, object]:
    def by(attr: str) -> dict[str, int]:
        values = [str(getattr(c, attr)) for c in cat.checks]
        return {v: values.count(v) for v in sorted(set(values))}

    return {
        "areas": len(cat.areas),
        "checks": len(cat.checks),
        "traits": len(cat.traits),
        "metrics": len(cat.metrics),
        "by_stage": by("stage"),
        "by_method": by("method"),
        "by_kind": by("kind"),
        "errors": len(cat.errors),
    }
