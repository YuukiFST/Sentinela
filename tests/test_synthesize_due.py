"""Headless tests for omoikane/bin/synthesize-due.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

due = importlib.import_module("synthesize-due")

LOG = """# Log

## [2026-09-09] init | Repository created

## [2026-09-10] distill | session aaaaaaaa
- created x
## [2026-09-11] ingest | Some article
## [2026-09-12] distill | session bbbbbbbb | nothing kept
"""


class DistillsSinceSynthesis(unittest.TestCase):
    def test_counts_every_distill_when_never_synthesized(self) -> None:
        self.assertEqual(due.distills_since_synthesis(LOG), 2)

    def test_counts_only_distills_after_the_last_synthesis(self) -> None:
        log = LOG + "## [2026-09-13] synthesize | 2 sessions\n## [2026-09-14] distill | session cccccccc\n"
        self.assertEqual(due.distills_since_synthesis(log), 1)

    def test_ignores_distill_mentioned_outside_a_heading(self) -> None:
        self.assertEqual(due.distills_since_synthesis("- see ## [2026-09-10] distill | session x\n"), 0)



class ExitCode(unittest.TestCase):
    # wiki-ingest.ps1 runs /synthesize only on exit 0.
    def test_due_at_the_threshold_and_not_below_or_without_a_log(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.md"
            log.write_text(LOG, encoding="utf-8")
            for every, code in (("2", 0), ("3", 1)):
                with self.subTest(every=every), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(due.main(["--every", every], log), code)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(due.main(["--every", "1"], Path(d) / "missing.md"), 1)

if __name__ == "__main__":
    unittest.main()
