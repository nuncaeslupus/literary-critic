"""`lc index …` commands: build the literary index in bounded steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from litcritic import packets, prepass, workspace


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
                if nxt is None and doc.get("new_names"):
                    print(
                        f"all packets done; {len(doc['new_names'])} new names queued: "
                        "run `lc index plan` for their entity packet"
                    )
                elif nxt is None:
                    print("all packets done")
                else:
                    sys.stdout.write(packets.render(ws.root, doc, nxt))
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
