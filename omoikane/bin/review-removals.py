"""Record in log.md the proposals and todos whose bullet the human deleted from _review.md.

Deleting a bullet is how the human rejects a proposal, and how an interactive session clears one it applied.
Either way the item is decided and must not be filed again, but the deletion left no trace, so the next /distill
of a session with the same lesson filed it again (#41). wiki-ingest.ps1 runs this before any operation; /distill
and /synthesize read the `- removed` lines.
Usage: python omoikane/bin/review-removals.py [--omoikane DIR]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from wikilib import OMOIKANE, review_lines

# `- routed (<kind>) <slug>:` from /distill and /synthesize, `- unguarded <slug>` from /lint (a guard it filed),
# `- removed (<kind>) <slug>` from this script.
EVENT = re.compile(r"^- (?:(routed|removed) \((guard|prompt|todo|rule)\)|(unguarded)) ([\w.-]+)", re.MULTILINE)


def still_open(kind: str, slug: str, lines: list[str]) -> bool:
    """Whether a line outside the fences names both the kind and the slug, as whole words; with `kind` empty, the
    slug alone.

    Loose on purpose: a bullet indented like the prompt's template, or with the slug in backticks, is still the
    human's to decide, and reading it as deleted would silence a lesson nobody saw.
    Example: still_open("todo", "a", ["   - todo `a`: x"]) returns True.
    """
    word = re.compile(rf"(?<![\w-]){re.escape(slug)}(?![\w-])")
    return any((not kind or re.search(rf"\b{kind}\b", line)) and word.search(line) for line in lines)


def removed(log: str, review: str) -> list[tuple[str, str]]:
    """(kind, slug) for each item whose last log event is `routed` and that _review.md no longer names.

    Raises ValueError when _review.md ends inside a fence: every item after it would read as deleted.
    Example: removed("- routed (guard) a: x\\n", "# Review queue\\n") returns [("guard", "a")].
    """
    # (kind, slug) -> (last event, filed by /lint). /lint files its items in two shapes, one of which ("no check
    # can catch this") never says "guard", so a /lint item is open while any line names its slug.
    last: dict[tuple[str, str], tuple[str, bool]] = {}
    for event, kind, unguarded, slug in EVENT.findall(log):
        last[(kind or "guard", slug)] = (event or "routed", bool(unguarded))
    lines = review_lines(review, strict=True)
    return [(kind, slug) for (kind, slug), (event, by_lint) in last.items()
            if event == "routed" and not still_open("" if by_lint else kind, slug, lines)]


def record(log: str, items: list[tuple[str, str]], today: str) -> str:
    """`log` with one entry listing `items` appended.

    Example: record("# Log\\n", [("rule", "a")], "2026-10-01") returns
    "# Log\\n\\n## [2026-10-01] review | removed from _review.md\\n\\n- removed (rule) a\\n".
    """
    lines = [f"- removed ({kind}) {slug}" for kind, slug in items]
    return log.rstrip("\n") + f"\n\n## [{today}] review | removed from _review.md\n\n" + "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--omoikane", type=Path, default=OMOIKANE)
    args = parser.parse_args(argv)
    log_path, review_path = args.omoikane / "log.md", args.omoikane / "_review.md"
    if not log_path.is_file() or not review_path.is_file():
        return 0
    log = log_path.read_text(encoding="utf-8")
    try:
        items = removed(log, review_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"review-removals: {exc}; nothing recorded until the fence is closed", file=sys.stderr)
        return 1
    if items:
        log_path.write_text(record(log, items, date.today().isoformat()), encoding="utf-8", newline="\n")
        print(f"review-removals: {len(items)} item(s) removed from _review.md recorded in log.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
