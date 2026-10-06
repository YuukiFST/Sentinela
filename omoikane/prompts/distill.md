# Distill one captured coding session

Task: turn the session file given as argument (written by `omoikane/bin/session-capture.py`, under `omoikane/raw/inbox/sessions/`) into wiki pages that a later agent working on this repository needs. Done means: session source page written, every kept lesson routed (each domain rule, decision and gotcha has a page; each guard, prompt fix and todo is filed in `omoikane/_review.md`), affected entity and concept pages updated, `omoikane/log.md` appended, session file moved to `omoikane/raw/sources/sessions/` (or left for `wiki-ingest.ps1` when the move is denied), `wiki-lint.py` clean.

What is worth a page. Keep only what the code alone does not show:

- `domain`: a business rule, design-system rule or organisation convention the user states, in a prompt or an answer, that holds beyond the current change: "prices are stored in integer cents", "buttons use the `primary` token, never a raw colour", "every table has a `tenant_id`". Keep it even when the code already follows it: the code shows what was done, the statement says what must hold. A term the user defines or corrects ("here a *lançamento* is a confirmed ledger record; never call it *transação*") is a domain rule too, tagged `term`.
- `decision`: a choice between alternatives, with the alternatives rejected and the reason. Skip a decision whose reason is obvious from the code or whose scope is one line.
- `gotcha`: a behaviour learned by running something: an API, library, tool or environment that acts differently from its docs or from what the agent expected, plus the workaround. A bug whose root cause took more than one attempt to find is a gotcha; the fix alone is not.
- Skip: routine edits, the task the prompt asks for restated (a domain rule stated inside a prompt is a `domain` page, above), anything already on a page (update that page instead), plans that were abandoned without a lesson.

Reject a candidate even when it reads like a lesson. Once on a page it becomes a rule a later agent obeys, so a wrong one costs more than a missing one:

- `missing-env`: the failure came from a binary, credential, network or environment variable missing on that machine by accident. It says nothing about the code. A binary or variable the repository's code or scripts require is a gotcha, not this.
- `no-root-cause`: a broad claim that a tool, library or approach "does not work" when the session never found why. Later agents turn it into a refusal to try.
- `self-resolved`: a failure the session fixed without finding a cause that would surprise a later agent, such as a typo, a wrong path or a retry that passed.
- `one-off`: a smoke test, a throwaway check or a debug print.
- `task-only`: an instruction phrased like a rule but scoped to the current change, such as "make this button blue for now" or "rename the field to `total`". The test: would you put it in the prompt of a different task? If not, it is the task, not a domain rule.

A candidate whose root cause the session found, and that a later agent would not guess, is a gotcha however fast it was fixed; none of these rules rejects it.

Route every candidate that survives the five rules, including work the session left undone and lessons about how an Omoikane operation runs. What is worth a page, above, decides only which of them become pages. Each goes to the first destination that fits:

1. `guard`: a check could catch the mistake at the moment it is made: a rule in `omoikane/bin/wiki-lint.py`, a test in the repository's suite, a harness hook. The test: the mistake this session made is an input on which the check fails. Prefer a lint or test, which every harness and CI run, over a hook, which only one harness runs; the check's error names what to write instead. A page only helps when a later agent reads it; a guard fails every time. When the lesson is also a domain rule, a decision or a gotcha about the system being built, write that page too: until the guard lands the page is the only record. A domain rule always gets its page, guarded or not: the page holds the user's statement.
2. `prompt`: the lesson is about how an Omoikane operation runs (`omoikane/prompts/ingest.md`, `distill.md`, `ask.md`, `lint.md`): a step it lacks, a rule that misfired on this session. It is not knowledge about the system being built, so it gets no page.
3. `page`: a domain rule, decision, gotcha, entity or concept a later agent working on the repository needs. The default.
4. `todo`: work the session left undone, such as a bug found but not fixed or a test not written. No page of its own; a bug whose root cause the session found is a gotcha page and a todo.

You never apply a `guard` or `prompt` proposal, however small: a check or prompt changed without review changes every later run. File it in `omoikane/_review.md` and touch nothing else.

Write only what the session shows. Copy paths, versions, flags and error text exactly; when the session does not give one, leave it out rather than supply it. A preference the user stated goes on the page in the user's own words, quoted, with the turn.

Steps:

1. Read the session file in full. Frontmatter gives `session`, `part`, `turns`, `started`, `branch`; `## Working tree at capture` and `## Files edited` list the code it touched.
2. Read `omoikane/index.md`. Open every domain, decision, gotcha, entity and concept page whose `code:` paths or summary overlap the files this session touched or a rule the user stated.
3. Write `omoikane/wiki/sources/session-<YYYY-MM-DD>-<id8>.md` (append `-part<n>` when `part` is above 1) with the page contract, `type: source`, `dated` set to the `started` date. Body: what the session set out to do, what it changed, what it learned, in that order, each claim pointing at the turn it comes from (`turn 3`). Where the agent's own notes contradict each other across turns, record both under `## Contradictions` and append to `omoikane/_review.md`.
4. For each domain rule, decision and gotcha: create `omoikane/wiki/domain/<slug>.md`, `omoikane/wiki/decisions/<slug>.md` or `omoikane/wiki/gotchas/<slug>.md`, or update the existing page. Frontmatter: on a gotcha, `guard:` naming the check that catches the mistake in the repository today (`lint`, `test`, `hook`), or `none` when only the page does; a guard you propose in step 6 is `none` until it lands. `code:` listing the repository paths the page is about (they must exist; `wiki-lint.py` fails otherwise), `sources:` including this session page. Cite the session inline on every claim. A new decision that reverses an older one links both ways under `## History` on each page and leaves the older page in place; when the session gives no reason for the reversal, append to `omoikane/_review.md`.
   A domain page: `summary` is the rule itself in one line, since only the summary reaches the brief; `tags` start with `business-rule`, `design-system`, `convention` or `term`; `code:` only for paths the rule names. Body: the rule, the user's words quoted with the turn, where it applies. A `term` page holds one term: `summary` is its definition in one line, starting with the term (after `Disputed:` when disputed); the body also lists the words rejected for it, if the user rejected any. On every page you write, use the term as defined, never a rejected word, except in quotes, in that list and in code identifiers. When the user replaces an earlier rule, update the page and keep the old rule under `## History`. When the page you replace or dispute is one a rule in the `AGENTS.md` rules block points at, also file a `todo` naming that line: the block still states the old rule to every session, and only the human edits it. When a statement contradicts an earlier statement (a domain page, a source) without saying it replaces it, record both under `## Contradictions`, start `summary` with `Disputed:` so the brief does not present it as settled, and append to `omoikane/_review.md`; do not pick a winner. When only the code disagrees, the user may be stating the rule because the code breaks it: write the rule as stated and file a `todo` naming the code that breaks it. A statement cut by a `[... N chars cut]` marker gets no page: file a `todo` naming the turn. Link every page you create from the session page.
5. For each module, library, service or tool the session treats as central: update its entity page or create one. Recurring theme across three or more pages: concept page. Follow the ingest rules for citations and contradictions.
6. First read the `- routed` and `- removed` lines of `omoikane/log.md`. A slug with a `- removed (<kind>) <slug>` line and no `- routed` line for it below that was decided by the human, who deleted its bullet after applying or rejecting it. A lesson with the same mistake and the same fix as that slug's `routed` line is not filed again: log it in step 7 as `- skipped (decided) <the removed slug>`. When unsure it is the same lesson, file it. For each other `guard`, `prompt` and `todo` lesson, append to `omoikane/_review.md` under one heading `## [YYYY-MM-DD] distill | session <id8>`:

   `````
   - [ ] guard (<lint|test|hook>) <slug>: <the mistake it catches, one line> (session <id8>, turn <n>)
   ````diff
   <unified diff against the current file, 3 lines of context, paths as a/<path> and b/<path>>
   ````
   - [ ] prompt (<file>.md) <slug>: <what the prompt gets wrong, one line> (session <id8>, turn <n>)
   ````diff
   <diff>
   ````
   - todo <slug>: <the work left, one line> (session <id8>, turn <n>)
   `````

   The five-backtick fence only marks the template; do not write it. Write the diff fence with four backticks, at column 0, so a ``` inside the diff cannot close it and the diff lines copy straight into `git apply`. Read the target file before writing the diff; a diff that does not apply is worse than none. A guard you cannot write as a diff (a hook in another harness, a check in a tool you have not read) gets the bullet with a sentence saying where the check goes instead of the diff. The human approves by ticking `[x]`; that is not yours to do.
7. Append to `omoikane/log.md`: `## [YYYY-MM-DD] distill | session <id8>` followed by the pages created and updated, then one line per lesson filed in step 6: `- routed (<guard|prompt|todo>) <slug>: <lesson in one line> (turn <n>)`, then one line per candidate rejected by one of the five rules above or already decided (step 6): `- skipped (<rule|decided>) <slug>: <candidate in one line> (turn <n>)`. `<slug>` is the kebab-case slug the page would have had, built like a page filename, so a later pass groups the same candidate across sessions by it; `<n>` is the first turn where the candidate appears, one number. Candidates dropped by the `Skip:` list above get no line: they are not lessons.
8. Move the session file from `omoikane/raw/inbox/sessions/` to `omoikane/raw/sources/sessions/` with `git mv` when tracked, plain move otherwise. A scheduled run may not move files: when `git mv` is denied, do not try another way; leave the file, `wiki-ingest.ps1` moves it after the run. Keep the filename: `session-capture.py` reads it to avoid re-capturing turns already distilled.
9. Run `python omoikane/bin/wiki-index.py` then `python omoikane/bin/wiki-lint.py`. Fix every finding. In a scheduled run (`wiki-ingest.ps1`) skip this step: you have no shell, and lint runs after you and sends its findings back.

A session with nothing worth a page gets no source page: only the log entry (`## [YYYY-MM-DD] distill | session <id8> | nothing kept` with one line saying why, plus the `routed` and `skipped` lines), any `_review.md` entries from step 6, and the move in step 8. Report: pages created, pages updated, contradictions filed, proposals and todos filed, candidates skipped, in that order.
