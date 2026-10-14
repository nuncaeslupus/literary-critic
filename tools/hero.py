"""Compose the README's hero image — an editor's sheet for literary-critic.

Not shipped code. Writes docs/hero.svg, then rasterises it to docs/hero.png,
and docs/logo.svg to docs/logo.png, with a headless Chromium (the README shows
the PNGs: GitHub's `<img>` view of an SVG loads no fonts, so the PNG is what
keeps the faces). Needs the Inter,
DejaVu Sans Mono and Liberation Serif fonts installed for the PNG to match, and
Pillow to crop.

The sheet deliberately carries no version or counts: a PNG cannot follow the
repo, so anything that changes on a release stays off it.

Usage, from the repository root:

    python3 tools/hero.py           # write docs/hero.svg, docs/hero.png and docs/logo.png
    CHROMIUM=/path/to/chrome python3 tools/hero.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT_SVG = ROOT / "docs" / "hero.svg"
OUT_PNG = ROOT / "docs" / "hero.png"
OUT_LOGO = ROOT / "docs" / "logo.png"

#: The GitHub social-preview size, which the README shows scaled to its column.
W, H = 1280, 640

GROUND = "#f3efe6"
GRID = "#e6e0d3"
LINE = "#cfc6b4"
INK = "#1f1c18"
DIM = "#756d60"
ACCENT = "#8b2c3a"  # the logo's oxblood
MARK = "#c0392b"  # the editor's red pencil
PAPER = "#fffdf8"
SANS = "Inter, 'DejaVu Sans', sans-serif"
DISPLAY = "'Inter Display', Inter, sans-serif"
MONO = "'DejaVu Sans Mono', monospace"
SERIF = "'Liberation Serif', 'DejaVu Serif', serif"
NEST = "\u203a"  # the chapter-to-scene separator in an anchor path
MONO_EM = 0.602  # DejaVu Sans Mono advance, in em


def serif_width(s: str, size: float) -> float:
    """Advance of `s` in the page's serif, from the installed face (fc-match)."""
    from PIL import ImageFont

    path = subprocess.run(
        ["fc-match", "-f", "%{file}", "Liberation Serif"], capture_output=True, text=True
    ).stdout
    return ImageFont.truetype(path, 100).getlength(s) * size / 100


def text(
    x: float,
    y: float,
    s: str,
    *,
    size: float,
    fill: str = INK,
    family: str = SANS,
    weight: int = 400,
    anchor: str = "start",
    spacing: float = 0,
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'letter-spacing="{spacing}" xml:space="preserve">{escape(s)}</text>'
    )


def nested(path: Path, x: float, y: float, size: float) -> str:
    src = path.read_text().strip()
    inner = src[src.index(">") + 1 : src.rindex("</svg>")]
    return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 64 64">{inner}</svg>'


def sheet() -> list[str]:
    """Grid, border with zone marks, registration marks — the claude-arsenal family."""
    out = [f'<rect width="{W}" height="{H}" fill="{GROUND}"/>']
    for x in range(0, W, 20):
        out.append(
            f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{GRID}" '
            f'stroke-width="{1 if x % 100 == 0 else 0.4}"/>'
        )
    for y in range(0, H, 20):
        out.append(
            f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{GRID}" '
            f'stroke-width="{1 if y % 100 == 0 else 0.4}"/>'
        )
    out.append(
        f'<rect x="16" y="16" width="{W - 32}" height="{H - 32}" fill="none" stroke="{LINE}"/>'
    )
    out.append(
        f'<rect x="30" y="30" width="{W - 60}" height="{H - 60}" fill="none" '
        f'stroke="{DIM}" stroke-width="1.5"/>'
    )
    zw = (W - 60) / 8
    for i in range(8):
        x = 30 + zw * i
        if i:
            out += [
                f'<line x1="{x}" y1="16" x2="{x}" y2="30" stroke="{LINE}"/>',
                f'<line x1="{x}" y1="{H - 30}" x2="{x}" y2="{H - 16}" stroke="{LINE}"/>',
            ]
        for y in (27, H - 19):
            out.append(
                text(x + zw / 2, y, str(8 - i), size=9, fill=DIM, family=MONO, anchor="middle")
            )
    zh = (H - 60) / 4
    for i in range(4):
        y = 30 + zh * i
        if i:
            out += [
                f'<line x1="16" y1="{y}" x2="30" y2="{y}" stroke="{LINE}"/>',
                f'<line x1="{W - 30}" y1="{y}" x2="{W - 16}" y2="{y}" stroke="{LINE}"/>',
            ]
        for x in (23, W - 23):
            out.append(
                text(x, y + zh / 2 + 3, "ABCD"[i], size=9, fill=DIM, family=MONO, anchor="middle")
            )
    for cx, cy in ((48, 48), (48, H - 48)):
        out += [
            f'<circle cx="{cx}" cy="{cy}" r="7" fill="none" stroke="{ACCENT}"/>',
            f'<line x1="{cx - 11}" y1="{cy}" x2="{cx + 11}" y2="{cy}" stroke="{ACCENT}"/>',
            f'<line x1="{cx}" y1="{cy - 11}" x2="{cx}" y2="{cy + 11}" stroke="{ACCENT}"/>',
        ]
    return out


#: One rule in every hero: the logo tile is 0.95 x the wordmark's font size, centred on
#: its capital band (baseline to cap height, 0.727 em), with a quarter-em gap before it.
WORD_SIZE, WORD_BASE, LOGO_X = 100, 160, 64
LOGO_SIZE = round(0.95 * WORD_SIZE)
LOGO_Y = round(WORD_BASE - 0.727 * WORD_SIZE / 2 - LOGO_SIZE / 2)
TEXT_X = LOGO_X + LOGO_SIZE + round(0.25 * WORD_SIZE)


def wordmark() -> list[str]:
    return [
        nested(ROOT / "docs" / "logo.svg", LOGO_X, LOGO_Y, LOGO_SIZE),
        f'<text x="{TEXT_X}" y="{WORD_BASE}" font-family="{DISPLAY}" '
        f'font-size="{WORD_SIZE}" font-weight="800" letter-spacing="-3">'
        f'<tspan fill="{INK}">literary-</tspan><tspan fill="{ACCENT}">critic</tspan></text>',
        text(LOGO_X, 210, "Editor-grade feedback on a whole novel.", size=27, fill="#3b362f"),
        text(
            LOGO_X,
            244,
            "Index · analyse · advise, across drafts — the writer writes",
            size=17,
            fill=DIM,
        ),
    ]


PANEL_Y, PANEL_H = 300, 206


def panel(x: float, w: float, step: str, title: str) -> list[str]:
    return [
        f'<rect x="{x + 3}" y="{PANEL_Y + 4}" width="{w}" height="{PANEL_H}" fill="{INK}" '
        'fill-opacity="0.07"/>',
        f'<rect x="{x}" y="{PANEL_Y}" width="{w}" height="{PANEL_H}" fill="{PAPER}" '
        f'stroke="{LINE}"/>',
        text(x, PANEL_Y - 10, step, size=9.5, fill=ACCENT, family=MONO, weight=700, spacing=1.5),
        text(x + w, PANEL_Y - 10, title, size=9.5, fill=DIM, family=MONO, anchor="end"),
    ]


def wavy(x: float, y: float, w: float) -> str:
    d = f"M {x:.1f} {y}" + " q 1.75 -2.2 3.5 0 t 3.5 0" * max(1, round(w / 7))
    return f'<path d="{d}" fill="none" stroke="{MARK}" stroke-width="1.3"/>'


def manuscript() -> list[str]:
    """Index: the draft, cut into stable anchors the rest of the work points at."""
    x, w = 64, 380
    out = panel(x, w, "1 · INDEX", f"ch 3 {NEST} sc 2")
    lx, size, lead = x + 54, 14.5, 22
    y = PANEL_Y + 36
    first = "Mara turned from the window, her grey"
    out.append(text(x + 14, y, "p14", size=9.5, fill=ACCENT, family=MONO))
    out.append(text(lx, y, first, size=size, family=SERIF))
    gx = lx + serif_width("Mara turned from the window, her ", size)
    out.append(wavy(gx, y + 4, serif_width("grey", size)))
    out.append(text(lx, y + lead, "eyes on the empty harbour.", size=size, family=SERIF))
    for i, (anchor, widths) in enumerate((("p15", (300, 288, 170)), ("p16", (296, 230)))):
        ty = y + lead * (2.6 + i * 3.4)
        out.append(text(x + 14, ty, anchor, size=9.5, fill=ACCENT, family=MONO))
        for j, bw in enumerate(widths):
            out.append(
                f'<rect x="{lx}" y="{ty + j * lead - 8}" width="{bw}" height="6" rx="3" '
                f'fill="{GRID}"/>'
            )
    out.append(f'<path d="M {x + 40} {PANEL_Y + 14} V {PANEL_Y + PANEL_H - 14}" stroke="{GRID}"/>')
    return out


def codex() -> list[str]:
    """Analyse: what the book says about itself, each fact tied to its text."""
    x, w = 476, 330
    out = panel(x, w, "2 · ANALYSE", "codex · character")
    out.append(text(x + 18, PANEL_Y + 36, "Mara Vell", size=19, weight=700))
    out.append(
        text(
            x + w - 18,
            PANEL_Y + 36,
            f"first seen ch 1 {NEST} sc 1",
            size=11,
            fill=DIM,
            anchor="end",
        )
    )
    rows = [
        ("eyes", "grey", "p14", INK),
        ("eyes", "brown", "p212", MARK),
        ("setup", "the brass key", "p40", INK),
        ("payoff", "—", "open", DIM),
    ]
    for i, (k, v, a, c) in enumerate(rows):
        ry = PANEL_Y + 68 + i * 22
        out.append(text(x + 18, ry, k, size=11.5, fill=DIM, family=MONO))
        out.append(text(x + 92, ry, v, size=13, fill=c))
        out.append(text(x + w - 18, ry, a, size=11.5, fill=ACCENT, family=MONO, anchor="end"))
    cy = PANEL_Y + PANEL_H - 36
    out.append(
        f'<rect x="{x + 18}" y="{cy}" width="{w - 36}" height="24" rx="12" fill="#f7e4e1" '
        f'stroke="{MARK}"/>'
    )
    out.append(
        text(
            x + w / 2,
            cy + 16,
            "finding · continuity · eye colour",
            size=11.5,
            fill=MARK,
            family=MONO,
            anchor="middle",
        )
    )
    return out


def advice() -> list[str]:
    """Advise: revision actions in rounds, structural first, each with a status."""
    x, w = 838, 380
    out = panel(x, w, "3 · ADVISE", "round 1")
    items = [
        (
            "STRUCTURE",
            ["The midpoint lands too early: move", "the harbour fire into ch 9."],
            "open",
        ),
        (
            "SCENE",
            [f"ch 3 {NEST} sc 2 repeats the beat", f"of ch 2 {NEST} sc 4 — cut or turn it."],
            "open",
        ),
        ("LINE", ["Mara's eyes: grey at p14,", "brown at p212."], "fixed · draft 3"),
    ]
    for i, (level, lines, status) in enumerate(items):
        iy = PANEL_Y + 30 + i * 60
        out.append(
            text(x + 18, iy, level, size=9.5, fill=ACCENT, family=MONO, weight=700, spacing=1)
        )
        done = status != "open"
        out.append(
            text(
                x + w - 18,
                iy,
                ("✓ " if done else "○ ") + status,
                size=10,
                fill="#3f7a4f" if done else DIM,
                family=MONO,
                anchor="end",
            )
        )
        for j, line in enumerate(lines):
            out.append(text(x + 18, iy + 19 + j * 17, line, size=13, fill=INK))
    return out


def leaders() -> list[str]:
    out = []
    for x1, x2 in ((450, 470), (812, 832)):
        y = PANEL_Y + PANEL_H / 2
        out += [
            f'<path d="M {x1} {y} H {x2 - 6}" stroke="{ACCENT}" stroke-width="1.2"/>',
            f'<path d="M {x2} {y} l -7 -3.2 v 6.4 Z" fill="{ACCENT}"/>',
        ]
    return out


def title_block() -> list[str]:
    x, y, w, h = 696, 528, 522, 64
    cells = [
        (0, "PROJECT", "literary-critic"),
        (220, "SHEET", "Whole-novel editing"),
        (420, "LICENSE", "Apache-2.0"),
    ]
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{GROUND}" stroke="{DIM}" '
        'stroke-width="1.2"/>'
    ]
    for cx, label, value in cells:
        if cx:
            out.append(f'<line x1="{x + cx}" y1="{y}" x2="{x + cx}" y2="{y + h}" stroke="{DIM}"/>')
        out.append(text(x + cx + 10, y + 18, label, size=9, fill=DIM, family=MONO, spacing=1.5))
        big = label == "PROJECT"
        out.append(
            text(
                x + cx + 10,
                y + 46,
                value,
                size=19 if big else 12,
                weight=700 if big else 400,
                family=MONO,
            )
        )
    return out


def width(s: str, size: float, face: str) -> float:
    """Advance of `s` in an installed face (an fc-match pattern)."""
    from PIL import ImageFont

    path = subprocess.run(
        ["fc-match", "-f", "%{file}", face], capture_output=True, text=True
    ).stdout
    return ImageFont.truetype(path, 100).getlength(s) * size / 100


ARSENAL = "#c4623f"  # claude-arsenal's own orange


def powered_by() -> list[str]:
    """The claude-arsenal stamp, set on the frame's bottom edge: what this repo is built with."""
    lead, name, url = "built with", "claude-arsenal", "github.com/nuncaeslupus/claude-arsenal"
    tile, pad, gap = 22, 8, 8
    lead_w = width(lead, 12, "Inter")
    name_w = width(name, 15, "Inter:weight=700")
    url_w = len(url) * 10 * MONO_EM
    total = pad + tile + gap + lead_w + 6 + name_w + 12 + url_w + pad + 6
    x, cy = 72, H - 30
    tx = x + pad + tile + gap
    return [
        f'<rect x="{x}" y="{cy - 16}" width="{total:.1f}" height="32" rx="16" '
        f'fill="{GROUND}" stroke="{ARSENAL}" stroke-width="1.5"/>',
        nested(ROOT / "docs" / "claude-arsenal-logo.svg", x + pad, cy - tile / 2, tile),
        text(tx, cy + 4.3, lead, size=12, fill=DIM),
        text(round(tx + lead_w + 6, 1), cy + 5.3, name, size=15, fill=ARSENAL, weight=700),
        text(
            round(tx + lead_w + 6 + name_w + 12, 1), cy + 3.6, url, size=10, fill=DIM, family=MONO
        ),
    ]


def svg() -> str:
    parts = sheet() + wordmark() + manuscript() + codex() + advice() + leaders() + title_block()
    parts += powered_by()
    body = "\n  ".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="literary-critic: a manuscript indexed '
        f'into anchors, a codex finding, and a round of revision advice">\n  {body}\n</svg>\n'
    )


def chromium() -> str:
    for c in (
        os.environ.get("CHROMIUM"),
        "/opt/pw-browsers/chromium",
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ):
        if c and Path(c).exists():
            return c
    sys.exit("hero: no Chromium found; set CHROMIUM=/path/to/chrome")


def shoot(svg_src: str, out: Path, w: int, h: int) -> None:
    """Rasterise `svg_src` at 2x through headless Chromium into `out`."""
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "shot.html"
        html.write_text(
            '<html><body style="margin:0;background:transparent">' + svg_src + "</body></html>"
        )
        subprocess.run(
            [
                chromium(),
                "--headless=new",
                "--no-sandbox",
                "--force-device-scale-factor=2",
                "--hide-scrollbars",
                "--default-background-color=00000000",
                f"--window-size={w},{h + 200}",
                f"--screenshot={out}",
                html.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    # Headless Chromium's viewport is shorter than its window; shoot tall, crop.
    from PIL import Image

    with Image.open(out) as shot:
        shot.crop((0, 0, w * 2, h * 2)).save(out, optimize=True)


def main() -> None:
    OUT_SVG.write_text(svg())
    shoot(svg(), OUT_PNG, W, H)
    # The README heading's 40px logo, from the same source as the hero's tile.
    logo = (
        (ROOT / "docs" / "logo.svg")
        .read_text()
        .replace("<svg ", '<svg width="128" height="128" ', 1)
    )
    shoot(logo, OUT_LOGO, 128, 128)
    for out in (OUT_SVG, OUT_PNG, OUT_LOGO):
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
