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

A *cleanup* (``kind: cleanup``) is one change for a mechanical fix in many places, such as
doubled spaces: a doc-control recipe from ``CLEANUPS``, approved with one click, which
runs the recipe again and writes every place it finds (``docx_cli.apply_ops``). It is
typography, not wording, so ``prose_suggestions`` does not limit it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from litcritic import dc, docx_cli, ingest, plan, rounds, settings, word_live, workspace

DEFAULT_DISMISS = "dismissed in the chat"
LIVE = ("proposed", "refused")
SENTENCE_END = re.compile(r"[.!?…]")
_CARD = {
    "en": ("Replace «{x}» with «{y}»?", "your words", "suggested by the assistant"),
    "es": ("¿Cambiar «{x}» por «{y}»?", "tus palabras", "sugerencia del asistente"),
}
# the card's buttons and settled words, in the novel's language
_BUTTONS = {
    "en": {
        "approve": "Approve",
        "dismiss": "Dismiss",
        "approve_all": "Approve all",
        "dismiss_all": "Dismiss all",
        "go": "Show in Word",
        "approved": "✓ Approved",
        "typed": "✓ Approved: you type it in",
        "dismissed": "Dismissed",
        "undone": "Undone",
        "applying": "Applying the change in Word…",
        "dismissing": "Dismissing…",
        "finding": "Finding it in Word…",
        "not_found": "Could not find that place in Word.",
        "change": "Change",
        "changes": "Changes",
    },
    "es": {
        "approve": "Aprobar",
        "dismiss": "Descartar",
        "approve_all": "Aprobar todos",
        "dismiss_all": "Descartar todos",
        "go": "Ver en Word",
        "approved": "✓ Aprobado",
        "typed": "✓ Aprobado: lo escribes tú",
        "dismissed": "Descartado",
        "undone": "Deshecho",
        "applying": "Aplicando el cambio en Word…",
        "dismissing": "Descartando…",
        "finding": "Buscando en Word…",
        "not_found": "No he encontrado ese sitio en Word.",
        "change": "Cambio",
        "changes": "Cambios",
    },
}


# The cleanups one card may offer: doc-control recipes whose every edit is a mechanical
# text fix, each named for the writer. One Approve writes every place the recipe finds.
CLEANUPS = {
    "collapse-spaces": {
        "en": "several spaces in a row become one",
        "es": "varios espacios seguidos pasan a ser uno",
    },
    "trim-trailing-spaces": {
        "en": "spaces at the end of a paragraph are removed",
        "es": "se quitan los espacios al final de un párrafo",
    },
    "leading-spaces": {
        "en": "spaces typed at the start of a paragraph are removed",
        "es": "se quitan los espacios escritos al principio de un párrafo",
    },
    "ellipsis-char": {
        "en": "three dots become the ellipsis character (…)",
        "es": "tres puntos pasan a ser el carácter de puntos suspensivos (…)",
    },
    "typographic-apostrophe": {
        "en": "a straight apostrophe becomes the typographic one (’)",  # noqa: RUF001
        "es": "el apóstrofo recto pasa a ser el tipográfico (’)",  # noqa: RUF001
    },
    "dashes-em": {
        "en": "two or three hyphens between words become a dash (—)",
        "es": "dos o tres guiones entre palabras pasan a ser una raya (—)",
    },
    "es-dialogue-dash": {
        "en": "a line of dialogue opened with a hyphen or short dash gets a long dash (—)",
        "es": "un diálogo abierto con guion o semirraya pasa a abrirse con raya (—)",
    },
    "es-space-before-punctuation": {
        "en": "the space before a punctuation mark is removed",
        "es": "se quita el espacio antes de un signo de puntuación",
    },
    "es-space-after-punctuation": {
        "en": "a comma, semicolon or colon glued to the next word gets its space",
        "es": "a una coma, punto y coma o dos puntos pegados a la palabra siguiente se le "
        "añade el espacio",
    },
}
_CLEANUP_CARD = {
    "en": ("Fix {n} places? {what}.", "Fix 1 place? {what}.", "mechanical fix", "Fix all {n}"),
    "es": (
        "¿Corregir {n} sitios? {what}.",
        "¿Corregir 1 sitio? {what}.",
        "corrección mecánica",
        "Corregir los {n}",
    ),
}
EXAMPLES = 3  # places a cleanup's card shows
_AROUND = 24  # characters shown on each side of an example


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
            if kind == "applied":  # where it was written: its paragraph as the write left it
                row["at"] = str((ev.get("data") or {}).get("at") or "")
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
    if c.get("kind") == "cleanup":
        return _cleanup_card(c, lang)
    ask, mine, theirs = _CARD.get(lang, _CARD["en"])
    suggested = c.get("proposed_by") == "assistant"
    return {
        "text": ask.format(x=c["quote"], y=c["replace"]),
        "words_by": theirs if suggested else mine,
        "suggested": suggested,
        "why": c.get("why", ""),
        "where": c.get("where"),
        "buttons": _BUTTONS.get(lang, _BUTTONS["en"]),
    }


def _cleanup_card(c: dict[str, Any], lang: str) -> dict[str, Any]:
    many, one, by, fix_all = _CLEANUP_CARD.get(lang, _CLEANUP_CARD["en"])
    names = CLEANUPS[str(c["recipe"])]
    what = names.get(lang, names["en"])
    n = int(c.get("count") or 0)
    text = (one if n == 1 else many).format(n=n, what=what[:1].upper() + what[1:])
    buttons = dict(_BUTTONS.get(lang, _BUTTONS["en"]))
    buttons["approve"] = fix_all.format(n=n) if n > 1 else buttons["approve"]
    return {
        "text": text,
        "words_by": by,
        "suggested": False,
        "why": c.get("why", ""),
        "where": c.get("where"),
        "examples": c.get("examples") or [],
        "count": n,
        "buttons": buttons,
    }


_SAID = {
    "en": {
        "moved": "Nothing was written: the text at that place has changed since this change "
        "was proposed (it was edited or moved). Ask for the change again.",
        "unconfirmed": "The change was written, but reading that place back did not find "
        "it as expected. Check it in Word; Ctrl+Z undoes it.",
        "not_found": "Could not find that place in Word.",
        "unsaved": "Nothing was changed: the document has changes in Word that are not saved "
        "yet. Save it in Word, then approve the fix again.",
        "cleanup_word": "Nothing was changed: Word could not open the document. Open it in "
        "Word, then approve the fix again.",
        "cleanup_off": "Nothing was changed: you asked me not to change the file myself, and "
        "a fix of many places cannot be typed by hand one by one.",
        "nothing_left": "There was nothing left to fix: no place has it any more.",
    },
    "es": {
        "moved": "No se ha cambiado nada: el texto en ese sitio ya no es el que había "
        "cuando se propuso el cambio (se ha editado o movido). Pide el cambio de nuevo.",
        "unconfirmed": "El cambio se ha escrito, pero al releer ese sitio no aparece como "
        "se esperaba. Revísalo en Word; Ctrl+Z lo deshace.",
        "not_found": "No he encontrado ese sitio en Word.",
        "unsaved": "No se ha cambiado nada: el documento tiene cambios en Word sin guardar. "
        "Guárdalo en Word y vuelve a aprobar la corrección.",
        "cleanup_word": "No se ha cambiado nada: Word no ha podido abrir el documento. Ábrelo "
        "en Word y vuelve a aprobar la corrección.",
        "cleanup_off": "No se ha cambiado nada: me pediste no cambiar el archivo yo, y una "
        "corrección de muchos sitios no se puede escribir a mano uno por uno.",
        "nothing_left": "No quedaba nada que corregir: ningún sitio lo tiene ya.",
    },
}


def said(root: Path, key: str) -> str:
    """A plain message for the writer, in the novel's language."""
    return _SAID.get(rounds.language(root), _SAID["en"])[key]


def _around(c: dict[str, Any]) -> tuple[str, str]:
    """The words pinned around a change when it was proposed; the chat's prefix and
    suffix for a proposal made before changes were pinned."""
    if "before" in c:
        return str(c["before"]), str(c["after"])
    return str(c.get("prefix", "")), str(c.get("suffix", ""))


def spot(root: Path, cid: str) -> dict[str, Any]:
    """Where a change is in the document, for its card's "Show in Word" button: the text
    to find there now (the new wording once applied, the old one before), with the words
    around it that the proposal kept so the phrase is found once."""
    c = _changes(root).get(cid)
    if c is None:
        raise ChangeRefused("unknown_change", f"no change {cid}")
    if c.get("kind") == "cleanup":  # its first place: the words before it, which it keeps
        applied = c["status"] == "applied"
        return {
            "change": cid,
            "status": c["status"],
            "text": str(c.get("find") or ""),
            "at": "" if applied else str(c.get("first") or ""),
            "document": c.get("document"),
        }
    text = c["replace"] if c["status"] == "applied" else c["quote"]
    before, after = _around(c)
    return {
        "change": cid,
        "status": c["status"],
        "text": f"{before}{text}{after}",
        "at": c.get("at", "") if c["status"] == "applied" else "",
        "document": c.get("document"),
    }


def _where(root: Path, doc: Path, at: str, quote: str, lang: str) -> dict[str, Any] | None:
    try:
        places = docx_cli._Places(root, doc, docx_cli._read(doc), lang, few=True)
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
            same = c.get("quote") == quote and c.get("replace") == replace
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
        try:
            data["before"], data["after"] = docx_cli.pin(doc, quote, prefix, suffix)
        except docx_cli.NotOnce as exc:
            raise ChangeRefused(
                "not_once", f"the quote is {exc}; give more of the text around it"
            ) from exc
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


def _shown_spaces(text: str, start: int, end: int) -> str:
    """``text`` with the spaces of the run of blanks around ``start``-``end`` shown as ``·``
    (a space removed or added is invisible otherwise)."""
    while start > 0 and text[start - 1] in " 	":
        start -= 1
    while end < len(text) and text[end] in " 	":
        end += 1
    return text[:start] + text[start:end].replace(" ", "·") + text[end:]


def _example(text: str, start: int, end: int, new: str) -> dict[str, str]:
    """One place a cleanup changes: a short stretch of its paragraph before and after."""
    a, b = max(0, start - _AROUND), min(len(text), end + _AROUND)
    while a > 0 and text[a - 1] not in " 	":  # whole words at the edges
        a -= 1
    while b < len(text) and text[b] not in " 	":
        b += 1
    old = text[start:end]
    blank = not old.strip() and not new.strip()
    after_text = text[:start] + new + text[end:]
    before = _shown_spaces(text, start, end) if blank else text
    after = _shown_spaces(after_text, start, start + len(new)) if blank else after_text
    cut = len(text) - b
    return {
        "before": ("…" if a else "") + before[a:b].strip() + ("…" if cut else ""),
        "after": ("…" if a else "") + after[a : len(after) - cut].strip() + ("…" if cut else ""),
    }


def cleanup(
    root: Path,
    recipe: str,
    *,
    why: str = "",
    again: bool = False,
    document: str | None = None,
) -> dict[str, Any]:
    """Propose a cleanup: one change that fixes every place a doc-control recipe finds
    (``CLEANUPS``), approved with one click. The card shows how many places and a few of
    them; approving runs the recipe again on the document as it is then."""
    if recipe not in CLEANUPS:
        raise ChangeRefused(
            "invalid", f"no cleanup {recipe!r}; one of: {', '.join(sorted(CLEANUPS))}"
        )
    if not again:
        for c in _changes(root).values():
            if c.get("recipe") == recipe and c["status"] in LIVE:
                raise ChangeRefused(
                    "repeat", f"{c['id']} already proposes this cleanup ({c['status']})"
                )
    doc = _document(root, document)
    if doc is None or doc.suffix.lower() != ".docx" or not doc.is_file():
        raise ChangeRefused("invalid", "a cleanup needs the novel's .docx")
    run = dc.run("recipe.run", {"doc": str(doc), "recipe": recipe})
    ops = [op for op in run["batch"]["ops"] if op.get("op") == "text.replace"]
    if not ops:
        raise ChangeRefused("nothing", f"no place needs it: {recipe} finds nothing to fix")
    examples: list[dict[str, str]] = []
    texts: dict[str, str] = {}
    for op in ops:
        if len(examples) == EXAMPLES:
            break
        m = docx_cli.ADDRESS.fullmatch(str(op["at"]))
        if not m:
            continue
        para = str(op["at"]).split(":", 1)[0]
        if para in texts:  # one example per paragraph
            continue
        texts[para] = str(dc.run("para.get", {"doc": str(doc), "at": para}).get("text") or "")
        examples.append(_example(texts[para], int(m.group(3)), int(m.group(4)), op["text"]))
    lang = rounds.language(root)
    first = str(ops[0]["at"])
    para = first.split(":", 1)[0]
    m = docx_cli.ADDRESS.fullmatch(first)
    words = texts.get(para, "")[: int(m.group(3)) if m else 0].split()
    data: dict[str, Any] = {
        "kind": "cleanup",
        "recipe": recipe,
        "count": len(ops),
        "examples": examples,
        "first": para,
        "find": " ".join(words[-6:]),
        "why": why,
        "proposed_by": "assistant",
        "language": lang,
        "sha256": run["batch"]["expect"]["sha256"],
        "document": docx_cli._shown(root, doc),
    }
    cid = _next_id(root)
    plan.record(root, "change.proposed", "tool", change=cid, data=data)
    return {"status": "proposed", "change": cid, "card": card(data, lang)}


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
    root: Path,
    cid: str,
    *,
    closes: bool = False,
    document: str | None = None,
    word_only: bool = False,
) -> tuple[dict[str, Any], int]:
    """Record the writer's approval and apply the change. ``word_only`` (the desktop
    extension) writes only through Word: when Word cannot open the document, the card
    describes the change for the writer to type, as when edits in place are off."""
    c = _live(root, cid)
    if c.get("kind") == "cleanup":
        return _approve_cleanup(root, cid, c, document, word_only)
    refs = _refs(root, cid)
    closes = closes or bool(c.get("closes"))
    action = str(refs.get("action", ""))
    if closes and not action:
        raise ChangeRefused("invalid", "--closes needs the round action: --action A1")
    doc = _document(root, document)
    in_place = settings.load(root)["edit_in_place"]
    word_only = word_only or docx_cli.word_only_env()
    if doc is None or doc.suffix.lower() != ".docx":
        doc = None
    no_word = (
        word_only
        and in_place is not False
        and doc is not None
        and not (word_live.is_open(doc) or word_live.open_if_closed(doc))
    )
    if in_place is False or doc is None or no_word:
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
    # A pinned change is written only where all the words pinned around it still are.
    pinned = "before" in c
    before, after = _around(c)
    edit = (cid, c["quote"], c["replace"], before, after)
    why = {cid: str(c.get("why", ""))}
    payload, code = docx_cli.apply_edits(root, doc, [edit], why, word_only=word_only, pinned=pinned)
    if code != 0 and pinned and payload.get("reason") == "edit":
        payload = {**payload, "reason": "moved", "message": said(root, "moved")}
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
    # Read the place back: the very paragraph written, as the change leaves it (its new
    # wording alone may well be in the novel many times, as a one-word heading is).
    phrase = before + c["replace"] + after
    live = payload.get("how") == "live"
    at = str((payload.get("places") or {}).get(cid, ""))
    confirmed = not pinned or (bool(at) and docx_cli.confirm(doc, at, live))
    data = {"backup": payload.get("backup"), "edit_id": cid, "confirmed": confirmed, "at": at}
    plan.record(root, "change.applied", "tool", change=cid, data=data, refs=refs)
    if not confirmed:
        return {
            "status": "unconfirmed",
            "change": cid,
            "reason": "unconfirmed",
            "message": said(root, "unconfirmed"),
            "backup": payload.get("backup"),
        }, 1
    out: dict[str, Any] = {
        "status": "applied",
        "change": cid,
        "backup": payload.get("backup"),
        "locate": _locate_call(phrase),
    }
    if payload.get("how"):
        out["how"] = payload["how"]  # "live": in the open document, the writer saves
        out["locate"]["live"] = {"doc": str(doc), "find_phrase": phrase}
        if at:
            out["locate"]["live"] = {"doc": str(doc), "at": at}
    if closes:
        out["action"] = rounds.mark(root, action, "done")
    return out, 0


def _approve_cleanup(
    root: Path, cid: str, c: dict[str, Any], document: str | None, word_only: bool
) -> tuple[dict[str, Any], int]:
    """Approve a cleanup: run its recipe on the document as it is now and write every place
    it finds in one batch. Open in Word, it is written there only when Word holds no
    unsaved changes (the recipe reads the saved file, so its places must be Word's too);
    otherwise to the file, all or nothing, with a backup."""
    refs = _refs(root, cid)

    def refused(reason: str, message: str) -> tuple[dict[str, Any], int]:
        plan.record(
            root,
            "change.refused",
            "tool",
            change=cid,
            reason=message,
            data={"reason": reason},
            refs=refs,
        )
        return {"status": "refused", "change": cid, "reason": reason, "message": message}, 1

    doc = _document(root, document)
    if settings.load(root)["edit_in_place"] is False:
        return refused("cleanup_off", said(root, "cleanup_off"))
    if doc is None or doc.suffix.lower() != ".docx" or not doc.is_file():
        return refused("missing", "the novel's .docx is not there")
    live = word_live.is_open(doc)
    if (word_only or docx_cli.word_only_env()) and not live:
        live = word_live.open_if_closed(doc) and word_live.is_open(doc)
        if not live:
            return refused("word_needed", said(root, "cleanup_word"))
    if live:
        try:
            dirty = bool(dc.run("live.status", {"doc": str(doc)}).get("dirty"))
        except dc.DocError:
            dirty = True  # cannot tell: as if unsaved, nothing is written
        if dirty:
            return refused("unsaved", said(root, "unsaved"))
    try:
        run = dc.run("recipe.run", {"doc": str(doc), "recipe": str(c["recipe"])})
    except dc.DocError as exc:
        return refused("error", exc.message)
    ops = [op for op in run["batch"]["ops"] if op.get("op") == "text.replace"]
    plan.record(root, "change.approved", "writer", change=cid, refs=refs)
    if not ops:
        data = {"count": 0, "edit_id": cid, "confirmed": True, "at": ""}
        plan.record(root, "change.applied", "tool", change=cid, data=data, refs=refs)
        return {
            "status": "applied",
            "change": cid,
            "count": 0,
            "message": said(root, "nothing_left"),
        }, 0
    sha = str(run["batch"]["expect"]["sha256"])
    why = str(c.get("why") or c["recipe"])
    payload, code = docx_cli.apply_ops(root, doc, ops, cid, why, sha, live)
    if code != 0:
        return refused(str(payload.get("reason") or "refused"), str(payload.get("message") or ""))
    data = {
        "backup": payload.get("backup"),
        "edit_id": cid,
        "count": len(ops),
        "confirmed": True,
        "at": "",
    }
    plan.record(root, "change.applied", "tool", change=cid, data=data, refs=refs)
    out: dict[str, Any] = {
        "status": "applied",
        "change": cid,
        "count": len(ops),
        "backup": payload.get("backup"),
    }
    if payload.get("how"):
        out["how"] = payload["how"]  # "live": in the open document, the writer saves
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
        if act == "cleanup":
            if not args.recipe:
                raise ChangeRefused("invalid", "usage: lc change cleanup --recipe collapse-spaces")
            _out(
                cleanup(
                    root,
                    args.recipe,
                    why=args.why or "",
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
    p = sub.add_parser(
        "change", help="small changes put to the writer: propose, cleanup, approve, dismiss"
    )
    p.add_argument("verb", choices=["propose", "cleanup", "approve", "dismiss", "status"])
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
    p.add_argument("--recipe", default=None, help="cleanup: e.g. collapse-spaces")
    p.add_argument("--reason", default=None, help="dismiss: why")
    p.add_argument("--document", default=None, help="the .docx (default: last one read)")
    p.add_argument("--home", type=Path, default=None, help="where to look for works")
    p.set_defaults(func=_cmd)
