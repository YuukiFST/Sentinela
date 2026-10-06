"""Exit 0 when the cross-session pass is due: at least --every distills logged since the last /synthesize.

Run by wiki-ingest.ps1 after the inbox is processed; omoikane/log.md is the only state, so a deleted or
reverted log entry changes the count the same way it changes the history.
Usage: python omoikane/bin/synthesize-due.py [--every 5]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from wikilib import OMOIKANE

OPERATION = re.compile(r"## \[\d{4}-\d{2}-\d{2}\] (\w+) \|")


def distills_since_synthesis(log: str) -> int:
    """Count `distill` headings in log.md after the last `synthesize` heading.

    Example: distills_since_synthesis("## [2026-09-10] distill | session a\\n## [2026-09-11] synthesize | 1 sessions\\n"
    "## [2026-09-12] distill | session b\\n") returns 1.
    """
    count = 0
    for line in log.splitlines():
        m = OPERATION.match(line)
        if not m:
            continue
        if m.group(1) == "synthesize":
            count = 0
        elif m.group(1) == "distill":
            count += 1
    return count


def main(argv: list[str] | None = None, log: Path = OMOIKANE / "log.md") -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, default=5, help="distills between two cross-session passes")
    args = parser.parse_args(argv)
    count = distills_since_synthesis(log.read_text(encoding="utf-8")) if log.is_file() else 0
    print(f"synthesize-due: {count} distills since the last synthesize, due at {args.every}")
    return 0 if count >= args.every else 1


if __name__ == "__main__":
    sys.exit(main())
