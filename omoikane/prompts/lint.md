# Semantic health check

Task: find what `omoikane/bin/wiki-lint.py` cannot: wrong or stale meaning, not broken structure. Done means every finding is written to `omoikane/_review.md` with `file:line` and the log has an entry. You change no wiki page in this pass.

Check, in order:

1. Contradictions: two pages asserting incompatible facts without a `## Contradictions` section. A source that claims completeness and omits what another source asserts counts.
2. Stale claims: a page cites a source whose `dated` is older than another source in `omoikane/wiki/sources/` that supersedes it.
   Also run `python omoikane/bin/wiki-lint.py`. Each `warning:` line about a `code:` path names a page whose code changed after its `updated` date. Read the page and the current code, and file a finding only when a claim no longer holds.
3. Unguarded gotchas: each `wiki-lint.py` `warning:` containing ``still has `guard: none` ``. Skip a gotcha whose log already has the exact line `- unguarded <slug>` or `- removed (guard) <slug>`: filed before, whether the human applied or rejected it. Otherwise propose the guard in the format of `omoikane/prompts/distill.md` step 6, with its diff, ending in `(lint YYYY-MM-DD)` where distill writes the session: `- [ ] guard (test) <slug>: <the mistake it catches> (lint YYYY-MM-DD)`. When no check can catch the mistake, file `- <file>:<line> <slug>: no check can catch this, because <reason>` instead.
4. Missing pages: an entity or concept named on three or more pages with no page of its own.
5. Thin hubs: a page with many inbound links and under ten lines of content.
6. Gaps: questions the wiki raises but no source answers. Name the source type that would close each gap.

Write findings to `omoikane/_review.md` under `## [YYYY-MM-DD] lint`, one bullet per finding, `file:line` first except the guard proposals of check 3. Append `## [YYYY-MM-DD] lint | <n> findings` to `omoikane/log.md`, with one line `- unguarded <slug>` per gotcha filed in check 3.
