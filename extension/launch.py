"""The extension's entry point: start ``lc mcp`` over the folders the writer granted.

The app runs it with uv in the unpacked bundle, so the project is already installed. An
optional folder setting the writer left empty can reach us as its unexpanded placeholder,
which is not a folder and is dropped.
"""

import sys

from litcritic.cli import main


def folders(argv: list[str]) -> list[str]:
    return [a for a in argv if a.strip() and not a.startswith("${")]


if __name__ == "__main__":
    raise SystemExit(main(["mcp", *folders(sys.argv[1:])]))
