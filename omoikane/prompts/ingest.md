# Ingest one source

Task: integrate the source file given as argument into the wiki. Done means: source page written, every affected domain, entity and concept page updated, `omoikane/log.md` appended, source moved to `omoikane/raw/sources/`, `wiki-lint.py` clean.

Steps:

1. Read the source in full. If it references images under `omoikane/raw/assets/`, view each one after the text.
2. Read `omoikane/index.md` and open every existing page the source touches: same entities, same concepts, same claims.
3. Write `omoikane/wiki/sources/<slug>.md` with the page contract from `AGENTS.md`. Set `dated` to the date the source bears (commit date, publish date, report date), `unknown` when none is found; say in the body how you established it. Content: what the source says, the scope it claims (complete map, partial notes, snapshot of one date), its key claims with dates and numbers exact, what it adds beyond what the wiki already knows. Where the source contradicts itself, record both passages under `## Contradictions` on this page and append to `omoikane/_review.md`.
4. For each entity or concept in the source: update the existing page, or create one when the wiki has none and the source treats it as central. Cite the new source inline on every claim you add. Add a `## Contradictions` section where the source disagrees with a claim already on the page, and append the disagreement to `omoikane/_review.md`.
   - Omission is disagreement when the source claims completeness. A source that presents itself as the full list, the whole schema, or the thing to read instead of the code, and leaves out what another source asserts, contradicts that source. Record it as a contradiction, not as "not covered".
   - A rule the source sets for the system being built (a business rule, a design-system rule, an organisation convention) goes on a `domain` page under `omoikane/wiki/domain/`, as `omoikane/prompts/distill.md` step 4 describes, quoting the source with where it says so. One page per topic a later agent works on (a component, an area of the business), holding that topic's rules, with `summary` stating its main rule: the brief lists domain pages first, and one page per rule of a long guide would push every decision and gotcha out of it. Terms the source defines (a glossary, a "we call X ...") follow the same rule: one `term` page per topic, listing each term with its definition and the words rejected for it. A term the source pairs with a rejected word gets a `term` page of its own, as distill step 4 describes: that is the term an agent gets wrong.
5. Append to `omoikane/log.md`: `## [YYYY-MM-DD] ingest | <title>` followed by the list of pages created and updated.
6. Move the source file from `omoikane/raw/inbox/` to `omoikane/raw/sources/` with `git mv` when tracked, plain move otherwise. A scheduled run may not move files: when `git mv` is denied, do not try another way; leave the file, `wiki-ingest.ps1` moves it after the run.
7. Run `python omoikane/bin/wiki-index.py` then `python omoikane/bin/wiki-lint.py`. Fix every finding. In a scheduled run (`wiki-ingest.ps1`) skip this step: you have no shell, and lint runs after you and sends its findings back.

Report: pages created, pages updated, contradictions filed, in that order. Cite `file:line` for each contradiction.
