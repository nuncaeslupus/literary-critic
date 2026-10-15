"""The writer's open Word: done by doc-control's live engine, or by the agent's computer use.

doc-control owns the live engine that drives an open Word (``live.*`` operations, its
``live`` extra). ``lc word`` first asks it: when ``lc`` runs on the writer's computer, with
Word open on the document, the operation is done and the answer is ``{"status": "done",
"how": "live", ...}``. Otherwise (Cowork's sandbox, no Word, the document not open in it)
the answer is ``{"status": "manual", "how": "computer-use", "steps": [...], "writer":
"..."}``: the steps the agent performs with computer use, and the plain instruction for
the writer when computer use is not available. It also carries ``live``: the doc-control
MCP tool and arguments that would do it, for an agent that has doc-control's MCP server
on the writer's computer, and why the engine could not. Its ``doc`` is the file name
alone: the sandbox's path means nothing on the writer's computer, and doc-control (0.6.1+)
resolves a bare name to the one open document of that name. literary-critic builds no
live-Word code of its own.

``locate`` is fed by ``lc docx locate``: its whole answer is a valid request
(``document``, ``path``, ``at``, ``find``, ``unique``, ``paragraphs_after``, ``locator``;
``find`` may also come from the locator alone). The live engine selects the paragraph by
its address ``at``, which it checks against the open document, or, without one, by the
``find`` phrase. A live call that fails, or takes longer than ``LIVE_TIMEOUT``, leaves the
steps to do it. Edits never go through
Word: ``lc docx edits`` / ``rename`` change the file while Word has it closed, and these
operations only save, close, reopen and bring Word to the passage.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from litcritic import dc, locate

# operation -> request keys it needs
OPERATIONS: dict[str, tuple[str, ...]] = {
    "locate": ("document", "find"),
    "apply_edits": ("document", "edits"),
    "rename": ("document", "old", "new", "case_sensitive"),
    "save": ("document",),
    "close": ("document", "save"),
    "reopen": ("document",),
    "selection": ("document",),
}
MANUAL_KEYS = ("status", "how", "steps", "writer")
# request keys that may be absent
OPTIONAL = {"locate": ("locator", "language", "unique", "paragraphs_after", "path", "at")}
# operation -> doc-control live operation that does it
LIVE = {
    "locate": "live.select",
    "save": "live.save",
    "close": "live.close",
    "reopen": "live.open",
    "selection": "live.selection",
}


class WordLiveError(Exception):
    """A request that cannot be answered (unknown operation, missing keys)."""


# Word for Windows translates its shortcuts along with its menus. Measured on a Spanish
# Word (16.0.17932, `Application.FindKey`): Ctrl+F indents the paragraph, Ctrl+S
# underlines and Ctrl+W resets the paragraph's formatting; Find is Ctrl+B. Shift+F12
# (save) and Ctrl+F4 (close) do the same in every language, so the steps use those,
# and Find names its key by language.
WINDOWS_FIND = {"English": "Ctrl+F", "Spanish": "Ctrl+B"}


@dataclass(frozen=True)
class Keys:
    """How the agent reaches Word and its commands on the writer's system."""

    switch: str
    find: str
    land: str
    save: str
    close: str


def _keys(platform: str) -> Keys:
    if platform == "darwin":
        land = (
            "Press Enter: Word selects the passage. Close the search box; leave the "
            "selection for the writer to see."
        )
        return Keys("click Word in the Dock", "Press Cmd+F", land, "Cmd+S", "Cmd+W")
    by_language = ", ".join(f"{key} in {lang}" for lang, key in WINDOWS_FIND.items())
    find = (
        f"Open Word's search with the key for the language of its menus ({by_language}; "
        "in any other language click Find on the Home tab: a wrong key changes the "
        "paragraph's formatting)"
    )
    # Measured on the same Word: the pane searches by itself about two seconds after the
    # typing stops; an Enter before that goes to the previous search's result.
    land = (
        "Wait until the result count under the search box is for what you typed: Word "
        "searches by itself a moment after the typing stops and selects the passage (an "
        "Enter before that jumps to the previous search's result). Then press Enter, and "
        "Esc to close the search pane; the selection stays for the writer to see."
    )
    return Keys("click Word in the taskbar", find, land, "Shift+F12", "Ctrl+F4")


def _name(payload: dict[str, Any]) -> str:
    return Path(str(payload.get("document", "the document"))).name


def _where(locator: Any, lang: str) -> str:
    """The writer's locator line (as everywhere else in the tool), or "" when incomplete."""
    if not isinstance(locator, dict):
        return ""
    needed = ("chapter", "first_words", "last_words")
    if not all(isinstance(locator.get(k), str) and locator[k] for k in needed):
        return ""
    try:
        return locate.describe(locate.from_where({"anchor": "", **locator}), lang)
    except (TypeError, ValueError):
        return ""


def _below(payload: dict[str, Any]) -> int:
    """Paragraphs to move down from where Find lands (0 when it lands on the passage)."""
    if payload.get("unique", True) is not False:
        return 0
    try:
        return max(int(payload.get("paragraphs_after") or 0), 0)
    except (TypeError, ValueError):
        return 0


def manual(op: str, payload: dict[str, Any], platform: str = sys.platform) -> dict[str, Any]:
    """What the agent does with computer use, and what to tell the writer otherwise."""
    keys = _keys(platform)
    name = _name(payload)
    steps: list[str]
    if op == "locate":
        steps = [
            f"Bring Word to the front with {name} open ({keys.switch}).",
            f"{keys.find}, then type exactly: {payload['find']}",
            keys.land,
        ]
        if below := _below(payload):
            steps.append(
                f"Find lands on a paragraph above the passage: move down {below} "
                "paragraph(s) (Down arrow) and select that one."
            )
        steps.append("If nothing is found, tell the writer where it is in plain words instead.")
        lang = str(payload.get("language") or "en")
        where = _where(payload.get("locator"), lang)
        if lang == "es":
            writer = f"En {name}: {where}." if where else f"En {name}, busca «{payload['find']}»."
        else:
            writer = (
                f"In {name}: {where}." if where else f"In {name}, look for “{payload['find']}”."
            )
    elif op in ("apply_edits", "rename"):
        steps = [
            f"Run `lc docx status` first. If {name} is open in Word, save and close it "
            f"({keys.save}, then {keys.close}), or ask the writer to.",
            "Apply the change with `lc docx edits` or `lc docx rename`.",
            f"Reopen {name} in Word (double-click it in its folder); the change is "
            "already written into the text, and a backup was kept.",
        ]
        writer = f"Please save and close {name} in Word; I will tell you when to open it again."
    elif op == "save":
        steps = [f"Bring Word to the front ({keys.switch}) and press {keys.save}."]
        writer = f"Please save {name} in Word."
    elif op == "close":
        both = f"press {keys.save}, then {keys.close}"
        verb = both if payload.get("save") else f"press {keys.close}"
        steps = [
            f"Bring Word to the front ({keys.switch}) and {verb}.",
            "If Word asks whether to save, answer as the writer decided; never discard "
            "their unsaved work without asking.",
        ]
        writer = (
            f"Please save and close {name} in Word."
            if payload.get("save")
            else f"Please close {name} in Word; when it asks, choose not to save."
        )
    elif op == "reopen":
        steps = [f"Open {name} from its folder (double-click it) and bring Word to the front."]
        writer = f"You can open {name} again now."
    else:  # selection
        steps = [
            "Bring Word to the front and read the selected text from the screen.",
            "Pass the first words to `lc docx locate` to find it in the document.",
        ]
        writer = "Please copy the passage you mean and paste it here."
    return {"status": "manual", "how": "computer-use", "steps": steps, "writer": writer}


def _with_find(payload: dict[str, Any]) -> dict[str, Any]:
    """A ``locate`` request with ``find`` taken from its locator when not given."""
    locator = payload.get("locator")
    if locator is not None and not isinstance(locator, dict):
        raise WordLiveError("locator must be the object `lc docx locate` prints")
    if payload.get("find") or not isinstance(locator, dict) or not locator.get("find"):
        return payload
    return {**payload, "find": locator["find"]}


def _unfindable(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The answer for a passage Word's search cannot reach, when its locator says where it is.

    `lc docx locate` gives no Find string for a paragraph with no phrase of its own that
    types into the Find box (it repeats others, or its words hold a soft or no-break hyphen).
    """
    if payload.get("find") or not payload.get("document"):
        return None
    lang = str(payload.get("language") or "en")
    where = _where(payload.get("locator"), lang)
    if not where:
        return None
    name = _name(payload)
    steps = ["Word's search cannot find this passage: tell the writer where it is in plain words."]
    writer = f"En {name}: {where}." if lang == "es" else f"In {name}: {where}."
    return {"status": "manual", "how": "computer-use", "steps": steps, "writer": writer}


LIVE_TIMEOUT = 10.0  # seconds a live call may take before the steps take over
FIND_CODES = {"^p": "\r", "^t": "\t", "^^": "^"}  # Word's Find-box codes with a plain form


def _phrase(find: str) -> str | None:
    """A Find-box string as the plain phrase ``live.select`` takes, or None when it
    holds a code with no plain form (``^u173``, ``^-``, ``^~``…)."""
    out, k = [], 0
    while k < len(find):
        code = find[k : k + 2]
        if find[k] == "^":
            if code not in FIND_CODES:
                return None
            out.append(FIND_CODES[code])
            k += 2
        else:
            out.append(find[k])
            k += 1
    return "".join(out)


def place(found: dict[str, Any], lang: str) -> dict[str, Any]:
    """One ``live_places`` entry for what ``lc docx locate`` found: its button's label, the
    paragraph's address, and Word's search phrase as the fallback when the address fails
    (only a phrase found once: elsewhere it would land on the wrong paragraph)."""
    found = _with_find(found)
    loc = found.get("locator")
    if isinstance(loc, dict) and _where(loc, lang):
        approx = "" if loc.get("page_exact") else "≈"
        first = loc["first_words"]
        label = (
            f"Capítulo {loc['chapter']}, pág. {approx}{loc['page']}"
            if lang == "es"
            else f"Chapter {loc['chapter']}, p. {approx}{loc['page']}"
        )
        if first not in loc["chapter"]:  # the heading itself needs no quote
            label += f": «{first}…»" if lang == "es" else f": “{first}…”"
    else:
        label = f"“{found.get('find') or found.get('at')}”"
    out: dict[str, Any] = {"label": label, "at": str(found["at"])}
    if found.get("unique") and (phrase := _phrase(str(found.get("find") or ""))):
        out["find_phrase"] = phrase
    return out


def _request(op: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The doc-control live request for ``op``; None when it has none (no full path, or a
    passage with neither its address nor a phrase Word's search could type)."""
    if op not in LIVE:
        return None
    doc = str(payload.get("path") or payload.get("document") or "")
    if not Path(doc).is_absolute():
        return None
    request: dict[str, Any] = {"doc": doc}
    if op == "locate":
        # the cursor at the passage's start, centred and in front: nothing selected, so a
        # key pressed by the writer cannot replace the passage
        request["mode"] = "cursor"
        if payload.get("at"):
            request["at"] = str(payload["at"])
        elif phrase := _phrase(str(payload.get("find") or "")):
            request["find_phrase"] = phrase
            if payload.get("paragraphs_after"):
                request["paragraphs_after"] = int(payload["paragraphs_after"])
        else:
            return None
    elif op == "close":
        request["save"] = bool(payload.get("save"))
    elif op == "reopen":
        request["app"] = "word"
    return request


_POOL: concurrent.futures.ThreadPoolExecutor | None = None


def _thread() -> concurrent.futures.ThreadPoolExecutor:
    """The one thread every live call runs on. doc-control's Word engine keeps its COM
    handle across calls, and a COM handle answers only on the thread that made it: a call
    from another thread sees no open document (so an approved edit falls to the file and
    is refused as locked, and ``locate`` does not move the cursor)."""
    global _POOL
    if _POOL is None:
        _POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="live")
    return _POOL


def run(name: str, request: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
    """doc-control's ``name`` on the live thread, given up after ``timeout`` seconds
    (raises ``dc.DocError``). A call that times out leaves its thread stuck, so the next
    call starts a new one."""
    global _POOL
    future = _thread().submit(dc.run, name, request)
    try:
        return future.result(timeout=timeout)
    except TimeoutError as exc:
        stuck, _POOL = _POOL, None
        if stuck is not None:
            stuck.shutdown(wait=False)
        raise dc.DocError("LIVE_TIMEOUT", f"Word did not answer in {timeout:g}s") from exc


def _timed(name: str, request: dict[str, Any]) -> dict[str, Any]:
    """doc-control's ``name``, given up after ``LIVE_TIMEOUT`` (raises ``dc.DocError``)."""
    return run(name, request, LIVE_TIMEOUT)


def open_documents() -> list[Path]:
    """Full paths of the documents open in Word (or another live app), empty when none
    can be reached: no live engine, no Word running, or no answer in time."""
    try:
        docs = _timed("live.status", {}).get("documents") or []
    except dc.DocError:
        return []
    return [Path(d["path"]) for d in docs if isinstance(d, dict) and d.get("path")]


def is_open(doc: Path) -> bool:
    """Whether the live engine holds ``doc`` open (Word or LibreOffice), so approved
    edits go into the open document instead of the file."""
    want = os.path.normcase(str(doc.resolve()))
    return any(os.path.normcase(str(d.resolve())) == want for d in open_documents())


def write(request: dict[str, Any]) -> dict[str, Any]:
    """One ``doc.batch`` in the open document (``engine: "live"``). The request carries
    ``"tracked": false``, so the edit is a plain write; an older doc-control refuses that
    with ``SCHEMA_INVALID``. Raises ``dc.DocError``."""
    return run("doc.batch", {**request, "engine": "live"})


def _live(op: str, request: dict[str, Any]) -> dict[str, Any]:
    """Run ``op`` in the open Word through doc-control (raises ``dc.DocError``, also when
    Word takes longer than ``LIVE_TIMEOUT`` or a passage is not found)."""
    result = _timed(LIVE[op], request)
    if op == "locate" and (not result.get("at") or result.get("selected") is False):
        raise dc.DocError("NOT_SELECTED", "Word did not go to the passage")
    return result


def _done(op: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "done", "how": "live"}
    if op == "locate":
        out["selected"] = result.get("text", "")
        lang = str(payload.get("language") or "en")
        where = _where(payload.get("locator"), lang) or (
            "el cursor está al principio del pasaje en Word"
            if lang == "es"
            else "the cursor is at the start of the passage in Word"
        )
        out["writer"] = f"{'En' if lang == 'es' else 'In'} {_name(payload)}: {where}."
    elif op == "selection":
        out["selected"] = result.get("text", "")
        out["paragraph"] = result.get("paragraph")
    else:
        out["result"] = {k: v for k, v in result.items() if not k.startswith("_")}
    return out


def call(op: str, payload: dict[str, Any], platform: str = sys.platform) -> dict[str, Any]:
    """One operation done in the open Word, or its computer-use steps and writer line."""
    if op not in OPERATIONS:
        raise WordLiveError(f"unknown operation {op!r}; one of {', '.join(OPERATIONS)}")
    if op == "locate":
        payload = _with_find(payload)
    request = _request(op, payload)
    if request is not None:
        try:
            return _done(op, payload, _live(op, request))
        except dc.DocError as exc:
            why = {"code": exc.code, "message": exc.message}
    if op == "locate" and (plain := _unfindable(payload)):
        return _with_live(plain, op, request, why if request else None)
    missing = [k for k in OPERATIONS[op] if k not in payload or payload[k] in ("", None)]
    if missing:
        raise WordLiveError(f"{op} needs {', '.join(missing)}")
    return _with_live(manual(op, payload, platform), op, request, why if request else None)


def _with_live(
    out: dict[str, Any], op: str, request: dict[str, Any] | None, why: dict[str, str] | None
) -> dict[str, Any]:
    """A manual answer, with the doc-control MCP call that would do it and why it was not."""
    if request is None:
        return out
    tool = LIVE[op].replace(".", "_")  # doc-control's MCP tool names
    # the bare file name: doc-control resolves it to the open document of that name
    arguments = {**request, "doc": PurePath(request["doc"]).name}
    return {**out, "live": {"tool": tool, "arguments": arguments, "error": why}}


def _cmd(args: Any) -> int:
    try:
        raw = args.payload
        inline = raw.lstrip().startswith(("{", "["))
        payload = json.loads(raw if inline else Path(raw).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("the payload must be a JSON object")
        out = call(args.op, payload)
    except (WordLiveError, ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("word", help="steps for the open Word, done with computer use")
    p.add_argument("op", choices=list(OPERATIONS))
    p.add_argument(
        "--payload",
        required=True,
        help="the request: JSON, or a JSON file (for locate, what `lc docx locate` printed)",
    )
    p.set_defaults(func=_cmd)
