"""Structural checks that need no LLM.

Exit 1 on any finding so agents and CI stop on it. Warnings print but keep exit 0: they need a judgement
the script cannot make, and the semantic /lint pass reads them.
Usage: python omoikane/bin/wiki-lint.py
"""
from __future__ import annotations

import os
import posixpath
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path, PureWindowsPath

from wikilib import (CODE_KEY, DATE, FENCE, GUARD_KEY, GUARDS, PAGE_TYPES, PRACTICE_MIN_SESSIONS, PRUNE_KEY,
                     PRUNE_MARKS, REPO, REQUIRED_KEYS, SESSION_PAGE, SOURCE_KEYS, UNDATED, WIKI, Page, load_pages,
                     managed_rules, review_bullets)

GUARD_CHOICES = f"{', '.join(GUARDS[:-1])} or {GUARDS[-1]}"
# The pointer wiki-rules.py ends each promoted rule with: (omoikane/wiki/<folder>/<slug>.md).
RULE_POINTER = re.compile(r"\((omoikane/wiki/([^()\s/]+/[^()\s/]+\.md))\)\s*$")
# Days a gotcha may rely on being read before the lint asks for a check. Long enough for the human to act on
# the guard distill proposed, short enough that an unguarded gotcha does not become the norm.
GUARD_GRACE_DAYS = 14


def lint_pages(pages: list[Page], repo: Path = REPO) -> list[str]:
    """Return one finding per contract violation; an empty list means clean.

    Example: lint_pages([Page(path, "x", {"type": "gotcha", "code": ["gone.py"], ...})], repo)
    returns ["...: code path `gone.py` does not exist", ...].
    """
    slugs = {p.slug for p in pages}
    source_pages = {f"wiki/sources/{p.slug}.md" for p in pages if p.meta.get("type") == "source"}
    inbound: dict[str, int] = {s: 0 for s in slugs}
    findings: list[str] = []
    # A wikilink names a slug, not a folder: `decisions/x.md` and `gotchas/x.md` would both answer [[x]].
    first_with_slug: dict[str, Page] = {}
    for p in pages:
        if p.slug in first_with_slug:
            findings.append(f"{p.rel}: slug `{p.slug}` is also {first_with_slug[p.slug].rel}; [[{p.slug}]] is ambiguous")
        first_with_slug.setdefault(p.slug, p)

    for p in pages:
        if not p.meta:
            findings.append(f"{p.rel}: missing frontmatter")
            continue
        for key in REQUIRED_KEYS:
            if key not in p.meta:
                findings.append(f"{p.rel}: frontmatter missing `{key}`")
        if p.meta.get("type") not in PAGE_TYPES:
            findings.append(f"{p.rel}: type must be one of {', '.join(PAGE_TYPES)}")
        if p.meta.get("type") == "gotcha":
            guard = p.meta.get(GUARD_KEY)
            if guard is None:
                findings.append(f"{p.rel}: gotcha missing `{GUARD_KEY}` ({GUARD_CHOICES})")
            elif guard not in GUARDS:
                findings.append(f"{p.rel}: `{GUARD_KEY}` is `{guard}`, expected {GUARD_CHOICES}")
        elif GUARD_KEY in p.meta:
            findings.append(f"{p.rel}: `{GUARD_KEY}` belongs on gotcha pages only")
        mark = p.meta.get(PRUNE_KEY)
        if mark is not None and mark not in PRUNE_MARKS:
            findings.append(f"{p.rel}: `{PRUNE_KEY}` is `{mark}`, expected {', '.join(PRUNE_MARKS[:-1])} or "
                            f"{PRUNE_MARKS[-1]}")
        if p.meta.get("type") == "practice":
            cited = p.meta.get("sources")
            # Only session pages that exist count: a cited path is not evidence until the page is there.
            sessions = {m.group(1) for s in (cited if isinstance(cited, list) else [])
                        if (m := SESSION_PAGE.match(str(s))) and posixpath.basename(str(s))[:-3] in slugs}
            if len(sessions) < PRACTICE_MIN_SESSIONS:
                findings.append(f"{p.rel}: practice cites {len(sessions)} session, "
                                f"needs {PRACTICE_MIN_SESSIONS} or more")
        if p.meta.get("type") == "domain":
            cited = p.meta.get("sources")
            # Valid from one statement, but only with it: a rule nobody stated is a guess every session would obey.
            # Only a source page records a statement; the agent's own pages (this one, a concept) do not.
            if not any(str(s) in source_pages for s in (cited if isinstance(cited, list) else [])):
                findings.append(f"{p.rel}: domain page cites no existing source page; cite the session or document "
                                "that states it")
        if p.meta.get("type") == "source":
            for key in SOURCE_KEYS:
                if key not in p.meta:
                    findings.append(f"{p.rel}: source page missing `{key}` (date the source bears, or {UNDATED})")
        for key in ("created", "updated", "dated"):
            value = str(p.meta.get(key, ""))
            if key in p.meta and not DATE.match(value) and not (key == "dated" and value == UNDATED):
                findings.append(f"{p.rel}: `{key}` is `{value}`, expected YYYY-MM-DD")
        summary = str(p.meta.get("summary", ""))
        if len(summary) > 120:
            findings.append(f"{p.rel}: summary is {len(summary)} chars, limit 120")
        for target in p.links:
            if target in slugs:
                inbound[target] += 1
            else:
                findings.append(f"{p.rel}: broken wikilink [[{target}]]")
        # `sources:` entries are relative to omoikane/ (`wiki/sources/x.md`), matching the page contract in AGENTS.md.
        for src in p.meta.get("sources", []) or []:
            if not (str(src).startswith("wiki/") and str(src).endswith(".md")):
                findings.append(f"{p.rel}: sources entry `{src}` is not a wiki path")
        code = p.meta.get(CODE_KEY, [])
        if not isinstance(code, list):
            findings.append(f"{p.rel}: `{CODE_KEY}` must be an inline list of repository paths")
            code = []
        for path in code:
            # `code:` entries are relative to the repository root. A page about code that no longer exists is stale
            # by definition; the agent must revisit it. Paths escaping the repository are never valid.
            if is_absolute(path):
                findings.append(f"{p.rel}: code path `{path}` is absolute; write it relative to the repository root")
            elif existing_code_path(repo, path) is None:
                findings.append(f"{p.rel}: code path `{path}` does not exist")

    for p in pages:
        if inbound.get(p.slug, 0) == 0 and p.meta.get("type") != "query":
            findings.append(f"{p.rel}: orphan page, no inbound wikilink")
    return findings


def git_path(path: object) -> str:
    """Spell a `code:` entry the way git prints paths: posix, relative, no `./` or trailing slash.

    Backslashes (a page written on Windows) become slashes.
    Example: git_path("./src/pkg/") returns "src/pkg"; git_path(".") returns ".".
    """
    return posixpath.normpath(str(path).replace("\\", "/"))


def is_absolute(path: object) -> bool:
    """True for a path that names one machine's checkout: `/x`, `\\x`, `C:\\x`, `C:x`, `\\\\server\\share`.

    Example: is_absolute("C:\\src") returns True; is_absolute("src/a.py") returns False.
    """
    return bool(PureWindowsPath(str(path)).anchor)


def existing_code_path(repo: Path, path: object) -> str | None:
    """The `code:` entry in git spelling when it names something inside the repository, else None.

    Resolved from its git spelling, never the raw string, and every component must exist with its exact name,
    so Windows and Linux agree (#32): `src\\a.py` is `src/a.py` on both, while `SRC/a.py` and `src/a.py.`,
    which Windows would resolve, exist on neither. Absolute paths are None on every OS.
    Example: existing_code_path(repo, ".\\src\\") returns "src"; existing_code_path(repo, "C:\\src") returns None.
    """
    if is_absolute(path):
        return None
    spelled = git_path(path)
    if not (repo / spelled).resolve().is_relative_to(repo.resolve()):
        return None
    here = repo
    for part in [] if spelled == "." else spelled.split("/"):
        if not here.is_dir() or part not in os.listdir(here):
            return None
        here = here / part
    return spelled


def code_paths(pages: list[Page], repo: Path = REPO) -> list[str]:
    """Every `code:` path that exists inside the repository, in git spelling.

    Paths `lint_pages` reports as missing, absolute or outside the repository are left out: git refuses a
    pathspec outside the repository, and one bad page must not hide every other finding behind a traceback.
    Example: code_paths([page with code ["./src/", "../outside.py"]], repo) returns ["src"].
    """
    paths: set[str] = set()
    for p in pages:
        code = p.meta.get(CODE_KEY)
        if not isinstance(code, list):
            continue
        paths.update(spelled for path in code if (spelled := existing_code_path(repo, path)) is not None)
    return sorted(paths)


def last_changed(repo: Path, paths: list[str]) -> dict[str, str]:
    """Map each file under `paths` to the date (YYYY-MM-DD) its newest change reached the current branch.

    One `git log` call, limited to the `code:` paths so a long history outside them costs nothing.
    `--first-parent` dates a merged change at its merge, not at the side commit (this repository merges
    PRs with merge commits). Returns {} without git, outside a repository, or in a shallow clone, where
    every file would carry HEAD's date and every page would warn.
    Example: last_changed(repo, ["src"]) returns {"src/a.py": "2026-09-05"}.
    """
    if not paths:
        return {}
    git = ["git", "-C", str(repo), "-c", "core.quotePath=false"]
    try:
        shallow = subprocess.run([*git, "rev-parse", "--is-shallow-repository"], capture_output=True, text=True,
                                 check=False)
        if shallow.returncode != 0 or shallow.stdout.strip() != "false":
            return {}
        log = subprocess.run([*git, "log", "--first-parent", "--format=>%cs", "--name-only", "--", *paths],
                             capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError:
        return {}
    if log.returncode != 0:
        return {}
    dates: dict[str, str] = {}
    current = ""
    for line in log.stdout.splitlines():
        if line.startswith(">"):
            current = line[1:]
        elif line:
            dates.setdefault(line, current)  # git log lists newest first
    return dates


def stale_pages(pages: list[Page], changed: dict[str, str]) -> list[str]:
    """Warn about pages whose `code:` paths have a commit dated after the page's `updated` date.

    Most code changes leave the page true, so this is a warning for /lint to judge, not a finding.
    Example: stale_pages([gotcha with updated 2026-09-15, code [src/a.py]], {"src/a.py": "2026-09-20"})
    returns ["...: `src/a.py` changed on 2026-09-20, after the page's `updated` 2026-09-15; ..."].
    """
    warnings: list[str] = []
    for p in pages:
        updated = str(p.meta.get("updated", ""))
        code = p.meta.get(CODE_KEY) or []
        if not isinstance(code, list) or not DATE.match(updated):
            continue
        for path in code:
            prefix = git_path(path)
            latest = max((d for f, d in changed.items()
                          if prefix == "." or f == prefix or f.startswith(prefix + "/")), default="")
            if latest > updated:
                warnings.append(f"{p.rel}: `{path}` changed on {latest}, after the page's `updated` {updated}; "
                                "check the page still matches the code")
    return warnings


def unguarded_gotchas(pages: list[Page], today: date) -> list[str]:
    """Warn about gotchas that still have `guard: none` more than GUARD_GRACE_DAYS after they were created.

    A warning, not a finding: some mistakes no check can catch, and /lint judges which.
    Example: unguarded_gotchas([gotcha created 2026-09-01, guard none], date(2026, 10, 1))
    returns ["...: gotcha created 2026-09-01 still has `guard: none` after 14 days; ..."].
    """
    cutoff = (today - timedelta(days=GUARD_GRACE_DAYS)).isoformat()
    warnings: list[str] = []
    for p in pages:
        created = str(p.meta.get("created", ""))
        if p.meta.get("type") != "gotcha" or p.meta.get(GUARD_KEY) != "none" or not DATE.match(created):
            continue
        if created < cutoff:
            warnings.append(f"{p.rel}: gotcha created {created} still has `guard: none` after {GUARD_GRACE_DAYS} "
                            "days; a lint rule, test or hook would catch the mistake every time")
    return warnings


def rule_pointers(agents: str, pages: list[Page]) -> list[str]:
    """Warn about each promoted rule in AGENTS.md whose page is gone, now `Disputed:` or marked `prune:`: the block
    still states the old rule in every session (#86 review: a domain page changes in place, and nothing noticed).

    Warnings, not findings: only the human edits the block, and a finding goes back to the scheduled run's agent,
    which may not touch AGENTS.md and would spend every lint round on it. /lint reads warnings.
    Example: rule_pointers("<!-- omoikane:rules:start -->\\n- Do x. (omoikane/wiki/domain/x.md)\\n<!-- ... -->", [])
    returns ["AGENTS.md: the rule \\"- Do x. ...\\" points at omoikane/wiki/domain/x.md, which does not exist; ..."].
    """
    by_place = {f"{p.path.parent.name}/{p.path.name}": p for p in pages}
    warnings: list[str] = []
    for rule in managed_rules(agents) or []:
        m = RULE_POINTER.search(rule)
        if not m:
            continue
        page = by_place.get(m.group(2))
        if page is None:
            warnings.append(f"AGENTS.md: the rule \"{rule}\" points at {m.group(1)}, which does not exist; the human "
                            "repoints or retires it in the rules block")
        elif str(page.meta.get("summary", "")).startswith("Disputed:") or PRUNE_KEY in page.meta:
            warnings.append(f"AGENTS.md: the rule \"{rule}\" points at {m.group(1)}, now disputed or marked prune; "
                            "the block still states it to every session")
    return warnings


def review_diffs(review: str) -> list[tuple[str, str, bool]]:
    """Each diff fence of _review.md (info string `diff`) under a bullet of its section, as (bullet, diff text,
    whether the fence closes). Fences follow wikilib.review_lines, so a ``` context line inside a four-backtick diff
    does not close it.

    Example: review_diffs("- [ ] guard (test) x: y\\n````diff\\n--- a/f\\n````\\n") returns
    [("- [ ] guard (test) x: y", "--- a/f\\n", True)].
    """
    diffs: list[tuple[str, str, bool]] = []
    bullet, fence, is_diff, body = "", "", False, []
    # split, not splitlines: a form feed or   in a context line would split the diff and corrupt it.
    for line in review.split("\n"):
        m = FENCE.match(line)
        if not fence and m:
            fence, is_diff, body = m.group(1), m.group(2).strip() == "diff", []
        elif fence and m and m.group(1).startswith(fence) and not m.group(2).strip():
            if is_diff and bullet:
                diffs.append((bullet, "".join(body), True))
            fence = ""
        elif fence:
            body.append(line + "\n")
        elif line.startswith("- "):
            bullet = line
        elif line.startswith("#"):
            bullet = ""  # a diff under a new heading belongs to no earlier bullet
    if fence and is_diff and bullet:
        diffs.append((bullet, "".join(body), False))  # a truncated last proposal (#110 review)
    return diffs


def unchecked(bullet: str) -> str:
    """The bullet with its checkbox cleared: ticking a proposal does not make it a new one."""
    return re.sub(r"^- \[[xX]\]", "- [ ]", bullet)


def review_patches(review: Path, repo: Path) -> tuple[list[str], list[str]]:
    """(findings, warnings) for the diffs in _review.md that `git apply --check` rejects (#106).

    A bullet HEAD's _review.md lacks was written by this run, which can fix its own diff, so it is a finding. An
    older one went stale when its target changed; only the human rewrites or deletes it, and a finding would go
    back to a scheduled run that may not (gotcha lint-findings-the-scheduled-agent-cannot-fix-are-warnings).
    Example: a new guard whose diff has wrong context lines gives (["omoikane/_review.md: the diff under ..."], []).
    """
    if not review.is_file():
        return [], []
    rel = posixpath.relpath(review.resolve().as_posix(), repo.resolve().as_posix())
    try:
        # `./`: relative to `repo`, not to the top of the repository it sits in.
        shown = subprocess.run(["git", "-C", str(repo), "show", f"HEAD:./{rel}"], capture_output=True, text=True,
                               encoding="utf-8", check=False)
    except OSError:
        return [], []  # no git: skipped, as the `code:` dates are
    committed = {unchecked(b) for b in review_bullets(shown.stdout)} if shown.returncode == 0 else set()
    findings: list[str] = []
    warnings: list[str] = []
    for bullet, diff, closed in review_diffs(review.read_text(encoding="utf-8")):
        if closed:
            # Bytes, not text: on Windows a text pipe writes every \n as \r\n, and no diff would apply.
            check = subprocess.run(["git", "-C", str(repo), "apply", "--check", "-"], input=diff.encode("utf-8"),
                                   capture_output=True, check=False)
            if check.returncode == 0:
                continue
            lines = check.stderr.decode("utf-8", "replace").strip().splitlines()
            # git warns about whitespace before it names the failure; the agent must see the failure.
            error = next((line for line in lines if line.startswith("error:")), lines[0] if lines else "git apply "
                         "failed")
        else:
            error = "its fence is never closed"
        if unchecked(bullet) in committed:
            warnings.append(f"{rel}: the diff under \"{bullet}\" no longer applies ({error}); its target changed "
                            "since it was proposed, so the human rewrites or deletes it")
        else:
            findings.append(f"{rel}: the diff under \"{bullet}\" does not apply ({error}); read the target file "
                            "again and rewrite the diff against it, 3 lines of context, paths as a/<path> b/<path>")
    return findings, warnings


def main(wiki: Path = WIKI, repo: Path = REPO) -> int:
    pages = load_pages(wiki)
    findings = lint_pages(pages, repo)
    warnings = stale_pages(pages, last_changed(repo, code_paths(pages, repo))) + unguarded_gotchas(pages, date.today())
    agents = repo / "AGENTS.md"
    if agents.is_file():
        warnings += rule_pointers(agents.read_text(encoding="utf-8"), pages)
    patch_findings, patch_warnings = review_patches(wiki.parent / "_review.md", repo)
    findings += patch_findings
    warnings += patch_warnings
    for f in findings:
        print(f)
    for w in warnings:
        print(f"warning: {w}")
    print(f"wiki-lint: {len(pages)} pages, {len(findings)} findings, {len(warnings)} warnings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
