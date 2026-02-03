#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

import re
import subprocess
from pathlib import Path

README_PATH = Path(__file__).resolve().parents[1] / "README.md"
START_MARKER = "<!-- CLI-PARAMS-START -->"
END_MARKER = "<!-- CLI-PARAMS-END -->"


def _render_cli_block() -> str:
    result = subprocess.run(
        ["uv", "run", "autopkg_wrapper", "--help"],
        check=True,
        text=True,
        capture_output=True,
    )
    help_text = result.stdout.rstrip()
    return "\n".join(
        [
            START_MARKER,
            "",
            "```shell",
            help_text,
            "```",
            "",
            END_MARKER,
        ]
    )


def _replace_block(content: str, block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    if not pattern.search(content):
        raise SystemExit("CLI markers not found in README.md")
    return pattern.sub(block, content)


def main() -> None:
    content = README_PATH.read_text(encoding="utf-8")
    updated = _replace_block(content, _render_cli_block())
    README_PATH.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
