"""`lc index …` commands: build the literary index in bounded steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from litcritic import prepass, workspace


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
