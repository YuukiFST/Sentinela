"""Headless tests for omoikane/bin/headless-scope.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "omoikane" / "bin"
sys.path.insert(0, str(BIN))

scope = importlib.import_module("headless-scope")

AGENT = "omoikane-headless-test0001"
EDITABLE = ("omoikane/wiki/sources/session-x.md", "omoikane/wiki/gotchas/a.md", "omoikane/log.md", "omoikane/_review.md")
NOT_EDITABLE = ("AGENTS.md", "CLAUDE.md", "omoikane/prompts/distill.md", "omoikane/bin/wiki-lint.py",
                "omoikane/index.md", "omoikane/raw/sources/x.md", ".opencode/plugins/omoikane.ts", "tests/test_x.py",
                ".git/config", ".git/hooks/pre-commit",
                # runs as `python omoikane/bin/wiki-index.py` from inside omoikane/wiki/ (#39)
                "omoikane/wiki/omoikane/bin/wiki-index.py", "omoikane/wiki/x.py")
# No shell at all: an allowed script is code the agent can replace or shadow (#39).
NOT_RUNNABLE = ("python omoikane/bin/wiki-index.py", "python omoikane/bin/wiki-lint.py", "git status",
                "git commit -m x", "rm -rf omoikane/wiki", "curl x")
# A user config that allows everything, through the keys the scope also uses. Config maps merge key by key.
HOSTILE_USER = {
    "permission": {"*": "allow", "bash": {"*": "allow", "git *": "allow"}, "edit": {"*": "allow", "AGENTS.md": "allow"},
                   "apply_patch": "allow"},
    "agent": {"omoikane-headless": {"permission": {"bash": {"*": "allow", "git *": "allow"}, "edit": "allow"}}},
    "command": {"distill": {"agent": "build", "template": "x"}},
}


def opencode_decides(rules: list[tuple[str, str, str]], key: str, subject: str) -> str:
    """OpenCode's documented matching (opencode.ai/docs/permissions): `*` any run of characters, `?` one, and the
    last matching rule wins; a rule for permission `*` applies to every permission."""
    verdict = ""
    for permission, pattern, action in rules:
        regex = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
        if permission in ("*", key) and re.fullmatch(regex, subject, re.DOTALL):
            verdict = action
    return verdict


def flatten(permission: dict[str, object]) -> list[tuple[str, str, str]]:
    """(permission, pattern, action) in config order, as `opencode debug agent` lists them."""
    return [(key, pattern, action) for key, rules in permission.items()
            for pattern, action in (rules.items() if isinstance(rules, dict) else [("*", rules)])]


class ScopeTable:
    """The allow/deny table every OpenCode rendering must satisfy; `RULES` is the resolved rule list."""

    RULES: list[tuple[str, str, str]] = []

    def test_edits_only_wiki_pages_the_log_and_the_review_queue(self) -> None:
        for path, verdict in [(p, "allow") for p in EDITABLE] + [(p, "deny") for p in NOT_EDITABLE]:
            with self.subTest(path=path):  # type: ignore[attr-defined]
                self.assertEqual(opencode_decides(self.RULES, "edit", path), verdict)  # type: ignore[attr-defined]

    def test_runs_nothing(self) -> None:
        for command in NOT_RUNNABLE:
            with self.subTest(command=command):  # type: ignore[attr-defined]
                self.assertEqual(opencode_decides(self.RULES, "bash", command), "deny")  # type: ignore[attr-defined]

    def test_reads_the_repository_and_denies_everything_else(self) -> None:
        for key, subject, verdict in (("read", "omoikane/wiki/x.md", "allow"), ("glob", "*", "allow"),
                                      ("read", ".env", "deny"), ("read", "mcp:github:repo://x", "deny"),
                                      ("webfetch", "x", "deny"),
                                      ("websearch", "x", "deny"), ("task", "x", "deny"), ("skill", "x", "deny"),
                                      ("external_directory", "x", "deny"), ("question", "x", "deny"),
                                      ("lsp", "x", "deny")):
            with self.subTest(key=key, subject=subject):  # type: ignore[attr-defined]
                self.assertEqual(opencode_decides(self.RULES, key, subject), verdict)  # type: ignore[attr-defined]


class OpenCodeRendering(ScopeTable, unittest.TestCase):
    # The OpenCode run had no scope at all (#39). The user's rules come first, the agent's last.
    RULES = flatten(HOSTILE_USER["permission"]) + flatten(scope.opencode_config(AGENT)["agent"][AGENT]["permission"])


@unittest.skipUnless(shutil.which("opencode"), "opencode not on PATH")
class OpenCodeResolved(ScopeTable, unittest.TestCase):
    """The rules OpenCode itself resolves for the agent under a hostile user config (`opencode debug agent`)."""

    @staticmethod
    def resolve(user: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as d:
            hostile = Path(d) / "user.json"
            hostile.write_text(json.dumps(user), encoding="utf-8")
            env = {**os.environ, "OPENCODE_CONFIG": str(hostile),
                   "OPENCODE_CONFIG_CONTENT": json.dumps(scope.opencode_config(AGENT))}
            out = subprocess.run([shutil.which("opencode") or "opencode", "--pure", "debug", "agent", AGENT], cwd=REPO, env=env,
                                 stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                 check=True).stdout
        return json.loads(out)

    @classmethod
    def setUpClass(cls) -> None:
        # An explicit model: the default comes from the developer's own OpenCode state, and may be a gpt- one.
        resolved = cls.resolve({**HOSTILE_USER, "model": "anthropic/claude-sonnet-4-5"})
        cls.TOOLS = resolved["tools"]
        cls.RULES = [(r["permission"], r["pattern"], r["action"]) for r in resolved["permission"]]

    def test_offers_only_the_tools_of_the_scope(self) -> None:
        self.assertEqual(scope.unsafe_tools(self.TOOLS), [])

    def test_apply_patch_offered_to_a_gpt_model_is_refused(self) -> None:
        # A gpt- model gets apply_patch in place of edit, whatever the edit rules say, and the target of its
        # `*** Move to:` is never checked against them (#40, third review).
        tools = self.resolve({**HOSTILE_USER, "model": "openai/gpt-5"})["tools"]
        self.assertEqual(scope.unsafe_tools(tools), ["apply_patch"])


class ClaudeRendering(unittest.TestCase):
    ARGS = scope.claude_args()

    def value(self, flag: str) -> str:
        return self.ARGS[self.ARGS.index(flag) + 1]

    def test_no_shell_and_edits_only_in_scope(self) -> None:
        self.assertEqual(self.value("--tools"), "Read,Glob,Grep,Edit,Write")
        self.assertEqual(set(self.value("--allowedTools").split(",")),
                         {"Read(/**)", "Edit(/omoikane/wiki/**/*.md)", "Edit(/omoikane/log.md)",
                          "Edit(/omoikane/_review.md)"})

    def test_reads_only_the_repository_and_no_env_file(self) -> None:
        # A bare `Read` read ~/.ssh and .env; the deny also filters .env out of Glob and Grep results (probe, #40).
        self.assertEqual(self.value("--disallowedTools"), "Read(/**/.env*)")

    def test_user_settings_and_mcp_servers_are_ignored(self) -> None:
        # User-level allow rules and hooks let git through in the headless run (#25).
        self.assertEqual(self.value("--setting-sources"), "project")
        self.assertEqual(self.value("--permission-mode"), "dontAsk")
        self.assertIn("--strict-mcp-config", self.ARGS)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   capture_output=True, check=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Verify(unittest.TestCase):
    """The tree after the run, whatever the harness allowed: any change outside the scope is named (#39)."""

    def repo(self, d: str) -> Path:
        repo = Path(d)
        git(repo, "init", "-q")
        for path in ("AGENTS.md", "omoikane/log.md", "omoikane/wiki/gotchas/a.md", "omoikane/bin/wiki-index.py"):
            write(repo / path, "x\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
        write(repo / "omoikane/raw/inbox/pending.md", "dirty before the run\n")
        # Ignored the way a user's global git ignore does it; `git status` lists none of these.
        write(repo / ".git/info/exclude", ".claude/settings.local.json\n.venv/\n")
        write(repo / ".venv/lib/site.pth", "present before the run\n")
        return repo

    def test_changes_inside_the_scope_pass(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = self.repo(d)
            before = scope.snapshot(repo)
            write(repo / "omoikane/wiki/gotchas/a.md", "y\n")
            write(repo / "omoikane/wiki/concepts/b.md", "new\n")
            write(repo / "omoikane/log.md", "x\nmore\n")
            write(repo / "omoikane/raw/inbox/sessions/2026-10-01-abcdef12.md", "the Stop hook of a coding session\n")
            # Routine git work in any worktree of the repository writes these; none of it runs code (#40).
            git(repo, "config", "branch.main.remote", "origin")
            git(repo, "config", "remote.origin.url", "https://example.invalid/r.git")
            write(repo / ".git/info/refs", "written by git gc\n")
            self.assertEqual(scope.out_of_scope(before, scope.snapshot(repo)), [])

    def test_each_change_outside_the_scope_is_named(self) -> None:
        cases = {
            "AGENTS.md": lambda r: write(r / "AGENTS.md", "pwned\n"),
            "omoikane/index.md": lambda r: write(r / "omoikane/index.md", "written by the agent\n"),
            "omoikane/wiki/omoikane/bin/wiki-index.py": lambda r: write(r / "omoikane/wiki/omoikane/bin/wiki-index.py", "x"),
            "omoikane/bin/wiki-index.py": lambda r: (r / "omoikane/bin/wiki-index.py").unlink(),
            "MANUAL.md": lambda r: git(r, "mv", "AGENTS.md", "MANUAL.md"),
            "head moved": lambda r: git(r, "commit", "-q", "--allow-empty", "-m", "agent"),
            "index moved": lambda r: (write(r / "omoikane/log.md", "staged\n"), git(r, "add", "omoikane/log.md")),
            # apply_patch's `*** Move to:` onto a path the user's git ignores (#40, third review)
            ".claude/settings.local.json": lambda r: (r / ".claude").mkdir() or
            (r / "omoikane/wiki/gotchas/a.md").rename(r / ".claude/settings.local.json"),
            ".venv/lib/site.pth": lambda r: write(r / ".venv/lib/site.pth", "import os; os.system('x')\n"),
            # Exempt is the script's own log, not every name that starts like it.
            "omoikane/.wiki-ingest.log.ps1": lambda r: write(r / "omoikane/.wiki-ingest.log.ps1", "x"),
            # git status and git commit run right after the agent, and they run hooks and read the config.
            ".git/hooks/pre-commit": lambda r: write(r / ".git/hooks/pre-commit", "#!/bin/sh\ncurl x\n"),
            ".git/config": lambda r: git(r, "config", "core.fsmonitor", "./omoikane/wiki/x.md"),
        }
        for expected, action in cases.items():
            with self.subTest(expected), tempfile.TemporaryDirectory() as d:
                repo = self.repo(d)
                before = scope.snapshot(repo)
                action(repo)
                self.assertIn(expected, scope.out_of_scope(before, scope.snapshot(repo)))


class Cli(unittest.TestCase):
    def test_prints_what_wiki_ingest_consumes(self) -> None:
        for args, expected in ((["claude"], scope.claude_args()),
                               (["opencode", "--agent-name", AGENT], scope.opencode_config(AGENT))):
            with self.subTest(args=args):
                out = subprocess.run([sys.executable, "-I", str(BIN / "headless-scope.py"), *args],
                                     capture_output=True, text=True, encoding="utf-8", check=True).stdout
                self.assertEqual(json.loads(out), expected)

    def test_verify_exits_3_on_a_change_outside_the_scope(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Verify().repo(d)
            before = repo.parent / f"{repo.name}-before.json"
            before.write_text(json.dumps(scope.snapshot(repo)), encoding="utf-8")
            write(repo / "AGENTS.md", "pwned\n")
            run = subprocess.run([sys.executable, "-I", str(BIN / "headless-scope.py"), "--repo", str(repo), "verify",
                                  "--before", str(before)], capture_output=True, text=True, encoding="utf-8")
            before.unlink()
        self.assertEqual((run.returncode, run.stdout), (3, "headless-scope: out of scope: AGENTS.md\n"))

    def test_verify_names_a_non_ascii_path_instead_of_crashing(self) -> None:
        # Under `python -I` on a cp1252 console, print() raised UnicodeEncodeError: exit 1, no verdict (#40). In
        # process, with a cp1252 stdout, so the Linux CI's UTF-8 console cannot hide it.
        with tempfile.TemporaryDirectory() as d:
            repo = Verify().repo(d)
            before = repo.parent / f"{repo.name}-before.json"
            before.write_text(json.dumps(scope.snapshot(repo)), encoding="utf-8")
            write(repo / "思.md", "x\n")
            console, saved = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n"), sys.stdout
            sys.stdout = console
            try:
                code = scope.main(["--repo", str(repo), "verify", "--before", str(before)])
            finally:
                sys.stdout = saved
            before.unlink()
        console.flush()
        self.assertEqual((code, console.buffer.getvalue().decode("utf-8")),  # type: ignore[attr-defined]
                         (3, "headless-scope: out of scope: 思.md\n"))


if __name__ == "__main__":
    unittest.main()
