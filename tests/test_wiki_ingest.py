"""End-to-end tests of omoikane/bin/wiki-ingest.ps1 with a fake `claude` and `opencode` on PATH.
Run: python -m unittest discover -s tests

The fake stands for the headless agent: it records the arguments and the OpenCode config it was given, and edits
the throwaway repository the way a run that goes well, or one that leaves its scope, would.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from test_review_gate import FAKE_GH

REPO = Path(__file__).resolve().parent.parent
PWSH = shutil.which("pwsh")

FAKE_AGENT = textwrap.dedent('''
    import json, os, re, sys
    from pathlib import Path
    harness, args = sys.argv[1], sys.argv[2:]
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": args, "config": os.environ.get("OPENCODE_CONFIG_CONTENT")}) + "\\n")
    pure = "--pure" in args
    args = [a for a in args if a != "--pure"]
    if harness == "opencode":
        # The first OpenCode start writes .opencode/.gitignore; without --pure, starts also install plugin deps.
        Path(".opencode").mkdir(exist_ok=True)
        if not Path(".opencode/.gitignore").exists():
            Path(".opencode/.gitignore").write_text(".gitignore\\nnode_modules\\n", encoding="utf-8")
        if not pure:
            Path(".opencode/node_modules").mkdir(exist_ok=True)
            Path(".opencode/node_modules/dep.js").write_text("x", encoding="utf-8")
    if harness == "opencode" and args[:2] == ["debug", "agent"]:
        # What `opencode debug agent` resolves: a gpt- model gets apply_patch in place of edit and write. Without
        # --pure a user plugin's config hook may set another model, which the pure run never sees.
        tools = {"bash": False, "read": True, "glob": True, "grep": True, "todowrite": True}
        gpt = os.environ.get("FAKE_MODEL") == "gpt" and pure
        tools.update({"apply_patch": True} if gpt else {"edit": True, "write": True})
        print(json.dumps({"name": args[2], "mode": "primary", "tools": tools}))
        sys.exit(0)
    if harness == "opencode" and args[0] == "debug":
        print("{}")
        sys.exit(0)
    prompt = args[-1] if harness == "opencode" else args[args.index("-p") + 1]
    m = re.match(r"/(\\w+)|Read `omoikane/prompts/(\\w+)\\.md`", prompt)
    op = (m.group(1) or m.group(2)) if m else "fix"
    page = "---\\ntitle: {0}\\ntype: concept\\nsummary: s\\ntags: []\\ncreated: 2026-10-01\\nupdated: 2026-10-01\\nsources: []\\n---\\n{1}\\n"
    mode = os.environ["FAKE_MODE"]
    review = Path("omoikane/_review.md")
    if mode == "escape" or (mode == "escape-on-distill" and op == "distill"):
        Path("AGENTS.md").write_text("# Manual, rewritten by the agent\\n", encoding="utf-8")
    elif mode == "corrupt-index":
        Path(".git/index").write_bytes(b"not an index")
    elif mode == "tick":
        review.write_text(review.read_text(encoding="utf-8").replace("- [ ] ", "- [x] "), encoding="utf-8")
    elif mode == "undecodable-review":
        review.write_bytes(b"# Review queue\\n- [x] \\xff\\xfe\\n")
    elif mode == "delete-bullet":
        review.write_text("# Review queue\\n", encoding="utf-8")
    elif mode == "distill" and op == "distill":
        with open("omoikane/log.md", "a", encoding="utf-8") as f:
            f.write("\\n## [2026-10-01] distill | session\\n")
    elif mode == "fail-with-edits" and "article" in prompt:
        Path("omoikane/wiki/concepts/half.md").write_text(page.format("half", "Half done."), encoding="utf-8")
        sys.exit(1)
    elif mode in ("orphan", "orphan-then-fail") and op == "ingest":
        Path("omoikane/wiki/concepts/lonely.md").write_text(page.format("lonely", "Alone."), encoding="utf-8")
    elif mode == "orphan-then-fail":
        sys.exit(1)
    elif mode == "orphan" and "orphan page" in prompt:
        Path("omoikane/wiki/concepts/lonely.md").write_text(page.format("lonely", "See [[hub]]."), encoding="utf-8")
        Path("omoikane/wiki/concepts/hub.md").write_text(page.format("hub", "See [[lonely]]."), encoding="utf-8")
''')


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


class IngestFixture:
    """A throwaway Omoikane repository, with fake `claude`, `opencode` and `gh` first on PATH."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo, shims, self.calls = root / "repo", root / "bin", root / "calls.jsonl"
        for part in ("omoikane/bin", "omoikane/prompts"):
            shutil.copytree(REPO / part, self.repo / part, ignore=shutil.ignore_patterns("__pycache__"))
        for part in ("AGENTS.md", ".gitignore", ".gitattributes"):
            shutil.copy(REPO / part, self.repo / part)
        for folder in ("concepts", "sources"):
            (self.repo / "omoikane/wiki" / folder).mkdir(parents=True)
            (self.repo / "omoikane/wiki" / folder / ".gitkeep").write_text("", encoding="utf-8")
        (self.repo / "omoikane/log.md").write_text("# Log\n", encoding="utf-8")
        (self.repo / "omoikane/_review.md").write_text("# Review queue\n\n- [ ] rule a: A. (s)\n", encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        (self.repo / "omoikane/raw/inbox").mkdir(parents=True)
        (self.repo / "omoikane/raw/inbox/article.md").write_text("a source\n", encoding="utf-8")
        shims.mkdir()
        (shims / "fake_agent.py").write_text(FAKE_AGENT, encoding="utf-8")
        for harness in ("claude", "opencode"):
            # pwsh finds `<name>.ps1` by its base name on Windows, the extensionless script on Linux.
            (shims / f"{harness}.ps1").write_text(
                f'& "{sys.executable}" "{shims / "fake_agent.py"}" {harness} @args\nexit $LASTEXITCODE\n', encoding="utf-8")
            (shims / harness).write_text(
                f'#!/bin/sh\nexec "{sys.executable}" "{shims / "fake_agent.py"}" {harness} "$@"\n', encoding="utf-8")
            (shims / harness).chmod(0o755)
        # review-gate.py runs gh as a process, not through pwsh: a .cmd on Windows, a script elsewhere.
        (shims / "fake_gh.py").write_text(FAKE_GH, encoding="utf-8")
        (shims / "gh.cmd").write_text(f'@"{sys.executable}" "{shims / "fake_gh.py"}" %*\r\n', encoding="utf-8")
        (shims / "gh").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{shims / "fake_gh.py"}" "$@"\n', encoding="utf-8")
        (shims / "gh").chmod(0o755)
        self.gh_log = root / "gh.jsonl"
        self.env = {**os.environ, "PATH": f"{shims}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.calls),
                    "FAKE_GH_LOG": str(self.gh_log), "FAKE_GH_STATE": str(root / "gh.state")}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ingest(self, mode: str, *args: str, gate: bool = False, **env: str) -> subprocess.CompletedProcess[str]:
        """Run wiki-ingest.ps1 -Commit; without `gate`, as the review gate runs it inside its worktree (-NoGate)."""
        return subprocess.run([str(PWSH), "-NoProfile", "-File", str(self.repo / "omoikane/bin/wiki-ingest.ps1"),
                               "-Commit", *(() if gate else ("-NoGate",)), *(args or ("-SynthesizeEvery", "0"))],
                              env={**self.env, "FAKE_MODE": mode, **env}, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", timeout=300)

    def calls_made(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.calls.read_text(encoding="utf-8").splitlines()] if self.calls.exists() else []

    def prompts(self) -> list[str]:
        return [str(call["argv"][call["argv"].index("-p") + 1]) for call in self.calls_made()]  # type: ignore[union-attr]

    def commits(self) -> list[str]:
        return git(self.repo, "log", "--format=%s").splitlines()


@unittest.skipUnless(PWSH or os.environ.get("CI"), "pwsh not on PATH")
class WikiIngest(IngestFixture, unittest.TestCase):
    def assert_blocked(self, run: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(run.returncode, 0, run.stdout)
        self.assertTrue((self.repo / "omoikane/.wiki-ingest.blocked").is_file(), run.stdout + run.stderr)
        self.assertEqual(self.commits(), ["init"])  # nothing committed
        self.assertTrue((self.repo / "omoikane/raw/inbox/article.md").is_file())  # not marked as processed

    def test_a_run_that_leaves_its_scope_blocks_every_later_run(self) -> None:
        run = self.ingest("escape")
        self.assert_blocked(run)
        self.assertIn("AGENTS.md", (self.repo / "omoikane/.wiki-ingest.log").read_text(encoding="utf-8"))
        self.assertEqual(self.ingest("escape").returncode, 1)
        self.assertEqual(len(self.calls_made()), 1)  # the blocked run never called the agent

    def test_a_scope_check_that_crashes_blocks_the_run(self) -> None:
        # A crash of verify once failed open: exit 1, no block, and the next snapshot absorbed the file (#40).
        self.assert_blocked(self.ingest("corrupt-index"))

    def test_lint_findings_go_back_to_the_agent_and_only_the_operation_is_committed(self) -> None:
        active = self.repo / "omoikane/raw/inbox/sessions/2026-10-01-active01.md"
        active.parent.mkdir()
        active.write_text("a coding session still being captured\n", encoding="utf-8")
        run = self.ingest("orphan")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        first, fix = self.calls_made()
        self.assertEqual(first["argv"][first["argv"].index("--tools") + 1], "Read,Glob,Grep,Edit,Write")  # type: ignore[union-attr,index]
        self.assertIn("orphan page, no inbound wikilink", self.prompts()[1])
        self.assertEqual(self.commits()[0], "feat(wiki): ingest article")
        committed = git(self.repo, "show", "--name-only", "--format=", "HEAD").split()
        for path in ("omoikane/wiki/concepts/hub.md", "omoikane/wiki/concepts/lonely.md",
                     "omoikane/raw/sources/article.md", "omoikane/index.md"):
            self.assertIn(path, committed)
        # Not the run's to commit: `git add omoikane/raw` once took every capture still in the inbox.
        self.assertIn("?? omoikane/raw/inbox/sessions/2026-10-01-active01.md",
                      git(self.repo, "status", "--porcelain", "--untracked-files=all"))

    def test_only_findings_go_back_not_warnings(self) -> None:
        # Warnings need /lint's judgement; 25 of them once buried the one finding the agent had to fix.
        (self.repo / "omoikane/wiki/gotchas").mkdir()
        (self.repo / "omoikane/wiki/gotchas/old.md").write_text(
            "---\ntitle: old\ntype: gotcha\nsummary: s\ntags: []\ncreated: 2026-01-01\nupdated: 2026-01-01\n"
            "sources: []\nguard: none\n---\nSee [[old]].\n", encoding="utf-8")
        git(self.repo, "add", "-A", "omoikane/wiki")
        git(self.repo, "commit", "-q", "-m", "old gotcha")
        self.ingest("orphan")
        self.assertNotIn("warning:", self.prompts()[1])

    def test_an_agent_that_fails_after_a_lint_round_fails_the_operation(self) -> None:
        run = self.ingest("orphan-then-fail")
        self.assertIn("ingest FAILED omoikane/raw/inbox/article.md", run.stdout)
        self.assertEqual(self.commits(), ["init"])
        self.assertTrue((self.repo / "omoikane/raw/inbox/article.md").is_file())

    def test_what_the_human_staged_stays_out_of_the_run_commits(self) -> None:
        (self.repo / "notes.txt").write_text("staged by the human before the run\n", encoding="utf-8")
        git(self.repo, "add", "notes.txt")
        run = self.ingest("orphan")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertNotIn("notes.txt", git(self.repo, "show", "--name-only", "--format=", "HEAD").split())
        self.assertIn("A  notes.txt", git(self.repo, "status", "--porcelain"))

    def test_uncommitted_wiki_changes_keep_the_agent_from_running(self) -> None:
        # Committing on top of them would file the human's edit under the run's message.
        (self.repo / "omoikane/wiki/concepts/draft.md").write_text("an edit nobody committed\n", encoding="utf-8")
        run = self.ingest("orphan")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("uncommitted changes under the wiki", run.stdout + run.stderr)
        self.assertEqual((self.calls_made(), self.commits()), ([], ["init"]))

    def test_a_failed_operation_that_left_edits_blocks_the_run(self) -> None:
        # The next operation's `git add omoikane/wiki` once committed them under its own message.
        (self.repo / "omoikane/raw/inbox/later.md").write_text("another source\n", encoding="utf-8")
        run = self.ingest("fail-with-edits")
        self.assert_blocked(run)
        self.assertTrue((self.repo / "omoikane/wiki/concepts/half.md").is_file())  # left for the human to read

    def test_a_tick_the_agent_adds_is_undone_before_the_commit(self) -> None:
        run = self.ingest("tick")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("- [ ] rule a: A. (s)", git(self.repo, "show", "HEAD:omoikane/_review.md"))

    def test_a_bullet_the_agent_deletes_blocks_the_run(self) -> None:
        # The next review-removals.py would record the deletion as the human's rejection (#41).
        self.assert_blocked(self.ingest("delete-bullet"))

    def test_the_items_the_human_removed_are_logged_and_committed_before_the_first_operation(self) -> None:
        log = self.repo / "omoikane/log.md"
        log.write_text("# Log\n\n## [2026-09-30] distill | session aaaa0001\n- routed (todo) gone-item: x (turn 1)\n",
                       encoding="utf-8")
        git(self.repo, "commit", "-q", "-am", "a distill that filed gone-item, since deleted by the human")
        run = self.ingest("none")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(self.commits()[:2], ["feat(wiki): ingest article",
                                              "feat(wiki): record the review items the human removed"])
        self.assertIn("- removed (todo) gone-item", git(self.repo, "show", "HEAD~1:omoikane/log.md"))

    def test_an_uncommitted_review_edit_does_not_fail_a_run_with_nothing_to_do(self) -> None:
        # The human deleting a bullet and not yet committing is the feature's own input (#44 review).
        (self.repo / "omoikane/raw/inbox/article.md").unlink()
        (self.repo / "omoikane/_review.md").write_text("# Review queue\n", encoding="utf-8")
        run = self.ingest("none")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("nothing in inbox", run.stdout)

    def test_a_review_queue_with_an_open_fence_records_nothing_and_the_run_goes_on(self) -> None:
        (self.repo / "omoikane/_review.md").write_text("# Review queue\n\n````diff\n- [ ] rule a: A. (s)\n",
                                                       encoding="utf-8")
        git(self.repo, "commit", "-q", "-am", "an unclosed fence")
        run = self.ingest("none")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("review-removals.py recorded nothing", run.stdout)
        self.assertEqual(self.commits()[0], "feat(wiki): ingest article")

    def test_a_review_queue_the_tick_check_cannot_read_blocks_the_run(self) -> None:
        # Unchecked, review-ticks.py failed and the agent's tick was committed as the human's approval (#40).
        self.assert_blocked(self.ingest("undecodable-review"))

    def test_the_opencode_run_carries_the_scope_in_a_fresh_agent_and_restores_the_user_config(self) -> None:
        hook, seen = self.repo / ".git/hooks/pre-commit", Path(self.tmp.name) / "hook.txt"
        hook.write_text(f'#!/bin/sh\nprintf "%s" "${{OPENCODE_CONFIG_CONTENT-unset}}" > "{seen.as_posix()}"\n',
                        encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        git(self.repo, "config", "core.hooksPath", ".git/hooks")  # over a global hooksPath
        # A fresh clone: OpenCode writes .opencode/ on its first start, which must happen outside the scope check.
        run = self.ingest("none", "-Agent", "opencode", "-SynthesizeEvery", "0", OPENCODE_CONFIG_CONTENT='{"user": 1}')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        calls = self.calls_made()
        (resolve,) = [c for c in calls if c["argv"][1:3] == ["debug", "agent"]]  # type: ignore[index]
        (agent,) = [c for c in calls if c["argv"][0] == "run"]  # type: ignore[index]
        name = resolve["argv"][3]  # type: ignore[index]
        # --pure on both: a user plugin's config hook must not change what the check sees.
        self.assertEqual(resolve["argv"], ["--pure", "debug", "agent", name])
        self.assertEqual(agent["argv"][:4], ["run", "--pure", "--agent", name])  # type: ignore[index]
        self.assertTrue(agent["argv"][-1].startswith("Read `omoikane/prompts/ingest.md` and follow it."))  # type: ignore[index,union-attr]
        config = json.loads(str(agent["config"]))
        self.assertEqual(config["agent"][name]["permission"]["*"], "deny")
        self.assertEqual(self.commits()[0], "feat(wiki): ingest article")
        self.assertEqual(seen.read_text(encoding="utf-8"), '{"user": 1}')  # restored after the agent call

    def test_an_opencode_agent_offered_apply_patch_never_runs(self) -> None:
        # apply_patch checks edit rules on the source of a move only; a gpt- model always gets it (#40).
        run = self.ingest("escape", "-Agent", "opencode", "-SynthesizeEvery", "0", FAKE_MODEL="gpt")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("apply_patch", run.stdout)
        self.assertNotIn("run", [call["argv"][0] for call in self.calls_made()])  # type: ignore[index]
        self.assertEqual(self.commits(), ["init"])
        self.assertEqual((self.repo / "AGENTS.md").read_text(encoding="utf-8"), (REPO / "AGENTS.md").read_text(encoding="utf-8"))

    def test_synthesize_runs_after_the_distills_that_make_it_due(self) -> None:
        (self.repo / "omoikane/raw/inbox/article.md").unlink()
        session = self.repo / "omoikane/raw/inbox/sessions/2026-09-30-quiet001.md"
        session.parent.mkdir()
        session.write_text("a finished coding session\n", encoding="utf-8")
        old = time.time() - 3600
        os.utime(session, (old, old))
        run = self.ingest("distill", "-SynthesizeEvery", "1")
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual([p.split()[0] for p in self.prompts()], ["/distill", "/synthesize"])
        self.assertEqual(self.commits(), ["feat(wiki): synthesize sessions", "feat(wiki): distill 2026-09-30-quiet001", "init"])
        # The fake wrote no synthesize heading, so the script did, or every later run would start it again.
        self.assertIn("synthesize | ended without a log entry", git(self.repo, "show", "HEAD:omoikane/log.md"))


@unittest.skipUnless(PWSH or os.environ.get("CI"), "pwsh not on PATH")
class ReviewGateRun(IngestFixture, unittest.TestCase):
    """`wiki-ingest.ps1 -Commit` as the schedule runs it: through the review gate, with a local git origin (#45)."""

    def setUp(self) -> None:
        super().setUp()
        root = Path(self.tmp.name)
        self.origin, self.work = root / "origin.git", root / "repo-wiki-auto"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "-u", "origin", "main")
        session = self.repo / "omoikane/raw/inbox/sessions/2026-09-30-quiet001.md"
        session.parent.mkdir()
        session.write_text("a finished coding session\n", encoding="utf-8")
        old = time.time() - 3600
        os.utime(session, (old, old))

    def tearDown(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.work)], capture_output=True)
        super().tearDown()

    def gh_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.gh_log.read_text(encoding="utf-8").splitlines()] if self.gh_log.exists() else []

    def test_the_run_commits_on_wiki_auto_and_opens_one_pr_leaving_the_checkout_alone(self) -> None:
        run = self.ingest("distill", gate=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual((git(self.repo, "branch", "--show-current").strip(), self.commits()), ("main", ["init"]))
        self.assertEqual(git(self.repo, "status", "--porcelain", "--untracked-files=all"), "")  # inbox moved out
        self.assertEqual(git(self.origin, "log", "--format=%s", "main..wiki/auto").splitlines(),
                         ["feat(wiki): distill 2026-09-30-quiet001", "feat(wiki): ingest article"])
        self.assertEqual([c[:2] for c in self.gh_calls()].count(["pr", "create"]), 1)
        # Nothing new: the next run commits nothing and opens no second PR.
        self.assertEqual(self.ingest("distill", gate=True).returncode, 0)
        self.assertEqual([c[:2] for c in self.gh_calls()].count(["pr", "create"]), 1)

    def test_a_blocked_run_publishes_nothing_it_committed(self) -> None:
        # The ingest commits before the distill leaves its scope: publishing after a failed run would push it.
        run = self.ingest("escape-on-distill", gate=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertTrue((self.work / "omoikane/.wiki-ingest.blocked").is_file(), run.stdout + run.stderr)
        self.assertIn("feat(wiki): ingest article", git(self.work, "log", "--format=%s"))
        self.assertEqual(git(self.origin, "branch", "--list", "wiki/auto"), "")
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.commits(), ["init"])
        # The next run stops at the marker instead of merging into the blocked worktree.
        self.assertNotEqual(self.ingest("none", gate=True).returncode, 0)
        self.assertIn(".wiki-ingest.blocked", (self.repo / "omoikane/.wiki-ingest.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
