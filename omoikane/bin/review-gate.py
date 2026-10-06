"""Keep the scheduled run's commits off the human's checkout: a worktree on wiki/auto, pushed as a PR to main.

`prepare` brings the worktree up to date (origin/wiki/auto, then origin/main, both by merge: no rebase, no
force-push) and moves the quiet captures from the human's inbox into it; wiki-ingest.ps1 then runs there and
commits each operation. `publish` pushes wiki/auto and opens the PR, or lets the push update the open one.
Merging stays the human's act (#45).

Usage: python omoikane/bin/review-gate.py prepare [--quiet-minutes 30] [--worktree DIR]
       python omoikane/bin/review-gate.py publish [--worktree DIR] [--gh PATH]
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from wikilib import REPO

BRANCH = "wiki/auto"
INBOX = Path("omoikane/raw/inbox")
# Generated from frontmatter, so both sides of a conflict are wrong and the regenerated file is right.
INDEX = "omoikane/index.md"
# The human decides here by deleting and ticking bullets, the run only appends: a conflict is resolved as main's
# file plus the bullets the branch added. Not merge=union, which brought deleted bullets back (#56 review).
REVIEW = "omoikane/_review.md"
# All that -Commit commits. The scheduler runs the worktree's own scripts, so wiki/auto may differ from main in
# nothing else: it is not a protected branch (#56 review).
COMMITTED = ("omoikane/wiki", "omoikane/raw", "omoikane/log.md", REVIEW, INDEX)
BLOCKED = "omoikane/.wiki-ingest.blocked"


class GateError(Exception):
    """The worktree cannot be brought up to date without a human: a conflict, or a run that left changes."""


def git(cwd: Path, *args: str) -> str:
    run = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", check=False)
    if run.returncode != 0:
        raise GateError(f"git {' '.join(args)}: {run.stderr.strip()}")
    return run.stdout


def git_ok(cwd: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=False).returncode == 0


def default_worktree(repo: Path) -> Path:
    """Beside the repository, so no tool that walks the checkout sees it. Example: .../omoikane-wiki-auto."""
    return repo.parent / f"{repo.name}-wiki-auto"


def run_wiki_index(worktree: Path) -> None:
    subprocess.run([sys.executable, str(worktree / "omoikane" / "bin" / "wiki-index.py")], cwd=worktree,
                   capture_output=True, check=True)


def remote_branch_exists(repo: Path) -> bool:
    return bool(git(repo, "branch", "--remotes", "--list", f"origin/{BRANCH}").strip())


# Base lines before an added run that must still stand together in main's file to place the run after them: one
# line is ambiguous, since every proposal ends in the same closing fence.
ANCHOR_LINES = 3


def added_hunks(base: list[str], ours: list[str]) -> list[tuple[list[str], list[str]]]:
    """Each run of lines `ours` inserted relative to `base`, with up to ANCHOR_LINES base lines before it.

    Example: added_hunks(["a\\n", "b\\n"], ["a\\n", "x\\n", "b\\n"]) returns [(["a\\n"], ["x\\n"])].
    """
    return [(base[max(0, i1 - ANCHOR_LINES):i1], ours[j1:j2])
            for tag, i1, _, j1, j2 in difflib.SequenceMatcher(None, base, ours, autojunk=False).get_opcodes()
            if tag in ("insert", "replace")]


def find(lines: list[str], run: list[str], start: int = 0) -> int | None:
    """Index of the first place `run` stands in `lines` from `start`, or None."""
    return next((i for i in range(start, len(lines) - len(run) + 1) if lines[i:i + len(run)] == run), None)


def resolve_review(worktree: Path, ref: str) -> None:
    """Write _review.md as `ref`'s file plus each run of lines the branch added since the merge base, placed after
    the base lines it followed when they still stand together, at the end otherwise; once one run goes to the end,
    the later ones follow it, so the branch's order holds. A run main's file already holds as a whole is skipped;
    runs are compared whole, not line by line, so a diff proposal keeps its fences and headers.

    Example: base "a b", branch "a b c", main "a" (b rejected) gives "a c".
    """
    def show(rev: str) -> list[str]:
        text = git(worktree, "show", f"{rev}:{REVIEW}")
        return (text if text.endswith("\n") or not text else text + "\n").splitlines(keepends=True)

    base = git(worktree, "merge-base", "HEAD", ref).strip()
    theirs = show(ref)
    result = list(theirs)
    at = 0  # insertion point after the previous hunk, so hunks keep their order
    for anchor, run in added_hunks(show(base), show("HEAD")):
        if find(theirs, run) is not None:
            continue
        found = find(result, anchor, at) if anchor else 0
        at = len(result) if found is None else found + len(anchor)
        result[at:at] = run
        at += len(run)
    (worktree / REVIEW).write_text("".join(result), encoding="utf-8", newline="\n")


def merge(worktree: Path, ref: str, regenerate: Callable[[Path], None]) -> None:
    """Merge `ref` into the worktree's branch. A conflict in the generated index is resolved by regenerating it,
    one in _review.md by `resolve_review`; any other conflict is aborted, leaving the branch as it was, and raised.
    Example: merge(work, "origin/main", run_wiki_index).
    """
    run = subprocess.run(["git", "-C", str(worktree), "merge", "--no-edit", ref], capture_output=True, text=True,
                         encoding="utf-8", check=False)
    if run.returncode == 0:
        return
    conflicted = git(worktree, "diff", "--name-only", "--diff-filter=U").split()
    if conflicted and set(conflicted) <= {INDEX, REVIEW}:
        try:
            if REVIEW in conflicted:
                resolve_review(worktree, ref)
                git(worktree, "add", REVIEW)
            if INDEX in conflicted:
                regenerate(worktree)
                git(worktree, "add", INDEX)
            git(worktree, "commit", "--no-edit", "-q")
            return
        except (GateError, subprocess.CalledProcessError, OSError) as exc:
            # Left mid-merge, the next prepare would blame a crashed run instead of this.
            subprocess.run(["git", "-C", str(worktree), "merge", "--abort"], capture_output=True, check=False)
            raise GateError(f"resolving the conflict with {ref} in {', '.join(conflicted)} failed: {exc}") from exc
    subprocess.run(["git", "-C", str(worktree), "merge", "--abort"], capture_output=True, check=False)
    raise GateError(f"{BRANCH} conflicts with {ref} in {', '.join(conflicted) or run.stderr.strip()}; "
                    "merge it by hand in the worktree")


def patch_id(worktree: Path, *revs: str) -> str:
    """The stable patch id of the diff between `revs`, without context lines, so edits near it do not change it."""
    diff = subprocess.run(["git", "-C", str(worktree), "diff", "-U0", *revs], capture_output=True, check=True).stdout
    out = subprocess.run(["git", "-C", str(worktree), "patch-id", "--stable"], input=diff, capture_output=True,
                         check=True).stdout.decode()
    return out.split()[0] if out.strip() else ""


def find_landed(worktree: Path) -> tuple[str, str] | None:
    """The first and last of a run of consecutive non-merge commits on origin/main whose combined -U0 patch is what
    the branch changed up to one of its own commits: the branch landed by squash (a run of one) or by rebase
    merge (one commit per branch commit), possibly of an earlier head than the tip. None when there is none.
    Only main commits the branch does not hold are scanned, so a recorded landing is not found again, and only
    branch commits after `settled` are candidates. The longest matching run wins: a rebase recorded as its first
    commit alone let the next merge bring back a bullet deleted from a later one (#56 review 5).

    Example: find_landed(work) returns ("<sha>", "<sha>") after the PR was squash-merged.
    """
    since = settled(worktree)
    exclude = ["^origin/main"] + ([f"^{since}"] if since else [])
    wanted: set[str] = set()
    for commit in git(worktree, "rev-list", "--first-parent", "HEAD", *exclude).split():
        base = git(worktree, "merge-base", commit, "origin/main").strip()
        wanted.add(patch_id(worktree, base, commit))
    wanted.discard("")
    # A list, not a set: its length caps the window, and two branch commits can share a patch (#56 review 7).
    own = [patch_id(worktree, f"{c}^", c)
           for c in git(worktree, "rev-list", "--no-merges", "HEAD", *exclude).split()]
    if not wanted or not own:
        return None
    chain = git(worktree, "rev-list", "--first-parent", "--reverse", "origin/main", "^HEAD").split()
    merges = set(git(worktree, "rev-list", "--merges", "--first-parent", "origin/main", "^HEAD").split())
    single: dict[str, str] = {}

    def replayed(commit: str) -> bool:
        if commit not in single:
            single[commit] = patch_id(worktree, f"{commit}^", commit)
        return single[commit] in own

    for i, first in enumerate(chain):
        # A run longer than one is a rebase: each commit in it replays a branch commit, so a human revert right
        # after it is not swallowed by a combined patch that happens to match (#56 review 6).
        run = []
        for commit in chain[i:i + len(own)]:
            if commit in merges or (run and not (replayed(first) and replayed(commit))):
                break
            run.append(commit)
        for last in reversed(run):
            if patch_id(worktree, f"{first}^", last) in wanted:
                return first, last
    return None


def settled(worktree: Path) -> str | None:
    """The newest first-parent merge of a main commit whose tree is main's: after it the branch held nothing main
    had not taken. Branch commits before it are no longer candidates; kept, they matched a human revert on main and
    grew the scan every run (#56 review 5). A tree equal to the branch side is not enough: a `-s ours` record of
    an earlier head has it while later commits are still unlanded (#56 review 6).

    Example: settled(work) returns "<sha>" of the merge that synced the branch with main, None on a fresh branch.
    """
    for line in git(worktree, "rev-list", "--first-parent", "--parents", "HEAD", "^origin/main").splitlines():
        commit, *parents = line.split()
        if len(parents) != 2 or not git_ok(worktree, "merge-base", "--is-ancestor", parents[1], "origin/main"):
            continue
        trees = git(worktree, "rev-parse", f"{commit}^{{tree}}", f"{parents[1]}^{{tree}}").split()
        if trees[0] == trees[1]:
            return commit
    return None


def take_landed(worktree: Path, regenerate: Callable[[Path], None]) -> None:
    """Record a squash or rebase merge of the branch as merged, so the next merge of main starts after it. Without
    this the merge base stays before the landed lines, and a clean merge brings back a bullet the human deleted
    afterwards (#56 reviews 3 and 4): main up to the landing comes in by a normal merge, the landed commits with
    `-s ours`, since their content is the branch's own."""
    landed = find_landed(worktree)
    if landed is None:
        return
    first, last = landed
    merge(worktree, f"{first}^", regenerate)
    git(worktree, "merge", "-q", "-s", "ours", "--no-edit", "-m",
        f"Record the landing {first[:7]}..{last[:7]} of {BRANCH} on main", last)


def move_captures(repo: Path, worktree: Path, quiet_minutes: int, now: float) -> list[str]:
    """Move inbox files from the checkout into the worktree. A captured session modified in the last
    `quiet_minutes` may still be growing (the Stop hook rewrites it every turn) and stays. So does a file
    origin/main holds byte for byte: the worktree gets it from main, and moving it would leave a deletion in the
    human's checkout (#78). A tracked file the human edited, or never pushed, still moves: main has not got it.
    Example: move_captures(repo, work, 30, time.time()) returns ["omoikane/raw/inbox/sessions/<day>-<id8>.md"].
    """
    moved: list[str] = []
    inbox = repo / INBOX
    # On Windows the disk may spell a name in another case than the tree; a case-only rename must still match.
    ignorecase = subprocess.run(["git", "-C", str(repo), "config", "--bool", "core.ignorecase"], capture_output=True,
                                text=True, check=False).stdout.strip() == "true"  # unset, exit 1, on Linux
    fold = str.casefold if ignorecase else str
    on_main = {fold(line.split("\t", 1)[1]): line.split()[2]
               for line in git(repo, "ls-tree", "-r", "-z", "origin/main", "--", INBOX.as_posix()).split("\0") if line}
    for path in sorted(p for p in inbox.rglob("*") if p.is_file() and p.name != ".gitkeep") if inbox.is_dir() else []:
        if path.parent.name == "sessions" and path.stat().st_mtime > now - quiet_minutes * 60:
            continue
        rel = path.relative_to(repo).as_posix()
        if fold(rel) in on_main and git(repo, "hash-object", "--", rel).strip() == on_main[fold(rel)]:
            continue
        (worktree / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(worktree / rel))
        moved.append(rel)
    return moved


def prepare(repo: Path, worktree: Path, quiet_minutes: int, regenerate: Callable[[Path], None] = run_wiki_index,
            now: float | None = None) -> list[str]:
    """Bring the worktree on wiki/auto up to date with origin and move the quiet captures into it.

    Returns the moved paths. Raises GateError when the worktree holds changes a crashed run left, or a merge
    conflicts outside the index: both need the human, and running on would bury them.
    Example: prepare(Path("omoikane"), Path("omoikane-wiki-auto"), 30) returns ["omoikane/raw/inbox/a.md"].
    """
    git(repo, "fetch", "-q", "--prune", "origin")
    remote = remote_branch_exists(repo)
    if not (worktree / ".git").exists():
        git(repo, "worktree", "prune")
        if git_ok(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}"):
            # Never -B over an existing branch: commits a failed publish left unpushed would be dropped.
            git(repo, "worktree", "add", "-q", str(worktree), BRANCH)
        else:
            git(repo, "worktree", "add", "-q", "-b", BRANCH, str(worktree),
                f"origin/{BRANCH}" if remote else "origin/main")
    if (worktree / BLOCKED).exists():
        raise GateError(f"{worktree / BLOCKED} is there: read the worktree and its .wiki-ingest.log, then delete it")
    # A source whose operation failed stays untracked in the inbox and is retried; it is not a crashed run's leftover.
    dirty = git(worktree, "status", "--porcelain", "--untracked-files=all", "--", ".", f":!{INBOX.as_posix()}").strip()
    if dirty:
        raise GateError(f"the worktree has changes no run committed:\n{dirty}")
    # Before any merge: resolving an index conflict runs the worktree's own wiki-index.py.
    for ref in ("HEAD", *((f"origin/{BRANCH}",) if remote else ())):
        refuse_code(worktree, ref, since_base=True)
    if remote:
        merge(worktree, f"origin/{BRANCH}", regenerate)
    take_landed(worktree, regenerate)
    merge(worktree, "origin/main", regenerate)
    refuse_code(worktree, "HEAD")
    return move_captures(repo, worktree, quiet_minutes, time.time() if now is None else now)


def refuse_code(worktree: Path, ref: str, since_base: bool = False) -> None:
    """Raise GateError when `ref` differs from origin/main in anything -Commit does not commit. With `since_base`,
    only in what `ref` itself changed since the merge base: a criss-cross history can pick a base the human's own
    commits on main sit after.

    Example: refuse_code(work, "HEAD") raises on a wiki/auto that edited omoikane/bin/wiki-index.py.
    """
    def changed(*revs: str) -> set[str]:
        return set(git(worktree, "diff", "--name-only", *revs, "--", ".", *(f":!{p}" for p in COMMITTED)).split())

    beyond = changed("origin/main", ref)
    if since_base:
        beyond &= changed(f"origin/main...{ref}")
    if beyond:
        raise GateError(f"{BRANCH} differs from main outside the wiki, and the scheduler would run it: "
                        f"{', '.join(sorted(beyond))}")


def publish(worktree: Path, gh: Sequence[str] = ("gh",)) -> str:
    """Push wiki/auto when it is ahead of origin/main and open the PR, or let the push update the open one.

    Example: publish(Path("omoikane-wiki-auto")) returns "pushed; opened https://github.com/o/r/pull/9".
    """
    ahead = git(worktree, "log", "--format=- %s", "--reverse", "origin/main..HEAD").strip()
    # After a squash merge the commits stay ahead of main, but their content is in it.
    if not ahead or git_ok(worktree, "diff", "--quiet", "origin/main", "HEAD"):
        return "nothing to publish"

    def run_gh(*args: str) -> str:
        run = subprocess.run([*gh, *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8")
        if run.returncode != 0:  # gh's stderr says why, e.g. "gh auth login"
            raise GateError(f"gh {' '.join(args[:2])}: {run.stderr.strip()}")
        return run.stdout

    # `--state closed` also lists merged PRs. A rejected head that HEAD contains would go out again in a new PR,
    # whatever commits a later run or a merge from main put on top of it.
    closed = json.loads(run_gh("pr", "list", "--head", BRANCH, "--base", "main", "--state", "closed",
                               "--json", "number,headRefOid,state") or "[]")
    rejected = [pr for pr in closed if pr.get("state") == "CLOSED"
                and git_ok(worktree, "merge-base", "--is-ancestor", str(pr.get("headRefOid")), "HEAD")
                and not git_ok(worktree, "merge-base", "--is-ancestor", str(pr.get("headRefOid")), "origin/main")]
    if rejected:
        return (f"PR #{rejected[0]['number']} was closed unmerged and {BRANCH} still holds its commits; nothing "
                f"opened. To start over, reset {BRANCH} to origin/main in the worktree and delete the remote branch")
    git(worktree, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{BRANCH}")
    open_prs = json.loads(run_gh("pr", "list", "--head", BRANCH, "--base", "main", "--state", "open",
                                 "--json", "number,url") or "[]")
    if open_prs:
        return f"pushed; PR #{open_prs[0]['number']} updated"
    body = ("Opened by the scheduled run of `omoikane/bin/wiki-ingest.ps1 -Commit` (review gate). "
            "Read the diff before merging; the run never merges.\n\n" + ahead + "\n")
    url = run_gh("pr", "create", "--base", "main", "--head", BRANCH, "--title", "wiki: scheduled updates",
                 "--body", body).strip()
    return f"pushed; opened {url}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("prepare", "publish"))
    parser.add_argument("--worktree", type=Path, default=default_worktree(REPO))
    parser.add_argument("--quiet-minutes", type=int, default=30)
    parser.add_argument("--gh", default="gh", help="the gh executable, by path on Windows (wiki-ingest.ps1 resolves it)")
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            for rel in prepare(REPO, args.worktree, args.quiet_minutes):
                print(f"review-gate: moved {rel}", file=sys.stderr)
        else:
            print(f"review-gate: {publish(args.worktree, (args.gh,))}")
    except (GateError, subprocess.CalledProcessError) as exc:
        print(f"review-gate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
