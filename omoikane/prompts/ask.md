# Answer a question from the wiki

Task: answer the question given as argument using wiki pages, then file the answer so it compounds.

Steps:

1. Read `omoikane/index.md`. Pick every page whose summary bears on the question. Read them.
2. If the wiki lacks what the question needs, search the history the remote already holds before you give up, never local commits: `git log origin/main --grep=<word>` and `git log origin/main -S <identifier>` for the commits that state why, `git log origin/main --follow -- <path>` and `git blame -L <start>,<end> origin/main -- <path>` for the code the question names, `gh pr view <number> --json title,body` for a PR those commits name. When the history answers it, write what you found to `omoikane/raw/inbox/<YYYY-MM-DD>-history-<slug>.md`: the question, then each commit as short SHA, date and message, each PR as number, title and the passage that answers. Copy no author name, email, `*-by:` trailer or secret: what the wiki holds is pushed. Ingest that file with `omoikane/prompts/ingest.md`, then answer from the pages it wrote. In a scheduled run (`wiki-ingest.ps1`) you have no shell: skip the search.
   When neither holds the answer, say which pages you read, which searches you ran and what is missing, and suggest which source to add. Stop there; do not fill the gap from memory.
3. Write the answer with an inline `[[slug]]` citation on every claim. A reason a commit or PR does not state in words is your inference: say so. When the answer describes current state, open it with a cutoff line, "as of YYYY-MM-DD", using the `dated` of the newest source it rests on.
4. File it as `omoikane/wiki/queries/<YYYY-MM-DD>-<slug>.md` using the page contract, `type: query`, `sources:` listing every page cited.
5. Append to `omoikane/log.md`: `## [YYYY-MM-DD] query | <question>`.
6. Run `python omoikane/bin/wiki-index.py` then `python omoikane/bin/wiki-lint.py`. In a scheduled run (`wiki-ingest.ps1`) skip this step: you have no shell, and lint runs after you and sends its findings back.

Output: the answer, then the path of the filed page.
