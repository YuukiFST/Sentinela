"""Measure what every Claude Code session loads before its first prompt, and fail above the budget.

Parts: AGENTS.md (CLAUDE.md only imports it), the frontmatter of each .claude/skills/*/SKILL.md (the harness
injects every skill description), and the output of session-context.py. Also fails when the managed rules
block of AGENTS.md is missing or holds more than MAX_RULES. Runs in CI; nothing grows silently.

Tokens are estimated at 3.5 characters each, no tokenizer dependency. English prose runs nearer 4, so the
estimate errs high and the budget stays conservative.
Usage: python omoikane/bin/context-budget.py
"""
from __future__ import annotations

import importlib
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from wikilib import FRONTMATTER, MAX_RULES, OMOIKANE, PAGE_TYPES, REPO, RULES_END, RULES_START, managed_rules

session_context = importlib.import_module("session-context")
wiki_index = importlib.import_module("wiki-index")

CHARS_PER_TOKEN = 3.5
# AGENTS.md is ~1,870 tokens with an empty rules block (2026-10-01), so a full block (15 rules of at most 120
# characters plus a page pointer of up to ~90, ~65 tokens each) leaves ~13 tokens of the limit: text added to
# AGENTS.md must now pay for itself with a removal. tests/test_wiki_rules.py checks the full block against the real
# file. The brief is bounded by session-context.py's own 12,000-character index budget (~3,430 tokens) plus its
# header and pending notes; the gate measures that bound on a generated tree (worst_case_brief), since this
# repository's wiki may be small or empty (#37).
LIMITS = {"AGENTS.md": 2_800, "skill frontmatter": 600, "session brief": 4_000, "total": 7_000}


def tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def measure(agents: str, frontmatters: list[str], brief: str) -> dict[str, int]:
    """Estimated tokens per part, plus their total.

    Example: measure("x" * 35, [], "") returns {"AGENTS.md": 10, "skill frontmatter": 0, "session brief": 0,
    "total": 10}.
    """
    parts = {"AGENTS.md": tokens(agents), "skill frontmatter": sum(map(tokens, frontmatters)),
             "session brief": tokens(brief)}
    parts["total"] = sum(parts.values())
    return parts


def check(agents: str, frontmatters: list[str], brief: str, limits: dict[str, int] = LIMITS,
          brief_error: str = "") -> list[str]:
    """Return one finding per part over its limit, per problem with the managed rules block, and for a brief
    that failed: session-context.py always exits 0, so its stderr is the only sign a crash measured 0 tokens.

    Example: check("x" * 10_000, [], "") returns ["AGENTS.md: 2858 tokens, limit 2800; ...", "AGENTS.md: managed
    block markers ... not found"].
    """
    parts = measure(agents, frontmatters, brief)
    findings = [f"{name}: {used} tokens, limit {limits[name]}; move text to a page or skill read on demand "
                "before adding more" for name, used in parts.items() if used > limits[name]]
    if brief_error.strip():
        findings.append(f"session brief: session-context.py failed: {brief_error.strip()}")
    block = managed_rules(agents)
    if block is None:
        findings.append(f"AGENTS.md: managed block markers `{RULES_START}` ... `{RULES_END}` not found")
    elif len(block) > MAX_RULES:
        findings.append(f"AGENTS.md: managed block holds {len(block)} rules, cap {MAX_RULES}")
    return findings


def session_brief(*args: str) -> tuple[str, str]:
    """Run session-context.py as the SessionStart hook does, without the variable that silences it.

    Returns (stdout, stderr). Example: session_brief() returns ("Omoikane wiki brief follows: ...", "").
    """
    env = {k: v for k, v in os.environ.items() if k != "OMOIKANE_NO_CAPTURE"}
    run = subprocess.run([sys.executable, str(OMOIKANE / "bin" / "session-context.py"), *args], capture_output=True,
                         text=True, encoding="utf-8", env=env, check=False)
    return run.stdout, run.stderr


def write_worst_case(omoikane: Path) -> None:
    """Fill an omoikane/ tree past every bound of the brief: more index entries per section than the index
    budget holds, each at its longest (120 characters is the lint limit for a summary), four-digit omitted
    counts, 100 more pending captures than the brief lists, every kind of `_review.md` line it counts, and
    four-digit capture errors whose last line is past the length the brief shows.
    The index part stops within one entry (~250 characters) of its budget, since filling stops at the first
    entry that does not fit.

    Example: write_worst_case(Path(tmp) / "omoikane") writes index.md, _review.md, .capture-errors and
    raw/inbox/sessions/*.md.
    """
    entry = "- [[{slug}]] — " + "s" * 120 + " `src/module/a.py, src/module/b.py` `2026-09-30` `prune: low-value`"
    lines = ["# Index", ""]
    for kind in PAGE_TYPES:
        lines += [f"## {wiki_index.HEADINGS[kind]} (1000)", ""]
        lines += [entry.format(slug=f"{kind}-{i:04d}-" + "x" * 60) for i in range(1000)] + [""]
    sessions = omoikane / "raw" / "inbox" / "sessions"
    sessions.mkdir(parents=True)
    (omoikane / "index.md").write_text("\n".join(lines), encoding="utf-8")
    for i in range(session_context.PENDING_SESSIONS_SHOWN + 100):
        (sessions / f"2026-09-30-{i:08d}-part10.md").write_text("", encoding="utf-8")
    (omoikane / "_review.md").write_text(
        "- [ ] guard (test) a: open\n- [x] guard (test) b: approved\n- [x] prompt (distill.md) c: approved\n"
        "- [x] rule d: Do d. (synthesize)\n- [x] rule e: Do e. (synthesize)\n- todo f: open\n", encoding="utf-8")
    (omoikane / session_context.CAPTURE_ERRORS).write_text(
        "e\n" * 999 + "e" * (session_context.CAPTURE_ERROR_CHARS * 2) + "\n", encoding="utf-8")


def worst_case_brief(*args: str) -> tuple[str, str]:
    """The brief session-context.py prints for a tree past every bound, whatever this wiki holds (#37).

    Example: worst_case_brief() returns ("Omoikane wiki brief follows: ... Omitted by budget: ...", "").
    """
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "omoikane"
        write_worst_case(tree)
        return session_brief("--omoikane", str(tree), *args)


def main() -> int:
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    frontmatters = []
    for skill in sorted((REPO / ".claude" / "skills").glob("*/SKILL.md")):
        m = FRONTMATTER.match(skill.read_text(encoding="utf-8"))
        frontmatters.append(m.group(1) if m else "")
    here, here_error = session_brief()
    worst, worst_error = worst_case_brief()
    # The worst case bounds this wiki's brief. A longer brief here means the generated tree misses a bound of
    # session-context.py: measure the longer one and say so, so the tree gets fixed instead of the gate drifting.
    brief = max(here, worst, key=len)
    findings = check(agents, frontmatters, brief, brief_error="\n".join(e for e in (here_error, worst_error) if e))
    if len(here) > len(worst):
        findings.append("session brief: this wiki's brief is longer than the worst case; write_worst_case misses a "
                        "bound of session-context.py")
    for name, n in measure(agents, frontmatters, brief).items():
        print(f"{name:<18} {n:>6} / {LIMITS[name]} tokens (estimated)")
    print(f"{'':<18} session brief of this wiki: {tokens(here)} tokens")
    for f in findings:
        print(f)
    print(f"context-budget: {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
