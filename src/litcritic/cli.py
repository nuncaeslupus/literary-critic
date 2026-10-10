"""`lc` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from litcritic import __version__, checklist, guard, workspace


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        ws = workspace.create(args.slug, args.title, args.language, args.home)
    except workspace.WorkspaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"workspace created: {ws.root}")
    print(f"add character/place names to {ws.guard_terms_file}")
    return 0


def _cmd_guard(args: argparse.Namespace) -> int:
    repo = workspace.repo_root()
    files = guard.tracked_files(repo) if args.all else guard.staged_changes(repo)
    try:
        terms = guard.read_terms(guard.default_term_files(repo), [Path(p) for p in args.terms])
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    violations = guard.check(files, terms)
    for v in violations:
        print(f"BLOCKED {v.path}: {v.reason}", file=sys.stderr)
    print(f"guard: {len(files)} files, {len(terms)} terms, {len(violations)} violations")
    return 1 if violations else 0


def _cmd_checklist(args: argparse.Namespace) -> int:
    root = args.root or workspace.repo_root() / "checklist"
    cat = checklist.load(root)
    if args.action == "validate":
        for err in cat.errors:
            print(f"ERROR {err}", file=sys.stderr)
        print(
            f"checklist: {len(cat.areas)} areas, {len(cat.checks)} checks, {len(cat.errors)} errors"
        )
        return 1 if cat.errors else 0
    if args.action == "stats":
        print(json.dumps(checklist.stats(cat), indent=2))
        return 0
    # plan: select checks for a novel profile
    if cat.errors:
        print("error: catalogue is invalid; run `lc checklist validate`", file=sys.stderr)
        return 2
    traits: set[str] = set()
    mode = "revision"
    disabled: set[str] = set()
    if args.profile:
        prof = tomllib.loads(Path(args.profile).read_text(encoding="utf-8"))
        traits = set(prof.get("traits", []))
        mode = str(prof.get("mode", mode))
        disabled = set(prof.get("disabled", []))
        known_ids = {c.id for c in cat.checks} | set(cat.areas)
        problems = (
            [f"unknown traits {sorted(traits - set(cat.traits))}"]
            if traits - set(cat.traits)
            else []
        )
        if mode not in checklist.MODES:
            problems.append(f"unknown mode {mode!r} (use one of {checklist.MODES})")
        if disabled - known_ids:
            problems.append(f"unknown disabled ids {sorted(disabled - known_ids)}")
        if problems:
            for msg in problems:
                print(f"error: {msg}", file=sys.stderr)
            return 2
    for c in checklist.select(cat, traits, mode, disabled):
        print(f"{c.stage:<13} {c.id:<40} {c.method:<6} {c.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lc", description="literary-critic toolkit")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create a workspace for a novel")
    p_init.add_argument("slug")
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--language", required=True, help="ISO 639-1 code, e.g. es, en")
    p_init.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_init.set_defaults(func=_cmd_init)

    p_guard = sub.add_parser("guard", help="block working-novel content from the repo")
    p_guard.add_argument("--all", action="store_true", help="scan all tracked files")
    p_guard.add_argument("--terms", action="append", default=[], help="extra terms file")
    p_guard.set_defaults(func=_cmd_guard)

    p_check = sub.add_parser("checklist", help="validate or plan the analysis catalogue")
    p_check.add_argument("action", choices=["validate", "stats", "plan"])
    p_check.add_argument("--root", type=Path, default=None, help="catalogue directory")
    p_check.add_argument("--profile", help="novel profile TOML (traits, mode, disabled)")
    p_check.set_defaults(func=_cmd_checklist)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
