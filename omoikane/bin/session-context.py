"""Print the wiki brief for the harness to add to the agent's context at session start: pending work, then the index.

Runs from the SessionStart hook (see .claude/settings.json); stdout becomes context. Prints nothing when there is
nothing to say or when Omoikane is maintaining itself (OMOIKANE_NO_CAPTURE set), so those sessions pay no tokens.

Usage: python omoikane/bin/session-context.py [--budget 12000] [--omoikane DIR]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from wikilib import OMOIKANE, review_bullets

NO_CAPTURE_ENV = "OMOIKANE_NO_CAPTURE"
# Undistilled captures listed by path; older ones are only counted. A stalled scheduler must not flood the brief.
PENDING_SESSIONS_SHOWN = 5
# Failed captures, one line each, written by session-capture.py (#103); the brief shows the count and the last one.
CAPTURE_ERRORS = ".capture-errors"
# The last error is cut here: its time, harness, session and type plus the start of the message name the failure,
# and a full 400-character message would take half the brief's remaining room (context-budget.py).
CAPTURE_ERROR_CHARS = 240
HEADER = (
    "Omoikane wiki brief follows: pending work, then the index. Open a page before touching the area it covers; "
    "domain pages hold the rules the human stated, decisions and gotchas "
    "record what earlier sessions learned the hard way. Do not write under omoikane/wiki/ during coding "
    "work: the session is captured on stop and distilled later. Rules: AGENTS.md."
)
# The index sections that hold rules and lessons (wiki-index.py HEADINGS). Each gets a floor of the brief, so many
# pages of one cannot push the others out (#75); sources, entities, concepts and queries get none, since the
# omitted line sends the agent to index.md for them and a floor there would come out of the rules.
FLOORED = ("Domain", "Decisions", "Gotchas", "Practices")


def compact_index(text: str, budget: int) -> str:
    """Drop the generated header and fill the budget entry by entry, sections in index order (PAGE_TYPES).

    Two passes. First each FLOORED section takes its first entry, and more up to a floor (half the budget shared
    among them), so some 60 domain pages cannot push every decision and gotcha out of the brief (#75). Then the
    rest of the budget fills in index order, and priority is strict: filling stops at the first entry that does
    not fit, so no source takes the room a longer decision needed. A section larger than the budget keeps its
    first entries instead of vanishing (#11). The blank line between sections counts against the budget; the
    last line, naming how many entries each section lost, does not.

    Example: compact_index("# Index\\n\\nGenerated...\\n\\n## Decisions (2)\\n\\n- [[x]] — a\\n- [[y]] — b", 40)
    returns "## Decisions (2)\\n\\n- [[x]] — a\\n\\nOmitted by budget: Decisions 1. Read omoikane/index.md for them."
    """
    sections: list[tuple[str, list[str]]] = []
    for section in [s for s in text.split("\n## ") if s.strip()][1:]:
        heading, *lines = section.rstrip().splitlines()
        sections.append((heading, [line for line in lines if line.startswith("- ")]))
    fit = [0] * len(sections)
    # Each section's first entry pays for the "\n\n" before it too; the first section has none, hence the + 2.
    limit = budget + 2

    def cost(i: int) -> int:
        """Characters the next entry of section i adds; the first also pays for "## ", the heading, a blank line
        and the separator before the section."""
        return len(sections[i][1][fit[i]]) + 1 + (len(sections[i][0]) + 6 if fit[i] == 0 else 0)

    floored = [i for i, (heading, entries) in enumerate(sections) if heading.split(" (")[0] in FLOORED and entries]
    floor = budget // (2 * len(floored)) if floored else 0
    used = 0
    for i in floored:
        spent = 0
        while fit[i] < len(sections[i][1]) and used + cost(i) <= limit and (fit[i] == 0 or spent + cost(i) <= floor):
            spent += cost(i)
            used += cost(i)
            fit[i] += 1
    for i, (_, entries) in enumerate(sections):
        while fit[i] < len(entries) and used + cost(i) <= limit:
            used += cost(i)
            fit[i] += 1
        if fit[i] < len(entries):
            break
    kept = ["\n".join(["## " + heading, "", *entries[:n]]) for (heading, entries), n in zip(sections, fit) if n]
    omitted = [f"{heading.split(' (')[0]} {len(entries) - n}"
               for (heading, entries), n in zip(sections, fit) if n < len(entries)]
    if omitted:
        kept.append(f"Omitted by budget: {', '.join(omitted)}. Read omoikane/index.md for them.")
    return "\n\n".join(kept)


def review_items(review: str) -> tuple[int, int, int]:
    """Count the top-level bullets of _review.md (review_bullets: diff lines in fences are not bullets) and,
    among them, the ticked `- [x]` proposals and rules.

    A ticked rule is counted apart: it has no diff, and only wiki-rules.py writes the AGENTS.md block.
    Example: review_items("- [x] guard: x\\n````diff\\n- old\\n ```\\n````\\n- [x] rule r: R. (s)\\n- todo y: y")
    returns (3, 1, 1).
    """
    bullets = review_bullets(review)
    rules = sum(line.startswith(("- [x] rule ", "- [X] rule ")) for line in bullets)
    approved = sum(line.startswith(("- [x]", "- [X]")) for line in bullets) - rules
    return len(bullets), approved, rules


def pending_notes(omoikane: Path) -> str:
    """Name what is known but not in the wiki yet: captured sessions waiting for /distill, open review items.

    The newest undistilled capture is where the previous session stopped; pointing at it lets the agent resume
    without waiting for the next /wrap-up.

    Example: pending_notes(Path("omoikane")) returns
    "## Pending\\n\\nCaptured sessions not yet distilled, ...\\n- `omoikane/raw/inbox/sessions/2026-09-15-e04462b2.md`".
    """
    lines: list[str] = []
    errors = omoikane / CAPTURE_ERRORS
    failed = errors.read_text(encoding="utf-8", errors="replace").splitlines() if errors.is_file() else []
    failed = [line.strip() for line in failed if line.strip()]
    if failed:
        last = failed[-1] if len(failed[-1]) <= CAPTURE_ERROR_CHARS else failed[-1][:CAPTURE_ERROR_CHARS] + " [...]"
        lines.append(f"Session capture failed {len(failed)} time{'s' if len(failed) > 1 else ''}, so sessions are "
                     f"missing; last: {last}. Fix omoikane/bin/session-capture.py, then delete "
                     f"omoikane/{CAPTURE_ERRORS}.")
    # Not name order: names carry the start day and a random id tail. The Stop hook rewrites a capture on
    # every turn, so modification time is the last activity.
    sessions = sorted((omoikane / "raw" / "inbox" / "sessions").glob("*.md"), key=lambda p: p.stat().st_mtime)
    if sessions:
        lines.append("Captured sessions not yet distilled, by last activity; the last one is where the previous "
                     "session stopped:")
        if len(sessions) > PENDING_SESSIONS_SHOWN:
            lines.append(f"- ... {len(sessions) - PENDING_SESSIONS_SHOWN} older")
        lines += [f"- `{p.relative_to(omoikane.parent).as_posix()}`" for p in sessions[-PENDING_SESSIONS_SHOWN:]]
    review = omoikane / "_review.md"
    if review.is_file():
        open_items, approved, rules = review_items(review.read_text(encoding="utf-8"))
        if open_items - approved - rules:
            lines.append(f"{open_items - approved - rules} open items in omoikane/_review.md are waiting on the "
                         "human.")
        if approved:
            lines.append(f"{approved} approved proposal{'s' if approved > 1 else ''} in omoikane/_review.md "
                         "ready to apply: apply the diff, run the tests, delete the bullet.")
        if rules:
            lines.append(f"{rules} approved rule{'s' if rules > 1 else ''} in omoikane/_review.md: the human runs "
                         "python omoikane/bin/wiki-rules.py; do not edit the AGENTS.md block yourself.")
    return "## Pending\n\n" + "\n".join(lines) if lines else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--budget", type=int, default=12_000, help="max characters of index to inject")
    # context-budget.py briefs on a generated worst-case tree, so its gate does not depend on this wiki's size.
    parser.add_argument("--omoikane", type=Path, default=OMOIKANE, help="omoikane/ tree to brief on")
    args = parser.parse_args(argv)
    if os.environ.get(NO_CAPTURE_ENV):
        return 0
    index = args.omoikane / "index.md"
    body = compact_index(index.read_text(encoding="utf-8"), args.budget) if index.is_file() else ""
    parts = [part for part in (pending_notes(args.omoikane), body) if part]
    if parts:
        # Windows consoles default to a legacy code page; the index holds UTF-8 (em dashes, non-ASCII titles).
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(HEADER + "\n\n" + "\n\n".join(parts) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - context injection must never block a session from starting
        # stderr: the Pi extension and the OpenCode plugin inject stdout into the system prompt
        print(f"session-context: error {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(0)
