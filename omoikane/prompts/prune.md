# Prune the wiki

Task: find the pages that cost more than they give, mark them for the human, and merge duplicates into the stronger page. Done means: every finding applied as below, `omoikane/log.md` appended, `wiki-lint.py` clean, nothing committed. You never delete a page or a file: the human reads the git diff and deletes what the marks point at.

A page earns its place when a later agent would get something wrong without it and the mistake comes up often or costs real work. Findings, one per page:

- `stale`: a claim no longer holds. The current code says otherwise (a `wiki-lint.py` `warning:` names the page, or its `code:` paths read differently now), or a newer source supersedes the one the page cites.
- `redundant`: another page says the same thing: one entity under two slugs, a gotcha restating a decision, two sessions writing one lesson twice.
- `low-value`: a later agent would get it right without the page: it restates the code, the prompt or `AGENTS.md`, or records a one-line choice.

Not findings: source pages (the record of what was ingested; claims cite them); a page a rule in the `AGENTS.md` rules block points at, which restates that rule by design (when it is redundant with another page, file a `todo` in `omoikane/_review.md` to repoint the rule instead); an older decision linked under `## History` from the decision that reversed it, which `omoikane/prompts/distill.md` step 4 keeps; a page with a `## Contradictions` section, whose two sides wait for the human; `stale` on a domain page that no later statement or source replaced, even when the code disagrees (the code may be what breaks the rule; two domain pages holding one rule are still `redundant`); a page whose only flaw is style; a page already marked.

Steps:

1. Audit, changing nothing. Read `omoikane/index.md`, run `python omoikane/bin/wiki-lint.py`, and open every page. For each candidate write down the mark, the evidence (`file:line` on the page and on the code, source or page that shows it) and, for `redundant`, which page is stronger: more citations, more inbound links, the more precise title.
2. Gate. Fewer than 3 findings: stop here. Change no file, not even the log, and report the findings you have with their evidence. Pruning is worth a diff for the human to read only when there are several.
3. Merge each `redundant` pair. Copy every claim of the weaker page that the stronger one lacks, with its citation, into the stronger page; a claim that contradicts the stronger page goes under its `## Contradictions` instead, with an entry in `omoikane/_review.md`, as `AGENTS.md` requires. Union `sources:`, `code:` and `tags:` and set `updated` on the stronger page. On every other page, repoint `[[weaker]]` wikilinks to `[[stronger]]` and `sources:` entries naming the weaker page to the stronger one. Append `- Merged from [[weaker]] (prune YYYY-MM-DD).` to the stronger page's `## History`, creating the section if absent; that link keeps the weaker page reachable until the human deletes it. The weaker page itself changes only as step 4 says.
4. Mark each finding: add `prune: <stale|redundant|low-value>` to the page's frontmatter and, as the first body line, `> Pruned YYYY-MM-DD: <the evidence in one sentence>.` On a merged page the sentence names the stronger page. Change nothing else on a marked page.
5. Append to `omoikane/log.md`: `## [YYYY-MM-DD] prune | <n> findings`, then `- marked (<mark>) <slug>: <evidence in one line>` per page and `- merged <weaker> into <stronger>` per pair.
6. Run `python omoikane/bin/wiki-index.py` then `python omoikane/bin/wiki-lint.py`. Fix every finding.

Report: pages marked by mark, pairs merged, and every path you changed, in that order.
