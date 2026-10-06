"""Promote the rule proposals the human ticked in _review.md into the managed block of AGENTS.md.

Only a ticked `- [x] rule <slug>: <rule> (...)` bullet is promoted, and only while the block holds fewer than
MAX_RULES; the applied bullet leaves _review.md. The human runs this, never the scheduled headless run: its
permissions do not include this script, so an agent cannot tick a box and promote in the same run.
Usage: python omoikane/bin/wiki-rules.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from wikilib import MAX_RULES, PRUNE_KEY, REPO, RULES_END, load_pages, managed_rules

# One short imperative line; a rule that needs a paragraph is a page, not an always-loaded rule. At 120, a full
# block of MAX_RULES stays inside the AGENTS.md budget of context-budget.py.
MAX_RULE_CHARS = 120
TICKED = re.compile(r"- \[[xX]\] rule ")
# The last parenthetical is the reference (`(synthesize)`, `(synthesize; replaces <slug>)`); the rule may hold others.
TICKED_RULE = re.compile(r"- \[[xX]\] rule ([a-z0-9-]+): (.+) \([^()]*\)\s*$")


def promote(agents: str, review: str, practices: set[str], domain: frozenset[str] | set[str] = frozenset(),
            held: frozenset[str] | set[str] = frozenset()) -> tuple[str, str, list[str]]:
    """Move each ticked rule proposal of `review` into the managed block of `agents`.

    `practices` and `domain` hold the slugs of the existing practice and domain pages; a rule points at its page.
    A domain rule is valid from one statement, so it reaches the block without a second session (#76). `held` holds
    the slugs of pages now `Disputed:` or marked `prune:`, which a page can become between proposal and tick.
    Returns the new AGENTS.md, the new _review.md, and one line per proposal left in place with the reason. Raises
    ValueError when AGENTS.md has no managed block.
    Example: promote(agents, "- [x] rule s: Do y. (synthesize)\\n", {"s"}) returns
    (agents with "- Do y. (omoikane/wiki/practices/s.md)" in the block, "", []).
    """
    block = managed_rules(agents)
    if block is None:
        raise ValueError("AGENTS.md has no managed rules block")
    added: list[str] = []
    kept: list[str] = []
    problems: list[str] = []
    for line in review.splitlines(keepends=True):
        m = TICKED_RULE.match(line)
        if not m:
            if TICKED.match(line):
                problems.append(f"{line.strip()}: no trailing (reference); not promoted")
            kept.append(line)
            continue
        slug, rule = m.group(1), m.group(2).strip()
        page = f"omoikane/wiki/{'domain' if slug in domain else 'practices'}/{slug}.md"
        pointer = f"({page})"
        entry = f"- {rule} {pointer}"
        current = block + added
        if entry in current:
            continue  # promoted before; the proposal is done
        problem = ""
        if slug not in practices and slug not in domain:
            problem = f"no page omoikane/wiki/practices/{slug}.md or omoikane/wiki/domain/{slug}.md"
        elif slug in practices and slug in domain:
            problem = "both a practice and a domain page have this slug; wiki-lint.py reports it, fix that first"
        elif slug in held:
            problem = f"{page} is disputed or marked prune; settle it first"
        elif "<!--" in rule:
            problem = "rule contains `<!--`"  # would end the managed block early
        elif len(rule) > MAX_RULE_CHARS:
            problem = f"rule is {len(rule)} chars, limit {MAX_RULE_CHARS}"
        elif any(r.endswith(pointer) for r in current):
            problem = f"{page} already has a rule; remove it first"
        elif len(current) >= MAX_RULES:
            problem = f"the block holds {MAX_RULES} rules, the cap; remove one from AGENTS.md first"
        if problem:
            problems.append(f"{slug}: {problem}")
            kept.append(line)
        else:
            added.append(entry)
    if not added:
        return agents, "".join(kept), problems
    end = agents.find(RULES_END)
    return agents[:end] + "".join(f"{e}\n" for e in added) + agents[end:], "".join(kept), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO, help="repository whose AGENTS.md and omoikane/ to use")
    repo = parser.parse_args(argv).repo
    agents_path, review_path, wiki = repo / "AGENTS.md", repo / "omoikane" / "_review.md", repo / "omoikane" / "wiki"
    pages = load_pages(wiki / "practices") + load_pages(wiki / "domain")
    practices = {p.slug for p in pages if p.path.parent.name == "practices"}
    domain = {p.slug for p in pages if p.path.parent.name == "domain"}
    held = {p.slug for p in pages if PRUNE_KEY in p.meta or str(p.meta.get("summary", "")).startswith("Disputed:")}
    agents, review = agents_path.read_text(encoding="utf-8"), review_path.read_text(encoding="utf-8")
    new_agents, new_review, problems = promote(agents, review, practices, domain, held)
    if new_agents != agents:
        agents_path.write_text(new_agents, encoding="utf-8", newline="\n")
    if new_review != review:
        review_path.write_text(new_review, encoding="utf-8", newline="\n")
    for problem in problems:
        print(f"not promoted: {problem}")
    print(f"wiki-rules: {len(managed_rules(new_agents) or [])} of {MAX_RULES} rules in AGENTS.md")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
