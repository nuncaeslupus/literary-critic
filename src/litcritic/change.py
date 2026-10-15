"""Small changes put to the writer one at a time: propose, approve, dismiss.

A proposal is a ``change.proposed`` event in the plan log (``<ws>/plan/log.jsonl``), ids
``C1``, ``C2``... Approving rebuilds the edit only from the stored proposal and writes it
through ``docx_cli.apply_edits`` (the same path as ``lc docx edits``), with the change id
as the edit id. Events: ``change.proposed``, ``change.approved``, ``change.applied``,
``change.refused``, ``change.dismissed``. A change is *live* (can be approved or
dismissed) while its last event is ``proposed`` or ``refused`` (a refused write, such as
a locked file, can be tried again).

Who proposes the new wording follows the profile's ``prose_suggestions``: ``false`` means
only the writer's own words (``--by assistant`` is refused, ``prose_off``); ``minor``
allows at most ``rounds.MAX_QUOTE_WORDS`` changed words and no new sentence; on allows
a whole paragraph, never more than one.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from litcritic import dc, docx_cli, ingest, plan, rounds, settings, workspace

DEFAULT_DISMISS = "dismissed in the chat"
LIVE = ("proposed", "refused")
SENTENCE_END = re.compile(r"[.!?…]")
_CARD = {
    "en": ("Replace «{x}» with «{y}»?", "your words", "suggested by the assistant"),
    "es": ("¿Cambiar «{x}» por «{y}»?", "tus palabras", "sugerencia del asistente"),
}


class ChangeRefused(plan.Refused):
    """A proposal or a move on a change that is not allowed (``reason`` is stable)."""


# --- the log, read as changes ------------------------------------------------


def _events(root: Path, cid: str) -> list[dict[str, Any]]:
    return [e for e in plan.read_log(root) if e.get("change") == cid]


def _changes(root: Path) -> dict[str, dict[str, Any]]:
    """Every change by id: its proposal data, its status and the last reason given."""
    out: dict[str, dict[str, Any]] = {}
    for ev in plan.read_log(root):
        name = str(ev["event"])
        cid = ev.get("change")
        if not name.startswith("change.") or not cid:
            continue
        kind = name.split(".", 1)[1]
        if kind == "proposed":
            out[cid] = {"id": cid, "status": "proposed", **(ev.get("data") or {})}
        elif cid in out:
            row = out[cid]
            row["status"] = kind
            if kind == "approved" and (ev.get("data") or {}).get("typed_by") == "writer":
                row["status"] = "typed_by_writer"
            if ev.get("reason"):
                row["reason"] = ev["reason"]
    return out


def _next_id(root: Path) -> str:
    n = sum(1 for ev in plan.read_log(root) if ev["event"] == "change.proposed")
    return f"C{n + 1}"


# --- rules -------------------------------------------------------------------


def changed_words(quote: str, replace: str) -> int:
    a, b = quote.split(), replace.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def _prose_rule(level: Any, by: str, quote: str, replace: str) -> None:
    if by != "assistant":
        return
    if level is False:
        raise ChangeRefused(
            "prose_off",
            "the profile lets only the writer's own words into the novel "
            "(prose_suggestions is off): the writer gives the new wording",
        )
    if level == "minor":
        if changed_words(quote, replace) > rounds.MAX_QUOTE_WORDS:
            raise ChangeRefused(
                "too_long",
                f"more than {rounds.MAX_QUOTE_WORDS} words change; "
                "that is not a small change, the writer types it",
            )
        if len(SENTENCE_END.findall(replace)) > len(SENTENCE_END.findall(quote)):
            raise ChangeRefused("too_long", "a small change adds no new sentence")


def _document(root: Path, name: str | None) -> Path | None:
    if name:
        return docx_cli._document(root, name)
    docs = ingest.known_documents(root, ".docx")
    return docs[-1] if docs else None


# --- commands ----------------------------------------------------------------


def card(c: dict[str, Any], lang: str) -> dict[str, Any]:
    ask, mine, theirs = _CARD.get(lang, _CARD["en"])
    suggested = c.get("proposed_by") == "assistant"
    return {
        "text": ask.format(x=c["quote"], y=c["replace"]),
        "words_by": theirs if suggested else mine,
        "suggested": suggested,
        "why": c.get("why", ""),
        "where": c.get("where"),
    }


def _where(root: Path, doc: Path, at: str, quote: str, lang: str) -> dict[str, Any] | None:
    try:
        places = docx_cli._Places(root, doc, doc.read_bytes(), lang, few=True)
        hit = places.hit(at, quote)
    except (dc.DocError, OSError, ValueError, KeyError):
        return None
    return {k: hit.get(k) for k in ("find", "unique", "locator")}


def propose(
    root: Path,
    quote: str,
    replace: str,
    *,
    by: str,
    why: str = "",
    prefix: str = "",
    suffix: str = "",
    part: str = "",
    action: str = "",
    closes: bool = False,
    again: bool = False,
    document: str | None = None,
) -> dict[str, Any]:
    if by not in ("writer", "assistant"):
        raise ChangeRefused("invalid", "say who wrote the new wording: --by writer|assistant")
    if not quote.strip():
        raise ChangeRefused("invalid", "the quote is empty")
    if quote == replace:
        raise ChangeRefused("invalid", "the new text is the same as the old")
    if closes and not action:
        raise ChangeRefused("invalid", "--closes needs the round action: --action A1")
    level = settings.load(root)["prose_suggestions"]
    _prose_rule(level, by, quote, replace)
    if "\n" in replace.strip():
        raise ChangeRefused(
            "too_long" if by == "assistant" else "not_once",
            "a change stays inside one paragraph",
        )
    if not again:
        for c in _changes(root).values():
            same = c["quote"] == quote and c["replace"] == replace
            if same and c["status"] in (*LIVE, "dismissed"):
                raise ChangeRefused(
                    "repeat",
                    f"{c['id']} already has this change ({c['status']}); "
                    "propose it again only if the writer asks (--again)",
                )
    lang = rounds.language(root)
    doc = _document(root, document)
    data: dict[str, Any] = {
        "quote": quote,
        "replace": replace,
        "prefix": prefix,
        "suffix": suffix,
        "why": why,
        "proposed_by": by,
        "closes": closes,
        "language": lang,
    }
    if doc is not None and doc.suffix.lower() == ".docx" and doc.is_file():
        try:
            at = docx_cli._resolve(doc, quote, prefix, suffix)
        except docx_cli.NotOnce as exc:
            raise ChangeRefused(
                "not_once", f"the quote is {exc}; give more of the text around it"
            ) from exc
        if not docx_cli.ADDRESS.fullmatch(at):
            raise ChangeRefused("not_once", "the quote must stay inside one paragraph")
        data["sha256"] = docx_cli._sha256(doc)
        data["document"] = docx_cli._shown(root, doc)
        data["where"] = _where(root, doc, at, quote, lang)
    refs = {k: v for k, v in (("part", part), ("action", action)) if v}
    cid = _next_id(root)
    plan.record(
        root,
        "change.proposed",
        "writer" if by == "writer" else "tool",
        change=cid,
        data=data,
        refs=refs,
    )
    return {"status": "proposed", "change": cid, "card": card(data, lang), "level": level}


def _live(root: Path, cid: str) -> dict[str, Any]:
    c = _changes(root).get(cid)
    if c is None:
        raise ChangeRefused("unknown_change", f"no change {cid}")
    if c["status"] not in LIVE:
        raise ChangeRefused("not_proposed", f"not proposed: {cid} is {c['status']}")
    return c


def _refs(root: Path, cid: str) -> dict[str, Any]:
    first = _events(root, cid)[0]
    return dict(first.get("refs") or {})


def _locate_call(text: str) -> dict[str, Any]:
    return {"target": text, "command": "lc docx locate --quote --go " + json.dumps(text)}


def approve(
    root: Path, cid: str, *, closes: bool = False, document: str | None = None
) -> tuple[dict[str, Any], int]:
    c = _live(root, cid)
    refs = _refs(root, cid)
    closes = closes or bool(c.get("closes"))
    action = str(refs.get("action", ""))
    if closes and not action:
        raise ChangeRefused("invalid", "--closes needs the round action: --action A1")
    doc = _document(root, document)
    in_place = settings.load(root)["edit_in_place"]
    if in_place is False or doc is None or doc.suffix.lower() != ".docx":
        plan.record(
            root, "change.approved", "writer", change=cid, data={"typed_by": "writer"}, refs=refs
        )
        return {
            "status": "typed_by_writer",
            "change": cid,
            "typed_by": "writer",
            "message": "nothing was written: the writer types it at the place",
            "locate": _locate_call(c["quote"]),
        }, 0
    plan.record(root, "change.approved", "writer", change=cid, refs=refs)
    edit = (cid, c["quote"], c["replace"], c.get("prefix", ""), c.get("suffix", ""))
    payload, code = docx_cli.apply_edits(root, doc, [edit], {cid: str(c.get("why", ""))})
    if code != 0:
        plan.record(
            root,
            "change.refused",
            "tool",
            change=cid,
            reason=str(payload.get("message", "")),
            data={"reason": payload.get("reason")},
            refs=refs,
        )
        return {
            "status": "refused",
            "change": cid,
            "reason": payload.get("reason"),
            "message": payload.get("message"),
        }, 1
    plan.record(
        root,
        "change.applied",
        "tool",
        change=cid,
        data={"backup": payload.get("backup"), "edit_id": cid},
        refs=refs,
    )
    out: dict[str, Any] = {
        "status": "applied",
        "change": cid,
        "backup": payload.get("backup"),
        "locate": _locate_call(c["replace"]),
    }
    if closes:
        out["action"] = rounds.mark(root, action, "done")
    return out, 0


def mark_undone(root: Path, edit_ids: list[str], op_id: str) -> str | None:
    """Log ``change.undone`` for the first of ``edit_ids`` that is an applied change."""
    known = _changes(root)
    for cid in edit_ids:
        if cid in known and known[cid]["status"] == "applied":
            plan.record(
                root,
                "change.undone",
                "tool",
                change=cid,
                data={"undid": op_id},
                refs=_refs(root, cid),
            )
            return cid
    return None


def dismiss(root: Path, cid: str, reason: str = "") -> dict[str, Any]:
    _live(root, cid)
    _state, ev = plan.record(
        root,
        "change.dismissed",
        "writer",
        change=cid,
        reason=reason.strip() or DEFAULT_DISMISS,
        refs=_refs(root, cid),
    )
    return {"status": "dismissed", "change": cid, "reason": ev["reason"]}


def status(root: Path, cid: str | None = None) -> dict[str, Any]:
    rows = _changes(root)
    if cid:
        if cid not in rows:
            raise ChangeRefused("unknown_change", f"no change {cid}")
        rows = {cid: rows[cid]}
    lang = rounds.language(root)
    return {
        "status": "ok",
        "changes": [
            {
                "id": c["id"],
                "status": c["status"],
                "reason": c.get("reason", ""),
                "card": card(c, str(c.get("language", lang))),
            }
            for c in rows.values()
        ],
    }


# --- CLI ---------------------------------------------------------------------


def _out(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _cmd(args: argparse.Namespace) -> int:
    try:
        root = workspace.resolve(args.workspace, args.home).root
        act = args.verb
        if act == "propose":
            if args.quote is None or args.replace is None:
                raise ChangeRefused("invalid", "usage: lc change propose --quote X --replace Y")
            _out(
                propose(
                    root,
                    args.quote,
                    args.replace,
                    by=args.by or "",
                    why=args.why or "",
                    prefix=args.prefix or "",
                    suffix=args.suffix or "",
                    part=args.part or "",
                    action=args.action or "",
                    closes=args.closes,
                    again=args.again,
                    document=args.document,
                )
            )
            return 0
        if act == "status":
            _out(status(root, args.change))
            return 0
        if not args.change:
            raise ChangeRefused("invalid", f"usage: lc change {act} C1")
        if act == "approve":
            out, code = approve(root, args.change, closes=args.closes, document=args.document)
            _out(out)
            return code
        _out(dismiss(root, args.change, args.reason or ""))
        return 0
    except plan.Refused as exc:
        _out({"status": "refused", "reason": exc.reason, "message": exc.message})
        return 1
    except (
        workspace.WorkspaceError,
        plan.PlanError,
        rounds.RoundError,
        docx_cli.CliError,
        dc.DocError,
        OSError,
        ValueError,
    ) as exc:
        _out({"status": "error", "message": str(exc)})
        return 2


def register(sub: Any) -> None:
    p = sub.add_parser("change", help="small changes put to the writer: propose, approve, dismiss")
    p.add_argument("verb", choices=["propose", "approve", "dismiss", "status"])
    p.add_argument("change", nargs="?", default=None, help="the change, e.g. C1")
    p.add_argument("--workspace", required=True, help="workspace folder or slug")
    p.add_argument("--quote", default=None, help="propose: the text to change, verbatim")
    p.add_argument("--prefix", default="", help="propose: text just before the quote")
    p.add_argument("--suffix", default="", help="propose: text just after the quote")
    p.add_argument("--replace", default=None, help="propose: the new text")
    p.add_argument("--why", default="", help="propose: the reason")
    p.add_argument("--by", choices=["writer", "assistant"], default=None, help="who wrote it")
    p.add_argument("--part", default=None, help="propose: the plan part it belongs to")
    p.add_argument("--action", default=None, help="propose: the round action, e.g. A7")
    p.add_argument("--closes", action="store_true", help="mark the round action done")
    p.add_argument("--again", action="store_true", help="propose it again (the writer asked)")
    p.add_argument("--reason", default=None, help="dismiss: why")
    p.add_argument("--document", default=None, help="the .docx (default: last one read)")
    p.add_argument("--home", type=Path, default=None, help="where to look for works")
    p.set_defaults(func=_cmd)
