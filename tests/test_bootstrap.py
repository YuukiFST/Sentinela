"""Headless tests for omoikane/bin/bootstrap.py against real local git repositories.
Run: python -m unittest discover -s tests"""
from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

bootstrap = importlib.import_module("bootstrap")
from wikilib import RULES_END, RULES_START  # noqa: E402

MANUAL = f"# Omoikane — agent operating manual\n\nLayout.\n\n{RULES_START}\n- A rule (omoikane/wiki/practices/r.md)\n{RULES_END}\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        write(repo / name, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


class Bootstrap(unittest.TestCase):
    # A project that adopts Omoikane, or a system that replaces one, started with an empty wiki although its README,
    # docs, rule files and history already state its rules (#79).
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project, self.omoikane = self.root / "shop", self.root / "new" / "omoikane"
        self.redact = self.root / "redact"
        self.redact.write_text("Acme\n", encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main", str(self.project))
        commit(self.project, {
            "README.md": "# Shop\n\nPrices are integer cents.\n",
            "docs/adr/0001-tenancy.md": "# Every table has a tenant_id\n",
            "pkg/api/CLAUDE.md": "Use the primary token for buttons.\n",
            ".cursor/rules/style.mdc": "No hex colours in components.\n",
            "README_files/logo.png": "\0PNG",
            "src/total.py": "def total(): ...\n",
            "omoikane/wiki/domain/x.md": "an Omoikane page\n",
        }, "feat: start the shop\n\nCents because floats lost a cent on refunds.")
        commit(self.project, {"src/total.py": "def total(): return 0\n"}, "fix: clamp the total at zero")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_on(self, project: Path) -> list[str]:
        return bootstrap.bootstrap(project, self.omoikane, redact_file=self.redact)

    def inbox(self) -> dict[str, str]:
        folder = self.omoikane / "raw" / "inbox"
        return {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.md")} if folder.is_dir() else {}

    def test_docs_rules_and_history_land_in_the_inbox(self) -> None:
        written = self.run_on(self.project)
        files = self.inbox()
        self.assertEqual(sorted(files), sorted(written))
        self.assertEqual(sorted(files), ["bootstrap-cursor-rules-style-mdc.md", "bootstrap-docs-adr-0001-tenancy-md.md",
                                         "bootstrap-git-history.md", "bootstrap-pkg-api-claude-md.md",
                                         "bootstrap-readme-md.md"])
        readme = files["bootstrap-readme-md.md"]
        self.assertIn("Prices are integer cents.", readme)
        # /ingest dates a source by the date it bears: the file's last commit.
        self.assertIn("`README.md`", readme)
        self.assertRegex(readme, r"last changed \d{4}-\d{2}-\d{2}")
        history = files["bootstrap-git-history.md"]
        self.assertIn("feat: start the shop", history)
        self.assertIn("Cents because floats lost a cent on refunds.", history)
        self.assertIn("fix: clamp the total at zero", history)

    def test_content_comes_from_the_commit_and_is_redacted(self) -> None:
        # The run pushes what it ingests: a secret or a listed term in a doc went out unredacted (#84 review).
        token = "ghp_" + "a1B2" * 9
        commit(self.project, {"docs/deploy.md": f"Deploy for Acme with GITHUB_TOKEN={token}\n"}, "docs: deploy")
        (self.project / "README.md").unlink()  # deleted in the working tree only: HEAD still has it
        self.run_on(self.project)
        files = self.inbox()
        self.assertIn("Prices are integer cents.", files["bootstrap-readme-md.md"])
        self.assertNotIn(token[4:], files["bootstrap-docs-deploy-md.md"])
        self.assertNotIn("Acme", files["bootstrap-docs-deploy-md.md"])

    def test_names_that_collide_get_their_own_file(self) -> None:
        commit(self.project, {"docs/a-b.md": "FIRST\n", "docs/a/b.md": "SECOND\n", "docs/日本.md": "J\n",
                              "docs/中文.md": "C\n"}, "docs: four pages")
        self.run_on(self.project)
        bodies = "".join(self.inbox().values())
        for text in ("FIRST", "SECOND", "\nJ\n", "\nC\n"):
            self.assertIn(text, bodies)

    def test_a_second_run_writes_nothing_new(self) -> None:
        self.run_on(self.project)
        write(self.omoikane / "raw" / "sources" / "bootstrap-readme-md.md", "ingested")
        (self.omoikane / "raw" / "inbox" / "bootstrap-readme-md.md").unlink()
        write(self.omoikane / "raw" / "inbox" / "bootstrap-pkg-api-claude-md.md", "edited by the human")
        self.assertEqual(self.run_on(self.project), [])
        self.assertEqual(self.inbox()["bootstrap-pkg-api-claude-md.md"], "edited by the human")
        self.assertNotIn("bootstrap-readme-md.md", self.inbox())

    def test_what_the_review_gate_holds_is_not_written_again(self) -> None:
        # The gate moves inbox files to wiki/auto; until the human pulls, a second run wrote them all again and the
        # next run's move onto the ingested copy failed (#84 review).
        repo = self.root / "new"
        git(self.root, "init", "-q", "-b", "main", str(repo))
        commit(repo, {"omoikane/log.md": "# Log\n"}, "init")
        git(repo, "checkout", "-q", "-b", "wiki/auto")
        commit(repo, {"omoikane/raw/sources/bootstrap-readme-md.md": "ingested on the gate"}, "ingest")
        git(repo, "checkout", "-q", "main")
        self.assertNotIn("bootstrap-readme-md.md", self.run_on(self.project))

    def test_what_the_template_shipped_is_skipped(self) -> None:
        # A system born from the template holds the template's manual, README and history; they describe Omoikane.
        # new-system.py empties the manual's rules block, which made the whole manual look like the system's own.
        template = self.root / "template"
        git(self.root, "init", "-q", "-b", "main", str(template))
        commit(template, {"AGENTS.md": MANUAL, "CLAUDE.md": "@AGENTS.md\n", "README.md": "# Omoikane\n",
                          "docs/architecture.md": "# Architecture\n"}, "feat: the template")
        system = self.root / "system"
        git(self.root, "clone", "-q", "-o", "template", str(template), str(system))
        commit(system, {"AGENTS.md": MANUAL.replace("- A rule (omoikane/wiki/practices/r.md)\n", ""),
                        "README.md": "# Omoikane\n\nRefunds go back to the card.\n"}, "chore: new system")
        # The template moves on; the system fetches it but keeps its own copy of the architecture.
        commit(template, {"docs/architecture.md": "# Architecture\n\nNewer.\n"}, "docs: newer architecture")
        git(system, "fetch", "-q", "template")
        self.run_on(system)
        files = self.inbox()
        self.assertEqual(sorted(files), ["bootstrap-git-history.md", "bootstrap-readme-md.md"])
        self.assertIn("Refunds go back to the card.", files["bootstrap-readme-md.md"])
        self.assertNotIn("# Omoikane\n", files["bootstrap-readme-md.md"].split("---", 1)[1])
        self.assertIn("chore: new system", files["bootstrap-git-history.md"])
        self.assertNotIn("feat: the template", files["bootstrap-git-history.md"])

    def test_omoikane_s_manual_in_an_adopting_project_is_skipped(self) -> None:
        commit(self.project, {"AGENTS.md": MANUAL, "pkg/AGENTS.md": "# Pkg rules\n\nAmounts are cents.\n\n" + MANUAL,
                              "node_modules/lib/AGENTS.md": "a dependency's rules\n"}, "chore: adopt Omoikane")
        self.run_on(self.project)
        files = self.inbox()
        self.assertNotIn("bootstrap-agents-md.md", files)
        self.assertNotIn("bootstrap-node_modules-lib-agents-md.md", files)
        self.assertIn("Amounts are cents.", files["bootstrap-pkg-agents-md.md"])
        self.assertNotIn("Layout.", files["bootstrap-pkg-agents-md.md"])

    def test_a_use_this_template_system_skips_the_template_by_its_reset(self) -> None:
        # "Use this template" starts from an unrelated commit, and new-system.py may leave no `template` remote:
        # the README, docs, specs and 147 template commits were copied (#84 second review).
        repo = Path(__file__).resolve().parent.parent
        system = self.root / "store"
        for name in filter(None, git(repo, "ls-files", "-z").split("\0")):
            if (repo / name).is_file():
                (system / name).parent.mkdir(parents=True, exist_ok=True)
                (system / name).write_bytes((repo / name).read_bytes())
        git(self.root, "init", "-q", "-b", "main", str(system))
        commit(system, {}, "Initial commit")
        reset = subprocess.run([sys.executable, str(system / "omoikane" / "bin" / "new-system.py")], cwd=system,
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(reset.returncode, 0, reset.stdout + reset.stderr)
        commit(system, {}, "chore: start the store from the template")
        readme = (system / "README.md").read_text(encoding="utf-8")
        commit(system, {"README.md": readme + "\nRefunds go back to the card.\n"}, "docs: refunds")
        self.run_on(system)
        files = self.inbox()
        self.assertEqual(sorted(files), ["bootstrap-git-history.md", "bootstrap-readme-md.md"])
        self.assertEqual(files["bootstrap-readme-md.md"].split("---\n\n", 1)[1].strip(), "Refunds go back to the card.")
        self.assertNotIn("Initial commit", files["bootstrap-git-history.md"])

    def test_names_and_cut_bodies_leak_nothing(self) -> None:
        # The inbox name is pushed too, and a token cut by the body limit no longer matched its shape (#84 review).
        token = "ghp_" + "a1B2" * 9
        commit(self.project, {"docs/clients/acme-contract.md": "terms\n"},
               "docs: contract\n\n" + "x" * 990 + " " + token + "\n\nSigned-off-by: Ana <ana@example.invalid>")
        self.run_on(self.project)
        self.assertFalse([name for name in self.inbox() if "acme" in name])
        history = self.inbox()["bootstrap-git-history.md"]
        self.assertNotIn(token[4:14], history)
        self.assertNotIn("ana@example.invalid", history)

    def test_a_template_remote_never_fetched_stops_the_run(self) -> None:
        git(self.project, "remote", "add", "template", "https://example.invalid/omoikane.git")
        with self.assertRaises(bootstrap.BootstrapError):
            self.run_on(self.project)

    def test_merged_branches_keep_their_reasons(self) -> None:
        git(self.project, "checkout", "-q", "-b", "feat/x")
        commit(self.project, {"src/x.py": "x\n"}, "feat: x\n\nBecause the old flow lost orders.")
        git(self.project, "checkout", "-q", "main")
        git(self.project, "merge", "-q", "--no-ff", "-m", "Merge pull request #1", "feat/x")
        self.run_on(self.project)
        self.assertIn("Because the old flow lost orders.", self.inbox()["bootstrap-git-history.md"])

    def test_it_says_why_it_cannot_run(self) -> None:
        plain, empty = self.root / "plain", self.root / "empty"
        plain.mkdir()
        git(self.root, "init", "-q", str(empty))
        for folder, reason in ((plain, "not a git repository"), (empty, "no commit yet")):
            with self.subTest(folder=folder.name):
                result = subprocess.run([sys.executable, str(Path(bootstrap.__file__)), "--from", str(folder)],
                                        capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 2)
                self.assertIn(reason, result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
