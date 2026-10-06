"""Headless tests for omoikane/bin/review-removals.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import contextlib
import importlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

removals = importlib.import_module("review-removals")

LOG = """# Log

## [2026-09-30] distill | session aaaaaaaa

- routed (guard) typecheck-harness-plugins: the .ts files are not typechecked (turn 4)
- routed (todo) pi-live-verification: run the Pi extension live (turn 4)
- skipped (one-off) probe: a probe (turn 2)

## [2026-09-30] synthesize | 2 sessions

- routed (rule) review-each-pr: review before merge (sessions a, b; turns 3, 3)
"""

REVIEW = """# Review queue

## [2026-09-30] distill | session aaaaaaaa

- [ ] guard (test) typecheck-harness-plugins: the .ts files are not typechecked (session aaaaaaaa, turn 4)
````diff
- todo pi-live-verification: a removed diff line is not a bullet
````
- todo pi-live-verification: run the Pi extension live (session aaaaaaaa, turn 4)

## [2026-09-30] synthesize

- [x] rule review-each-pr: Review before merge. (synthesize)
"""


class Removed(unittest.TestCase):
    # A bullet the human deleted left no trace, so the next distill filed it again (#41).
    def test_a_routed_proposal_whose_bullet_is_gone_is_removed(self) -> None:
        review = REVIEW.replace("- [ ] guard (test) typecheck-harness-plugins: the .ts files are not typechecked "
                                "(session aaaaaaaa, turn 4)\n", "")
        self.assertEqual(removals.removed(LOG, review), [("guard", "typecheck-harness-plugins")])

    def test_open_or_ticked_bullets_are_not_removed(self) -> None:
        self.assertEqual(removals.removed(LOG, REVIEW), [])

    def test_a_bullet_only_inside_a_diff_fence_is_gone(self) -> None:
        review = REVIEW.replace("- todo pi-live-verification: run the Pi extension live (session aaaaaaaa, turn 4)\n", "")
        self.assertEqual(removals.removed(LOG, review), [("todo", "pi-live-verification")])

    def test_other_bullet_shapes_still_count_as_open(self) -> None:
        # A shape the matcher misses would read as a rejection and silence a lesson the human never saw.
        log = "- routed (todo) a: x\n- routed (guard) b: y\n- routed (prompt) c: z\n"
        for review in ("   - todo a: x\n- [X] guard (lint) b: y\n- [ ] prompt (distill.md) c: z\n",
                       "- todo `a`: x\n- [ ] guard (test) `b`: y\n- [ ] prompt (distill.md) `c`: z\n"):
            with self.subTest(review=review):
                self.assertEqual(removals.removed(log, review), [])

    def test_one_slug_under_two_kinds_is_tracked_per_kind(self) -> None:
        log = "- routed (guard) a: x\n- routed (rule) a: Do a. (synthesize)\n"
        self.assertEqual(removals.removed(log, "- [ ] guard (test) a: x\n"), [("rule", "a")])

    def test_a_guard_lint_filed_is_tracked_too(self) -> None:
        self.assertEqual(removals.removed("- unguarded g\n", "# Review queue\n"), [("guard", "g")])

    def test_a_lint_item_saying_no_check_can_catch_it_is_still_open(self) -> None:
        # lint.md logs `- unguarded` for this form too, and it never says "guard" (#44 review).
        review = "- omoikane/wiki/gotchas/flaky-clock.md:12 flaky-clock: no check can catch this, because the clock\n"
        self.assertEqual(removals.removed("- unguarded flaky-clock\n", review), [])

    def test_an_unclosed_fence_records_nothing(self) -> None:
        # Everything after an unclosed fence would read as deleted; a diff context line " ````" closes a
        # four-backtick fence early and leaves the real closing line open.
        log = "- routed (todo) a: x\n- routed (todo) b: y\n"
        for review in ("````diff\n- x\n- todo a: x\n- todo b: y\n",
                       "- todo a: x\n````diff\n ````\n````\n- todo b: y\n"):
            with self.subTest(review=review), self.assertRaises(ValueError):
                removals.removed(log, review)

    def test_a_removal_is_recorded_once(self) -> None:
        log = removals.record(LOG, [("rule", "review-each-pr")], "2026-10-01")
        self.assertIn("## [2026-10-01] review | removed from _review.md\n\n- removed (rule) review-each-pr\n", log)
        self.assertEqual(removals.removed(log, "# Review queue\n"),
                         [("guard", "typecheck-harness-plugins"), ("todo", "pi-live-verification")])

    def test_a_slug_filed_again_after_its_removal_can_be_removed_again(self) -> None:
        log = removals.record(LOG, [("guard", "typecheck-harness-plugins")], "2026-10-01")
        log += "\n## [2026-10-02] distill | session bbbbbbbb\n\n- routed (guard) typecheck-harness-plugins: again (turn 1)\n"
        self.assertIn(("guard", "typecheck-harness-plugins"), removals.removed(log, "# Review queue\n"))

    def test_run_appends_to_the_log_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "log.md").write_text(LOG, encoding="utf-8")
            (root / "_review.md").write_text("# Review queue\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(removals.main(["--omoikane", str(root)]), 0)
                once = (root / "log.md").read_text(encoding="utf-8")
                removals.main(["--omoikane", str(root)])
            self.assertEqual((root / "log.md").read_text(encoding="utf-8"), once)
        self.assertEqual(once.count("- removed ("), 3)


if __name__ == "__main__":
    unittest.main()
