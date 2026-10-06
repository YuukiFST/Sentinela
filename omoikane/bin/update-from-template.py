"""Merge the template's later prompts, scripts and docs into a system, keeping the system's own memory.

A system born from the template had no path to take later fixes: a plain `git merge template/main` brought the
template's own captures and pages into the system's wiki and conflicted on _review.md and index.md (#105). This
fetches the `template` remote, merges template/main without committing, puts back the paths the system owns
(MEMORY) as HEAD has them, removes what the template added there, keeps the rules block of AGENTS.md as the
system has it and regenerates index.md with the merged wiki-index.py. Any other conflict stays for the human. It
refuses a tree with uncommitted changes or an operation in progress and never commits: read `git diff --cached`,
then commit, or undo with `git merge --abort`.

A repository made with "Use this template" shares no commit with the template, and its root commit holds the
template's tree as it was. The template commit with that tree is grafted under the root for the merge only, so
the merge finds the base a clone would; the merge commit then relates the histories for every later update.

Exit codes: 0 merged and staged; 1 merged, with conflicts left for the human; 2 refused or failed before merging,
nothing changed; 3 failed after the merge started, which `git merge --abort` undoes.
Usage: python omoikane/bin/update-from-template.py [--branch main]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from wikilib import REPO, RULES_END, RULES_START

TEMPLATE_REMOTE = "template"
# What the system learned about itself; the template's own copies of these are its memory, not a fix.
MEMORY = ("omoikane/wiki", "omoikane/raw", "omoikane/log.md", "omoikane/_review.md")
INDEX = "omoikane/index.md"
# The index is rendered by these as merged, the way CI renders it; while one is in conflict the human does it.
RENDERER = ("omoikane/bin/wiki-index.py", "omoikane/bin/wikilib.py")
AGENTS = "AGENTS.md"
# Files git writes while a merge, rebase, cherry-pick or revert waits for the human (`git rev-parse --git-path`).
IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")


class Refused(Exception):
    """A reason to stop before the tree is changed."""


def git(repo: Path, *args: str, ok: tuple[int, ...] = (0,), stdin: str | None = None) -> str:
    run = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                         input=stdin)
    if run.returncode not in ok:
        raise subprocess.CalledProcessError(run.returncode, ["git", *args], run.stdout, run.stderr)
    return run.stdout


def tracked(repo: Path, rev: str | None) -> set[str]:
    """Files under MEMORY in `rev`, or in the index when `rev` is None (unmerged paths included)."""
    listed = (git(repo, "ls-tree", "-r", "-z", "--name-only", rev, "--", *MEMORY) if rev
              else git(repo, "ls-files", "-z", "--", *MEMORY))
    return set(filter(None, listed.split("\0")))


def unmerged(repo: Path) -> list[str]:
    return sorted(set(filter(None, git(repo, "diff", "-z", "--name-only", "--diff-filter=U").split("\0"))))


def roots(repo: Path) -> list[str]:
    return git(repo, "rev-list", "--max-parents=0", "HEAD").split()


def template_base(repo: Path, target: str) -> str | None:
    """The template commit whose tree is the tree of HEAD's root commit, for a history the template does not share.

    Example: template_base(Path("."), "template/main") returns the sha "Use this template" copied, or None.
    """
    trees = {git(repo, "rev-parse", f"{root}^{{tree}}").strip() for root in roots(repo)}
    for line in git(repo, "log", "--format=%H %T", target).splitlines():
        commit, tree = line.split()
        if tree in trees:
            return commit
    return None


def rules_span(text: str) -> tuple[int, int] | None:
    start, end = text.find(RULES_START), text.find(RULES_END)
    return (start, end + len(RULES_END)) if 0 <= start < end else None


def with_rules(text: str, rules_from: str) -> str:
    """`text` with its managed rules block replaced by the one in `rules_from`; both must have one.

    Example: with_rules("a\\n<s>\\n- t\\n<e>\\nb", "<s>\\n- r\\n<e>") returns "a\\n<s>\\n- r\\n<e>\\nb" (markers
    abbreviated).
    """
    here, there = rules_span(text), rules_span(rules_from)
    assert here is not None and there is not None
    return text[:here[0]] + rules_from[there[0]:there[1]] + text[here[1]:]


def merge_agents(repo: Path, base: str, target: str) -> str:
    """Merge AGENTS.md again with every side holding HEAD's rules block, so the template's own rules neither
    conflict nor arrive. Returns "" when merged, else what the human must look at.
    """
    def show(rev: str) -> str | None:
        return git(repo, "show", f"{rev}:{AGENTS}", ok=(0, 128)) or None

    ours, ancestor, theirs = show("HEAD"), show(base), show(target)
    if ours is None or ancestor is None or theirs is None:
        return ""  # added or deleted on one side: git's own result stands
    if any(rules_span(t) is None for t in (ours, ancestor, theirs)):
        # Without a block on every side, the substitution would read as the block's deletion (#108 review).
        return f"{AGENTS}: a rules block marker is missing on one side; check the block by hand"
    sides = {"ours": ours, "base": with_rules(ancestor, ours), "theirs": with_rules(theirs, ours)}
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in sides.items():
            (Path(tmp) / name).write_text(text, encoding="utf-8", newline="\n")
        merged = subprocess.run(["git", "merge-file", "-p", "-L", "HEAD", "-L", "base", "-L", target,
                                 *(str(Path(tmp) / name) for name in sides)],
                                capture_output=True, text=True, encoding="utf-8")
    # The exit code counts the conflicts, up to 127; an error is negative, 255 as a process status.
    if not 0 <= merged.returncode <= 127:
        raise subprocess.CalledProcessError(merged.returncode, ["git", "merge-file"], merged.stdout, merged.stderr)
    (repo / AGENTS).write_text(merged.stdout, encoding="utf-8", newline="\n")
    if merged.returncode == 0:
        git(repo, "add", "--", AGENTS)
        return ""
    # The stages keep git's own versions: `git checkout --theirs` would bring the template's rules in.
    blobs = [git(repo, "hash-object", "-w", "--stdin", stdin=sides[name]).strip() for name in sides]
    git(repo, "update-index", "--index-info",
        stdin="".join(f"100644 {blob} {stage}\t{AGENTS}\n" for stage, blob in zip((2, 1, 3), blobs)))
    return f"{AGENTS}: a conflict outside the rules block"


def keep_memory(repo: Path) -> int:
    """Put MEMORY back as HEAD has it and drop what the merge brought there that HEAD lacks; return how many."""
    added = sorted(tracked(repo, None) - tracked(repo, "HEAD"))
    for start in range(0, len(added), 100):
        git(repo, "rm", "-q", "-f", "--", *added[start:start + 100])
    kept = [path for path in MEMORY if git(repo, "ls-tree", "--name-only", "HEAD", "--", path).strip()]
    if kept:
        git(repo, "checkout", "HEAD", "--", *kept)
    return len(added)


def refresh_index(repo: Path) -> str:
    """Regenerate index.md with the merged wiki-index.py, as CI will; "" when done, else what the human must do."""
    if set(RENDERER) & set(unmerged(repo)):
        return f"{INDEX}: run python {RENDERER[0]} once the conflicts above are resolved"
    git(repo, "checkout", "HEAD", "--", INDEX, ok=(0, 1))  # its conflict markers would only be overwritten
    run = subprocess.run([sys.executable, str(repo / RENDERER[0])], cwd=repo, capture_output=True, text=True,
                         encoding="utf-8")
    if run.returncode:
        return f"{INDEX}: python {RENDERER[0]} failed: {(run.stderr or run.stdout).strip()}"
    git(repo, "add", "--", INDEX)
    return ""


def finish_merge(repo: Path, base: str, target: str) -> int:
    dropped = keep_memory(repo)
    notes = [note for note in (merge_agents(repo, base, target), refresh_index(repo)) if note]
    left = unmerged(repo)
    print(f"update-from-template: merged {target}; kept the system's memory as HEAD has it and dropped {dropped} "
          "files under it that the merge brought")
    if left or notes:
        print("update-from-template: for the human, then `git add` and commit:\n" + "\n".join(notes + left))
        return 1
    print("update-from-template: read `git diff --cached`, then `git commit`; `git merge --abort` undoes it")
    return 0


def update(repo: Path, branch: str) -> int:
    if TEMPLATE_REMOTE not in git(repo, "remote").split():
        raise Refused(f"no `{TEMPLATE_REMOTE}` remote; add the template with `git remote add {TEMPLATE_REMOTE} <url>`")
    busy = [name for name in IN_PROGRESS if Path(repo, git(repo, "rev-parse", "--git-path", name).strip()).exists()]
    if busy:
        raise Refused(f"a merge in progress ({', '.join(busy)}); commit it or `git merge --abort` first")
    if git(repo, "status", "--porcelain"):
        raise Refused("commit or discard these changes first, so `git merge --abort` can undo the update:\n"
                      + git(repo, "status", "--short"))
    head_roots = set(roots(repo))
    for stale in set(git(repo, "replace", "-l").split()) & head_roots:
        git(repo, "replace", "-d", stale)  # left by a run killed mid-merge; it would fake a shared history
    git(repo, "fetch", "-q", TEMPLATE_REMOTE)
    target = f"{TEMPLATE_REMOTE}/{branch}"
    git(repo, "rev-parse", "--verify", "-q", target)
    grafted = None
    if not git(repo, "merge-base", "HEAD", target, ok=(0, 1)).strip():
        found = template_base(repo, target)
        if found is None:
            raise Refused(f"HEAD shares no history with {target}, and no commit of {target} has the tree of HEAD's "
                          "first commit; merge it by hand")
        grafted = sorted(head_roots)[0]
        git(repo, "replace", "--graft", grafted, found)
    try:
        base = git(repo, "merge-base", "HEAD", target).strip()
        merged = subprocess.run(["git", "-C", str(repo), "merge", "--no-commit", "--no-ff", target],
                                capture_output=True, text=True, encoding="utf-8")
    finally:
        if grafted:
            git(repo, "replace", "-d", grafted)
    started = bool(git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD", ok=(0, 1)).strip())
    if merged.returncode not in (0, 1) or (merged.returncode and not started):
        # Stopped before merging, e.g. an untracked file the merge would overwrite.
        raise subprocess.CalledProcessError(merged.returncode, ["git", "merge", target], merged.stdout, merged.stderr)
    if not started:
        print(f"update-from-template: nothing to merge from {target}")
        return 0
    try:
        return finish_merge(repo, base, target)
    except (subprocess.CalledProcessError, OSError, UnicodeError) as exc:
        detail = (getattr(exc, "stderr", "") or str(exc)).strip()
        print(f"update-from-template: failed with the merge in progress ({detail}); `git merge --abort` undoes it")
        return 3


def main(argv: list[str] | None = None, repo: Path = REPO) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", default="main", help="template branch to merge (default: main)")
    args = parser.parse_args(argv)
    try:
        return update(repo, args.branch)
    except Refused as exc:
        print(f"update-from-template: {exc}; nothing was changed")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"update-from-template: `{' '.join(exc.cmd)}` failed: {(exc.stderr or exc.stdout).strip()}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
