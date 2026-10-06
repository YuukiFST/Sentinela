"""Shared helpers for the wiki scripts: frontmatter parsing and page discovery."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# omoikane/ holds everything the wiki owns; its parent is the repository (the system being built, in build mode).
OMOIKANE = Path(__file__).resolve().parent.parent
REPO = OMOIKANE.parent
WIKI = OMOIKANE / "wiki"
REQUIRED_KEYS = ("title", "type", "summary", "tags", "created", "updated", "sources")
# Order matters: wiki-index.py and session-context.py emit groups in this order, most useful to a coding agent first.
# Domain pages (business rules, design system, organisation conventions the user stated) lead: they govern the code
# being written, so the brief cuts them last (#64).
PAGE_TYPES = ("domain", "decision", "gotcha", "practice", "concept", "entity", "source", "query")
# A practice page must cite at least this many distinct sessions: one session is distill's job, not a pattern.
PRACTICE_MIN_SESSIONS = 2
# wiki/sources/session-<YYYY-MM-DD>-<id8>[-part<n>].md; the id tail names the session across its parts.
SESSION_PAGE = re.compile(r"wiki/sources/session-\d{4}-\d{2}-\d{2}-([0-9A-Za-z]+)(?:-part\d+)?\.md\Z")
# Source pages carry `dated`: the date the source itself bears. Not in REQUIRED_KEYS so older pages of other types keep passing.
SOURCE_KEYS = ("dated",)
# Optional on any page: repository paths the page is about. wiki-lint.py fails when one no longer exists or is absolute.
CODE_KEY = "code"
# Required on gotcha pages: the check that catches the mistake today, `none` when only the page does.
GUARD_KEY = "guard"
GUARDS = ("lint", "test", "hook", "none")
# Optional, set by /prune on a page the human should delete or merge; the agent never deletes a page itself.
PRUNE_KEY = "prune"
PRUNE_MARKS = ("stale", "redundant", "low-value")
# The block of AGENTS.md that wiki-rules.py manages. Every session loads AGENTS.md, so the cap keeps promoted
# rules from crowding out the hand-written ones: adherence drops for all rules as the file grows.
RULES_START = "<!-- omoikane:rules:start -->"
RULES_END = "<!-- omoikane:rules:end -->"
MAX_RULES = 15
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
UNDATED = "unknown"
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
# A fence line: up to three spaces, then three or more backticks or tildes (group 1), then the info string.
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass
class Page:
    path: Path
    slug: str
    meta: dict[str, object] = field(default_factory=dict)
    body: str = ""
    links: set[str] = field(default_factory=set)

    @property
    def rel(self) -> str:
        return self.path.relative_to(REPO).as_posix() if self.path.is_relative_to(REPO) else self.path.as_posix()


def parse_frontmatter(text: str) -> tuple[dict[str, object], str] | None:
    """Parse the YAML subset the page contract uses: scalars and inline lists.

    Example: parse_frontmatter("---\\ntitle: A\\ntags: [x, y]\\n---\\nbody")
    returns ({"title": "A", "tags": ["x", "y"]}, "body").
    """
    m = FRONTMATTER.match(text)
    if not m:
        return None
    meta: dict[str, object] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith("#"):
            continue
        key, _, raw = line.partition(":")
        raw = raw.split("  #")[0].strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            meta[key.strip()] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            meta[key.strip()] = raw
    return meta, text[m.end():]


def managed_rules(agents: str) -> list[str] | None:
    """The bullet lines between RULES_START and RULES_END, or None when either marker is missing.

    Example: managed_rules("x\\n<!-- omoikane:rules:start -->\\n- Do y.\\n<!-- omoikane:rules:end -->\\n")
    returns ["- Do y."].
    """
    start, end = agents.find(RULES_START), agents.find(RULES_END)
    if start < 0 or end < start:
        return None
    return [line for line in agents[start + len(RULES_START):end].splitlines() if line.startswith("- ")]


def review_lines(review: str, strict: bool = False) -> list[str]:
    """The lines of _review.md outside fenced blocks.

    A proposal carries its diff in a fence, and a removed diff line starts with "- ". Fences follow CommonMark:
    at most three spaces of indent, closed by the same character repeated at least as often. Proposals open
    with four backticks so a diff context line such as " ```" cannot close them. `strict` raises ValueError
    when the text ends inside a fence: every line after a broken fence would be missing from the result.
    Example: review_lines("- [x] guard: x\\n````diff\\n- old\\n ```\\n````\\n- todo y: y")
    returns ["- [x] guard: x", "- todo y: y"].
    """
    lines: list[str] = []
    fence = ""
    for line in review.splitlines():
        m = FENCE.match(line)
        if fence:
            if m and m.group(1).startswith(fence) and not m.group(2).strip():
                fence = ""
        elif m:
            fence = m.group(1)
        else:
            lines.append(line)
    if strict and fence:
        raise ValueError(f"_review.md ends inside a {fence} fence")
    return lines


def review_bullets(review: str) -> list[str]:
    """The top-level `- ` bullets of _review.md, outside fenced blocks (review_lines).

    Example: review_bullets("- [x] guard: x\\n````diff\\n- old\\n````\\n- todo y: y")
    returns ["- [x] guard: x", "- todo y: y"].
    """
    return [line for line in review_lines(review) if line.startswith("- ")]


def load_pages(wiki: Path = WIKI) -> list[Page]:
    pages: list[Page] = []
    for path in sorted(wiki.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        parsed = parse_frontmatter(text)
        meta, body = parsed if parsed else ({}, text)
        links = {slug.strip() for slug in WIKILINK.findall(body)}
        pages.append(Page(path=path, slug=path.stem, meta=meta, body=body, links=links))
    return pages
