"""Parse every PowerShell script with PowerShell's own parser. Run: python -m unittest discover -s tests

The scripts run unattended (the scheduled task), never in CI; a syntax error would surface only when the task
fires and does nothing (#42). ubuntu-latest ships pwsh; in CI a missing pwsh fails instead of skipping.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PWSH = shutil.which("pwsh")
# EscapeNonAscii: pwsh writes stdout in the console code page on Windows; a path such as C:\Users\João would
# otherwise not decode as UTF-8.
PARSE = (
    "$out = foreach ($f in $args) { $e = $null; "
    "[System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$e) | Out-Null; "
    "foreach ($x in $e) { \"${f}:$($x.Extent.StartLineNumber): $($x.Message)\" } }; "
    "ConvertTo-Json -EscapeHandling EscapeNonAscii -InputObject @($out)"
)


def parse_errors(paths: list[Path]) -> list[str]:
    """One `file:line: message` per parse error in `paths`, from a single pwsh call."""
    # -File, not -Command: only a script file receives the paths in $args.
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "parse.ps1"
        script.write_text(PARSE, encoding="utf-8")
        run = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-File", str(script), *map(str, paths)],
                             capture_output=True, text=True, encoding="utf-8", check=False)
    if run.returncode != 0:
        raise AssertionError(f"pwsh exited {run.returncode}: {run.stderr}")
    return json.loads(run.stdout)


@unittest.skipUnless(PWSH or os.environ.get("CI"), "pwsh not on PATH")
class PowerShellScripts(unittest.TestCase):
    def test_every_tracked_script_parses(self) -> None:
        # Tracked only: a .ps1 dropped into raw/inbox as a source, or a local .venv, is not ours to parse.
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.ps1"], capture_output=True, text=True,
                                 check=True).stdout.split()
        self.assertTrue(tracked)
        self.assertEqual(parse_errors([REPO / p for p in tracked]), [])

    def test_a_syntax_error_is_reported_under_a_non_ascii_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "ação" / "bad.ps1"
            bad.parent.mkdir()
            bad.write_text('param(\n    [string] $x\nif ($x) { "unclosed"\n', encoding="utf-8")
            errors = parse_errors([bad])
        self.assertTrue(errors)
        self.assertTrue(all(e.startswith(f"{bad}:") for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
