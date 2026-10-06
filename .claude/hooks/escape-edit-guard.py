"""PreToolUse hook for the Bash tool: block shell edits that rewrite the escapes in their text.

Three times an agent here edited a file through the shell and `\\n` in the text became a real line break: twice
through a Python heredoc script, once through a `sed` replacement; one corrupted docstring reached main (#47).
The Edit tool writes the text as given. Exit 2 blocks the call and shows stderr to the agent.

Blocked: `sed -i` (or `gsed`, `--in-place`) run as a command, and a heredoc fed to Python (`python -`, `py -`,
`cat <<EOF | python -`) whose body holds `\\n`, `\\t` or `\\\\`. Commands are read token by token with heredoc
bodies taken out, so quoted text, comments and heredoc bodies are data: a commit message, a PR title or a `grep`
about `sed -i` or python passes. A heredoc that is the input of a `.py` script passes too.
Usage (from .claude/settings.json): python .claude/hooks/escape-edit-guard.py < hook-payload.json
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from collections.abc import Iterator

# `<<`, `<<-`, quoted, backslash-quoted or bare delimiter; not the `<<<` here-string.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*\\?(['\"]?)([A-Za-z_][\w-]*)\1")
PYTHON = re.compile(r"(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?")
ESCAPE = re.compile(r"\\[nt\\]")
SEPARATORS = {";", ";;", "&", "&&", "|", "||", "|&", "(", ")"}
REDIRECTS = {">", ">>", "<", "<<", ">&", "<&", ">|", "&>"}
# Words after which the next word is still a command: wrappers and shell keywords.
PREFIXES = {"sudo", "xargs", "env", "command", "nohup", "time", "exec",
            "if", "then", "else", "elif", "while", "until", "do", "!", "{", "}"}
SED = {"sed", "gsed", "sed.exe"}
IN_PLACE = re.compile(r"-[a-zA-Z]*i|--in-place")
ADVICE = "Use the Edit tool (or Write for a new file); to run a script, save it to a .py file and run that"


def split_heredocs(command: str) -> tuple[str, list[tuple[str, str]]]:
    """The command with heredoc bodies taken out, and (line that opens it, body) for each heredoc.

    Example: split_heredocs("cat <<EOF\\nx\\nEOF\\nls") returns ("cat <<EOF\\nls", [("cat <<EOF", "x")]).
    """
    lines = command.split("\n")
    shell: list[str] = []
    docs: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        shell.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            body: list[str] = []
            while i < len(lines) and lines[i].strip() != m.group(2):
                body.append(lines[i])
                i += 1
            i += 1  # the delimiter line
            docs.append((line, "\n".join(body)))
    return "\n".join(shell), docs


def simple_commands(line: str) -> Iterator[list[str]]:
    """Each simple command of one shell line: its name, then its arguments, without wrappers, keywords,
    `VAR=x` assignments, redirections or comments. Yields nothing for a line bash would refuse.

    Example: list(simple_commands("for f in *; do LC_ALL=C sed -i x \\"$f\\" > o; done")) returns
    [["for", "f", "in", "*"], ["sed", "-i", "x", "$f"]].
    """
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes
        return
    words: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
        elif token in SEPARATORS:
            if words:
                yield words
            words = []
        elif token in REDIRECTS or re.fullmatch(r"\d*[<>]+&?", token):
            skip_next = True  # the redirection target
        elif not words and (token in PREFIXES or token.startswith("-") or re.match(r"[A-Za-z_]\w*=", token)):
            continue
        else:
            words.append(token)
    if words:
        yield words


def name(word: str) -> str:
    return word.replace("\\", "/").rsplit("/", 1)[-1]


def runs_sed_in_place(shell: str) -> bool:
    """Whether a command of `shell` (heredoc bodies already out) is sed with an in-place option.

    Example: runs_sed_in_place("cd x && sed -i 's/a/b/' f") returns True; runs_sed_in_place("grep 'sed -i' f")
    returns False.
    """
    for line in shell.replace("\\\n", " ").split("\n"):
        for words in simple_commands(line):
            if name(words[0]) in SED and any(IN_PLACE.match(w) for w in words[1:]):
                return True
    return False


def feeds_python(line: str) -> bool:
    """Whether the line opening a heredoc runs Python on source it is not given as a `.py` file.

    Example: feeds_python("cat <<'EOF' | python -") returns True; feeds_python("python tool.py <<EOF") returns False.
    """
    commands = list(simple_commands(line))
    if not commands and PYTHON.search(line):  # bash would need the next lines too: `python -c "$(cat <<EOF`
        return True
    for words in commands:
        # The interpreter is the command, or follows `run` (`uv run python -`, `poetry run python -`).
        at = next((i for i, w in enumerate(words) if PYTHON.fullmatch(name(w)) and (i == 0 or words[i - 1] == "run")),
                  None)
        if at is not None and not any(arg.endswith(".py") for arg in words[at + 1:]):
            return True
    return False


def reason(command: str) -> str:
    """Why `command` is blocked, or "" when it may run.

    Example: reason("sed -i 's/a/b/' x.py") returns "sed -i rewrites escapes in its replacement".
    """
    shell, docs = split_heredocs(command)
    if runs_sed_in_place(shell):
        return "sed -i rewrites escapes in its replacement"
    for line, body in docs:
        if ESCAPE.search(body) and feeds_python(line):
            return r"a Python heredoc with \n, \t or \\ in its text rewrites them on the way to the file"
    return ""


def main() -> int:
    payload = json.load(sys.stdin)
    why = reason(str(payload.get("tool_input", {}).get("command", ""))) if payload.get("tool_name") == "Bash" else ""
    if not why:
        return 0
    print(f"Blocked: {why}. {ADVICE}.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
