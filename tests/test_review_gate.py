"""Headless tests for omoikane/bin/review-gate.py against a real local git origin. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "omoikane" / "bin"))

gate = importlib.import_module("review-gate")

FAKE_GH = """import json, os, sys
state = os.environ["FAKE_GH_STATE"]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["pr", "list"] and sys.argv[sys.argv.index("--state") + 1] == "closed":
    print(os.environ.get("FAKE_GH_CLOSED", "[]"))
elif sys.argv[1:3] == ["pr", "list"]:
    print(json.dumps([{"number": 7, "url": "https://example.invalid/pull/7"}] if os.path.exists(state) else []))
elif sys.argv[1:3] == ["pr", "create"]:
    open(state, "w").close()
    print("https://example.invalid/pull/7")
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class Gate(unittest.TestCase):
    """The scheduled run's commits go to wiki/auto in a worktree of their own, never onto the human's checkout (#45)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.origin, self.repo, self.work = root / "origin.git", root / "repo", root / "repo-wiki-auto"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(root, "clone", "-q", str(self.origin), str(self.repo))
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@example.invalid")
        for name in (".gitattributes", ".gitignore"):
            write(self.repo / name, (REPO / name).read_text(encoding="utf-8"))
        for path, text in (("AGENTS.md", "# Manual\n"), ("omoikane/log.md", "# Log\n"),
                           ("omoikane/_review.md", "# Review queue\n"), ("omoikane/index.md", "# Index\n"),
                           ("omoikane/raw/inbox/sessions/.gitkeep", ""), ("omoikane/raw/sources/sessions/.gitkeep", "")):
            write(self.repo / path, text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.gh_log, self.gh_state = root / "gh.log", root / "gh.state"
        fake = root / "gh.py"
        fake.write_text(FAKE_GH, encoding="utf-8")
        self.gh = (sys.executable, str(fake))
        os.environ.update(FAKE_GH_LOG=str(self.gh_log), FAKE_GH_STATE=str(self.gh_state))

    def tearDown(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.work)], capture_output=True)
        self.tmp.cleanup()

    def prepare(self) -> list[str]:
        return gate.prepare(self.repo, self.work, quiet_minutes=30)

    def commit_in_worktree(self, path: str, text: str, message: str) -> None:
        write(self.work / path, text)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", message)

    def human_pushes_to_main(self, path: str, text: str) -> None:
        git(self.repo, "pull", "-q", "--ff-only")
        write(self.repo / path, text)
        git(self.repo, "commit", "-q", "-am", f"human edits {path}")
        git(self.repo, "push", "-q", "origin", "main")

    def gh_calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.gh_log.read_text(encoding="utf-8").splitlines()] if self.gh_log.exists() else []

    def test_the_worktree_starts_on_wiki_auto_and_the_checkout_is_untouched(self) -> None:
        write(self.repo / "notes.txt", "the human's uncommitted work\n")
        self.prepare()
        self.assertEqual(git(self.work, "branch", "--show-current").strip(), "wiki/auto")
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "origin/main"))
        self.assertEqual(git(self.repo, "branch", "--show-current").strip(), "main")
        self.assertEqual(git(self.repo, "status", "--short"), "?? notes.txt\n")

    def test_only_quiet_captures_move_into_the_worktree(self) -> None:
        inbox = self.repo / "omoikane/raw/inbox"
        # On origin/main as it stands here, so the worktree has it already; moved, it would show as deleted in the
        # checkout (#78). A tracked file the worktree does not get as it is (edited since, or not pushed) still moves.
        for name in ("committed.md", "edited.md"):
            write(inbox / name, f"{name} as pushed")
        git(self.repo, "add", "omoikane/raw/inbox")
        git(self.repo, "commit", "-q", "-m", "human commits two sources")
        git(self.repo, "push", "-q", "origin", "main")
        write(inbox / "edited.md", "edited.md as the human edited it")
        write(inbox / "staged.md", "staged, never pushed")
        git(self.repo, "add", "omoikane/raw/inbox/staged.md")
        write(inbox / "sessions/2026-09-30-aaaaaaaa.md", "old")
        write(inbox / "sessions/2026-09-30-bbbbbbbb.md", "still growing")
        write(inbox / "article.md", "a source")
        hour_ago = time.time() - 3600
        os.utime(inbox / "sessions/2026-09-30-aaaaaaaa.md", (hour_ago, hour_ago))
        moved = self.prepare()
        self.assertEqual(sorted(moved), ["omoikane/raw/inbox/article.md", "omoikane/raw/inbox/edited.md",
                                         "omoikane/raw/inbox/sessions/2026-09-30-aaaaaaaa.md",
                                         "omoikane/raw/inbox/staged.md"])
        self.assertTrue((self.work / "omoikane/raw/inbox/sessions/2026-09-30-aaaaaaaa.md").is_file())
        self.assertTrue((inbox / "sessions/2026-09-30-bbbbbbbb.md").is_file())
        self.assertFalse((inbox / "article.md").exists())
        self.assertEqual(git(self.repo, "status", "--short", "--", "omoikane/raw/inbox/committed.md"), "")
        self.assertEqual((self.work / "omoikane/raw/inbox/edited.md").read_text(encoding="utf-8"),
                         "edited.md as the human edited it")
        self.assertEqual((self.work / "omoikane/raw/inbox/staged.md").read_text(encoding="utf-8"),
                         "staged, never pushed")

    def test_publish_pushes_and_opens_one_pr(self) -> None:
        self.prepare()
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")
        self.assertEqual(self.gh_calls(), [])
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        self.assertIn("opened https://example.invalid/pull/7", gate.publish(self.work, self.gh))
        self.assertEqual(git(self.repo, "ls-remote", "--heads", "origin", "wiki/auto").split()[0],
                         git(self.work, "rev-parse", "HEAD").strip())
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n\n## distill | b\n", "feat(wiki): distill b")
        self.assertIn("PR #7 updated", gate.publish(self.work, self.gh))
        creates = [c for c in self.gh_calls() if c[:2] == ["pr", "create"]]
        self.assertEqual(len(creates), 1)
        self.assertIn("feat(wiki): distill a", creates[0][creates[0].index("--body") + 1])

    def test_main_comes_in_by_merge_and_the_log_by_union(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        gate.publish(self.work, self.gh)
        self.human_pushes_to_main("omoikane/log.md", "# Log\n\n## review | removed\n")
        self.prepare()
        log = (self.work / "omoikane/log.md").read_text(encoding="utf-8")
        self.assertIn("## distill | a", log)
        self.assertIn("## review | removed", log)
        self.assertEqual(git(self.work, "rev-list", "--count", "HEAD..origin/main").strip(), "0")

    def test_an_index_conflict_is_regenerated(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/index.md", "# Index\n\nfrom the run\n", "feat(wiki): distill a")
        self.human_pushes_to_main("omoikane/index.md", "# Index\n\nfrom main\n")
        regenerated: list[Path] = []
        gate.prepare(self.repo, self.work, 30, regenerate=lambda w: (regenerated.append(w),
                                                                     write(w / "omoikane/index.md", "# Index\n\nfresh\n")))
        self.assertEqual(regenerated, [self.work])
        self.assertEqual((self.work / "omoikane/index.md").read_text(encoding="utf-8"), "# Index\n\nfresh\n")
        self.assertEqual(git(self.work, "status", "--short"), "")

    def test_any_other_conflict_stops_and_leaves_the_branch_as_it_was(self) -> None:
        self.prepare()
        self.commit_in_worktree("AGENTS.md", "# Manual by the run\n", "feat(wiki): distill a")
        head = git(self.work, "rev-parse", "HEAD")
        self.human_pushes_to_main("AGENTS.md", "# Manual by the human\n")
        with self.assertRaisesRegex(gate.GateError, "AGENTS.md"):
            self.prepare()
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.work, "status", "--short"), "")

    def test_after_the_pr_is_merged_the_branch_restarts_from_main(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        gate.publish(self.work, self.gh)
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "merge", "-q", "--no-ff", "--no-edit", "origin/wiki/auto")
        git(self.repo, "push", "-q", "origin", "main")
        self.prepare()
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "origin/main"))
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")

    def test_a_dirty_worktree_stops_prepare(self) -> None:
        self.prepare()
        write(self.work / "omoikane/wiki/leftover.md", "a run that crashed")
        with self.assertRaisesRegex(gate.GateError, "leftover.md"):
            self.prepare()

    def test_a_source_a_failed_operation_left_in_the_inbox_is_retried(self) -> None:
        # Once it stopped every later prepare, so one failed agent call ended the schedule (#56 review).
        self.prepare()
        write(self.work / "omoikane/raw/inbox/article.md", "moved in, its ingest failed")
        self.prepare()
        self.assertTrue((self.work / "omoikane/raw/inbox/article.md").is_file())

    def test_a_blocked_worktree_stops_prepare(self) -> None:
        self.prepare()
        write(self.work / "omoikane/.wiki-ingest.blocked", "the run changed files outside its scope")
        with self.assertRaisesRegex(gate.GateError, r"\.wiki-ingest\.blocked"):
            self.prepare()

    def review_after_the_human(self, human_review: str) -> str:
        """The branch appends bullet c; the human then rewrites _review.md on main; return the worktree's file."""
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule b: B. (s)\n")
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md",
                                "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule b: B. (s)\n- [ ] rule c: C. (s)\n",
                                "feat(wiki): distill c")
        self.human_pushes_to_main("omoikane/_review.md", human_review)
        self.prepare()
        return (self.work / "omoikane/_review.md").read_text(encoding="utf-8")

    def test_a_bullet_the_human_deleted_stays_deleted(self) -> None:
        # A union merge brought the rejected bullet back, and review-removals.py never saw the rejection.
        review = self.review_after_the_human("# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.assertEqual(review, "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n")

    def test_a_bullet_the_human_ticked_is_not_duplicated(self) -> None:
        review = self.review_after_the_human("# Review queue\n\n- [ ] rule a: A. (s)\n- [x] rule b: B. (s)\n")
        self.assertEqual(review, "# Review queue\n\n- [ ] rule a: A. (s)\n- [x] rule b: B. (s)\n- [ ] rule c: C. (s)\n")

    def test_commits_not_yet_pushed_survive_a_deleted_worktree(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        git(self.repo, "worktree", "remove", "--force", str(self.work))
        self.prepare()
        self.assertIn("feat(wiki): distill a", git(self.work, "log", "--format=%s"))

    def test_a_branch_that_changed_more_than_the_wiki_is_refused(self) -> None:
        # The scheduler runs the worktree's own scripts; wiki/auto is not protected the way main is.
        self.prepare()
        self.commit_in_worktree("omoikane/bin/wiki-ingest.ps1", "Write-Host pwned\n", "feat(wiki): distill a")
        with self.assertRaisesRegex(gate.GateError, "omoikane/bin/wiki-ingest.ps1"):
            self.prepare()

    def squash_merge(self) -> None:
        """The human squash-merges the published PR on main, as the repository allows."""
        if self.gh_state.exists():
            self.gh_state.unlink()  # the PR is merged
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "merge", "-q", "--squash", "origin/wiki/auto")
        git(self.repo, "commit", "-q", "-m", "wiki: scheduled updates (#7)")
        git(self.repo, "push", "-q", "origin", "main")

    def test_a_squash_merged_branch_has_nothing_to_publish(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        gate.publish(self.work, self.gh)
        self.squash_merge()
        self.prepare()
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")

    def squash_then(self, human_review: str) -> str:
        """Bullet c published and squash-merged; the human then rewrites _review.md on main."""
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule b: B. (s)\n")
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md",
                                "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule b: B. (s)\n- [ ] rule c: C. (s)\n",
                                "feat(wiki): distill c")
        gate.publish(self.work, self.gh)
        self.squash_merge()
        self.human_pushes_to_main("omoikane/_review.md", human_review)
        self.prepare()
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")
        return (self.work / "omoikane/_review.md").read_text(encoding="utf-8")

    def test_after_a_squash_merge_the_human_s_decision_on_a_squashed_bullet_stands(self) -> None:
        # The merge base stayed before the squashed bullet c, so a clean merge brought c back after the human
        # deleted it, or next to its ticked twin (#56 reviews 2 and 3).
        for decided in ("- [ ] rule b: B. (s)\n", "- [ ] rule b: B. (s)\n- [x] rule c: C. (s)\n"):
            with self.subTest(decided):
                self.tearDown()
                self.setUp()
                human = "# Review queue\n\n- [ ] rule a: A. (s)\n" + decided
                self.assertEqual(self.squash_then(human), human)

    def test_a_human_revert_on_main_is_not_taken_for_a_landing(self) -> None:
        # Every old branch diff stayed wanted, so the revert restoring c matched the diff of the squashed commit,
        # was recorded with `-s ours`, and the next PR deleted c again (#56 review 5).
        self.squash_then("# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule b: B. (s)\n")
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "revert", "--no-edit", "HEAD")
        git(self.repo, "push", "-q", "origin", "main")
        self.prepare()
        self.assertIn("- [ ] rule c: C. (s)", (self.work / "omoikane/_review.md").read_text(encoding="utf-8"))
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")

    def land_then_delete_c_and_d(self, land: str) -> str:
        """Bullet c, then bullet d with a log line, published as two commits and landed on main by `land`; the human
        then deletes c and d on main."""
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n",
                                "feat(wiki): distill c")
        x = git(self.work, "rev-parse", "HEAD").strip()
        self.commit_in_worktree("omoikane/_review.md",
                                "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n- [ ] rule d: D. (s)\n",
                                "feat(wiki): distill d")
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | y\n", "feat(wiki): distill y")
        y = git(self.work, "rev-parse", "HEAD").strip()
        gate.publish(self.work, self.gh)
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "fetch", "-q", "origin")
        if land == "rebase":  # what GitHub's rebase merge does: the commits one by one onto main
            git(self.repo, "cherry-pick", f"{x}^..{y}")
        else:  # squash of an earlier head x, while a run had already committed and pushed d and y
            git(self.repo, "merge", "-q", "--squash", x)
            git(self.repo, "commit", "-q", "-m", "wiki: scheduled updates (#7)")
        git(self.repo, "push", "-q", "origin", "main")
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.prepare()
        return (self.work / "omoikane/_review.md").read_text(encoding="utf-8")

    def test_after_a_rebase_merge_a_deleted_bullet_stays_deleted(self) -> None:
        # Only the first replayed commit was recorded once, so d, deleted from the second, came back (#56 review 5).
        self.assertEqual(self.land_then_delete_c_and_d("rebase"), "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")

    def test_a_squash_of_an_earlier_head_is_found_too(self) -> None:
        # The PR was squashed at x while the run pushed d and y on top: neither tip matches the squash. Main never
        # held d, so the human's rewrite removes only c.
        review = self.land_then_delete_c_and_d("squash-earlier")
        self.assertEqual(review, "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule d: D. (s)\n")
        self.assertIn("## distill | y", (self.work / "omoikane/log.md").read_text(encoding="utf-8"))
        # The rest lands by a second squash; the record of the first must not hide it (#56 review 6).
        gate.publish(self.work, self.gh)
        self.squash_merge()
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.prepare()
        self.assertEqual((self.work / "omoikane/_review.md").read_text(encoding="utf-8"),
                         "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.assertEqual(gate.publish(self.work, self.gh), "nothing to publish")

    def test_a_rebase_with_a_repeated_patch_is_recorded_whole(self) -> None:
        # c1 and c3 share a patch; counting distinct patches cut the window before c4 (#56 review 7).
        a = "# Review queue\n\n- [ ] rule a: A. (s)\n"
        self.human_pushes_to_main("omoikane/_review.md", a)
        self.prepare()
        shas = []
        for text in (a + "- [ ] rule c: C. (s)\n", a, a + "- [ ] rule c: C. (s)\n",
                     a + "- [ ] rule c: C. (s)\n- [ ] rule d: D. (s)\n"):
            self.commit_in_worktree("omoikane/_review.md", text, f"feat(wiki): step {len(shas)}")
            shas.append(git(self.work, "rev-parse", "HEAD").strip())
        gate.publish(self.work, self.gh)
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "cherry-pick", f"{shas[0]}^..{shas[3]}")
        git(self.repo, "push", "-q", "origin", "main")
        self.human_pushes_to_main("omoikane/_review.md", a + "- [ ] rule c: C. (s)\n")
        self.prepare()
        self.assertEqual((self.work / "omoikane/_review.md").read_text(encoding="utf-8"),
                         a + "- [ ] rule c: C. (s)\n")

    def test_a_human_revert_right_after_a_rebase_is_not_recorded_with_it(self) -> None:
        # x'^..revert of y' equals x's own patch; the longest window ended on the revert (#56 review 6).
        self.human_pushes_to_main("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n")
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md", "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n",
                                "feat(wiki): distill c")
        x = git(self.work, "rev-parse", "HEAD").strip()
        self.commit_in_worktree("omoikane/_review.md",
                                "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n- [ ] rule d: D. (s)\n",
                                "feat(wiki): distill d")
        y = git(self.work, "rev-parse", "HEAD").strip()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | z\n", "feat(wiki): distill z")
        gate.publish(self.work, self.gh)
        git(self.repo, "pull", "-q", "--ff-only")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "cherry-pick", f"{x}^..{y}")
        git(self.repo, "revert", "--no-edit", "HEAD")
        git(self.repo, "push", "-q", "origin", "main")
        self.prepare()
        self.assertEqual((self.work / "omoikane/_review.md").read_text(encoding="utf-8"),
                         "# Review queue\n\n- [ ] rule a: A. (s)\n- [ ] rule c: C. (s)\n")

    def test_a_run_lands_after_the_lines_it_followed_not_an_earlier_twin(self) -> None:
        # Every proposal ends in the same closing fence; one anchor line once put a todo inside another section.
        proposal = "- [ ] guard (test) {0}: {0}\n````diff\n+import {0}\n````\n"
        main = ("# Review queue\n\n## [2026-10-01] lint\n\n" + proposal.format("x") + "\n## [2026-10-01] distill | aa\n\n"
                + proposal.format("y"))
        self.human_pushes_to_main("omoikane/_review.md", main)
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md", main + "- todo z: Z.\n", "feat(wiki): distill bb")
        rejected = main.replace(proposal.format("y"), "")
        self.human_pushes_to_main("omoikane/_review.md", rejected)
        self.prepare()
        self.assertEqual((self.work / "omoikane/_review.md").read_text(encoding="utf-8"), rejected + "- todo z: Z.\n")

    def test_a_multi_line_proposal_and_a_repeated_heading_survive_a_review_conflict(self) -> None:
        # Lines were deduplicated one by one, so fences, diff headers and a second same-day heading vanished.
        proposal = "- [ ] guard (test) {0}: {0}\n````diff\n--- /dev/null\n+++ b/{0}.py\n@@ -0,0 +1 @@\n+import os\n````\n"
        main = ("# Review queue\n\n## [2026-10-01] lint\n\n- todo w: W.\n\n## [2026-10-01] distill | aa\n\n"
                + proposal.format("x") + "- [ ] rule b: B. (s)\n")
        added = "\n## [2026-10-01] lint\n\n- todo z: Z.\n\n## [2026-10-01] distill | bb\n\n" + proposal.format("y")
        self.human_pushes_to_main("omoikane/_review.md", main)
        self.prepare()
        self.commit_in_worktree("omoikane/_review.md", main + added, "feat(wiki): distill bb")
        rejected = main.replace("- [ ] rule b: B. (s)\n", "")
        self.human_pushes_to_main("omoikane/_review.md", rejected)
        self.prepare()
        self.assertEqual((self.work / "omoikane/_review.md").read_text(encoding="utf-8"), rejected + added)

    def test_branch_code_is_refused_before_any_merge_runs_it(self) -> None:
        # An index conflict once ran the branch's own wiki-index.py before the refusal (#56 review).
        self.prepare()
        write(self.work / "omoikane/bin/wiki-index.py", "open('pwned', 'w')\n")
        self.commit_in_worktree("omoikane/index.md", "# Index\n\nfrom the run\n", "feat(wiki): distill a")
        self.human_pushes_to_main("omoikane/index.md", "# Index\n\nfrom main\n")
        regenerated: list[Path] = []
        with self.assertRaisesRegex(gate.GateError, "omoikane/bin/wiki-index.py"):
            gate.prepare(self.repo, self.work, 30, regenerate=regenerated.append)
        self.assertEqual(regenerated, [])

    def test_a_pr_closed_unmerged_is_not_opened_again_after_main_moves(self) -> None:
        self.prepare()
        self.commit_in_worktree("omoikane/log.md", "# Log\n\n## distill | a\n", "feat(wiki): distill a")
        head = git(self.work, "rev-parse", "HEAD").strip()
        self.human_pushes_to_main("AGENTS.md", "# Manual, edited\n")
        self.prepare()  # main merged in: HEAD moved past the rejected head
        closed = [{"number": 7, "headRefOid": head, "state": "CLOSED"},
                  {"number": 5, "headRefOid": "0" * 40, "state": "MERGED"}]
        os.environ["FAKE_GH_CLOSED"] = json.dumps(closed)
        try:
            self.assertIn("PR #7 was closed unmerged", gate.publish(self.work, self.gh))
        finally:
            del os.environ["FAKE_GH_CLOSED"]
        self.assertNotIn(["pr", "create"], [c[:2] for c in self.gh_calls()])


if __name__ == "__main__":
    unittest.main()
