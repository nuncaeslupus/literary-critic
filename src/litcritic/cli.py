"""`lc` command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from litcritic import __version__, guard, workspace


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
    term_files = guard.default_term_files(repo) + [Path(p) for p in args.terms]
    terms = guard.read_terms(term_files)
    violations = guard.check(files, terms)
    for v in violations:
        print(f"BLOCKED {v.path}: {v.reason}", file=sys.stderr)
    print(f"guard: {len(files)} files, {len(terms)} terms, {len(violations)} violations")
    return 1 if violations else 0


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
