"""Validate LLM-written artefacts against the JSON schemas in ``schemas/``.

Runtime is stdlib only, so this implements the subset of JSON Schema the
schemas use: type, const, enum, required, properties, additionalProperties,
items, minItems, minLength, minimum, maximum, pattern and local ``$ref``, plus
``x-maxWords`` (word limit for quotes and summaries). Findings and profiles are
also checked against the catalogue (known check ids, traits, areas).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from litcritic import checklist
from litcritic.workspace import repo_root

KINDS = ("scene-card", "register", "finding", "action", "profile")
TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


def schema_dir() -> Path:
    return repo_root() / "schemas"


def load_schema(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r} (use one of {', '.join(KINDS)})")
    data: dict[str, Any] = json.loads(
        (schema_dir() / f"{kind}.schema.json").read_text(encoding="utf-8")
    )
    return data


def check(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    """Errors for ``value`` against ``schema``; ``root`` resolves ``#/...`` refs."""
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return check(value, target, root, path)
    if "const" in schema and value != schema["const"]:
        return [f"{path}: must be {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} not one of {schema['enum']}"]
    expected = schema.get("type")
    if expected:
        ok = isinstance(value, TYPES[expected]) and not (
            isinstance(value, bool) and expected in ("integer", "number")
        )
        if not ok:
            return [f"{path}: expected {expected}, got {type(value).__name__}"]
    errors: list[str] = []
    if isinstance(value, dict):
        errors += _check_object(value, schema, root, path)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += check(item, schema["items"], root, f"{path}[{i}]")
    elif isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            errors.append(f"{path}: must not be empty")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        words = len(value.split())
        if words > schema.get("x-maxWords", words):
            errors.append(f"{path}: {words} words, limit {schema['x-maxWords']}")
    elif isinstance(value, int | float):
        if value < schema.get("minimum", value):
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if value > schema.get("maximum", value):
            errors.append(f"{path}: above maximum {schema['maximum']}")
    return errors


def _check_object(
    value: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], path: str
) -> list[str]:
    errors = [f"{path}: missing {k}" for k in schema.get("required", []) if k not in value]
    props = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        if key in props:
            errors += check(item, props[key], root, f"{path}.{key}")
        elif extra is False:
            errors.append(f"{path}: unknown field {key}")
        elif isinstance(extra, dict):
            errors += check(item, extra, root, f"{path}.{key}")
    return errors


def validate(kind: str, data: Any, catalogue: checklist.Catalogue | None = None) -> list[str]:
    """Schema errors plus catalogue cross-checks; a JSON list is validated item by item."""
    schema = load_schema(kind)
    items = data if isinstance(data, list) and kind != "profile" else [data]
    errors: list[str] = []
    for i, item in enumerate(items):
        prefix = f"$[{i}]" if items is data else "$"
        errors += check(item, schema, schema, prefix)
        if catalogue is not None and isinstance(item, dict):
            errors += [f"{prefix}: {e}" for e in _cross_check(kind, item, catalogue)]
    return errors


def _cross_check(kind: str, item: dict[str, Any], cat: checklist.Catalogue) -> list[str]:
    known = {c.id for c in cat.checks}
    if kind == "finding" and "check_id" in item and item["check_id"] not in known:
        return [f"unknown check_id {item['check_id']!r}"]
    if kind == "profile":
        errors = [f"unknown trait {t!r}" for t in item.get("traits", []) if t not in cat.traits]
        errors += [
            f"unknown check or area {d!r} in disabled"
            for d in item.get("disabled", [])
            if d not in known and d not in cat.areas
        ]
        errors += [
            f"unknown check or area {w!r} in weights"
            for w in item.get("weights", {})
            if w not in known and w not in cat.areas
        ]
        return errors
    return []


def load_file(kind: str, path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if kind == "profile" or path.suffix == ".toml":
        return tomllib.loads(text)
    return json.loads(text)
