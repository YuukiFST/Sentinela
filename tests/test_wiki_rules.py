"""Headless tests for omoikane/bin/wiki-rules.py and context-budget.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

from wikilib import MAX_RULES, RULES_END, RULES_START, managed_rules  # noqa: E402

rules = importlib.import_module("wiki-rules")
budget = importlib.import_module("context-budget")


def agents_md(*lines: str) -> str:
    return "# Manual\n\n## Rules\n\n" + "\n".join([RULES_START, *lines, RULES_END]) + "\n\n## Domain\n"


REVIEW = """# Review queue

Intro.

## [2026-10-01] synthesize

- [x] rule eval-in-clone: Run the headless eval in a throwaway clone before a prompt PR. (synthesize)
- [ ] rule english-commits: Write commit messages in English. (synthesize)
- todo other: something else (synthesize)
"""


class Promote(unittest.TestCase):
    def test_ticked_rule_moves_into_the_block_and_leaves_the_queue(self) -> None:
        agents, review, problems = rules.promote(agents_md(), REVIEW, {"eval-in-clone", "english-commits"})
        self.assertEqual(problems, [])
        self.assertEqual(managed_rules(agents), [
            "- Run the headless eval in a throwaway clone before a prompt PR. "
            "(omoikane/wiki/practices/eval-in-clone.md)"])
        self.assertNotIn("eval-in-clone", review)
        self.assertIn("- [ ] rule english-commits", review)
        self.assertIn("- todo other", review)
        self.assertTrue(agents.startswith("# Manual\n\n## Rules\n\n") and agents.endswith("\n\n## Domain\n"))

    def test_at_the_cap_nothing_enters_and_the_proposal_stays(self) -> None:
        full = agents_md(*[f"- rule {i} (omoikane/wiki/practices/r{i}.md)" for i in range(MAX_RULES)])
        agents, review, problems = rules.promote(full, REVIEW, {"eval-in-clone"})
        self.assertEqual(agents, full)
        self.assertEqual(review, REVIEW)
        self.assertEqual(problems, [f"eval-in-clone: the block holds {MAX_RULES} rules, the cap; remove one from "
                                    "AGENTS.md first"])

    def test_a_domain_rule_points_at_its_domain_page(self) -> None:
        # A rule the user stated once ("every table has a tenant_id") governs every task, but only practice
        # pages could be promoted (#76).
        review = "- [x] rule every-table-has-a-tenant-id: Every table has a `tenant_id` column. (synthesize)\n"
        agents, left, problems = rules.promote(agents_md(), review, set(), {"every-table-has-a-tenant-id"})
        self.assertEqual(problems, [])
        self.assertEqual(managed_rules(agents), ["- Every table has a `tenant_id` column. "
                                                 "(omoikane/wiki/domain/every-table-has-a-tenant-id.md)"])
        self.assertEqual(left, "")

    def test_the_script_promotes_from_the_pages_it_finds_and_holds_disputed_ones(self) -> None:
        # The domain glob in main() had no test, and a page could turn Disputed between proposal and tick (#86 review).
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "AGENTS.md").write_text(agents_md(), encoding="utf-8")
            (repo / "omoikane" / "wiki" / "domain").mkdir(parents=True)
            for slug, summary in (("tenant", "Every table has a tenant_id"), ("money", "Disputed: cents or decimal")):
                (repo / "omoikane" / "wiki" / "domain" / f"{slug}.md").write_text(
                    f"---\ntitle: {slug}\ntype: domain\nsummary: {summary}\n---\n", encoding="utf-8")
            (repo / "omoikane" / "_review.md").write_text(
                "- [x] rule tenant: Every table has a `tenant_id`. (synthesize)\n"
                "- [x] rule money: Money is integer cents. (synthesize)\n", encoding="utf-8")
            run = subprocess.run([sys.executable, str(Path(rules.__file__)), "--repo", str(repo)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
            self.assertEqual(managed_rules((repo / "AGENTS.md").read_text(encoding="utf-8")),
                             ["- Every table has a `tenant_id`. (omoikane/wiki/domain/tenant.md)"])
            self.assertIn("money: omoikane/wiki/domain/money.md is disputed", run.stdout)

    def test_a_slug_both_a_practice_and_a_domain_page_is_refused(self) -> None:
        block = agents_md("- Old text. (omoikane/wiki/practices/x.md)")
        agents, _, problems = rules.promote(block, "- [x] rule x: New text. (synthesize)\n", {"x"}, {"x"})
        self.assertEqual(agents, block)
        self.assertIn("both a practice and a domain page", problems[0])

    def test_refuses_a_rule_without_its_practice_page(self) -> None:
        agents, review, problems = rules.promote(agents_md(), REVIEW, set())
        self.assertEqual((agents, review), (agents_md(), REVIEW))
        self.assertEqual(problems, ["eval-in-clone: no page omoikane/wiki/practices/eval-in-clone.md or "
                                    "omoikane/wiki/domain/eval-in-clone.md"])

    def test_refuses_a_rule_longer_than_one_short_line(self) -> None:
        review = f"- [x] rule long: {'x' * (rules.MAX_RULE_CHARS + 1)} (synthesize)\n"
        _, left, problems = rules.promote(agents_md(), review, {"long"})
        self.assertEqual(left, review)
        self.assertEqual(problems, [f"long: rule is {rules.MAX_RULE_CHARS + 1} chars, limit {rules.MAX_RULE_CHARS}"])

    def test_a_rule_already_promoted_is_not_added_twice(self) -> None:
        once, _, _ = rules.promote(agents_md(), REVIEW, {"eval-in-clone"})
        twice, review, problems = rules.promote(once, REVIEW, {"eval-in-clone"})
        self.assertEqual(managed_rules(twice), managed_rules(once))
        self.assertNotIn("eval-in-clone", review)
        self.assertEqual(problems, [])

    def test_several_ticked_rules_stop_at_the_cap(self) -> None:
        almost = agents_md(*[f"- rule {i} (omoikane/wiki/practices/r{i}.md)" for i in range(MAX_RULES - 1)])
        review = "- [x] rule a: Do a. (synthesize)\n- [X] rule b: Do b. (synthesize)\r\n"
        agents, left, problems = rules.promote(almost, review, {"a", "b"})
        self.assertEqual(len(managed_rules(agents) or []), MAX_RULES)
        self.assertEqual(left, "- [X] rule b: Do b. (synthesize)\r\n")
        self.assertEqual(problems, [f"b: the block holds {MAX_RULES} rules, the cap; remove one from AGENTS.md first"])

    def test_only_the_last_parenthetical_is_the_reference(self) -> None:
        review = "- [x] rule p: Use pytest (not unittest). (synthesize; replaces q)\n"
        agents, _, _ = rules.promote(agents_md(), review, {"p"})
        self.assertEqual(managed_rules(agents), ["- Use pytest (not unittest). (omoikane/wiki/practices/p.md)"])

    def test_refuses_what_it_cannot_parse_or_would_break_the_block(self) -> None:
        once, _, _ = rules.promote(agents_md(), REVIEW, {"eval-in-clone"})
        for review, problem in (
                ("- [x] rule a: Do a.\n", "- [x] rule a: Do a.: no trailing (reference); not promoted"),
                (f"- [x] rule a: Do {RULES_END} a. (synthesize)\n", "a: rule contains `<!--`"),
                ("- [x] rule eval-in-clone: Other text. (synthesize)\n",
                 "eval-in-clone: omoikane/wiki/practices/eval-in-clone.md already has a rule; remove it first")):
            with self.subTest(review=review):
                agents, left, problems = rules.promote(once, review, {"a", "eval-in-clone"})
                self.assertEqual((agents, left, problems), (once, review, [problem]))

    def test_missing_block_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            rules.promote("# Manual\n", REVIEW, {"eval-in-clone"})


class ContextBudget(unittest.TestCase):
    LIMITS = {"AGENTS.md": 100, "skill frontmatter": 50, "session brief": 100, "total": 200}

    def test_within_budget_is_clean(self) -> None:
        self.assertEqual(budget.check(agents_md(), ["name: a"], "brief", self.LIMITS), [])

    def test_a_part_over_its_limit_is_a_finding(self) -> None:
        findings = budget.check(agents_md() + "x" * 400, [], "", self.LIMITS)
        self.assertEqual(len(findings), 1)
        self.assertRegex(findings[0], r"^AGENTS\.md: \d+ tokens, limit 100")

    def test_parts_under_their_limits_can_exceed_the_total(self) -> None:
        findings = budget.check(agents_md() + "x" * 250, ["x" * 170], "x" * 340, self.LIMITS)
        self.assertEqual(len(findings), 1)
        self.assertRegex(findings[0], r"^total: \d+ tokens, limit 200")

    def test_a_full_block_of_long_rules_fits_the_agents_limit(self) -> None:
        # A promotion the cap allows must not turn CI red. Slugs come from page titles, so 60 characters is real.
        agents = (Path(budget.REPO) / "AGENTS.md").read_text(encoding="utf-8")
        # The rules already promoted are emptied out: the worst case is MAX_RULES rules, all at the length cap.
        agents = agents[:agents.index(RULES_START) + len(RULES_START)] + "\n" + agents[agents.index(RULES_END):]
        slugs = [f"{i:02d}-" + "s" * 57 for i in range(MAX_RULES)]
        review = "".join(f"- [x] rule {s}: {'r' * rules.MAX_RULE_CHARS} (synthesize)\n" for s in slugs)
        full, _, problems = rules.promote(agents, review, set(slugs))
        self.assertEqual((len(managed_rules(full) or []), problems), (MAX_RULES, []))
        self.assertEqual([f for f in budget.check(full, [], "") if f.startswith("AGENTS.md")], [])

    def test_a_failing_brief_is_a_finding(self) -> None:
        # session-context.py never exits non-zero; a crash would measure 0 tokens and pass.
        self.assertEqual(budget.check(agents_md(), [], "", self.LIMITS, brief_error="Traceback: boom"),
                         ["session brief: session-context.py failed: Traceback: boom"])

    def test_worst_case_brief_reaches_the_cap_without_the_repository_wiki(self) -> None:
        # In CI the wiki was empty, so the brief limit never bit (#37). The generated tree is past every bound,
        # so raising the brief's cap in session-context.py turns the last assertion red.
        brief, error = budget.worst_case_brief()
        self.assertEqual(error, "")
        self.assertIn("Omitted by budget: Domain", brief)
        self.assertIn("- ... 100 older", brief)
        for line in ("open items", "approved proposals", "approved rules", "Session capture failed 1000 times"):
            self.assertIn(line, brief)
        self.assertEqual([f for f in budget.check(agents_md(), [], brief) if f.startswith("session brief")], [])

    def test_block_over_the_cap_or_missing_is_a_finding(self) -> None:
        over = agents_md(*[f"- r{i}" for i in range(MAX_RULES + 1)])
        self.assertIn(f"AGENTS.md: managed block holds {MAX_RULES + 1} rules, cap {MAX_RULES}",
                      budget.check(over, [], "", {k: 10_000 for k in self.LIMITS}))
        self.assertIn(f"AGENTS.md: managed block markers `{RULES_START}` ... `{RULES_END}` not found",
                      budget.check("# Manual\n", [], "", self.LIMITS))


if __name__ == "__main__":
    unittest.main()
