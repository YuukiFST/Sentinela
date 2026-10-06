"""Headless tests for omoikane/bin/wiki-lint.py, wiki-index.py and session-context.py. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import contextlib
import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

from wikilib import Page  # noqa: E402

lint = importlib.import_module("wiki-lint")
context = importlib.import_module("session-context")
index = importlib.import_module("wiki-index")


def page(slug: str, kind: str, **meta: object) -> Page:
    base: dict[str, object] = {"title": slug, "type": kind, "summary": "s", "tags": [], "created": "2026-09-15",
                               "updated": "2026-09-15", "sources": ["wiki/sources/x.md"]}
    if kind == "gotcha":
        base["guard"] = "test"
    base.update(meta)
    return Page(path=Path(f"/wiki/{slug}.md"), slug=slug, meta=base)


class CodePaths(unittest.TestCase):
    def test_missing_code_path_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.py").write_text("", encoding="utf-8")
            hub = page("hub", "concept", body="")
            hub.links = {"g"}
            g = page("g", "gotcha", code=["keep.py", "gone.py"])
            g.links = {"hub"}
            findings = lint.lint_pages([hub, g], Path(d))
        self.assertEqual(findings, ["/wiki/g.md: code path `gone.py` does not exist"])

    def test_code_path_outside_repo_is_a_finding(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            repo.mkdir()
            (Path(d) / "outside.py").write_text("", encoding="utf-8")
            g = page("g", "gotcha", code=["../outside.py"])
            hub = page("hub", "concept")
            hub.links, g.links = {"g"}, {"hub"}
            findings = lint.lint_pages([hub, g], repo)
        self.assertEqual(findings, ["/wiki/g.md: code path `../outside.py` does not exist"])

    def test_code_path_is_judged_the_same_on_every_os(self) -> None:
        # A page written on Windows passed locally and failed on the Linux CI (#32): the check must not depend on
        # which OS resolves the path.
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "src").mkdir()
            (repo / "src" / "keep.py").write_text("", encoding="utf-8")
            absolute = str(repo / "src" / "keep.py")
            for path, findings, git in (
                    ("src\\keep.py", [], ["src/keep.py"]),
                    (".\\src\\", [], ["src"]),
                    # Windows resolves both to src/keep.py; Linux and git do not.
                    ("SRC/keep.py", ["/wiki/g.md: code path `SRC/keep.py` does not exist"], []),
                    ("src/keep.py.", ["/wiki/g.md: code path `src/keep.py.` does not exist"], []),
                    (absolute, [f"/wiki/g.md: code path `{absolute}` is absolute; write it relative to the "
                                "repository root"], []),
                    ("C:\\src\\keep.py", ["/wiki/g.md: code path `C:\\src\\keep.py` is absolute; write it relative "
                                          "to the repository root"], []),
                    ("/src/keep.py", ["/wiki/g.md: code path `/src/keep.py` is absolute; write it relative to the "
                                      "repository root"], [])):
                with self.subTest(path=path):
                    g = page("g", "gotcha", code=[path])
                    hub = page("hub", "concept")
                    hub.links, g.links = {"g"}, {"hub"}
                    self.assertEqual(lint.lint_pages([hub, g], repo), findings)
                    self.assertEqual(lint.code_paths([g], repo), git)

    def test_new_types_accepted(self) -> None:
        a = page("a", "decision")
        b = page("b", "gotcha")
        a.links, b.links = {"b"}, {"a"}
        self.assertEqual(lint.lint_pages([a, b], Path(".")), [])

    def test_gotcha_guard_must_be_one_of_the_known_checks(self) -> None:
        for kind, meta, finding in (
                ("gotcha", {}, "/wiki/g.md: gotcha missing `guard` (lint, test, hook or none)"),
                ("gotcha", {"guard": "maybe"}, "/wiki/g.md: `guard` is `maybe`, expected lint, test, hook or none"),
                ("decision", {"guard": "lint"}, "/wiki/g.md: `guard` belongs on gotcha pages only")):
            with self.subTest(kind=kind, meta=meta):
                g = page("g", kind)
                g.meta.pop("guard", None)
                g.meta.update(meta)
                hub = page("hub", "concept")
                hub.links, g.links = {"g"}, {"hub"}
                self.assertEqual(lint.lint_pages([hub, g], Path(".")), [finding])

    def test_practice_needs_evidence_from_two_sessions(self) -> None:
        a, b, a2 = "session-2026-09-15-aaaaaaaa", "session-2026-09-20-bbbbbbbb-part2", "session-2026-09-15-aaaaaaaa-part2"
        cite = lambda *slugs: [f"wiki/sources/{s}.md" for s in slugs]  # noqa: E731
        needs_two = ["/wiki/p.md: practice cites 1 session, needs 2 or more"]
        cases = (
            (cite(a, "article"), needs_two),
            # Two parts of one session are one session: the continuation file repeats the same id tail.
            (cite(a, a2), needs_two),
            # A cited session with no page is no evidence: a model can write any path.
            (cite(a, "session-2026-09-21-cccccccc"), needs_two),
            (cite(a, b), []),
        )
        for sources, findings in cases:
            with self.subTest(sources=sources):
                p = page("p", "practice", sources=sources)
                hub = page("hub", "concept")
                hub.links, p.links = {"p", a, a2, b}, {"hub"}
                pages = [hub, p] + [page(s, "source", dated="2026-09-15", sources=[]) for s in (a, a2, b)]
                self.assertEqual(lint.lint_pages(pages, Path(".")), findings)

    def test_domain_page_cites_a_source_that_exists(self) -> None:
        # A business rule or design-system rule is valid from one statement (#64), but only with the statement:
        # a rule nobody stated is the agent's guess, and every later session would obey it.
        s = "session-2026-10-02-aaaaaaaa"
        no_source = ["/wiki/r.md: domain page cites no existing source page; cite the session or document that "
                     "states it"]
        for sources, findings in (([f"wiki/sources/{s}.md"], []), ([], no_source),
                                  (["wiki/sources/session-2026-10-02-bbbbbbbb.md"], no_source),
                                  # The agent's own pages are not a statement: itself, a concept, a source slug
                                  # cited from the wrong folder.
                                  (["wiki/domain/r.md"], no_source), (["wiki/concepts/hub.md"], no_source),
                                  ([f"wiki/decisions/{s}.md"], no_source)):
            with self.subTest(sources=sources):
                r = page("r", "domain", sources=sources)
                hub = page("hub", "concept")
                hub.links, r.links = {"r", s}, {"hub"}
                pages = [hub, r, page(s, "source", dated="2026-10-02", sources=[])]
                self.assertEqual(lint.lint_pages(pages, Path(".")), findings)

    def test_prune_mark_must_be_a_known_reason(self) -> None:
        for mark, findings in (("stale", []), ("redundant", []), ("low-value", []),
                               ("obsolete", ["/wiki/p.md: `prune` is `obsolete`, expected stale, redundant or low-value"])):
            with self.subTest(mark=mark):
                p = page("p", "concept", prune=mark)
                hub = page("hub", "concept")
                hub.links, p.links = {"p"}, {"hub"}
                self.assertEqual(lint.lint_pages([hub, p], Path(".")), findings)

    def test_same_slug_in_two_folders_is_a_finding(self) -> None:
        a = page("x", "decision")
        b = page("x", "gotcha")
        a.path, b.path = Path("/wiki/decisions/x.md"), Path("/wiki/gotchas/x.md")
        a.links, b.links = {"x"}, {"x"}
        findings = lint.lint_pages([a, b], Path("."))
        self.assertEqual(findings, ["/wiki/gotchas/x.md: slug `x` is also /wiki/decisions/x.md; [[x]] is ambiguous"])


class StalePages(unittest.TestCase):
    CHANGED = {"src/a.py": "2026-09-20", "src/pkg/b.py": "2026-09-12", "src/pkg/c.py": "2026-09-18"}

    def test_code_committed_after_update_is_a_warning(self) -> None:
        g = page("g", "gotcha", updated="2026-09-15", code=["src/a.py"])
        self.assertEqual(lint.stale_pages([g], self.CHANGED), [
            "/wiki/g.md: `src/a.py` changed on 2026-09-20, after the page's `updated` 2026-09-15; "
            "check the page still matches the code"])

    def test_code_committed_on_or_before_update_is_fine(self) -> None:
        g = page("g", "gotcha", updated="2026-09-20", code=["src/a.py", "src/pkg/b.py"])
        self.assertEqual(lint.stale_pages([g], self.CHANGED), [])

    def test_directory_takes_its_newest_file(self) -> None:
        d = page("d", "decision", updated="2026-09-15", code=["src/pkg/"])
        self.assertEqual(len(lint.stale_pages([d], self.CHANGED)), 1)
        self.assertIn("changed on 2026-09-18", lint.stale_pages([d], self.CHANGED)[0])

    def test_code_path_spellings_match_git_paths(self) -> None:
        for spelling in (".", "./src", "src\\pkg", "./src/pkg/c.py"):
            with self.subTest(spelling=spelling):
                p = page("p", "concept", updated="2026-09-15", code=[spelling])
                self.assertEqual(len(lint.stale_pages([p], self.CHANGED)), 1)

    def test_code_paths_keeps_only_paths_inside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            (repo / "src").mkdir(parents=True)
            (Path(d) / "outside.py").write_text("", encoding="utf-8")
            p = page("p", "concept", code=["./src/", "../outside.py", "gone.py"])
            self.assertEqual(lint.code_paths([p], repo), ["src"])


class UnguardedGotchas(unittest.TestCase):
    TODAY = date(2026, 10, 1)

    def test_old_gotcha_without_guard_is_a_warning(self) -> None:
        created = (self.TODAY - timedelta(days=lint.GUARD_GRACE_DAYS + 1)).isoformat()
        g = page("g", "gotcha", guard="none", created=created)
        self.assertEqual(lint.unguarded_gotchas([g], self.TODAY), [
            f"/wiki/g.md: gotcha created {created} still has `guard: none` after {lint.GUARD_GRACE_DAYS} days; "
            "a lint rule, test or hook would catch the mistake every time"])

    def test_lint_run_prints_the_warning_and_exits_zero(self) -> None:
        old = (date.today() - timedelta(days=lint.GUARD_GRACE_DAYS + 1)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            wiki = Path(d) / "wiki"
            wiki.mkdir()
            head = "---\ntitle: {0}\ntype: {1}\nsummary: s\ntags: []\ncreated: {2}\nupdated: {2}\nsources: []\n"
            (wiki / "g.md").write_text(head.format("g", "gotcha", old) + "guard: none\n---\n[[hub]]\n",
                                       encoding="utf-8")
            (wiki / "hub.md").write_text(head.format("hub", "concept", old) + "---\n[[g]]\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = lint.main(wiki, Path(d))
        self.assertEqual(code, 0)
        self.assertIn("still has `guard: none`", out.getvalue())

    def test_no_warning_inside_the_grace_period_or_with_a_guard(self) -> None:
        recent = self.TODAY - timedelta(days=lint.GUARD_GRACE_DAYS)
        pages = [page("new", "gotcha", guard="none", created=recent.isoformat()),
                 page("guarded", "gotcha", guard="lint", created="2026-01-01"),
                 page("decision", "decision", created="2026-01-01"),
                 page("bad-date", "gotcha", guard="none", created="soon")]
        self.assertEqual(lint.unguarded_gotchas(pages, self.TODAY), [])


def commit(repo: Path, day: str, *args: str) -> None:
    """Run a git command in `repo` with a fixed identity and both dates pinned to `day`."""
    stamp = f"2026-09-{day}T12:00:00Z"
    env = {**os.environ, "GIT_COMMITTER_DATE": stamp, "GIT_AUTHOR_DATE": stamp}
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, env=env, capture_output=True)


class RulePointers(unittest.TestCase):
    # A promoted rule is a frozen copy of its page; a domain page changes in place, and nothing noticed the AGENTS.md
    # block had gone stale (#86 review).
    def test_a_rule_whose_page_is_gone_disputed_or_pruned_is_reported(self) -> None:
        def domain(slug: str, **meta: object) -> Page:
            p = page(slug, "domain", **meta)
            p.path = Path(f"/wiki/domain/{slug}.md")
            return p

        agents = ("<!-- omoikane:rules:start -->\n- Keep a. (omoikane/wiki/domain/a.md)\n"
                  "- Keep b. (omoikane/wiki/domain/b.md)\n- Keep c. (omoikane/wiki/domain/c.md)\n"
                  "- Keep d. (omoikane/wiki/practices/d.md)\n<!-- omoikane:rules:end -->\n")
        warnings = lint.rule_pointers(agents, [domain("a"), domain("b", summary="Disputed: b or not b"),
                                               domain("c", prune="stale")])
        self.assertEqual([w.split("points at ")[1].split(",")[0] for w in warnings],
                         ["omoikane/wiki/domain/b.md", "omoikane/wiki/domain/c.md", "omoikane/wiki/practices/d.md"])
        self.assertIn("which does not exist", warnings[2])


class ReviewDiffs(unittest.TestCase):
    # distill.md says a diff that does not apply is worse than none, but nothing checked it: one was never tried and
    # another went stale once its target changed (43423c4).
    GOOD = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n one\n-two\n+2\n"
    STALE = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n uno\n-two\n+2\n"

    def lint_run(self, diff: str, committed: bool, close: str = "````\n") -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "omoikane" / "wiki").mkdir(parents=True)
            (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8", newline="\n")
            review = repo / "omoikane" / "_review.md"
            review.write_text("# Review queue\n", encoding="utf-8", newline="\n")
            commit(repo, "15", "init", "-q", "-b", "main")
            commit(repo, "15", "add", "-A")
            commit(repo, "15", "commit", "-q", "-m", "init")
            review.write_text(f"# Review queue\n\n- [ ] guard (test) two-is-a-digit: write 2 (session aaaaaaaa, "
                              f"turn 1)\n````diff\n{diff}{close}", encoding="utf-8", newline="\n")
            if committed:
                commit(repo, "16", "commit", "-q", "-am", "distill")
                # The human ticks it later; the bullet is still the one HEAD holds.
                review.write_text(review.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8",
                                  newline="\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = lint.main(repo / "omoikane" / "wiki", repo)
        return code, out.getvalue()

    def test_a_diff_that_does_not_apply_is_reported(self) -> None:
        cases = {
            "valid, new": (self.GOOD, False, "````\n", 0, None),
            "wrong context, new: the run that wrote it fixes it": (self.STALE, False, "````\n", 1, "does not apply"),
            "wrong context, committed: the target changed, the human decides": (self.STALE, True, "````\n", 0,
                                                                                "warning: omoikane/_review.md"),
            # A truncated last proposal was skipped, not checked (#110 review).
            "fence never closed": (self.STALE, False, "", 1, "never closed"),
            # git's whitespace warning came first and hid the real error (#110 review).
            "whitespace warning before the error": (self.STALE.replace("+2\n", "+2   \n"), False, "````\n", 1,
                                                    "error: patch failed"),
        }
        for name, (diff, committed, close, exit_code, expected) in cases.items():
            with self.subTest(name):
                code, out = self.lint_run(diff, committed, close)
                self.assertEqual(code, exit_code, out)
                if expected is None:
                    self.assertNotIn("_review.md", out)
                else:
                    self.assertIn(expected, out)
                    self.assertIn("two-is-a-digit", out)


class LastChanged(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        (self.repo / "src" / "a.py").write_text("1", encoding="utf-8")
        (self.repo / "other.py").write_text("1", encoding="utf-8")
        commit(self.repo, "01", "add", ".")
        commit(self.repo, "01", "commit", "-q", "-m", "one")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reads_newest_commit_per_file(self) -> None:
        (self.repo / "src" / "a.py").write_text("2", encoding="utf-8")
        commit(self.repo, "05", "commit", "-q", "-am", "two")
        self.assertEqual(lint.last_changed(self.repo, ["src"]), {"src/a.py": "2026-09-05"})

    def test_merged_change_carries_the_merge_date(self) -> None:
        # A page updated on the 15th, between the side commit (10th) and its merge (20th), is stale.
        commit(self.repo, "10", "switch", "-q", "-c", "side")
        (self.repo / "src" / "a.py").write_text("2", encoding="utf-8")
        commit(self.repo, "10", "commit", "-q", "-am", "side")
        commit(self.repo, "20", "switch", "-q", "main")
        commit(self.repo, "20", "merge", "-q", "--no-ff", "-m", "merge", "side")
        self.assertEqual(lint.last_changed(self.repo, ["src"]), {"src/a.py": "2026-09-20"})

    def test_shallow_clone_gives_no_dates(self) -> None:
        # A depth-1 clone (actions/checkout default) dates every file at HEAD; that would warn on every page.
        clone = Path(self.tmp.name) / "clone"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(clone)], check=True)
        self.assertEqual(lint.last_changed(clone, ["src"]), {})

    def test_no_repository_gives_no_dates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lint.last_changed(Path(d), ["src"]), {})

    def test_no_code_paths_gives_no_dates(self) -> None:
        self.assertEqual(lint.last_changed(Path("/nonexistent"), []), {})


class CompactIndex(unittest.TestCase):
    INDEX = "# Index\n\nGenerated by x.\n\n## Decisions (1)\n\n- [[a]] — one\n\n## Sources (1)\n\n- [[s]] — two\n"

    def test_drops_header_keeps_sections(self) -> None:
        out = context.compact_index(self.INDEX, 12_000)
        self.assertTrue(out.startswith("## Decisions (1)"))
        self.assertIn("## Sources (1)", out)
        self.assertNotIn("Generated by", out)

    def test_keeps_entries_of_a_section_larger_than_the_budget(self) -> None:
        index = "# Index\n\n## Decisions (3)\n\n- [[a]] — one\n- [[b]] — two\n- [[c]] — three\n\n## Sources (1)\n\n- [[s]] — x\n"
        out = context.compact_index(index, 50)
        self.assertIn("- [[a]] — one", out)
        self.assertNotIn("[[c]]", out)
        self.assertNotIn("## Sources", out)
        self.assertIn("Omitted by budget: Decisions 1, Sources 1. Read omoikane/index.md", out)

    def test_a_long_decision_is_not_skipped_for_shorter_sources(self) -> None:
        index = f"# Index\n\n## Decisions (1)\n\n- [[d]] — {'x' * 200}\n\n## Sources (1)\n\n- [[s]] — y\n"
        out = context.compact_index(index, 60)
        self.assertNotIn("[[s]]", out)
        self.assertIn("Omitted by budget: Decisions 1, Sources 1.", out)

    def test_no_omitted_line_when_everything_fits(self) -> None:
        self.assertNotIn("Omitted", context.compact_index(self.INDEX, 12_000))

    @staticmethod
    def index_of(*sections: tuple[str, str, int, int]) -> str:
        """Sections of (heading, slug prefix, entries, characters per summary)."""
        return "# Index\n\n" + "\n\n".join(f"## {name} ({n})\n\n" + "\n".join(f"- [[{slug}{i}]] — {'r' * size}"
                                                                           for i in range(n))
                                           for name, slug, n, size in sections)

    def test_many_domain_pages_leave_room_for_decisions_and_gotchas(self) -> None:
        # About 60 domain pages filled the 12,000 characters, and no decision or gotcha reached the brief (#75).
        index = self.index_of(("Domain", "rule", 80, 150), ("Decisions", "dec", 20, 150),
                              ("Gotchas", "got", 20, 150), ("Sources", "src", 20, 150))
        out = context.compact_index(index, 12_000)
        for first in ("[[dec0]]", "[[got0]]"):
            self.assertIn(first, out)
        # Domain still leads and keeps the largest share; sources get no floor out of the rules (#83 review).
        self.assertTrue(out.startswith("## Domain (80)"))
        self.assertGreater(out.count("[[rule"), out.count("[[dec") + out.count("[[got"))
        self.assertNotIn("[[src0]]", out)

    def test_a_first_entry_larger_than_the_floor_still_comes_in(self) -> None:
        # A decision listing many code paths outgrew the floor and vanished behind domain pages (#83 review).
        index = self.index_of(("Domain", "rule", 60, 230), ("Decisions", "big", 1, 760), ("Gotchas", "got", 5, 100))
        self.assertIn("[[big0]]", context.compact_index(index, 3_000))

    def test_the_index_part_never_passes_the_budget(self) -> None:
        # The blank line between sections was not counted, so eight kept sections ran 14 characters over (#83 review).
        names = ("Domain", "Decisions", "Gotchas", "Practices", "Concepts", "Entities", "Sources", "Queries")
        for budget in (*range(50, 2_500, 61), 12_000):
            for size in (17, 23, 32, 41):
                with self.subTest(budget=budget, size=size):
                    index = self.index_of(*((name, f"{name[:3]}{size}-", 40, size) for name in names))
                    out = context.compact_index(index, budget)
                    self.assertLessEqual(len(out.split("Omitted by budget:")[0].rstrip("\n")), budget)


class RenderIndex(unittest.TestCase):
    def test_marked_page_shows_its_mark(self) -> None:
        # Agents read the index first; a page the human has yet to delete must not look current.
        pages = [page("kept", "gotcha", summary="k"), page("old", "gotcha", summary="o", prune="stale")]
        out = index.render(pages)
        self.assertIn("- [[kept]] — k `2026-09-15`\n", out)
        self.assertIn("- [[old]] — o `2026-09-15` `prune: stale`", out)

    def test_domain_section_comes_first(self) -> None:
        # The brief keeps sections in index order up to its budget: the rules of the domain govern the code being
        # written, so they are the last to be cut (#64).
        out = index.render([page("d", "decision"), page("r", "domain", summary="Prices are integer cents")])
        self.assertLess(out.index("## Domain (1)\n\n- [[r]] — Prices are integer cents"), out.index("## Decisions"))


class PendingNotes(unittest.TestCase):
    def test_lists_undistilled_sessions_and_counts_review_items(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            omoikane = Path(d) / "omoikane"
            sessions = omoikane / "raw" / "inbox" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / ".gitkeep").write_text("", encoding="utf-8")
            # Same start day, ids in the opposite order of activity: the brief must follow the last write.
            (sessions / "2026-09-01-bbbbbbbb.md").write_text("", encoding="utf-8")
            (sessions / "2026-09-01-aaaaaaaa.md").write_text("", encoding="utf-8")
            os.utime(sessions / "2026-09-01-bbbbbbbb.md", (1_000, 1_000))
            os.utime(sessions / "2026-09-01-aaaaaaaa.md", (2_000, 2_000))
            (omoikane / "_review.md").write_text("# Review queue\n\nIntro.\n\n- one\n- two\n", encoding="utf-8")
            out = context.pending_notes(omoikane)
        self.assertLess(out.index("2026-09-01-bbbbbbbb.md"), out.index("2026-09-01-aaaaaaaa.md"))
        self.assertIn("`omoikane/raw/inbox/sessions/2026-09-01-aaaaaaaa.md`", out)
        self.assertNotIn(".gitkeep", out)
        self.assertIn("2 open items in omoikane/_review.md", out)

    def test_proposed_diff_lines_are_not_counted_as_items(self) -> None:
        # A guard or prompt proposal carries a diff; its removed lines start with "- " too.
        # A diff of a file with fences (AGENTS.md, a prompt) has context lines such as " ```": they must not
        # close the proposal's fence, which is longer for that reason.
        review = ("# Review queue\n\n- [ ] guard (lint) x: catch x\n````diff\n- old line\n ```\n- removed\n"
                  "     ```yaml\n+ new line\n````\n- [x] prompt (distill.md) y: fix y\n  ````diff\n  - old\n  ````\n"
                  "- todo z: z\n")
        with tempfile.TemporaryDirectory() as d:
            omoikane = Path(d) / "omoikane"
            omoikane.mkdir()
            (omoikane / "_review.md").write_text(review, encoding="utf-8")
            out = context.pending_notes(omoikane)
        self.assertIn("2 open items in omoikane/_review.md", out)
        self.assertIn("1 approved proposal in omoikane/_review.md", out)

    def test_ticked_rule_points_at_the_promotion_script(self) -> None:
        # A rule has no diff; an agent told to "apply the diff" would hand-edit the managed block.
        with tempfile.TemporaryDirectory() as d:
            omoikane = Path(d) / "omoikane"
            omoikane.mkdir()
            (omoikane / "_review.md").write_text("- [x] rule a: Do a. (synthesize)\n- [ ] rule b: Do b. (synthesize)\n",
                                                 encoding="utf-8")
            out = context.pending_notes(omoikane)
        self.assertIn("1 open items", out)
        self.assertIn("1 approved rule in omoikane/_review.md: the human runs python omoikane/bin/wiki-rules.py", out)
        self.assertNotIn("approved proposal", out)

    def test_empty_when_nothing_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            omoikane = Path(d) / "omoikane"
            omoikane.mkdir()
            (omoikane / "_review.md").write_text("# Review queue\n\nIntro.\n", encoding="utf-8")
            self.assertEqual(context.pending_notes(omoikane), "")


if __name__ == "__main__":
    unittest.main()
