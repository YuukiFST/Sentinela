"""Headless tests for omoikane/bin/session-capture.py against a fixture transcript. Run: python -m unittest discover -s tests"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omoikane" / "bin"))

import importlib

capture = importlib.import_module("session-capture")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BIN = Path(__file__).resolve().parent.parent / "omoikane" / "bin"


def user(text: str, **extra: object) -> dict[str, object]:
    return {"type": "user", "timestamp": "2026-09-15T10:00:00Z", "sessionId": "abcdef12-0000", "cwd": "C:/proj",
            "gitBranch": "main", "message": {"role": "user", "content": text}, **extra}


def assistant(*blocks: dict[str, object]) -> dict[str, object]:
    return {"type": "assistant", "timestamp": "2026-09-15T10:05:00Z", "message": {"role": "assistant", "content": list(blocks)}}


def tool_result(text: str, is_error: bool) -> dict[str, object]:
    return {"type": "user", "timestamp": "2026-09-15T10:06:00Z",
            "message": {"role": "user", "content": [{"type": "tool_result", "content": text, "is_error": is_error}]}}


def write_transcript(tmp: Path, entries: list[dict[str, object]]) -> Path:
    path = tmp / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\nnot json\n", encoding="utf-8")
    return path


CODING_SESSION = [
    {"type": "attachment", "attachment": {}},
    user("<local-command-caveat>ignored</local-command-caveat>", isMeta=True),
    user("Fix the parser"),
    assistant({"type": "thinking", "thinking": "hidden"},
              {"type": "text", "text": "Root cause: the regex misses CRLF."},
              {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/src/parser.py"}},
              {"type": "tool_use", "name": "Bash", "input": {"command": "python -m pytest\nsecond line"}}),
    tool_result("Exit code 1\nAssertionError", True),
    tool_result("ok", False),
    {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "subagent prompt"}},
    user("Now add a test"),
    assistant({"type": "text", "text": "Done, test added."},
              {"type": "tool_use", "name": "Write", "input": {"file_path": "C:/proj/tests/test_parser.py"}}),
]


class ReadTranscript(unittest.TestCase):
    def test_turns_files_commands_errors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            s = capture.read_claude_transcript(write_transcript(Path(d), CODING_SESSION))
        self.assertEqual(s.session_id, "abcdef12-0000")
        self.assertEqual(s.day, "2026-09-15")
        self.assertEqual([t.prompt for t in s.turns], ["Fix the parser", "Now add a test"])
        self.assertEqual(s.turns[0].files, ["src/parser.py"])
        self.assertEqual(s.turns[0].commands, ["python -m pytest"])
        self.assertEqual(s.turns[0].errors, ["Exit code 1\nAssertionError"])
        self.assertEqual(s.turns[0].notes, ["Root cause: the regex misses CRLF."])
        self.assertEqual(s.files, ["src/parser.py", "tests/test_parser.py"])

    def test_error_text_kept_when_block_has_no_type(self) -> None:
        entries = [user("Fix"), tool_result("ignored", False)]
        entries[1]["message"]["content"] = [{"type": "tool_result", "is_error": True, "content": [{"text": "Traceback boom"}]}]
        with tempfile.TemporaryDirectory() as d:
            s = capture.read_claude_transcript(write_transcript(Path(d), entries))
        self.assertEqual(s.turns[0].errors, ["Traceback boom"])

    def test_slash_command_recorded(self) -> None:
        entries = [user("<command-name>/ingest</command-name><command-args>x.md</command-args>")]
        with tempfile.TemporaryDirectory() as d:
            s = capture.read_claude_transcript(write_transcript(Path(d), entries))
        self.assertEqual(s.first_command, "/ingest")
        self.assertEqual(s.turns[0].prompt, "/ingest")

    def test_every_omoikane_operation_is_skipped(self) -> None:
        # A new prompt missing from the skip list gets its sessions captured and distilled, which loops.
        prompts = sorted((Path(capture.OMOIKANE) / "prompts").glob("*.md"))
        self.assertTrue(prompts)
        for prompt in prompts:
            with self.subTest(op=prompt.stem), tempfile.TemporaryDirectory() as d:
                entries = [user(f"<command-name>/{prompt.stem}</command-name>")]
                s = capture.read_claude_transcript(write_transcript(Path(d), entries))
                self.assertEqual(capture.skip_reason(s, ["M x.py"]), f"omoikane operation /{prompt.stem}")


class ReadPiTranscript(unittest.TestCase):
    """Fixture follows docs/session-format.md of @earendil-works/pi-coding-agent 0.85.1 (v3 tree)."""

    def test_turns_follow_active_branch(self) -> None:
        s = capture.read_pi_transcript(FIXTURES / "pi-session.jsonl")
        self.assertEqual(s.harness, "pi")
        self.assertEqual(s.session_id, "0192f0a1-1111-7000-8000-000000000001")
        self.assertEqual((s.cwd, s.day, s.ended), ("C:/proj", "2026-09-15", "2026-09-15T10:00:08.000Z"))
        self.assertEqual([t.prompt for t in s.turns], ["Fix the parser", "Now add a test"])  # e5 is a dead branch
        self.assertEqual(s.turns[0].files, ["src/parser.py"])
        self.assertEqual(s.turns[0].commands, ["python -m pytest", "git status"])  # tool call, then ! command
        self.assertEqual(s.turns[0].errors, ["Exit code 1\nAssertionError"])
        self.assertEqual(s.turns[0].notes, ["Root cause: the regex misses CRLF."])
        self.assertEqual(s.files, ["src/parser.py", "tests/test_parser.py"])

    def test_entry_without_id_in_a_tree_file_does_not_resurrect_dead_branches(self) -> None:
        lines = (FIXTURES / "pi-session.jsonl").read_text(encoding="utf-8").splitlines()
        lines.insert(3, json.dumps({"type": "label", "timestamp": "2026-09-15T10:00:02.500Z", "targetId": "e1", "label": "x"}))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "mixed.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            s = capture.read_pi_transcript(path)
        self.assertEqual([t.prompt for t in s.turns], ["Fix the parser", "Now add a test"])

    def test_legacy_v1_file_without_ids_is_read_linearly(self) -> None:
        entries = [{"type": "session", "version": 1, "id": "old", "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "C:/proj"},
                   {"type": "message", "timestamp": "2026-01-01T00:00:01.000Z", "message": {"role": "user", "content": "hi"}},
                   {"type": "message", "timestamp": "2026-01-01T00:00:02.000Z", "message": {"role": "user", "content": "again"}}]
        with tempfile.TemporaryDirectory() as d:
            s = capture.read_pi_transcript(write_transcript(Path(d), entries))
        self.assertEqual([t.prompt for t in s.turns], ["hi", "again"])


class ReadOpenCodeExport(unittest.TestCase):
    """Fixture has the shape of `opencode export <id>` on 1.18.30, which the plugin reproduces from the SDK."""

    def test_turns_files_commands_errors(self) -> None:
        s = capture.read_opencode_export(FIXTURES / "opencode-export.json")
        self.assertEqual(s.harness, "opencode")
        self.assertEqual(s.session_id, "ses_0123456789abcdefghijklmnop")
        self.assertEqual((s.cwd, s.started, s.ended), ("C:\\proj", "2026-09-15T10:20:00.000Z", "2026-09-15T10:30:00.000Z"))
        self.assertEqual([t.prompt for t in s.turns], ["Fix the parser", "Now add a test"])  # synthetic msg_3 dropped
        self.assertEqual(s.turns[0].files, ["src/parser.py"])
        self.assertEqual(s.turns[0].commands, ["python -m pytest"])
        self.assertEqual(s.turns[0].errors, ["Exit code 1\nAssertionError"])
        self.assertEqual(s.turns[0].notes, ["Root cause: the regex misses CRLF."])
        self.assertEqual(s.files, ["src/parser.py", "tests/test_parser.py"])
        self.assertEqual(s.parent, "")

    def test_command_template_as_first_prompt_is_the_first_command(self) -> None:
        doc = json.loads((FIXTURES / "opencode-export.json").read_text(encoding="utf-8"))
        doc["messages"][0]["parts"][0]["text"] = "Read `omoikane/prompts/distill.md` and follow it. Argument: x.md"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cmd.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            s = capture.read_opencode_export(path)
        self.assertEqual(s.first_command, "/distill")
        self.assertEqual(capture.skip_reason(s, []), "omoikane operation /distill")

    def test_subagent_session_is_skipped(self) -> None:
        doc = json.loads((FIXTURES / "opencode-export.json").read_text(encoding="utf-8"))
        doc["info"]["parentID"] = "ses_parent"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            s = capture.read_opencode_export(path)
        self.assertEqual(capture.skip_reason(s, []), "subagent of ses_parent")


class SkipRules(unittest.TestCase):
    def test_omoikane_operation_is_skipped(self) -> None:
        s = capture.Session(session_id="x", harness="claude", turns=[capture.Turn("/ask", files=["a"])])
        self.assertEqual(capture.skip_reason(s, []), "omoikane operation /ask")

    def test_no_edits_is_skipped_unless_worktree_dirty(self) -> None:
        s = capture.Session(session_id="x", harness="claude", turns=[capture.Turn("q")])
        self.assertEqual(capture.skip_reason(s, []), "no files edited")
        self.assertIsNone(capture.skip_reason(s, [" M a.py"]))


def claude_session(d: Path, first: str, later: str) -> capture.Session:
    command = lambda text: f"<command-name>/{text[1:]}</command-name>" if text.startswith("/") else text  # noqa: E731
    entries = [user(command(first)), assistant({"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/a.py"}}),
               user(command(later)), assistant({"type": "text", "text": "Answered."})]
    return capture.read_claude_transcript(write_transcript(d, entries))


def pi_session(d: Path, first: str | list[dict[str, str]], later: str) -> capture.Session:
    entries = [json.loads(line) for line in (FIXTURES / "pi-session.jsonl").read_text(encoding="utf-8").splitlines()
               if line.startswith("{")]
    for entry in entries:
        if entry.get("id") == "e1":
            entry["message"]["content"] = first
        elif entry.get("id") == "e7":
            entry["message"]["content"] = [{"type": "text", "text": later}]
    return capture.read_pi_transcript(write_transcript(d, entries))


def opencode_session(d: Path, first: str, later: str) -> capture.Session:
    template = lambda text: (f"Read `omoikane/prompts/{text[1:]}.md` and follow it. Argument: q"  # noqa: E731
                             if text.startswith("/") else text)
    doc = json.loads((FIXTURES / "opencode-export.json").read_text(encoding="utf-8"))
    user_texts = [p for m in doc["messages"] if m["info"]["role"] == "user"
                  for p in m["parts"] if p.get("type") == "text" and not p.get("synthetic")]
    user_texts[0]["text"], user_texts[-1]["text"] = template(first), template(later)
    path = d / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return capture.read_opencode_export(path)


class OperationOnlyFromTheFirstPrompt(unittest.TestCase):
    # One rule for every harness (#34): the Claude reader latched a command from any turn, so a coding session
    # that ran /ask in turn 4 was dropped whole, while the Pi and OpenCode readers read the first prompt only.
    READERS = {"claude": claude_session, "pi": pi_session, "opencode": opencode_session}

    def test_command_in_a_later_turn_keeps_the_session(self) -> None:
        for harness, read in self.READERS.items():
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as d:
                s = read(Path(d), "Fix the parser", "/ask")
                self.assertEqual(s.first_command, "")
                self.assertIsNone(capture.skip_reason(s, [" M a.py"]))

    def test_command_as_the_first_prompt_skips_the_session(self) -> None:
        for harness, read in self.READERS.items():
            with self.subTest(harness=harness), tempfile.TemporaryDirectory() as d:
                s = read(Path(d), "/distill", "Now add a test")
                self.assertEqual(capture.skip_reason(s, [" M a.py"]), "omoikane operation /distill")

    def test_claude_command_entries_before_the_first_real_prompt(self) -> None:
        # Claude Code writes /clear, /effort or /model as the first entry of a transcript (4 of 25 real ones), and
        # writes <command-message> before or after <command-name> depending on the command.
        edit = assistant({"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/a.py"}})
        clear = user("<command-name>/clear</command-name>\n<command-message>clear</command-message>\n<command-args></command-args>")
        distill = user("<command-message>distill</command-message>\n<command-name>/distill</command-name>\n"
                       "<command-args>x.md</command-args>")
        pasted = user("Why did this fail?\n<command-name>/ingest</command-name>")
        for name, entries, reason in (
                ("builtin then operation", [clear, distill, edit], "omoikane operation /distill"),
                ("builtin then coding", [clear, user("Fix the parser"), edit], None),
                ("command-message first", [distill, edit], "omoikane operation /distill"),
                ("tag pasted into prose", [pasted, edit], None)):
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                s = capture.read_claude_transcript(write_transcript(Path(d), entries))
                self.assertEqual(capture.skip_reason(s, [" M a.py"]), reason)

    def test_pi_first_prompt_as_a_content_list(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            s = pi_session(Path(d), [{"type": "text", "text": "/distill x.md"}], "Now add a test")
            self.assertEqual(capture.skip_reason(s, [" M a.py"]), "omoikane operation /distill")


class Render(unittest.TestCase):
    def test_markdown_has_frontmatter_and_sections(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            s = capture.read_claude_transcript(write_transcript(Path(d), CODING_SESSION))
        md = capture.render(s, s.turns, 1, [" M src/parser.py"])
        self.assertTrue(md.startswith("---\nharness: claude\nsession: abcdef12-0000\npart: 1\nturns: 2\n"))
        for needle in ("## Working tree at capture", "## Files edited", "- `src/parser.py`", "## Turn 2",
                       "### Errors", "Root cause: the regex misses CRLF."):
            self.assertIn(needle, md)
        self.assertNotIn("hidden", md)

    def test_keep_ends_keeps_start_and_end(self) -> None:
        self.assertEqual(capture.keep_ends([10, 10, 10, 10], 25), (1, 1))
        self.assertEqual(capture.keep_ends([10, 10], 100), (2, 0))


class Redaction(unittest.TestCase):
    # A capture is committed and pushed by the scheduled run, then immutable under raw/sources/ (#62). A name the
    # user lists in omoikane/.capture-redact must never reach the file, wherever the session wrote it.
    SESSION = [
        user("Read the Acme-Kit rules"),
        assistant({"type": "text", "text": "The ACME-KIT says prices are cents; axcme agrees."},
                  {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/acme/prices.py"}},
                  {"type": "tool_use", "name": "Bash", "input": {"command": "grep -c a.c+me src"}}),
    ]

    def captured(self, redact_list: str | None, session: list[dict[str, object]] | None = None,
                 encoding: str = "utf-8") -> str:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            redact_file = tmp / ".capture-redact"
            if redact_list is not None:
                redact_file.write_bytes(redact_list.encode(encoding))
            capture.capture(write_transcript(tmp, session or self.SESSION), inbox=tmp / "inbox",
                            redact_file=redact_file)
            return next((tmp / "inbox").glob("*.md")).read_text(encoding="utf-8")

    def test_the_list_is_read_whatever_editor_wrote_it(self) -> None:
        # Notepad and PowerShell 5.1 write a byte-order mark, `>` in PowerShell 5.1 writes UTF-16: the first term
        # once kept its BOM and matched nothing.
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                self.assertNotIn("acme", self.captured("acme\nother\n", encoding=encoding).lower())

    def test_frontmatter_ids_survive_so_continuation_still_matches(self) -> None:
        # ingested_parts() matches distilled parts by `session:` and reads `turns:`; a redacted id re-captured the
        # whole session as a new part, a redacted count crashed every later turn.
        for redact_list in ("abcdef\n", "1\n", "claude\n"):
            with self.subTest(redact_list=redact_list):
                md = self.captured(redact_list)
                self.assertTrue(md.startswith("---\nharness: claude\nsession: abcdef12-0000\npart: 1\nturns: 1\n"))

    def test_a_term_cut_by_a_clip_leaves_no_prefix(self) -> None:
        note = "y" * (capture.NOTE_CHARS - 10) + " Acme Corporation ships"
        md = self.captured("Acme Corporation\n", [user("Fix"), assistant({"type": "text", "text": note},
                           {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/a.py"}})])
        self.assertNotIn("acme", md.lower())
        self.assertIn("[redacted] [... ", md)

    def test_a_rule_at_the_end_of_a_long_prompt_reaches_the_capture(self) -> None:
        # Long prompts are where the user states rules: four times a rule past the 2,000th character never became a
        # page (#104). The prompt is kept whole, and redaction still applies to all of it.
        # OpenCode's read tool cuts every line at 2,000 characters, so one long paragraph is wrapped (#109 review).
        for name, filler in (("lines", "Context line for the task.\n"), ("one paragraph", "Context for the task. ")):
            with self.subTest(name):
                prompt = filler * 222 + "Rule: every Acme invoice total is in integer cents."
                md = self.captured("Acme\n", [user(prompt), assistant(
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/a.py"}})])
                self.assertGreater(len(prompt), 4800)
                self.assertIn("Rule: every [redacted] invoice total is in integer cents.", md)
                self.assertLessEqual(max(map(len, md.splitlines())), 2000)
        self.assertNotIn("acme", md.lower())

    def test_a_term_matches_either_path_separator_and_any_whitespace(self) -> None:
        session = [user("Fix"), assistant({"type": "text", "text": "Acme\n  Corp ships"},
                                          {"type": "tool_use", "name": "Bash",
                                           "input": {"command": "type C:\\proj\\acme\\notes.txt"}},
                                          {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/proj/a.py"}})]
        md = self.captured("C:/proj/acme\nAcme Corp\n", session).lower()
        self.assertNotIn("proj\\acme", md)
        self.assertNotIn("acme\n", md)
        self.assertIn("[redacted]\\notes.txt", md)

    def test_listed_terms_never_reach_the_capture(self) -> None:
        cases = [
            # (redact file, absent from the lower-cased capture, present in it)
            ("acme\nacme-kit\n", ["acme", "-kit"], ["Read the [redacted] rules", "[redacted]/prices.py"]),
            ("ACME\n", ["acme"], ["[redacted]-Kit"]),
            ("\n  \nacme\n", ["acme"], ["Read the", "says prices"]),
            ("a.c+me\n", ["a.c+me"], ["grep -c [redacted] src", "axcme agrees"]),
        ]
        for redact_list, absent, present in cases:
            with self.subTest(redact_list=redact_list):
                md = self.captured(redact_list)
                for term in absent:
                    self.assertNotIn(term, md.lower())
                for needle in present:
                    self.assertIn(needle, md)
                self.assertIn("session: abcdef12-0000\n", md)

    def test_secrets_never_reach_the_capture_without_a_list(self) -> None:
        # A key pasted into a prompt or printed in the agent's notes was committed and pushed with the capture (#77).
        # Built by concatenation, so the repository holds no string a secret scanner would flag.
        gh, aws, sk = "ghp_" + "a1B2" * 9, "AKIA" + "Q7XZ" * 4, "sk-ant-api03-" + "x9Y_" * 8
        jwt = "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxIn0" + "." + "c2lnbmF0dXJlLXZhbHVl"
        pem = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow" + "IBAAKCAQEA\n-----END RSA " + "PRIVATE KEY-----"
        cases = [
            # (text in the session, secret absent from the capture, context kept)
            (f"use token {gh} for the API", gh[4:], "use token [redacted] for the API"),
            (f"aws key {aws} in prod", aws, "aws key [redacted] in prod"),
            (f"ANTHROPIC_API_KEY={sk}", sk, "ANTHROPIC_API_KEY=[redacted]"),
            (f"curl -H 'Authorization: Bearer {jwt}'", "c2lnbmF0dXJl", "Bearer [redacted]"),
            ("DB_PASSWORD='hunter-Correct'", "hunter", "DB_PASSWORD='[redacted]'"),
            ("run PGPASSWORD=s3cretpw psql -h db", "s3cretpw", "PGPASSWORD=[redacted] psql -h db"),
            ("connect to postgres://app:s3cr3t-pw@db.local/shop", "s3cr3t", "postgres://app:[redacted]@db.local"),
            (f"the key is\n{pem}\nkeep it", "MIIEow", "the key is\n[redacted]\nkeep it"),
            # A clip can cut a secret short of its full shape; the part before the marker goes too.
            ("y" * (capture.NOTE_CHARS - 12) + f" ghp_a1B2a1B2 {gh}", "a1B2", "[redacted] [... "),
            ("y" * (capture.NOTE_CHARS - 17) + " DB_PASSWORD=hunt" + "x" * 30, "hunt", "DB_PASSWORD=[redacted] [... "),
            # Shapes the #82 review found leaking.
            ('{"password": "hunter22", "user": "ana"}', "hunter22", '{"password": "[redacted]", "user": "ana"}'),
            ("data = {'api_key': 'abcd1234efgh'}", "abcd1234", "{'api_key': '[redacted]'}"),
            ("mysql -uroot -pS3cr3tPass shop", "S3cr3tPass", "mysql -uroot -p[redacted] shop"),
            ("Authorization: Basic " + "dXNlcjpwYXNz" + "d29yZA==", "dXNlcjpw", "Authorization: Basic [redacted]"),
            ("curl -u admin:S3cr3tPass https://x", "S3cr3tPass", "curl -u admin:[redacted] https://x"),
            ("redis://:s3cr3tpw@cache:6379", "s3cr3tpw", "redis://:[redacted]@cache:6379"),
            ("postgres://u:p@ss1word@host/db", "ss1word", "postgres://u:[redacted]@host/db"),
            ("DB_PASS=hunter2xyz and STRIPE_KEY=abcd1234efgh5678", "hunter2xyz", "DB_PASS=[redacted] and STRIPE_KEY=[re"),
            ("password: 'p@ss w0rd'", "w0rd", "password: '[redacted]'"),
            ("**Password:** hunter2x", "hunter2x", "**Password:** [redacted]"),
            ("| password | hunter2x |", "hunter2x", "| password | [redacted] |"),
            ("DB_PASSWORD=$ecr3tP4ss", "ecr3tP4ss", "DB_PASSWORD=[redacted]"),
            ("token glpat-" + "a1b2c3d4e5f6g7h8i9j0", "a1b2c3d4", "token [redacted]"),
            ("-----BEGIN PGP " + "PRIVATE KEY BLOCK-----\n" + "lQOYBF" * 4 + "\n-----END PGP " + "PRIVATE KEY BLOCK-----",
             "lQOYBF", "[redacted]"),
            # Shapes the second #82 review found leaking.
            ("mysql --user=root --password=hunter22 shop", "hunter22", "--password=[redacted] shop"),
            ("gh secret set --api-key hunter22x now", "hunter22x", "--api-key [redacted] now"),
            ('"private_key": "-----BEGIN ' + 'PRIVATE KEY-----\\nMIIEvQ' + "IBADANBg" * 3 + '\\nAB==\\n-----END '
             + 'PRIVATE KEY-----\\n"', "IBADANBg", '"private_key": "[redacted]'),
            ("secretAccessKey: 'wJalrXUtnF" + "EMIK7MDENG'", "wJalrXUtnF", "secretAccessKey: '[redacted]'"),
            ("privateKey: 'hunter22'", "hunter22", "privateKey: '[redacted]'"),
            ('DB_PASSWORD: str = "hunter22"', "hunter22", 'DB_PASSWORD: str = "[redacted]"'),
            ('headers = {"Authorization": "Basic QWxhZGRp' + 'bjpvcGVu"}', "QWxhZGRp", '"Authorization": "Basic [redacted]"'),
            ("curl --user ana:hunter22 https://x", "hunter22", "curl --user ana:[redacted] https://x"),
            ("https://u:hunter22@host?email=a@b.com", "hunter22", "https://u:[redacted]@host?email=a@b.com"),
            ("-----BEGIN RSA " + "PRIVATE KEY-----\n" + "MIIEow" * 6 + "\nAAAAAAAAAA\n-----END RSA " + "PRIVATE KEY-----",
             "AAAAAAAAAA", "[redacted]"),
            ("> -----BEGIN RSA " + "PRIVATE KEY-----\n> " + "MIIEow" * 6 + "\n> -----END RSA " + "PRIVATE KEY-----",
             "MIIEow", "> [redacted]"),
            ("Password: `hunter22`", "hunter22", "Password: `[redacted]`"),
            ("password=/hunter22", "hunter22", "password=[redacted]"),
            # Shapes the third #82 review found leaking.
            ("-----BEGIN PGP " + "PRIVATE KEY BLOCK-----\nVersion: GnuPG v2.0.22 (GNU/Linux)\n\n" + "lQOYBF" * 5
             + "\n" + "Zm9vYmFy" * 4 + "\n=abcd\n-----END PGP " + "PRIVATE KEY BLOCK-----", "lQOYBF", "[redacted]"),
            ("use the password PGPASSWORD=s3cretpw psql", "s3cretpw", "PGPASSWORD=[redacted] psql"),
            ("Access Token Secret: abc123def456", "abc123", "Secret: [redacted]"),
            ('password := "hunter22"', "hunter22", 'password := "[redacted]"'),
            ("'password' => 'hunter22',", "hunter22", "'password' => '[redacted]',"),
            ('os.environ["DB_PASSWORD"] = "hunter22"', "hunter22", '["DB_PASSWORD"] = "[redacted]"'),
            ("ENV['DB_PASSWORD'] ||= 'hunter22'", "hunter22", "ENV['DB_PASSWORD'] ||= '[redacted]'"),
            ('key = ("-----BEGIN ' + 'PRIVATE KEY-----\\n"\n    "' + "MIIEvQ" * 5 + '\\n"\n    "-----END '
             + 'PRIVATE KEY-----")', "MIIEvQ", 'key = ("[redacted]")'),
            ("<password>hunter22</password>", "hunter22", "<password>[redacted]</password>"),
            ("AccountKey=" + "abcd1234" * 4 + "==;", "abcd1234", "AccountKey=[redacted]"),
        ]
        for text, absent, present in cases:
            with self.subTest(text=text[:40]):
                prompt = text if len(text) < capture.NOTE_CHARS else "Fix"  # the clip case is about notes
                session = [user(prompt), assistant({"type": "text", "text": text},
                                                 {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/p/a.py"}})]
                md = self.captured(None, session)
                self.assertNotIn(absent, md)
                self.assertIn(present, md)

    def test_code_that_only_names_a_secret_is_kept(self) -> None:
        # Redacting references would strip the code the session talks about, and the distill would lose it.
        text = ('token: str = os.environ["API_TOKEN"]; password = get_secret("db"); export API_KEY=$API_KEY; '
                "secret_key = settings.SECRET_KEY; max_tokens=100000; when the token: expired, log in again; "
                'password: "${DB_PASSWORD}"; token_env = "GITHUB_TOKEN"; token_type = "bearer"; '
                "token: OAuth2Token = fetch(); token_path=/home/ana/.config/gh/hosts.yml; pwd=/c/Users/ana/shop; "
                "tokenizer_name=bert-base-multilingual-cased; secretary=JaneDoe42; api_key_header: X-API-Key2; "
                "the bearer authenticationscheme; task-sk-learn-compatible-estimator-api; "
                # False positives the second #82 review found.
                'if password == expected: token === other; token := os.Getenv("GITHUB_TOKEN"); '
                "token: ${{ secrets.GITHUB_TOKEN }}; password: '{{ vault_db_password }}'; password: !vault |; "
                "bypass=check_v2; first_pass = run1; sort_key: created_at2; primary_key = user_id2; "
                "public_key = pk2; find /var/lib/mysql -type f -print; docker run --name mysql -p3306:3306 x; "
                "docker run -u 1000:1000 image; def refresh(token: OAuth2Token) -> None; "
                # False positives the third #82 review found.
                "$token = $env:GITHUB_TOKEN; password=$(cat /run/secrets/db); password=${DB_PASSWORD:-postgres}; "
                "apiKey: process.env.OPENAI_API_KEY!, I used curl and then docker run -u 1000:1000 image; "
                "sk-learn-compatible-estimator")
        md = self.captured(None, [user(text), assistant({"type": "tool_use", "name": "Edit",
                                                          "input": {"file_path": "C:/p/a.py"}})])
        self.assertIn(text, md)
        self.assertNotIn("[redacted]", md)

    def test_a_secret_header_without_its_end_takes_nothing_after_it(self) -> None:
        # A PEM header with no END line ran on to the end of the capture and erased the turns after it (#82 review).
        note = "The file starts with `-----BEGIN OPENSSH " + "PRIVATE KEY-----`, so it is an OpenSSH key"
        md = self.captured(None, [user("What key is this?"), assistant({"type": "text", "text": note}),
                                  user("Fix the deploy script"),
                                  assistant({"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/p/a.py"}})])
        self.assertIn("so it is an OpenSSH key", md)
        self.assertIn("Fix the deploy script", md)
        # Nor the blank lines and the heading of the next section, nor a long word on the next line.
        for after in ("\n\n## Turn 2\n", "\nAuthenticationFailedException thrown by paramiko",
                      "\nSee docs at keygen\n\nNext step: convert it, then\n-----END OPENSSH " + "PRIVATE KEY-----",
                      " and the footer -----END OPENSSH " + "PRIVATE KEY----- wrap it"):
            text = "-----BEGIN OPENSSH " + "PRIVATE KEY-----" + after
            self.assertEqual(capture.redact_secrets(text), "[redacted]" + after)
        prose = "the auth scheme is bearer\n\nsrc/auth/middleware2.ts handles it"
        self.assertEqual(capture.redact_secrets(prose), prose)

    def test_long_names_and_values_redact_in_linear_time(self) -> None:
        # A hyphenated run of keywords took 85 s on 8,000 characters, inside the Stop hook (#82 review).
        start = time.perf_counter()
        for text in ("password-" * 900, "token-" * 1300, "a-" * 4000, "password:" + " " * 8000,
                     "password" + " " * 4000 + "|" + " " * 4000, "a-" * 4000 + "://"):
            capture.redact_secrets(text)
        self.assertLess(time.perf_counter() - start, 2.0)
        # A prompt line may now hold 20,000 characters (#104): the curl and mysql scans each took over a second on
        # one such line of repeated commands (#109 review).
        start = time.perf_counter()
        for text in ("mysql=" * 3400, "x mysql," * 2500, "(curl a " * 2500):
            capture.redact_secrets(text)
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_no_redact_file_changes_nothing(self) -> None:
        for redact_list in (None, "", "\n\n"):
            with self.subTest(redact_list=redact_list):
                md = self.captured(redact_list)
                self.assertIn("Read the Acme-Kit rules", md)
                self.assertNotIn("[redacted]", md)


class Continuation(unittest.TestCase):
    # The review gate distills in a worktree on wiki/auto (#45): until its PR is merged and pulled, the distilled
    # capture is on that branch only. A session that goes on must not capture those turns again.
    def test_a_part_distilled_on_wiki_auto_counts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)

            def git(*args: str) -> None:
                subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                                *args], capture_output=True, check=True)

            git("init", "-q", "-b", "main")
            git("commit", "-q", "--allow-empty", "-m", "init")
            git("switch", "-q", "-c", "wiki/auto")
            sessions = repo / "omoikane/raw/sources/sessions"
            sessions.mkdir(parents=True)
            (sessions / "2026-09-15-abcdef12.md").write_text("---\nsession: abcdef12-0000\nturns: 2\n---\n", encoding="utf-8")
            (sessions / "2026-09-15-other000.md").write_text("---\nsession: other\nturns: 9\n---\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", "feat(wiki): distill 2026-09-15-abcdef12")
            git("switch", "-q", "main")
            session = capture.Session(session_id="abcdef12-0000", harness="claude", started="2026-09-15T10:00:00Z")
            self.assertEqual(capture.ingested_parts(session, ingested=sessions, repo=repo), [2])


class CaptureFailure(unittest.TestCase):
    # The Stop hook's stdout reaches nobody, so a capture that crashed on every turn lost every session unseen (#103).
    def test_a_failed_capture_is_named_in_the_next_brief(self) -> None:
        cases = {
            "listed term": ("Expecting\n".encode("utf-8"), " opencode 89abcdef JSONDecodeError: [redacted] value"),
            # PowerShell 5.1 Set-Content writes the list in the ANSI code page: reading it failed again while
            # recording, and the failure went unrecorded (#107 review). The message may hold a term, so it goes.
            "unreadable list": ("São Benedito\n".encode("cp1252"), " opencode 89abcdef JSONDecodeError: [message "
                                "withheld: omoikane/.capture-redact unreadable (UnicodeDecodeError)]"),
        }
        for name, (redact_list, expected) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                omoikane = Path(d) / "omoikane"
                shutil.copytree(BIN, omoikane / "bin", ignore=shutil.ignore_patterns("__pycache__"))
                (omoikane / ".capture-redact").write_bytes(redact_list)
                broken = Path(d) / "export.json"
                broken.write_text("not json", encoding="utf-8")
                hook = [sys.executable, str(omoikane / "bin" / "session-capture.py"), "--harness", "opencode",
                        "--transcript", str(broken), "--session-id", "ses_0123456789abcdef"]
                env = {k: v for k, v in os.environ.items() if k != capture.NO_CAPTURE_ENV}
                # A scheduled run sets the variable; a file written during it would block the run.
                subprocess.run(hook, env={**env, capture.NO_CAPTURE_ENV: "1"}, capture_output=True, check=True)
                self.assertFalse((omoikane / ".capture-errors").exists())
                stop = subprocess.run(hook, env=env, capture_output=True, text=True)
                brief = subprocess.run([sys.executable, str(omoikane / "bin" / "session-context.py")], env=env,
                                       capture_output=True, text=True, encoding="utf-8").stdout
                self.assertEqual(stop.returncode, 0)
                self.assertIn("Session capture failed 1 time", brief)
                self.assertIn(expected, brief)
                self.assertNotIn("Expecting", brief)

    def test_a_secret_in_the_error_message_is_redacted_before_its_lines_are_joined(self) -> None:
        # The key patterns read line breaks; joining the lines first leaked a clipped key body (#107 review).
        key = "-----BEGIN RSA PRIVATE KEY-----\n" + "MIIEpAIBAAKCAQEAxxxxxxxxxxxxxxxxxxxxxxxxxx\n" * 10
        with tempfile.TemporaryDirectory() as d:
            line = capture.record_error(ValueError(f"bad value: {key}"), "claude", "abcdef12-0000",
                                        errors=Path(d) / ".capture-errors", redact_file=Path(d) / "none")
        self.assertNotIn("MIIE", line)
        self.assertIn(" claude f12-0000 ValueError: bad value: [redacted]", line)


if __name__ == "__main__":
    unittest.main()
