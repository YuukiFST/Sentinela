"""Turn a coding-session transcript into a source file under raw/inbox/sessions/, with no LLM call.

Runs from the harness stop hooks: Claude Code Stop/SessionEnd (.claude/settings.json), Pi agent_end/session_shutdown
(.pi/extensions/omoikane.ts), OpenCode session idle (.opencode/plugins/omoikane.ts). Idempotent: every run rewrites
the file for the session, so firing on every turn is safe. Never blocks the harness: any failure prints one line,
appends it to omoikane/.capture-errors for the next session's brief, and exits 0.

Usage:
    python omoikane/bin/session-capture.py                                    # Claude hook: JSON payload on stdin
    python omoikane/bin/session-capture.py --transcript X.jsonl               # Claude transcript, manual or test run
    python omoikane/bin/session-capture.py --harness pi --transcript X.jsonl  # Pi session file
    python omoikane/bin/session-capture.py --harness opencode --transcript X.json  # `opencode export <id>` output

Each harness has its own reader producing the same Session/Turn objects; the Markdown and the skip rules are shared.
Claude Code's transcript is internal and undocumented; Pi's and OpenCode's are documented (links in docs/architecture.md).
Every reader ignores what it does not recognise, so a format change degrades to a thinner capture, not a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from wikilib import OMOIKANE, parse_frontmatter

INBOX = OMOIKANE / "raw" / "inbox" / "sessions"
INGESTED = OMOIKANE / "raw" / "sources" / "sessions"
# The review gate commits its distills here before the human merges them (review-gate.py).
AUTO_BRANCH = "wiki/auto"
NO_CAPTURE_ENV = "OMOIKANE_NO_CAPTURE"
# Terms the user never wants in a capture, one per line (#62). The scheduled run commits and pushes every capture,
# and under raw/sources/ it is immutable, so redaction happens here. Gitignored: the list itself names them.
REDACT_FILE = OMOIKANE / ".capture-redact"
# One line per failed capture; session-context.py names them in the brief (#103). The Stop hook's stdout reaches
# nobody, so a capture that crashed on every turn lost every session unseen. Gitignored, like the redact list.
ERRORS_FILE = OMOIKANE / ".capture-errors"
REDACTED = "[redacted]"
UNREDACTED_KEYS = ("harness", "session", "part", "turns", "started", "ended")
# Secrets go whether or not a list exists (#77): a key pasted into a prompt was pushed with the capture.
CLIP_MARK = r" \[\.\.\. \d+ chars cut\]"
CLIPPED = re.compile(CLIP_MARK)
# Token shapes with a known prefix. A token cut short by a clip still starts with its prefix, so that part goes too.
TOKENS = (r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_\w{20,}|sk-(?=[\w-]*\d)[\w-]{20,}"  # a digit: sk-learn-... is prose
          r"|[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|xox[abprs]-[A-Za-z0-9-]{10,}|xapp-[\w-]{20,}|AIza[\w-]{30,}"
          r"|(?:AKIA|ASIA)[0-9A-Z]{16}|glpat-[\w-]{20,}|npm_[A-Za-z0-9]{30,}|hf_[A-Za-z0-9]{30,}|pypi-[\w-]{20,}"
          r"|ya29\.[\w-]{20,}|GOCSPX-[\w-]{20,}|SG\.[\w-]{16,}\.[\w-]{16,}|whsec_[A-Za-z0-9+/]{20,}|hvs\.[\w-]{20,}"
          r"|eyJ[\w-]{8,}\.eyJ[\w-]{8,}(?:\.[\w-]*)?|https://hooks\.slack\.com/services/[\w/]+")
TOKEN_PREFIXES = (r"gh[pousr]_|github_pat_|sk-|[sr]k_(?:live|test)_|xox[abprs]-|xapp-|AIza|AKIA|ASIA|glpat-|npm_"
                  r"|hf_|pypi-|ya29\.|GOCSPX-|SG\.|whsec_|hvs\.|eyJ")
# A private key block, read by its structure: header, armor fields, base64 lines, footer. A line break may be real,
# escaped (`\n` in JSON or .env), or a string concatenation in code ("...\n"<newline>"..."), and a line may be
# `> `-quoted. Without a footer only whole base64 lines of 20+ characters follow, so a header quoted in prose takes
# nothing after it (#82 reviews: `.*?` up to a footer erased every later turn; a character class ate prose and
# stopped at an armor field's `(`, leaking the key body).
KEY_HEADER = r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
KEY_FOOTER = r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
KEY_BREAK = r"[ \t]*+(?:(?:\\r)?\\n(?:[\"'][ \t]*+\+?[ \t]*+\r?\n[ \t]*+[\"'])?|\r?\n)[ \t]*+(?:>[ \t]?)?"
KEY_ARMOR = r"(?:Proc-Type|DEK-Info|Version|Comment|Hash|Charset):[^\n\\]*"
PRIVATE_KEY = (KEY_HEADER + r"(?:(?:(?:" + KEY_BREAK + r")+(?:" + KEY_ARMOR + r"|[A-Za-z0-9+/=]+))*(?:" + KEY_BREAK
               + r")+" + KEY_FOOTER + r"|(?:[ \t]+[A-Za-z0-9+/=]{16,})+[ \t]+" + KEY_FOOTER
               + r"|(?:" + KEY_BREAK + r"[A-Za-z0-9+/=]{20,}(?=" + KEY_BREAK + r"|\Z|" + CLIP_MARK + r"))*"
               r"(?:" + KEY_BREAK + r"[A-Za-z0-9+/=]+(?=" + CLIP_MARK + r"))?)")
SECRET_SHAPES = re.compile(PRIVATE_KEY + r"|(?<![\w-])(?:" + TOKENS + r")"
                           r"|(?<![\w-])(?:" + TOKEN_PREFIXES + r")[\w.-]*(?=" + CLIP_MARK + r")")
# A label that stays, then the secret it introduces. Each pattern's group 1 is the label.
SECRET_AFTER = [re.compile(p) for p in (
    r"(?i)(\bbearer[ \t]+)(?=[\w.~+/-]*\d)[\w.~+/-]{16,}=*",  # a digit: "bearer authenticationscheme" is prose
    r"(?i)(\bbearer[ \t]+)[\w.~+/-]+(?=" + CLIP_MARK + r")",
    r"(?i)(<(?:password|passwd|secret|token|api[_-]?key)>)[^<\n]{1,200}(?=</)",  # XML, e.g. Maven settings.xml
    # The header line, or its JSON or dict form: "Authorization": "Basic ...".
    r"(?i)(\bauthorization[\"']?[ \t]*[:=][ \t]*[\"']?(?:basic|token)[ \t]+)[A-Za-z0-9+/]+=*",
    # Greedy to the last @ before the path or query: a hand-typed password may hold one.
    r"(?<![\w+.-])([a-z][\w+.-]*+://[^\s:/@]*:)[^\s/?#]+(?=@)",
    # curl -u user:password, curl as the command (at a line start or after ; & | ( or a backtick), not in prose.
    # The scan to the flag is bounded: unbounded, a 20,000-character line of repeated commands took over a second
    # on every turn (#109 review).
    r"(?m)((?:^|[;&|(`])[ \t]*curl\b[^\n|;&]{0,500}?\s(?:-u[ \t]*|--user[ =])[^\s:'\"]*:)[^\s'\"]+",
    # mysql -p<password>, no space; not a path ending in mysql, not a port mapping (docker -p3306:3306).
    r"((?<![/\w.-])mysql(?:dump|admin)?\b(?![/.:-])[^\n|;&]{0,500}?\s-p)(?!\d+(?::\d+)?(?:\s|$))[^\s'\"]+",
)]
# Names that hold a secret. `pass` and `key` only with a prefix that says so: `bypass`, `first_pass`, `sort_key`
# and `primary_key` hold none. Matched in the pattern, so a name that holds none consumes no value a later name
# needs, and bounded, so a long hyphenated run cannot backtrack (#82 review: 85 s on 8,000 characters).
SECRET_NAMES = (r"(?:[a-z_][\w-]{0,40}?)?(?:password|passwd|passphrase|secret|token|credentials?)s?"
                r"|(?:[\w-]{0,40}?[_-])?(?:db|smtp|mail|user|admin|root|ftp|redis|ldap|proxy|mysql|pg)[_-]?(?:pass|pwd|pw)"
                r"|pass|pwd|pw"
                r"|(?:[\w-]{0,40}?[_-]?)?(?:api|access|secret|secretaccess|private|client|signing|encryption|master"
                r"|auth|license|service|account|stripe|aws|openai|anthropic)[_-]?keys?")
SECRET_VALUE = r"(?:(?P<quote>[\"'`])(?P<quoted>[^\"'`\n]{1,200}?)(?P=quote)|(?P<opening>[\"']?)(?P<bare>[^\s\"'`,;|)]+))"
# `<name>=<value>`, `"<name>": "<value>"`, `cfg["<name>"] = <value>`, `**<Name>:** <value>`, `| <name> | <value> |`,
# `<name>: <Type> = <value>` (the type hint only after a colon), and `:=`, `||=` or `=>` before a quoted literal.
# Not `==`, `===`, nor `:=`/`=>` before code. A name followed by a space never takes the next word: that consumed
# the real assignment after it ("the password PGPASSWORD=...", #82 third review).
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?<![\w-])(?P<name>(?:--?)?(?:" + SECRET_NAMES + r"))(?![\w-])"
    r"(?P<sep>[\"']?\]?\**+(?:[ \t]*+(?:(?P<colon>:)(?![:=])|(?:\|\|)?=(?![=>~])|(?::=|=>)(?=[ \t]*+[\"'`]))"
    r"|[ \t]++\|)[ \t]*+\**+[ \t]*+)"
    r"(?(colon)(?P<hint>[A-Za-z_][\w.]*+(?:\[[^\]\n]*\])?[ \t]*+=(?![=>])[ \t]*+)?)" + SECRET_VALUE)
# `--password hunter22`: only a flag takes its value after a space.
SECRET_FLAG = re.compile(r"(?i)(?<![\w-])(?P<name>--?(?:" + SECRET_NAMES + r"))(?![\w-])(?P<sep>[ \t]++)(?=[^\s-])"
                         + SECRET_VALUE)
# A value that names where the secret lives instead of holding it, as a whole.
SECRET_REFERENCE = re.compile(
    r"(?:\$\{?(?:[A-Z][A-Z0-9_]*|[a-z][a-z_]*)\}?|%[A-Z_][A-Z0-9_]*%|<[^>\n]*>|\[redacted\]"  # $VAR, %VAR%, <token>
    r"|\$\{\w+:?[-=?+][^}]*\}|\$env:\w+|\$\(.*"  # ${VAR:-default}, PowerShell $env:VAR, $(command)
    r"|\$?\{\{.*|![A-Za-z]\w*"  # a template expression (Actions, Jinja), a YAML tag (!vault)
    r"|[A-Za-z_][\w.]*(?:\(.*\)|\[.*\]|[(\[])"  # a call or an index: get_secret("db"), os.environ["X"]
    r"|(?:os|self|cls|settings|config|conf|cfg|env|environ|process|request|app|ctx|secrets|vault|options|opts|args)"
    r"\.[\w.]+!?"
    r"|[A-Z][A-Z]*(?:_[A-Z][A-Z0-9]*)+"  # the name of an environment variable: GITHUB_TOKEN
    r"|(?:~|\.\.?)?/[\w.-]+/[\w./-]*|[A-Za-z]:[\\/]\S*)\Z")  # a path with a folder in it
# Headless runs of these commands are Omoikane maintaining itself; capturing them would loop forever. Read from
# the prompt files so a new operation cannot be left out of the list.
OMOIKANE_COMMANDS = {f"/{p.stem}" for p in (OMOIKANE / "prompts").glob("*.md")}
# Lower-cased tool names: Claude Code capitalises (Edit, Bash), Pi and OpenCode do not (edit, bash).
EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit"}
SHELL_TOOLS = {"bash", "powershell"}
# Path argument per harness: Claude Code file_path/notebook_path, OpenCode filePath, Pi path.
PATH_KEYS = ("file_path", "notebook_path", "filePath", "path")
# Claude Code's command entry, with <command-message> before or after <command-name>. Anchored at the start: a
# prompt that pastes a transcript excerpt is prose, not a command.
COMMAND_TAG = re.compile(r"\s*(?:<command-message>[^<]*</command-message>\s*)?<command-name>(/[\w:-]+)</command-name>")
# A prompt that starts with /name. Claude Code and OpenCode run such a prompt as the command, whatever follows it.
SLASH_COMMAND = re.compile(r"(/[\w:-]+)(?:\s|\Z)")
# A command stored as its expanded template (OpenCode does this); every .opencode/command/*.md starts this way.
COMMAND_TEMPLATE = re.compile(r"\s*Read `omoikane/prompts/(\w+)\.md` and follow it")
NOTE_CHARS = 1500
# Long prompts are where the user states rules: at 2,000 four rules past the cut never became pages (#104). The
# longest prompt in the captures up to 2026-10-06 had 10,306 characters; the limit only bounds a pasted log.
PROMPT_CHARS = 20_000
# OpenCode's read tool cuts each line at 2,000 characters; capture lines are wrapped below that (wrap_long_lines).
LINE_CHARS = 1900
ERROR_CHARS = 400
COMMAND_CHARS = 200
NOTES_BUDGET = 40_000


@dataclass
class Turn:
    prompt: str
    notes: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    harness: str
    cwd: str = ""
    branch: str = ""
    started: str = ""
    ended: str = ""
    parent: str = ""  # id of the session that spawned this one (OpenCode subagent); such sessions are skipped
    turns: list[Turn] = field(default_factory=list)

    @property
    def short_id(self) -> str:
        """Tail of the id, used in file names. Pi ids are UUIDv7 and OpenCode ids are time-ordered, so their heads
        collide for sessions started close together; the tail is random in all three harnesses."""
        return self.session_id[-8:] or "unknown"

    @property
    def day(self) -> str:
        return self.started[:10] if len(self.started) >= 10 else date.today().isoformat()

    @property
    def files(self) -> list[str]:
        return sorted({f for t in self.turns for f in t.files})

    @property
    def first_command(self) -> str:
        """The command the first prompt runs, "" when it runs none.

        Only the first prompt counts, and it is read here rather than in each reader: the Claude reader once
        latched a command from any turn and dropped a coding session that ran /ask in turn 4 (#34). Harness
        commands the agent never answered (/clear, /effort, /model typed before the task) are not the first
        prompt: Claude Code writes them at the head of the transcript, where they would hide a /distill after them.
        Example: Session(..., turns=[Turn("/clear"), Turn("/ingest"), Turn("/ask")]).first_command returns "/ingest".
        """
        for turn in self.turns:
            command = command_of(turn.prompt)
            answered = turn.notes or turn.files or turn.commands or turn.errors
            if command and command not in OMOIKANE_COMMANDS and not answered:
                continue
            return command
        return ""


def command_of(prompt: str) -> str:
    """The command a prompt runs, "" for prose: Claude Code stores the command name, OpenCode the expanded template.

    Example: command_of("Read `omoikane/prompts/distill.md` and follow it.") returns "/distill".
    """
    if template := COMMAND_TEMPLATE.match(prompt):
        return f"/{template.group(1)}"
    slash = SLASH_COMMAND.match(prompt.lstrip())
    return slash.group(1) if slash else ""


def clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + f" [... {len(text) - limit} chars cut]"


def wrap_long_lines(text: str, limit: int = LINE_CHARS) -> str:
    """Break each line longer than `limit` at its last space before the limit. OpenCode's read tool cuts every line
    at 2,000 characters, so a long one-paragraph prompt would lose its end in /distill (#109 review). Runs on the
    redacted capture, and a run with no space stays whole, so no break can hide a secret from redaction.

    Example: wrap_long_lines("aa bb cc", 5) returns "aa bb\\ncc".
    """
    out: list[str] = []
    for line in text.split("\n"):
        while len(line) > limit and (cut := line.rfind(" ", 1, limit + 1)) > 0:
            out.append(line[:cut])
            line = line[cut + 1:]
        out.append(line)
    return "\n".join(out)


def relative_to(path: str, cwd: str) -> str:
    """Path relative to the session cwd, posix-style; a path outside the cwd is returned as given.

    Separators are normalised first: OpenCode on Windows mixes `C:/x` and `C:\\x` between session and tool input,
    and a transcript captured on Windows must read the same on a Linux CI runner.
    """
    if not cwd:
        return path
    try:
        return Path(path.replace("\\", "/")).resolve().relative_to(Path(cwd.replace("\\", "/")).resolve()).as_posix()
    except (ValueError, OSError):
        return path


def iso_from_ms(stamp: object) -> str:
    """Unix milliseconds (Pi message and OpenCode timestamps) to the ISO-8601 UTC form Claude Code writes."""
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return ""
    moment = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def text_blocks(content: object) -> str:
    """Join the text of a content string or list of text blocks; image and thinking blocks contribute nothing.

    Example: text_blocks([{"type": "text", "text": "a"}, {"type": "image"}, {"text": "b"}]) returns "a\\nb".
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(str(b["text"]) for b in content if isinstance(b, dict) and "text" in b and b.get("type", "text") == "text")


def first_line(command: object) -> str:
    lines = str(command or "").strip().splitlines()
    return clip(lines[0], COMMAND_CHARS) if lines else ""


def jsonl_entries(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def read_claude_transcript(path: Path, session_id: str = "") -> Session:
    """Parse a Claude Code JSONL transcript into turns: one per user prompt, with what the agent did in reply.

    Example: read_claude_transcript(Path("~/.claude/projects/<proj>/<id>.jsonl")).turns[0].files
    returns the files the first prompt led the agent to edit.
    """
    session = Session(session_id=session_id, harness="claude")
    current: Turn | None = None
    for entry in jsonl_entries(path):
        if entry.get("isSidechain"):
            continue
        kind = entry.get("type")
        message = entry.get("message")
        if kind not in ("user", "assistant") or not isinstance(message, dict):
            continue
        stamp = str(entry.get("timestamp", ""))
        if stamp:
            session.started = session.started or stamp
            session.ended = stamp
        session.session_id = session.session_id or str(entry.get("sessionId", ""))
        session.cwd = session.cwd or str(entry.get("cwd", ""))
        session.branch = session.branch or str(entry.get("gitBranch", ""))
        content = message.get("content")
        if kind == "user" and isinstance(content, str):
            if entry.get("isMeta") or content.lstrip().startswith("<local-command-"):
                continue
            command = COMMAND_TAG.match(content)
            current = Turn(prompt=clip(command.group(1) if command else content, PROMPT_CHARS))
            session.turns.append(current)
            continue
        if current is None:
            continue
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if kind == "user" and block_type == "tool_result" and block.get("is_error"):
                current.errors.append(clip(text_blocks(block.get("content")), ERROR_CHARS))
            elif kind == "assistant" and block_type == "text" and str(block.get("text", "")).strip():
                current.notes.append(clip(str(block["text"]), NOTE_CHARS))
            elif kind == "assistant" and block_type == "tool_use":
                record_tool_use(current, str(block.get("name", "")), block.get("input") or {}, session.cwd)
    return session


def pi_active_branch(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Entries on the path from the current leaf to the root, oldest first; abandoned `/tree` branches are left out.

    Pi's leaf is the last entry appended (docs/session-format.md, "Tree Structure"). Legacy v1 files have no ids at
    all and are returned as they are; in a tree file an entry without an id is unreachable and dropped.

    Example: pi_active_branch([a, b(parent a), c(parent a)]) returns [a, c].
    """
    tree = [e for e in entries if e.get("type") != "session"]
    if not tree or not tree[-1].get("id"):
        return tree
    by_id = {str(e["id"]): e for e in tree if e.get("id")}
    path: list[dict[str, object]] = []
    current: dict[str, object] | None = tree[-1]
    while current is not None and len(path) < len(by_id):  # bound guards against a parentId cycle
        path.append(current)
        current = by_id.get(str(current.get("parentId") or ""))
    path.reverse()
    return path


def read_pi_transcript(path: Path, session_id: str = "") -> Session:
    """Parse a Pi coding agent session file (~/.pi/agent/sessions/**/*.jsonl) into turns.

    Example: read_pi_transcript(Path("2026-09-15T10-00-00-000Z_<uuid>.jsonl")).turns[0].commands
    returns the shell commands the agent ran for the first prompt.
    """
    session = Session(session_id=session_id, harness="pi")
    entries = jsonl_entries(path)
    header = next((e for e in entries if e.get("type") == "session"), {})
    session.session_id = session.session_id or str(header.get("id", ""))
    session.cwd = str(header.get("cwd", ""))
    session.started = str(header.get("timestamp", ""))
    current: Turn | None = None
    for entry in pi_active_branch(entries):
        message = entry.get("message")
        if entry.get("type") != "message" or not isinstance(message, dict):
            continue
        stamp = str(entry.get("timestamp", "")) or iso_from_ms(message.get("timestamp"))
        if stamp:
            session.started = session.started or stamp
            session.ended = stamp
        role = message.get("role")
        if role == "user":
            current = Turn(prompt=clip(text_blocks(message.get("content")), PROMPT_CHARS))
            session.turns.append(current)
        elif current is None:
            continue
        elif role == "bashExecution" and message.get("command"):
            current.commands.append(first_line(message.get("command")))
        elif role == "toolResult" and message.get("isError"):
            current.errors.append(clip(text_blocks(message.get("content")), ERROR_CHARS))
        elif role == "assistant":
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and str(block.get("text", "")).strip():
                    current.notes.append(clip(str(block["text"]), NOTE_CHARS))
                elif block.get("type") == "toolCall":
                    record_tool_use(current, str(block.get("name", "")), block.get("arguments") or {}, session.cwd)
    return session


def read_opencode_export(path: Path, session_id: str = "") -> Session:
    """Parse an OpenCode session document `{info, messages: [{info, parts}]}`: the output of `opencode export <id>`,
    and what the plugin writes from the SDK's `client.session.get` and `client.session.messages`.

    Example: read_opencode_export(Path("ses_x.json")).turns[0].files
    returns the files the first prompt led the agent to edit.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    info = doc.get("info") if isinstance(doc, dict) and isinstance(doc.get("info"), dict) else {}
    messages = doc.get("messages") if isinstance(doc, dict) and isinstance(doc.get("messages"), list) else []
    session = Session(session_id=session_id or str(info.get("id", "")), harness="opencode")
    session.cwd = str(info.get("directory", ""))
    session.parent = str(info.get("parentID") or "")
    times = info.get("time") if isinstance(info.get("time"), dict) else {}
    session.started = iso_from_ms(times.get("created"))
    session.ended = iso_from_ms(times.get("updated"))
    current: Turn | None = None
    for message in messages:
        if not isinstance(message, dict):
            continue
        meta = message.get("info") if isinstance(message.get("info"), dict) else {}
        raw_parts = message.get("parts") if isinstance(message.get("parts"), list) else []
        parts = [p for p in raw_parts if isinstance(p, dict)]
        role = meta.get("role")
        if role == "user":
            # synthetic parts are written by the harness (tool replays, compaction), not typed by the human
            prompt = "\n".join(str(p.get("text", "")) for p in parts if p.get("type") == "text" and not p.get("synthetic"))
            if not prompt.strip():
                continue
            current = Turn(prompt=clip(prompt, PROMPT_CHARS))
            session.turns.append(current)
            continue
        if role != "assistant" or current is None:
            continue
        for part in parts:
            if part.get("type") == "text" and str(part.get("text", "")).strip():
                current.notes.append(clip(str(part["text"]), NOTE_CHARS))
            elif part.get("type") == "tool":
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                record_tool_use(current, str(part.get("tool", "")), state.get("input") or {}, session.cwd)
                if state.get("status") == "error":
                    current.errors.append(clip(str(state.get("error", "")), ERROR_CHARS))
    return session


READERS: dict[str, Callable[[Path, str], Session]] = {
    "claude": read_claude_transcript,
    "pi": read_pi_transcript,
    "opencode": read_opencode_export,
}


def record_tool_use(turn: Turn, name: str, tool_input: object, cwd: str) -> None:
    if not isinstance(tool_input, dict):
        return
    if name.lower() in EDIT_TOOLS:
        path = next((str(tool_input[k]) for k in PATH_KEYS if tool_input.get(k)), "")
        if path and relative_to(path, cwd) not in turn.files:
            turn.files.append(relative_to(path, cwd))
    elif name.lower() in SHELL_TOOLS and first_line(tool_input.get("command")):
        turn.commands.append(first_line(tool_input.get("command")))


def skip_reason(session: Session, worktree: list[str]) -> str | None:
    """Return why the session is not worth a source file, or None when it is.

    Example: skip_reason(Session(..., turns=[Turn("/ingest")]), []) returns "omoikane operation /ingest".
    """
    if session.first_command in OMOIKANE_COMMANDS:
        return f"omoikane operation {session.first_command}"
    if session.parent:
        return f"subagent of {session.parent}"
    if not session.turns:
        return "no prompts"
    if not session.files and not worktree:
        return "no files edited"
    return None


def run_git(cwd: str, *args: str) -> str:
    if not cwd or not Path(cwd).is_dir():
        return ""
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def git_status(cwd: str) -> list[str]:
    """Changed paths in the working tree at capture time; catches edits made through shell commands, not edit tools."""
    return [line for line in run_git(cwd, "status", "--short").splitlines() if line.strip()][:50]


def git_branch(cwd: str) -> str:
    """Current branch, for harnesses whose transcript does not record it (Claude Code's does)."""
    return run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()


def keep_ends(lengths: list[int], budget: int) -> tuple[int, int]:
    """How many notes to keep from the start and from the end within a character budget: the plan and the outcome.

    Example: keep_ends([10, 10, 10, 10], 25) returns (1, 1).
    """
    if sum(lengths) <= budget:
        return len(lengths), 0
    head = used = 0
    while head < len(lengths) and used + lengths[head] <= budget // 2:
        used += lengths[head]
        head += 1
    tail = 0
    while head + tail < len(lengths) and used + lengths[-1 - tail] <= budget:
        used += lengths[-1 - tail]
        tail += 1
    return head, tail


def render(session: Session, turns: list[Turn], part: int, worktree: list[str]) -> str:
    """Markdown the distill prompt reads. Frontmatter carries the ids the continuation logic needs."""
    out = [
        "---",
        f"harness: {session.harness}",
        f"session: {session.session_id}",
        f"part: {part}",
        f"turns: {len(session.turns)}",
        f"started: {session.started}",
        f"ended: {session.ended}",
        f"cwd: {session.cwd}",
        f"branch: {session.branch}",
        "---",
        "",
        f"# Coding session {session.day} ({session.short_id}, part {part})",
        "",
        "Captured by `omoikane/bin/session-capture.py`, no LLM involved. Agent notes are clipped, not summarised.",
        "",
    ]
    if worktree:
        out += ["## Working tree at capture", "", "```", *worktree, "```", ""]
    files = sorted({f for t in turns for f in t.files})
    if files:
        out += ["## Files edited", "", *[f"- `{f}`" for f in files], ""]
    flat = [(ti, ni) for ti, t in enumerate(turns) for ni in range(len(t.notes))]
    head, tail = keep_ends([len(turns[ti].notes[ni]) for ti, ni in flat], NOTES_BUDGET)
    kept = set(flat[:head] + (flat[len(flat) - tail:] if tail else []))
    cut = len(flat) - len(kept)
    for i, t in enumerate(turns):
        out += [f"## Turn {i + 1}", "", "### Prompt", "", t.prompt, ""]
        if t.files:
            out += ["### Edited", "", *[f"- `{f}`" for f in t.files], ""]
        if t.commands:
            out += ["### Commands", "", "```", *t.commands, "```", ""]
        if t.errors:
            out += ["### Errors", "", *[f"- {e}" for e in t.errors], ""]
        notes = [n for ni, n in enumerate(t.notes) if (i, ni) in kept]
        if notes:
            out += ["### Agent notes", "", *[n + "\n" for n in notes]]
    if cut:
        out += [f"[... {cut} agent notes cut to fit {NOTES_BUDGET} chars]", ""]
    return "\n".join(out).rstrip() + "\n"


def ingested_parts(session: Session, ingested: Path = INGESTED, repo: Path = OMOIKANE.parent) -> list[int]:
    """`turns:` of every distilled part of this session under raw/sources/sessions/, matched by the full session id
    in the frontmatter, so the file-name scheme can change without losing continuation.

    Also on the review gate's branch: a part it distilled stays on wiki/auto until the human merges the PR and
    pulls (#45), and a session that goes on meanwhile must not capture those turns again.
    Example: ingested_parts(Session(session_id="abcdef12-0000", ...)) returns [2] after a two-turn distill.
    """
    texts = {path.name: path.read_text(encoding="utf-8") for path in ingested.glob(f"{session.day}-*.md")}
    folder = ingested.relative_to(repo).as_posix() if ingested.is_relative_to(repo) else ""
    for name in run_git(str(repo), "ls-tree", "--name-only", AUTO_BRANCH, f"{folder}/").split() if folder else []:
        base = name.rsplit("/", 1)[-1]
        if base.startswith(f"{session.day}-") and base not in texts:
            texts[base] = run_git(str(repo), "show", f"{AUTO_BRANCH}:{name}")
    parts: list[int] = []
    for text in texts.values():
        parsed = parse_frontmatter(text)
        if parsed and str(parsed[0].get("session")) == session.session_id:
            parts.append(int(str(parsed[0].get("turns", 0)) or 0))
    return parts


def redaction_terms(path: Path = REDACT_FILE) -> list[str]:
    """Non-blank lines of the redact file, stripped; none when it is missing.

    Example: a file holding "Acme\\n\\n  \\n" returns ["Acme"]. A blank line must not count: an empty term would
    match everywhere.
    """
    if not path.is_file():
        return []
    raw = path.read_bytes()
    # Notepad and PowerShell 5.1 write a BOM, and `>` in PowerShell 5.1 writes UTF-16: a BOM left on the first
    # term made it match nothing.
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    return [line.strip() for line in text.splitlines() if line.strip()]


def term_pattern(term: str) -> str:
    """Regex for a term taken literally, except that `\\` and `/` match each other and a whitespace run matches
    any whitespace: a path is spelt both ways in one transcript, and a name wraps across lines.

    Example: re.fullmatch(term_pattern("C:/a b"), "C:\\\\a\\n b") matches.
    """
    parts = (r"\s+" if part.isspace() else "".join(r"[\\/]" if c in "\\/" else re.escape(c) for c in part)
             for part in re.split(r"(\s+)", term) if part)
    return "".join(parts)


def redact(text: str, terms: list[str]) -> str:
    """Replace every term, in any case, with [redacted]. Longest first, so a term inside a longer one leaves no
    tail. The readers clip long text before this runs, so the start of a term cut by a clip, right before the
    clip marker, goes too.

    Example: redact("ACME-kit and acme", ["acme", "acme-kit"]) returns "[redacted] and [redacted]";
    redact("see Acme Co [... 9 chars cut]", ["Acme Corporation"]) returns "see [redacted] [... 9 chars cut]".
    """
    if not terms:
        return text
    whole = "|".join(term_pattern(term) for term in sorted(terms, key=len, reverse=True))
    text = re.sub(whole, REDACTED, text, flags=re.IGNORECASE)
    prefixes = sorted({term[:n].rstrip() for term in terms for n in range(1, len(term))} - {""}, key=len,
                      reverse=True)
    if not prefixes:
        return text
    cut = r"(?<!\w)(?:" + "|".join(map(term_pattern, prefixes)) + r")(?= \[\.\.\. \d+ chars cut\])"
    return re.sub(cut, REDACTED, text, flags=re.IGNORECASE)


def redact_secrets(text: str) -> str:
    """Replace API keys, tokens, private keys and passwords with [redacted], keeping the name or label before them.
    A value written unquoted counts only with a letter and a digit, a symbol, or 20 characters ("token: expired" is
    prose), unless a clip cut it; a value that names where the secret lives stays, quoted or not.

    Example: redact_secrets("PGPASSWORD=s3cretpw psql") returns "PGPASSWORD=[redacted] psql";
    redact_secrets('password = get_secret("db")') returns it unchanged.
    """
    def assignment(m: re.Match[str]) -> str:
        name, separator, quote, opening = m["name"], m["sep"], m["quote"], m["opening"]
        hint = m.groupdict().get("hint")
        value = m["quoted"] if quote else m["bare"]
        if SECRET_REFERENCE.match(value):
            return m.group(0)
        after = m.string[m.end():m.end() + 4]
        if ":" in separator and not hint and not quote and re.match(r"[ \t]*(?:[),\]]|->)", after) \
                and re.fullmatch(r"[A-Za-z_][\w.]*", value):
            return m.group(0)  # a parameter's type: `def f(token: OAuth2Token) -> None`
        cut = CLIPPED.match(m.string, m.end()) is not None
        secret_like = (len(value) >= 20 or bool(re.search(r"[!@#$%^&*+=?~]", value))
                       or (bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"\d", value))))
        if quote:
            return f"{name}{separator}{hint or ''}{quote}{REDACTED}{quote}" if len(value) >= 4 else m.group(0)
        return f"{name}{separator}{hint or ''}{opening}{REDACTED}" if secret_like or cut else m.group(0)

    text = SECRET_SHAPES.sub(REDACTED, text)
    for pattern in SECRET_AFTER:
        text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
    return SECRET_FLAG.sub(assignment, SECRET_ASSIGNMENT.sub(assignment, text))


def redact_capture(text: str, terms: list[str]) -> str:
    """Redact secrets and the listed terms from a rendered capture, except the frontmatter keys that never hold user
    text. ingested_parts() matches distilled parts by `session:` and reads `turns:`: a redacted id re-captured a
    distilled session as a new part, and a redacted count crashed every later turn. Secrets go first, while a
    listed term inside a token cannot yet break its shape.

    Example: redact_capture("---\\nsession: ab-1\\ncwd: C:/ab\\n---\\n\\nab", ["ab"]) keeps `session: ab-1`.
    """
    def scrub(part: str) -> str:
        return redact(redact_secrets(part), terms)

    head, sep, body = text.partition("\n---\n")
    kept = (line if line.split(":", 1)[0] in UNREDACTED_KEYS else scrub(line) for line in head.split("\n"))
    return "\n".join(kept) + sep + scrub(body)


def capture(transcript: Path, session_id: str = "", harness: str = "claude", inbox: Path = INBOX,
            redact_file: Path = REDACT_FILE) -> str:
    session = READERS[harness](transcript, session_id)
    worktree = git_status(session.cwd)
    reason = skip_reason(session, worktree)
    if reason:
        return f"skip: {reason}"
    session.branch = session.branch or git_branch(session.cwd)
    parts = ingested_parts(session)
    covered = max(parts, default=0)
    if covered >= len(session.turns):
        return "skip: already ingested"
    part = len(parts) + 1
    suffix = "" if part == 1 else f"-part{part}"
    target = inbox / f"{session.day}-{session.short_id}{suffix}.md"
    inbox.mkdir(parents=True, exist_ok=True)
    text = redact_capture(render(session, session.turns[covered:], part, worktree), redaction_terms(redact_file))
    # After redaction: a break between a name and its value (`password:` / `hunter22`) would hide the value from it.
    target.write_text(wrap_long_lines(text), encoding="utf-8")
    shown = target.relative_to(OMOIKANE.parent) if target.is_relative_to(OMOIKANE.parent) else target
    return f"captured {shown.as_posix()} ({len(session.turns) - covered} turns)"


def record_error(exc: Exception, harness: str, session_id: str, errors: Path = ERRORS_FILE,
                 redact_file: Path = REDACT_FILE) -> str:
    """Append one line naming a failed capture to the errors file and return it, redacted as a capture is: the
    brief puts it in a session's context, and that session's own capture would carry it on.

    Example: record_error(KeyError("x"), "pi", "0193-abcdef12") appends and returns
    "2026-10-06T12:00:00Z pi abcdef12 KeyError: 'x'".
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    head = f"{stamp} {harness} {session_id[-8:] or 'unknown'} {type(exc).__name__}"
    try:
        terms = redaction_terms(redact_file)
    except (OSError, UnicodeError) as unreadable:
        # The list may be what broke the capture; recording must not fail on it too, and without the list the
        # message may hold a term it names (#107 review).
        line = f"{head}: [message withheld: omoikane/.capture-redact unreadable ({type(unreadable).__name__})]"
    else:
        # Secrets first, on the raw text: the key patterns read line breaks that joining the lines would remove.
        message = " ".join(redact_secrets(str(exc)).split())
        line = redact(redact_secrets(f"{head}: {clip(message, ERROR_CHARS)}"), terms)
    with errors.open("a", encoding="utf-8") as out:
        out.write(line + "\n")
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--harness", choices=sorted(READERS), default="claude")
    parser.add_argument("--transcript", type=Path, help="session file; default: transcript_path from the Claude Code hook payload on stdin")
    parser.add_argument("--session-id", default="")
    args = parser.parse_args(argv)
    if os.environ.get(NO_CAPTURE_ENV):
        return 0
    transcript, session_id = args.transcript, args.session_id
    try:
        if transcript is None:
            payload = json.loads(sys.stdin.read() or "{}")
            transcript = Path(str(payload.get("transcript_path", "")))
            session_id = session_id or str(payload.get("session_id", ""))
        if not transcript or not transcript.is_file():
            print(f"session-capture: no transcript at {transcript}")
            return 0
        print(f"session-capture: {capture(transcript, session_id, args.harness)}")
    except Exception as exc:  # noqa: BLE001 - a capture failure must never block the harness from stopping
        print(f"session-capture: error {record_error(exc, args.harness, session_id)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - recording the failure failed too; still never block the harness
        print(f"session-capture: error {type(exc).__name__}: {exc}")
        sys.exit(0)
