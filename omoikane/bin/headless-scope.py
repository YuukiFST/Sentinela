"""What a scheduled headless run may do, rendered for each harness wiki-ingest.ps1 drives, and checked after it.

One scope, two renderings: the Claude Code flags and the OpenCode permission config were once written apart, and
the OpenCode run had none at all (#39). The scope: read the repository, edit only wiki pages (`.md`), the log and
the review queue. No shell at all: an allowed script is code the agent can replace or shadow from a directory it
writes to, so wiki-ingest.ps1 runs index and lint itself and hands the findings back.
Permission rules are the harness's and have holes the harness owns, so `verify` compares the working tree before
and after the run. wiki-ingest.ps1 runs a private copy of this file with `python -I`: nothing the agent writes
into the repository is on its path. Standard library only, for the same reason.

Usage: python -I headless-scope.py --repo DIR claude
       python -I headless-scope.py --repo DIR opencode --agent-name NAME
       opencode debug agent NAME > agent.json; python -I headless-scope.py opencode-tools --resolved agent.json
       python -I headless-scope.py --repo DIR snapshot > before.json
       python -I headless-scope.py --repo DIR verify --before before.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Repository-relative, gitignore style.
EDITABLE = ("omoikane/wiki/**/*.md", "omoikane/log.md", "omoikane/_review.md")
# Written while the run lasts by someone other than the agent: the Stop hook of a coding session in the same tree,
# and wiki-ingest.ps1's own log, matched exactly (a prefix let `omoikane/.wiki-ingest.log.ps1` through).
WRITTEN_BY_OTHERS = ("omoikane/raw/inbox/",)
WRITTEN_BY_SCRIPT = "omoikane/.wiki-ingest.log"
# Under the git directory, what the git commands run after the agent read or execute: hooks, config, excludes.
# Shared by every worktree, so only what can run code or hide a path: `git push -u` and `git branch -u` in another
# worktree rewrite branch.* and remote.* keys, and `git gc` writes info/refs (#40, fifth review).
GIT_HOOKS = "hooks"
GIT_INFO = ("info/exclude", "info/attributes", "info/sparse-checkout")
ROUTINE_CONFIG = ("branch.", "remote.", "gc.", "maintenance.")
# The OpenCode tools the scope needs. Any other tool OpenCode offers the agent is one its rules may not cover.
OPENCODE_TOOLS = {"read", "glob", "grep", "list", "edit", "write", "todowrite"}


def claude_args() -> list[str]:
    """Flags for `claude -p`, after the prompt.

    --tools offers no shell: there is nothing to allow or deny for one. --setting-sources project: allow rules
    and PreToolUse hooks in the user's own settings would otherwise apply too (#25); --strict-mcp-config keeps
    MCP servers out. dontAsk denies whatever the list does not allow. Edit(...) rules cover the Write tool; a
    leading / anchors at the repository root. Read rules cover Glob and Grep: a bare `Read` read `~/.ssh` and
    `.env`, and the `.env*` deny also drops those files from Glob and Grep results (probe, #40).
    Example: claude_args()[:2] returns ["--setting-sources", "project"].
    """
    allowed = ["Read(/**)", *(f"Edit(/{path})" for path in EDITABLE)]
    return ["--setting-sources", "project", "--strict-mcp-config", "--tools", "Read,Glob,Grep,Edit,Write",
            "--permission-mode", "dontAsk", "--allowedTools", ",".join(allowed), "--disallowedTools", "Read(/**/.env*)"]


def opencode_config(agent_name: str) -> dict[str, object]:
    """OpenCode config (schema https://opencode.ai/config.json, rules https://opencode.ai/docs/permissions/)
    defining the agent wiki-ingest.ps1 runs with `opencode run --pure --agent <agent_name>`.

    `*` matches any run of characters, `/` included, and the last matching rule wins, so every map opens with
    `"*": "deny"`; the `"*"` permission denies every one not named, bash among them. Why an agent: OpenCode
    merges config maps key by key, so a user's `"bash": {"*": "allow", "git *": "allow"}` kept `git *` after a
    top-level deny; agent rules come after the top-level ones. Why a fresh name per run: a same-named agent in
    the user's config would merge into ours the same way. `read` keeps OpenCode's `.env` protection and denies MCP
    resources. No rule can hide `apply_patch` (`unsafe_tools` explains), so wiki-ingest.ps1 checks the resolved
    tools before the run.
    Example: opencode_config("omoikane-headless-1a2b3c4d")["agent"]["omoikane-headless-1a2b3c4d"]["mode"]
    returns "primary".
    """
    return {"agent": {agent_name: {
        "mode": "primary",
        "description": "Scheduled Omoikane run: edits wiki pages, the log and the review queue, nothing else.",
        "permission": {
            "*": "deny",
            "read": {"*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow", "mcp:*": "deny"},
            "glob": "allow", "grep": "allow", "list": "allow", "todowrite": "allow",
            "edit": {"*": "deny", **{path.replace("**/", ""): "allow" for path in EDITABLE}},
        },
    }}}


def unsafe_tools(tools: dict[str, bool]) -> list[str]:
    """The tools `opencode debug agent` shows as offered beyond the scope's own; the run must not start with any.

    OpenCode 1.18 offers `apply_patch` in place of edit and write to a gpt- model whatever the rules say: the
    permission `apply_patch` maps onto `edit`, and its `*** Move to:` target is never checked against the edit
    rules, so a wiki page could be moved onto AGENTS.md (#40, third review).
    Example: unsafe_tools({"read": True, "apply_patch": True, "bash": False}) returns ["apply_patch"].
    """
    return sorted(tool for tool, offered in tools.items() if offered and tool not in OPENCODE_TOOLS)


def in_scope(path: str) -> bool:
    """Whether a change to `path` (repository-relative, `/`) may happen during the run.

    Example: in_scope("omoikane/wiki/gotchas/a.md") returns True; in_scope("omoikane/wiki/a.py") returns False.
    """
    if path in EDITABLE or path == WRITTEN_BY_SCRIPT or path.startswith(WRITTEN_BY_OTHERS):
        return True
    return path.startswith("omoikane/wiki/") and path.endswith(".md") and ".." not in path.split("/")


def git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def snapshot(repo: Path) -> dict[str, object]:
    """HEAD, the staged tree, a content hash of every changed or untracked file, and the size and mtime of every
    ignored one. `git status` lists no ignored file, and a page moved onto `.claude/settings.local.json` (ignored
    by a user's global git ignore) or a `.pth` under `.venv/` went unnoticed (#40, third review). Ignored trees
    such as `node_modules/` hold thousands of files, so those are not hashed. Also the git config, hooks and
    excludes: `git status` and `git commit` run right after the agent, and they read the first and run the second.
    Not seen: paths outside the repository, and the inside of a nested repository (listed as a directory).

    Example: snapshot(repo) returns {"head": "<sha>", "index": "<tree sha>", "files": {"omoikane/log.md": "<sha>"}}.
    """
    entries = iter(e for e in git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0") if e)
    paths: list[str] = []
    for entry in entries:
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:  # a rename or copy is followed by its source path
            paths.append(next(entries, ""))
    files: dict[str, str] = {}
    for path in filter(None, paths):
        full = repo / path
        files[path] = (git(repo, "hash-object", "--", path).strip() if full.is_file()
                       else "directory" if full.is_dir() else "deleted")
    for path in filter(None, git(repo, "ls-files", "-z", "--others", "--ignored", "--exclude-standard").split("\0")):
        stat = (repo / path).lstat()
        files[path] = f"ignored {stat.st_size} {stat.st_mtime_ns}"
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    watched = [common / name for name in GIT_INFO] + sorted((common / GIT_HOOKS).rglob("*"))
    for full in (p for p in watched if p.is_file()):
        name = full.relative_to(repo).as_posix() if full.is_relative_to(repo) else full.as_posix()
        files[name] = hashlib.sha256(full.read_bytes()).hexdigest()
    config = common / "config"
    if config.is_file():
        keys = git(repo, "config", "--file", str(config), "--list", "-z").split("\0")
        kept = "\0".join(sorted(k for k in keys if k and not k.startswith(ROUTINE_CONFIG)))
        name = config.relative_to(repo).as_posix() if config.is_relative_to(repo) else config.as_posix()
        files[name] = hashlib.sha256(kept.encode("utf-8")).hexdigest()
    return {"head": git(repo, "rev-parse", "HEAD").strip(), "index": git(repo, "write-tree").strip(), "files": files}


def out_of_scope(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """Every change between two snapshots the run may not make: HEAD or the staged tree moved, or a file outside
    the scope changed, appeared or went away.

    Example: out_of_scope(snap, {**snap, "files": {"AGENTS.md": "<sha>"}}) returns ["AGENTS.md"].
    """
    problems = [f"{key} moved" for key in ("head", "index") if before[key] != after[key]]
    old, new = dict(before["files"]), dict(after["files"])  # type: ignore[arg-type]
    problems += sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p) and not in_scope(p))
    return problems


def main(argv: list[str]) -> int:
    # `python -I` ignores PYTHONIOENCODING, and a cp1252 console made print() raise on a non-ASCII path (#40).
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent.parent)
    parser.add_argument("action", choices=("claude", "opencode", "opencode-tools", "snapshot", "verify"))
    parser.add_argument("--agent-name", default="omoikane-headless")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--resolved", type=Path, help="output of `opencode debug agent NAME`")
    args = parser.parse_args(argv)
    if args.action == "claude":
        print(json.dumps(claude_args()))
    elif args.action == "opencode":
        print(json.dumps(opencode_config(args.agent_name)))
    elif args.action == "opencode-tools":
        unsafe = unsafe_tools(json.loads(args.resolved.read_text(encoding="utf-8"))["tools"])
        for tool in unsafe:
            print(f"headless-scope: OpenCode offers the agent `{tool}`, which the scope cannot restrict")
        return 3 if unsafe else 0
    elif args.action == "snapshot":
        print(json.dumps(snapshot(args.repo)))
    else:
        problems = out_of_scope(json.loads(args.before.read_text(encoding="utf-8")), snapshot(args.repo))
        for problem in problems:
            print(f"headless-scope: out of scope: {problem}")
        return 3 if problems else 0  # 3, not 1: a crash exits 1 and must not read as a verdict
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
