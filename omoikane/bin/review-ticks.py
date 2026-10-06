"""Undo the `[x]` ticks a headless run added to _review.md, and fail when it deleted or rewrote a bullet.

Ticking a proposal is the human's approval. The scheduled run may edit _review.md to file proposals, so it
could also tick one; wiki-ingest.ps1 saves the file before each run and calls this after it.
Usage: python omoikane/bin/review-ticks.py --before <copy of _review.md taken before the run>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from wikilib import OMOIKANE, review_bullets

TICK = re.compile(r"- \[[xX]\] ")


def untick_new(before: str, after: str) -> tuple[str, int]:
    """Return `after` with every ticked bullet that was not ticked in `before` set back to `- [ ]`, and the count.

    Example: untick_new("- [ ] rule a: A. (s)\\n", "- [x] rule a: A. (s)\\n") returns ("- [ ] rule a: A. (s)\\n", 1).
    """
    approved = {line for line in before.splitlines() if TICK.match(line)}
    out: list[str] = []
    undone = 0
    for line in after.splitlines(keepends=True):
        if TICK.match(line) and line.rstrip("\r\n") not in approved:
            line = "- [ ] " + line[len("- [x] "):]
            undone += 1
        out.append(line)
    return "".join(out), undone


def lost_bullets(before: str, after: str) -> list[str]:
    """The bullets of `before` missing from `after`: deleted or rewritten by the run.

    Filing is append-only. A bullet the run deleted would read to review-removals.py as the human's decision (#41).
    Example: lost_bullets("- todo a: x\\n", "- todo a: y\\n") returns ["- todo a: x"].
    """
    kept = set(review_bullets(after))
    return [line for line in review_bullets(before) if line not in kept]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--before", type=Path, required=True)
    args = parser.parse_args(argv)
    review = OMOIKANE / "_review.md"
    if not review.is_file():
        return 0
    before = args.before.read_text(encoding="utf-8") if args.before.is_file() else ""
    text, undone = untick_new(before, review.read_text(encoding="utf-8"))
    if undone:
        review.write_text(text, encoding="utf-8", newline="\n")
        print(f"review-ticks: undid {undone} tick(s) the agent added to _review.md")
    lost = lost_bullets(before, text)
    for line in lost:
        print(f"review-ticks: the run deleted or rewrote: {line}")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
