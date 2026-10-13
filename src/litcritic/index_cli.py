"""`lc index …` commands: build the literary index in bounded steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from litcritic import index_eval, packets, prepass, workspace


def _prepass(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        doc = prepass.run(ws.root, args.version, args.budget)
        path = prepass.write(ws.root, doc)
    except (workspace.WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    st = doc["stats"]
    if args.json:
        print(json.dumps({**st, "path": str(path)}, ensure_ascii=False))
    else:
        print(
            f"{st['candidates']} candidates, {st['speaker_tags']} speaker tags, "
            f"{len(doc['scenes'])} scenes; candidate list ~{st['render_tokens']} tokens "
            f"({st['render_share']:.1%} of the text)"
        )
        print(f"wrote {path}")
    return 0


def _packets(args: argparse.Namespace) -> int:
    try:
        ws = workspace.resolve(args.workspace, args.home)
        cmd = args.index_cmd
        if cmd == "plan":
            doc = packets.plan(ws.root, changed=args.changed)
            st = doc["stats"]
            if args.json:
                print(json.dumps({**st, "path": str(packets.plan_path(ws.root))}))
                return 0
            print(
                f"{st['entity_packets']} entity packet(s), {st['scene_packets']} scene packet(s) "
                f"for {st['scenes']} scene(s); largest ~{st['max_packet_tokens']} tokens; "
                f"{st['tool_calls_per_scene']} tool calls per scene "
                f"({st['tool_calls_per_scene_chained']} chaining `import --next`)"
            )
            print(f"wrote {packets.plan_path(ws.root)}")
            return 0
        doc = packets.load_plan(ws.root)
        if cmd == "packet":
            sys.stdout.write(packets.render(ws.root, doc, args.id))
            packets.mark_printed(ws.root, args.id)
            return 0
        if cmd == "import":
            raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text("utf-8")
            line = packets.import_answer(ws.root, args.id, raw)
            print(line)
            if not line.startswith("ok "):
                return 1
            if args.next:
                doc = packets.load_plan(ws.root)
                nxt = next((p["id"] for p in doc["packets"] if p["status"] != "done"), None)
                if nxt is None:
                    print("all packets done")
                else:
                    sys.stdout.write(packets.render(ws.root, doc, nxt))
                    packets.mark_printed(ws.root, nxt)
            return 0
        if args.json:
            print(json.dumps(doc["packets"], ensure_ascii=False))
        else:
            print("\n".join(packets.status_lines(doc)))
        return 0
    except (
        workspace.WorkspaceError,
        packets.PacketError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc.msg}, line {exc.lineno})") from None


def _measure(args: argparse.Namespace) -> int:
    try:
        cmd = args.index_cmd
        if cmd == "compare":
            rep = index_eval.compare(_read_json(args.answers), _read_json(args.reference))
            lines = index_eval.compare_lines(rep)
        else:
            ws = workspace.resolve(args.workspace, args.home)
            if cmd == "cost":
                rep = index_eval.cost(ws.root)
                lines = index_eval.cost_lines(rep)
            else:
                rep = index_eval.evaluate(ws.root, _read_json(args.gold))
                lines = index_eval.eval_lines(rep)
    except (
        workspace.WorkspaceError,
        packets.PacketError,
        index_eval.EvalError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print("\n".join(lines))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("index", help="build the literary index (entities, scenes) step by step")
    isub = p.add_subparsers(dest="index_cmd", required=True)
    p_pre = isub.add_parser(
        "prepass", help="find entity candidates, role titles and speaker tags (no LLM)"
    )
    p_pre.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_pre.add_argument("--version", default=None, help="draft (default latest)")
    p_pre.add_argument(
        "--budget", type=int, default=None, help="token cap for the rendered list (default 10%%)"
    )
    p_pre.add_argument("--json", action="store_true", help="print the summary as JSON")
    p_pre.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_pre.set_defaults(func=_prepass)

    def common(q: Any) -> None:
        q.add_argument("--workspace", required=True, help="workspace folder or slug")
        q.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
        q.set_defaults(func=_packets)

    p_plan = isub.add_parser("plan", help="run the pre-pass and split the work into packets")
    p_plan.add_argument(
        "--changed", action="store_true", help="only the scenes the last sync asks to re-read"
    )
    p_plan.add_argument("--json", action="store_true", help="print the plan stats as JSON")
    common(p_plan)
    p_pk = isub.add_parser(
        "packet", help="print one packet for the LLM (instructions, schema, inputs)"
    )
    p_pk.add_argument("id", help="packet id (see `lc index status`)")
    common(p_pk)
    p_imp = isub.add_parser("import", help="validate an answer and write its items in one batch")
    p_imp.add_argument("id", help="packet id")
    p_imp.add_argument("--file", required=True, help="the JSON answer, or - for stdin")
    p_imp.add_argument(
        "--next", action="store_true", help="after an ok, print the next packet still to do"
    )
    common(p_imp)
    p_st = isub.add_parser("status", help="one line per packet")
    p_st.add_argument("--json", action="store_true", help="print the packets as JSON")
    common(p_st)
    p_cost = isub.add_parser(
        "cost", help="tokens in and out, calls and wall time per packet and in total"
    )
    p_cost.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_cost.add_argument("--json", action="store_true", help="print the report as JSON")
    p_cost.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_cost.set_defaults(func=_measure)
    p_ev = isub.add_parser(
        "eval", help="score the Codex entities against a gold list (precision, recall, merges)"
    )
    p_ev.add_argument("--workspace", required=True, help="workspace folder or slug")
    p_ev.add_argument("--gold", required=True, help="gold list (JSON, tests/fixtures/gold format)")
    p_ev.add_argument("--json", action="store_true", help="print the report as JSON")
    p_ev.add_argument("--home", type=Path, default=None, help="override $LITCRITIC_HOME")
    p_ev.set_defaults(func=_measure)
    p_cmp = isub.add_parser(
        "compare", help="agreement of one packet answer with a reference answer (numbers only)"
    )
    p_cmp.add_argument("--answers", required=True, help="the answer to check (JSON)")
    p_cmp.add_argument(
        "--reference", required=True, help="the reference answer to the same packet (JSON)"
    )
    p_cmp.add_argument("--json", action="store_true", help="print the report as JSON")
    p_cmp.set_defaults(func=_measure)
