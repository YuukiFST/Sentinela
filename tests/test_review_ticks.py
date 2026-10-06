"""Headless tests for omoikane/bin/review-ticks.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

ticks = importlib.import_module("review-ticks")

BEFORE = "# Review queue\n\n- [x] guard (test) a: approved by the human (session 1, turn 1)\n- [ ] rule b: Do b. (synthesize)\n"


class UntickNew(unittest.TestCase):
    def test_a_tick_the_agent_added_is_undone_and_the_human_ones_kept(self) -> None:
        # Approval is the human's act; the scheduled run can edit _review.md, so it could approve itself.
        after = BEFORE.replace("- [ ] rule b", "- [x] rule b") + "- [X] rule c: Do c. (synthesize)\n- [ ] prompt d: new\n"
        text, undone = ticks.untick_new(BEFORE, after)
        self.assertEqual(undone, 2)
        self.assertEqual(text, BEFORE + "- [ ] rule c: Do c. (synthesize)\n- [ ] prompt d: new\n")

    def test_nothing_changes_when_the_agent_ticked_nothing(self) -> None:
        after = BEFORE + "- todo e: e\n"
        self.assertEqual(ticks.untick_new(BEFORE, after), (after, 0))


class LostBullets(unittest.TestCase):
    # Filing is append-only. A bullet the run deleted would be recorded by review-removals.py as the human's
    # decision, forever (#41).
    def test_bullets_the_run_deleted_or_rewrote_are_named(self) -> None:
        after = BEFORE.replace("- [ ] rule b: Do b. (synthesize)\n", "- [ ] rule b: Do b better. (synthesize)\n")
        after = after.replace("- [x] guard (test) a: approved by the human (session 1, turn 1)\n", "")
        self.assertEqual(ticks.lost_bullets(BEFORE, after + "- todo new: appended\n"),
                         ["- [x] guard (test) a: approved by the human (session 1, turn 1)",
                          "- [ ] rule b: Do b. (synthesize)"])

    def test_appending_loses_nothing(self) -> None:
        self.assertEqual(ticks.lost_bullets(BEFORE, BEFORE + "\n## [2026-10-01] distill\n\n- todo new: x\n"), [])


if __name__ == "__main__":
    unittest.main()
