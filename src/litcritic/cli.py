"""`lc` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from litcritic import (
    __version__,
    checklist,
    codex,
    codex_cli,
    corpus,
    diff,
    docx_cli,
    docx_out,
    guard,
    index_cli,
    ingest,
    kinds,
    kit,
    locate,
    metrics,
    pack,
    query,
    report,
    rounds,
    setup,
    structure,
    synth,
    upgrade,
    validate,
    word_live,
    workspace,
)


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        ws = workspace.create(
            args.slug,
            args.title,
            args.language,
            args.home,
            author=args.author,
            kind=args.kind,
            series=args.series,
            tags=tuple(args.tag or []),
        )
    except workspace.WorkspaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"work created: {ws.root} (id {ws.manifest['id']})")
    print(f"add character/place names to {ws.guard_terms_file}")
    return 0


def _cmd_library(args: argparse.Namespace) -> int:
    try:
        works = workspace.all_workspaces(args.home)
    except (workspace.WorkspaceError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    groups: dict[str, list[str]] = {}
    for ws in works:
        m = ws.manifest
        tags = m.get("tags", [])
        if args.by == "tag":
            keys = [str(t) for t in tags] if isinstance(tags, list) else []
        else:
            keys = [str(m.get(args.by, ""))]
        line = f"{m.get('id', ws.root.name)}  {m.get('title', '')}  ({ws.root})"
        for key in keys or [""]:
            groups.setdefault(key or f"(no {args.by})", []).append(line)
    for key in sorted(groups):
        print(f"{key}:")
        for line in sorted(groups[key]):
            print(f"  {line}")
    print(f"{len(works)} work(s)")
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


def _cmd_corpus(args: argparse.Namespace) -> int:
    texts = corpus.load(args.root)
    for t in texts:
        words = len(t.read().split()) if t.path.is_file() else 0
        lang = t.meta.get("language", "?")
        print(f"{t.slug:<20} {lang!s:<3} {words:>7} words  {'ok' if t.documented else 'FAIL'}")
        for err in t.errors:
            print(f"  {err}", file=sys.stderr)
    ratio = corpus.documented_ratio(texts)
    print(f"corpus_sources_documented = {ratio:.3f} ({len(texts)} texts)")
    return 0 if ratio == 1.0 else 1


def _cmd_synth(args: argparse.Namespace) -> int:
    source = Path(args.text)
    if not source.is_file():
        try:
            source = corpus.get(args.text).path
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    draft = synth.generate(source.read_text(encoding="utf-8"), args.seed, args.rate)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "draft.txt").write_text(draft.text, encoding="utf-8")
    truth = {"source": str(source), "seed": args.seed, "rate": args.rate, **draft.truth()}
    (args.out / "truth.json").write_text(json.dumps(truth, indent=1) + "\n", encoding="utf-8")
    print(f"{len(draft.ops)} edits, {truth['old_count']} -> {truth['new_count']} paragraphs")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        result = ingest.ingest(Path(args.file), ws.root)
    except (workspace.WorkspaceError, ingest.IngestError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if result.unchanged:
        print(f"unchanged: same file as {result.version}")
    else:
        print(f"{result.version}: {result.paragraphs} paragraphs -> {result.text_path}")
    return 0


def _cmd_anchor(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        out, s, errors = structure.build(ws.root, args.version)
    except (workspace.WorkspaceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for err in errors:
        print(f"override rejected: {err}", file=sys.stderr)
    print("; ".join(s.notes))
    print(f"wrote {out}")
    return 1 if errors else 0


def _cmd_diff(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        out, _, data = diff.build(ws.root, args.old, args.new)
    except (workspace.WorkspaceError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    counts = ", ".join(f"{k} {v}" for k, v in data["counts"].items())
    print(f"{args.old} -> {args.new}: {counts}")
    for note in data["notes"]:
        print(f"note: {note}")
    print(f"stale scenes: {len(data['stale_scenes'])}; wrote {out}")
    return 0


def _cmd_metrics(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        version = args.version or structure.latest_version(ws.root)
        lang = args.language or str(ws.manifest.get("language", "en"))
        out, results = metrics.build(ws.root, version, lang)
    except (workspace.WorkspaceError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    unmeasured = sorted(k for k, v in results.items() if "unmeasured" in v)
    print(f"{len(results) - len(unmeasured)} metrics measured, {len(unmeasured)} need more input")
    print(f"wrote {out}")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        out, manifest = pack.pack(ws.root, args.out)
    except (workspace.WorkspaceError, pack.PackError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"generation {manifest['generation']}: {len(manifest['files'])} files -> {out}")
    print("keep this zip (e.g. in Drive); unpack it with `lc unpack` next session")
    return 0


def _cmd_unpack(args: argparse.Namespace) -> int:
    try:
        loaded = pack.read_zip(Path(args.zip))
        slug = str(loaded[0]["slug"])
        base = (args.home or workspace.home()).expanduser()
        if args.workspace:
            ref = Path(args.workspace).expanduser()
            target = ref if (ref.is_absolute() or len(ref.parts) > 1) else base / ref
        else:
            raw = loaded[1].get(workspace.MANIFEST, b"")
            wid = str(tomllib.loads(raw.decode("utf-8")).get("id", "")) if raw else ""
            same = workspace.find_id(wid, args.home) if wid else []
            target = same[0].root if len(same) == 1 else base / slug
        result = pack.unpack(Path(args.zip), target, force=args.force, loaded=loaded)
    except (workspace.WorkspaceError, pack.PackError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, pack.PackError) else 2
    print(f"{result.action}: {target} (generation {result.generation}, {result.written} files)")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        ix = query.load(ws.root, args.version)
        if args.command == "show":
            unit = args.unit or ""
            if not unit:
                text = query.toc(ix, args.budget)
            elif unit.endswith("-"):
                text = query.show_from(ix, unit, args.budget)
            else:
                text = query.show(ix, unit, args.budget, args.fp)
        elif args.command == "find":
            text = query.find(ix, args.query, args.budget, args.within or "")
        else:
            text = query.context(ix, args.anchor, args.budget)
    except (
        workspace.WorkspaceError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


def _cmd_locate(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        version = args.version or structure.latest_version(ws.root)
        ix = query.load(ws.root, version)
        lang = rounds.language(ws.root)
        locs = locate.Locations.of_workspace(ws.root, version, ix, lang, few=True)
        loc = locs.locate(args.anchor)
    except (workspace.WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(locate.as_json(loc) if args.json else locate.describe(loc, lang))
    return 0


def _cmd_round(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        if args.action == "build":
            out, actions, warnings = rounds.build(ws.root, args.version, args.level)
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
            print(f"{len(actions)} actions ({actions[0]['level'] if actions else '-'}) -> {out}")
        elif args.action == "letter":
            print(f"wrote {rounds.letter(ws.root, args.version)}")
        elif args.action == "mark":
            if not args.action_id or not args.status:
                raise rounds.RoundError("usage: lc round mark --id A3 --status accepted")
            a = rounds.mark(ws.root, args.action_id, args.status, args.reason or "")
            print(f"{a['id']}: {a['status']}")
        else:
            st = rounds.status(ws.root)
            print(json.dumps(st, ensure_ascii=False))
    except (
        workspace.WorkspaceError,
        rounds.RoundError,
        codex.CodexError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, rounds.RoundError) else 2
    return 0


def _cmd_docx_comments(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        out, n = docx_out.build(ws.root, args.version)
    except (
        workspace.WorkspaceError,
        docx_out.DocxError,
        rounds.RoundError,
        codex.CodexError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, docx_out.DocxError | rounds.RoundError) else 2
    print(f"{n} paragraphs commented; the original is unchanged -> {out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        out, complete = report.render(ws.root, args.version)
    except (
        workspace.WorkspaceError,
        report.ReportError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, report.ReportError) else 2
    missing = [name for name, ok in complete.items() if not ok]
    if missing:
        print(f"warning: sections without content: {', '.join(missing)}", file=sys.stderr)
    print(f"wrote {out}")
    return 0


def _cmd_kit(args: argparse.Namespace) -> int:
    try:
        out, n = (kit.build_skill if args.skill else kit.build)(args.out)
    except kit.KitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{n} files -> {out}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    problems = kit.doctor(args.home or workspace.home())
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        data = validate.load_file(args.kind, Path(args.file))
    except (OSError, ValueError) as exc:  # JSON and TOML decode errors are ValueErrors
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2
    cat = None if args.no_catalogue else checklist.load(workspace.repo_root() / "checklist")
    errors = validate.validate(args.kind, data, cat)
    for err in errors:
        print(err, file=sys.stderr)
    print(f"{args.kind}: {args.file}: {len(errors)} error(s)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lc", description="literary-critic toolkit")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create a workspace for a novel")
    p_init.add_argument("slug")
    p_init.add_argument("--title", required=True)
    p_init.add_argument("--language", required=True, help="ISO 639-1 code, e.g. es, en")
    p_init.add_argument("--author", default="")
    p_init.add_argument("--kind", default="novel", choices=kinds.available())
    p_init.add_argument("--series", default="")
    p_init.add_argument("--tag", action="append", help="repeatable")
    p_init.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_init.set_defaults(func=_cmd_init)

    p_lib = sub.add_parser("library", help="list the works under the home folder")
    p_lib.add_argument("--by", choices=["author", "kind", "series", "tag"], default="author")
    p_lib.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_lib.set_defaults(func=_cmd_library)

    p_guard = sub.add_parser("guard", help="block working-novel content from the repo")
    p_guard.add_argument("--all", action="store_true", help="scan all tracked files")
    p_guard.add_argument("--terms", action="append", default=[], help="extra terms file")
    p_guard.set_defaults(func=_cmd_guard)

    p_check = sub.add_parser("checklist", help="validate or plan the analysis catalogue")
    p_check.add_argument("action", choices=["validate", "stats", "plan"])
    p_check.add_argument("--root", type=Path, default=None, help="catalogue directory")
    p_check.add_argument("--profile", help="novel profile TOML (traits, mode, disabled)")
    p_check.set_defaults(func=_cmd_checklist)

    p_corpus = sub.add_parser("corpus", help="check the public-domain corpus source notes")
    p_corpus.add_argument("action", choices=["check"])
    p_corpus.add_argument("--root", type=Path, default=None, help="corpus directory")
    p_corpus.set_defaults(func=_cmd_corpus)

    p_synth = sub.add_parser("synth", help="derive a synthetic draft with a truth map")
    p_synth.add_argument("text", help="corpus slug or path to a text file")
    p_synth.add_argument("--seed", type=int, default=0)
    p_synth.add_argument("--rate", type=float, default=0.05, help="share of paragraphs edited")
    p_synth.add_argument("--out", type=Path, required=True, help="output directory")
    p_synth.set_defaults(func=_cmd_synth)

    p_ing = sub.add_parser("ingest", help="snapshot a draft and extract its normalised text")
    p_ing.add_argument("file", help=".txt, .md, .docx or .odt")
    p_ing.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_ing.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_ing.set_defaults(func=_cmd_ingest)

    p_anc = sub.add_parser("anchor", help="detect parts/chapters/scenes and anchor paragraphs")
    p_anc.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_anc.add_argument("--version", default=None, help="draft version, e.g. v002 (default latest)")
    p_anc.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_anc.set_defaults(func=_cmd_anchor)

    p_diff = sub.add_parser("diff", help="align two drafts: what changed, moved or is new")
    p_diff.add_argument("old", help="earlier version, e.g. v001")
    p_diff.add_argument("new", help="later version, e.g. v002")
    p_diff.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_diff.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_diff.set_defaults(func=_cmd_diff)

    p_met = sub.add_parser("metrics", help="measure a draft (registry: checklist/metrics.toml)")
    p_met.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_met.add_argument("--version", default=None, help="draft version (default latest)")
    p_met.add_argument("--language", default=None, help="override the workspace language")
    p_met.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_met.set_defaults(func=_cmd_metrics)

    p_pack = sub.add_parser("pack", help="zip a workspace with a checksummed manifest")
    p_pack.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_pack.add_argument("--out", type=Path, default=None, help="zip path (default next to it)")
    p_pack.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_pack.set_defaults(func=_cmd_pack)

    p_unp = sub.add_parser("unpack", help="restore a workspace zip; refuses to lose newer work")
    p_unp.add_argument("zip")
    p_unp.add_argument(
        "--workspace", default=None, help="target folder, or a name under home (default: the zip's)"
    )
    p_unp.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_unp.add_argument("--force", action="store_true", help="overwrite even newer/diverged work")
    p_unp.set_defaults(func=_cmd_unpack)

    def query_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workspace", required=True, help="workspace folder or slug")
        p.add_argument("--version", default=None, help="draft version (default latest)")
        p.add_argument("--budget", type=int, default=query.DEFAULT_BUDGET, help="max tokens")
        p.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
        p.set_defaults(func=_cmd_query)

    p_show = sub.add_parser("show", help="table of contents, or the text of a chapter/scene")
    p_show.add_argument("unit", nargs="?", help="c03, c03.s2, c03.s2.p4, or c03.s2.p4- to continue")
    p_show.add_argument("--fp", action="store_true", help="also print paragraph fingerprints")
    query_args(p_show)
    p_find = sub.add_parser("find", help="paragraphs containing all words (or a quoted phrase)")
    p_find.add_argument("query")
    p_find.add_argument("--in", dest="within", default=None, help="limit to a chapter or scene")
    query_args(p_find)
    p_ctx = sub.add_parser(
        "context", help="a paragraph with its chapter, Codex scene and neighbours"
    )
    p_ctx.add_argument("anchor")
    query_args(p_ctx)

    p_loc = sub.add_parser("locate", help="how a writer finds a paragraph (chapter, page, words)")
    p_loc.add_argument("anchor")
    p_loc.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_loc.add_argument("--version", default=None)
    p_loc.add_argument("--json", action="store_true", help="machine-readable output")
    p_loc.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_loc.set_defaults(func=_cmd_locate)

    p_round = sub.add_parser("round", help="revision rounds: build actions, letter, status, mark")
    p_round.add_argument("action", choices=["build", "status", "letter", "mark"])
    p_round.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_round.add_argument("--version", default=None)
    p_round.add_argument("--level", choices=list(rounds.LEVELS), default=None)
    p_round.add_argument("--id", dest="action_id", default=None, help="action id for mark, e.g. A3")
    p_round.add_argument(
        "--status", choices=["pending", "accepted", "rejected", "done", "deferred"], default=None
    )
    p_round.add_argument("--reason", default=None, help="why (for mark), in the writer's words")
    p_round.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_round.set_defaults(func=_cmd_round)

    p_dc = sub.add_parser(
        "docx-comments", help="copy of the .docx with the round's actions as comments"
    )
    p_dc.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_dc.add_argument("--version", default=None)
    p_dc.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_dc.set_defaults(func=_cmd_docx_comments)

    p_rep = sub.add_parser("report", help="render the reader report (reader-report mode)")
    p_rep.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_rep.add_argument("--version", default=None)
    p_rep.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_rep.set_defaults(func=_cmd_report)

    p_kit = sub.add_parser("kit", help="build the chat kit zip (for chatbots with code execution)")
    p_kit.add_argument("--out", type=Path, default=None, help="zip path (default dist/)")
    p_kit.add_argument("--skill", action="store_true", help="a Skill zip to upload to Claude")
    p_kit.set_defaults(func=_cmd_kit)
    p_doc = sub.add_parser("doctor", help="check that this platform can run the tool")
    p_doc.add_argument(
        "--home", type=Path, default=None, help="where workspaces will live (checked, not written)"
    )
    p_doc.set_defaults(func=_cmd_doctor)

    p_val = sub.add_parser("validate", help="check an LLM-written artefact against its schema")
    p_val.add_argument("kind", choices=validate.KINDS)
    p_val.add_argument("file", help="JSON file (one object or a list), or TOML for a profile")
    p_val.add_argument(
        "--no-catalogue", action="store_true", help="skip check-id/trait cross-checks"
    )
    p_val.set_defaults(func=_cmd_validate)
    codex_cli.register(sub)
    index_cli.register(sub)
    docx_cli.register(sub)
    setup.register(sub)
    upgrade.register(sub)
    word_live.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
