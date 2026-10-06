"""Headless tests for the PreToolUse hook in .claude/settings.json that blocks shell edits with escapes.
Run: python -m unittest discover -s tests

Each case runs the command registered in settings.json, as Claude Code would, with a sample hook payload (#47).
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

BLOCKED = {
    "sed -i": "sed -i 's/a/b/' omoikane/bin/wikilib.py",
    "sed -i with a backup suffix": "sed -i.bak 's/a/b/' x.py",
    "sed --in-place": "sed --in-place -e 's/a/b/' x.py",
    "sed -E -i after cd": "cd tests && sed -E -i 's/(a)/\\1\\\\n/' x.py",
    "python heredoc with \\n": "python - <<'EOF'\nfrom pathlib import Path\nPath('x').write_text('a\\nb')\nEOF",
    "python3 heredoc with \\t": "python3 - <<EOF\nprint('a\\tb')\nEOF",
    "python heredoc with \\\\": "cd x && python - << 'PY'\nprint('C:\\\\Users')\nPY",
    "sed -i after a quoted script with | and ;": "sed -e 's/a|b/c/;s/d/e/' -i x.py",
    "sed -ri": "sed -ri 's/a/b/' x.py",
    "gsed -i": "gsed -i 's/a/b/' x.py",
    "sed -i on a continuation line": "sed -e 's/a/b/' \\\n  -i x.py",
    "python3.11 heredoc": "python3.11 - <<'EOF'\nprint('a\\nb')\nEOF",
    "py launcher heredoc": "py - <<'EOF'\nprint('a\\nb')\nEOF",
    "python -u heredoc": "python -u - <<'EOF'\nprint('a\\nb')\nEOF",
    "heredoc piped into python": "cat <<'EOF' | python -\nprint('a\\nb')\nEOF",
    "heredoc inside python -c": "python -c \"$(cat <<'EOF'\nprint('a\\nb')\nEOF\n)\"",
    "python heredoc with a .py in a comment": "python - <<'EOF'  # edits wikilib.py\nprint('a\\nb')\nEOF",
    "python heredoc redirected to a .py": "python - <<'EOF' > out.py\nprint('a\\nb')\nEOF",
    "sed -i in a for loop": "for f in *.py; do sed -i 's/a/b/' \"$f\"; done",
    "sed -i in an if": "if true; then sed -i 's/a/b/' x.py; fi",
    "sed -i in a group": "{ sed -i 's/a/b/' x.py; }",
    "uv run python heredoc": "uv run python - <<'EOF'\nprint('a\\nb')\nEOF",
}
ALLOWED = {
    "sed without -i": "sed -n 1,5p x.py",
    "sed to stdout": "sed 's/a/b\\n/' x.py > y.py",
    "sed -n with -in in its script": "sed -n '/ -in/p' x.md",
    "python heredoc without escapes": "python - <<'EOF'\nprint(1)\nEOF",
    "python heredoc with escapes after it": "python - <<'EOF'\nprint(1)\nEOF\necho 'a\\nb'",
    "commit message heredoc with \\n": "git commit -F - <<'EOF'\nfix: a\\nb\nEOF",
    "commit message heredoc about sed -i": "git commit -F - <<'EOF'\nfeat: block sed -i\nEOF",
    "commit message about sed -i": "git commit -m \"feat(hooks): block sed -i\"",
    "PR body about sed -i": "gh pr create --body-file - <<'EOF'\nBlocks `sed -i` and `sed --in-place`.\nEOF",
    "grep for sed -i": "grep -rn \"sed -i\" omoikane/wiki",
    "rg for sed -i": "rg -n 'sed -i' .",
    "git log grep": "git log --grep=sed -i",
    "python -c with \\n": "python -c \"print('a\\nb')\"",
    "python script reading a heredoc": "python tool.py <<'EOF'\na\\nb\nEOF",
    "a word ending in sed": "echo used -i",
    "PR title naming python": "gh pr create --title \"fix(hooks): block python heredocs\" --body-file - <<'EOF'\na\\nb\nEOF",
    "backslash-quoted heredoc about sed -i": "git commit -F - <<\\EOF\nsed -i is blocked\nEOF",
}


def hook_command() -> str:
    settings = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
    (entry,) = [e for e in settings["hooks"]["PreToolUse"] if e.get("matcher") == "Bash"]
    (hook,) = entry["hooks"]
    return str(hook["command"])


def run_hook(tool: str, command: str) -> subprocess.CompletedProcess[str]:
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}
    # Expanded here: cmd.exe, the shell=True shell on Windows, does not expand ${VAR}.
    return subprocess.run(hook_command().replace("${CLAUDE_PROJECT_DIR}", str(REPO)), shell=True,
                          input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8")


class EscapeEditGuard(unittest.TestCase):
    def test_blocks_shell_edits_that_rewrite_escapes(self) -> None:
        for name, command in BLOCKED.items():
            with self.subTest(name):
                run = run_hook("Bash", command)
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertIn("Edit tool", run.stderr)

    def test_lets_every_other_command_through(self) -> None:
        for name, command in ALLOWED.items():
            with self.subTest(name):
                run = run_hook("Bash", command)
                self.assertEqual((run.returncode, run.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
