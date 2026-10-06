"""Seed the inbox from an existing project: its README, docs, agent rule files and git history, for /ingest.

A project that adopts Omoikane, or a system that replaces one, already states many of its rules in writing; without
this they reach the wiki only when the user restates them in a session (#79; after ai-memory's `bootstrap` and
brainmaxxing's `/ruminate`). Each source becomes one inbox file, headed with where it came from and when it last
changed, so /ingest can date it. Content is read from the commit HEAD points at, never from the working tree, and
goes through the same redaction as a captured session (secrets, omoikane/.capture-redact): the scheduled run pushes
what it ingests.

In a system born from the template (remote `template`, which new-system.py names), what the template shipped
describes Omoikane, not the system: a file the template shipped contributes only the lines the system added since
it branched off, and the history starts there too. Elsewhere, a file holding Omoikane's managed rules block is
Omoikane's manual and is skipped. A second run writes nothing already in the inbox, in raw/sources/, or on the
review gate's branch.

Usage: python omoikane/bin/bootstrap.py [--from PATH]     # default: this repository
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

from wikilib import OMOIKANE, REPO, RULES_END, RULES_START

capture = importlib.import_module("session-capture")

# What a project writes down for people and agents, not code. Names compare case-insensitively.
ROOT_FILES = {"readme", "readme.md", "readme.mdx", "readme.rst", "readme.txt", "contributing.md", ".cursorrules",
              ".windsurfrules", ".clinerules"}
AGENT_FILES = {"agents.md", "claude.md", "gemini.md"}  # at any depth: a monorepo keeps one per package
# Folders of other people's code, whose agent files are not this system's rules.
VENDORED = {"node_modules", "vendor", "third_party", "third-party", ".venv", "venv", "site-packages"}
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
TEMPLATE_REMOTE = "template"
# The log entry new-system.py writes: the commit that adds it is where the system's own history starts, whatever
# its remotes are called (a "Use this template" repository starts from an unrelated commit).
RESET_MARKER = "init | Memory reset from the Omoikane template"
MANUAL_HEADING = "# Omoikane — agent operating manual"
HISTORY_COMMITS = 300  # newest first; a long history past this adds little a rule needs
BODY_CHARS = 1000
TRAILER = re.compile(r"(?im)^[a-z][\w-]*-by:.*$\n?")  # Signed-off-by, Co-authored-by: names and emails
PREFIX = "bootstrap-"
MAX_SLUG = 150  # file names stay well under the 255 bytes Windows and Linux allow
# Where the review gate keeps what it ingested until the human's checkout pulls it (review-gate.py).
GATE_REFS = ("wiki/auto", "origin/wiki/auto", "origin/main")


class BootstrapError(Exception):
    """The project cannot be read: not a git repository, no commit yet, git missing, or the template not fetched."""


def git(repo: Path, *args: str, ok: bool = False) -> str:
    try:
        run = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
    except FileNotFoundError as exc:
        raise BootstrapError("git is not on PATH") from exc
    if run.returncode != 0:
        if ok:
            return ""
        raise BootstrapError(run.stderr.strip() or f"git {' '.join(args)} failed")
    return run.stdout


def is_source(path: str) -> bool:
    """Example: is_source("docs/adr/0001.md") and is_source("pkg/CLAUDE.md") are True; "src/a.py" is False."""
    p = PurePosixPath(path.lower())
    if p.parts[0] == "omoikane" or VENDORED & set(p.parts[:-1]):
        return False
    if len(p.parts) == 1 and p.name in ROOT_FILES or p.name in AGENT_FILES:
        return True
    if p.parts[0] == "docs" and p.suffix in DOC_SUFFIXES:
        return True
    return path.lower() == ".github/copilot-instructions.md" or (p.parts[:2] == (".cursor", "rules")
                                                                  and p.suffix in {".md", ".mdc"})


def tree(project: Path, rev: str) -> dict[str, str]:
    """Path to blob id of every regular file at `rev`; links and submodules are not text a project wrote."""
    blobs = {}
    for line in git(project, "ls-tree", "-r", "-z", rev).split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            mode, kind, sha = meta.split()
            if kind == "blob" and mode in ("100644", "100755"):
                blobs[path] = sha
    return blobs


def is_ancestor(project: Path, older: str, newer: str) -> bool:
    return subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0


def template_versions(project: Path) -> tuple[str | None, list[str]]:
    """Where the template ends in this history, and the template's other fetched tips.

    The base is the commit new-system.py's reset entry entered omoikane/log.md in, found by content, so neither a
    renamed remote nor a "Use this template" repository hides it (#84 second review); else the newest commit HEAD
    shares with a `template/*` branch. Template tips that hold the base are this system's own branches (a "Use
    this template" repository named its own remote `template`) and do not count. (None, []) outside a system born
    from the template.
    """
    refs = (git(project, "for-each-ref", "--format=%(refname)", f"refs/remotes/{TEMPLATE_REMOTE}/").split()
            if TEMPLATE_REMOTE in git(project, "remote").split() else [])
    reset = git(project, "log", "--format=%H", "-S", RESET_MARKER, "HEAD", "--", "omoikane/log.md").split()
    if reset:
        base = reset[-1]  # the oldest: the entry was added there
        return base, [r for r in refs if not is_ancestor(project, base, r)]
    if TEMPLATE_REMOTE not in git(project, "remote").split():
        return None, []
    bases = [b for b in (git(project, "merge-base", "HEAD", ref, ok=True).strip() for ref in refs) if b]
    if not bases:
        raise BootstrapError(f"remote `{TEMPLATE_REMOTE}` has no branch fetched that HEAD shares history with; "
                             f"run `git fetch {TEMPLATE_REMOTE}` first")
    # The common commit every other one is an ancestor of: the template's history ends there.
    newest = [b for b in bases if all(is_ancestor(project, other, b) for other in bases)]
    return (newest or bases)[0], refs


def without_rules(text: str) -> str:
    """Drop the managed rules block: wiki-rules.py and new-system.py rewrite it, and it points at wiki pages."""
    start, end = text.find(RULES_START), text.find(RULES_END)
    return text if start < 0 or end < start else text[:start] + text[end + len(RULES_END):]


def added_lines(old: str, new: str) -> str:
    """Example: added_lines("a\\nb\\n", "a\\nx\\nb\\n") returns "x\\n"."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    return "".join("".join(b[j1:j2]) for tag, _, _, j1, j2 in
                   difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag in ("insert", "replace"))


def without_manual(text: str) -> str | None:
    """A project's own text with Omoikane's manual taken out, or None when nothing else is left.

    Example: without_manual("# Shop rules\\n...\\n" + manual) returns "# Shop rules\\n...\\n".
    """
    start, end = text.find(MANUAL_HEADING), text.find(RULES_END)
    if start < 0 or end < start:
        return None  # the rules block without the heading: cannot tell the manual from the rest
    rest = text[:start] + text[end + len(RULES_END):]
    return rest if rest.strip() else None


def content(project: Path, path: str, sha: str, template: list[dict[str, str]] | None) -> str | None:
    """The text to ingest for one source, or None when it holds nothing of the system's own. `template` holds the
    trees of the template's versions, the base first; a file any of them holds as it is is the template's, and of
    a file they shipped only the lines none of them has are the system's."""
    text = git(project, "cat-file", "blob", sha)
    if "\0" in text:
        return None  # binary
    if template is None:
        return without_manual(text) if RULES_START in text else text  # a project that adopted Omoikane
    shipped = [version[path] for version in template if path in version]
    if not shipped:
        return text
    if sha in shipped:
        return None
    old = [without_rules(git(project, "cat-file", "blob", blob)) for blob in shipped]
    theirs = {line.strip() for version in old for line in version.splitlines() if line.strip()}
    added = [line for line in added_lines(old[0], without_rules(text)).splitlines(keepends=True)
             if line.strip() not in theirs]
    return "".join(added) if "".join(added).strip() else None


def slugs(paths: list[str], terms: list[str]) -> dict[str, str]:
    """Inbox name per path, from the path with the listed terms redacted (the name is pushed too). Unicode letters
    stay; a name is cut at MAX_SLUG, and a cut name or two paths that would share one get a hash of the path.

    Example: slugs(["docs/a-b.md", "docs/a/b.md"], []) gives two different names.
    """
    base = {p: re.sub(r"[^\w]+", "-", capture.redact(p, terms).lower()).strip("-_") for p in paths}
    counts: dict[str, int] = {}
    for name in base.values():
        counts[name] = counts.get(name, 0) + 1

    def name_of(p: str, name: str) -> str:
        unique = counts[name] == 1 and len(name) <= MAX_SLUG
        return f"{PREFIX}{name[:MAX_SLUG]}{'' if unique else '-' + hashlib.sha1(p.encode()).hexdigest()[:6]}.md"
    return {p: name_of(p, name) for p, name in base.items()}


def source_note(project: Path, path: str, text: str, partial: bool) -> str:
    changed = git(project, "log", "-1", "--format=%cs %h", "HEAD", "--", path).split()
    when = f"last changed {changed[0]} in commit {changed[1]}" if changed else "date unknown"
    scope = " Only the lines this system added to the template's copy follow." if partial else ""
    return (f"# {path} of {project.name} (bootstrap)\n\nCopied by `omoikane/bin/bootstrap.py` from `{path}` in "
            f"`{project.name}`, {when}.{scope}\n\n---\n\n{text}")


def history_note(project: Path, exclude: list[str]) -> str | None:
    """The commits of HEAD after the template's, newest first, subject and body. Merge commits are left out: in a
    pull-request workflow the reasons sit in the branch commits, not in "Merge pull request #n". Trailers go (they
    carry names and emails), and a long body is cut with the capture's own marker, so a secret cut short still
    matches the redaction's rule for clipped tokens."""
    log = git(project, "log", "--no-merges", f"-{HISTORY_COMMITS}", "--format=%x00%cs %h %s%n%b", "HEAD",
              *(f"^{rev}" for rev in exclude))
    entries = []
    for entry in filter(None, (e.strip() for e in log.split("\0"))):
        head, _, body = entry.partition("\n")
        body = capture.clip(TRAILER.sub("", body), BODY_CHARS)
        entries.append(f"## {head}\n\n{body}" if body else f"## {head}")
    if not entries:
        return None
    return (f"# Git history of {project.name} (bootstrap)\n\nCopied by `omoikane/bin/bootstrap.py`: the commits "
            f"of `{project.name}` without merges, newest first, at most {HISTORY_COMMITS}, as date, commit and "
            "subject, then the body. A body often holds the reason for a change.\n\n" + "\n\n".join(entries) + "\n")


def already_there(name: str, omoikane: Path) -> bool:
    """In this checkout's inbox or sources, or on the review gate's branch before the human pulled it."""
    if (omoikane / "raw" / "inbox" / name).exists() or (omoikane / "raw" / "sources" / name).exists():
        return True
    return any(subprocess.run(["git", "-C", str(omoikane.parent), "cat-file", "-e",
                               f"{ref}:omoikane/raw/{folder}/{name}"], capture_output=True).returncode == 0
               for ref in GATE_REFS for folder in ("sources", "inbox"))


def bootstrap(project: Path, omoikane: Path = OMOIKANE, redact_file: Path = capture.REDACT_FILE) -> list[str]:
    """Write one inbox file per source of `project` and one for its history; return the names written.

    Example: bootstrap(Path("../shop")) returns ["bootstrap-readme-md.md", ..., "bootstrap-git-history.md"].
    """
    if not git(project, "rev-parse", "--verify", "--quiet", "HEAD", ok=True):
        raise BootstrapError("it has no commit yet; bootstrap reads committed files")
    head = tree(project, "HEAD")
    base, tips = template_versions(project)
    template = [tree(project, rev) for rev in (base, *tips)] if base else None
    terms = capture.redaction_terms(redact_file)
    paths = sorted(p for p in head if is_source(p))
    names = slugs(paths, terms)
    notes: dict[str, str] = {}
    for path in paths:
        text = content(project, path, head[path], template)
        if text is not None:
            partial = template is not None and any(path in version for version in template)
            notes[names[path]] = source_note(project, path, text, partial)
    history = history_note(project, [base, *tips] if base else [])
    if history:
        notes[f"{PREFIX}git-history.md"] = history
    inbox = omoikane / "raw" / "inbox"
    written = []
    for name, text in notes.items():
        if already_there(name, omoikane):
            continue
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / name).write_text(capture.redact(capture.redact_secrets(text), terms), encoding="utf-8",
                                  newline="\n")
        written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="project", type=Path, default=REPO, help="the project to read")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # a legacy code page cannot print every file name
    try:
        git(project, "rev-parse", "--git-dir")
    except BootstrapError as exc:
        print(f"bootstrap: {project} is not a git repository: {exc}", file=sys.stderr)
        return 2
    try:
        written = bootstrap(project)
    except BootstrapError as exc:
        print(f"bootstrap: {project}: {exc}", file=sys.stderr)
        return 2
    if written and project != REPO.resolve():
        print(f"bootstrap: these come from {project.name}, another repository; the scheduled run commits and pushes "
              "what it ingests, so read them first and delete what must stay private")
    for name in written:
        print(f"bootstrap: wrote omoikane/raw/inbox/{name}")
    print(f"bootstrap: {len(written)} files for /ingest, one agent run each")
    return 0


if __name__ == "__main__":
    sys.exit(main())
