---
title: Sentinela git history
type: source
summary: Fork adiciona allowlist, copia de midia e limpeza apos historia do WhatsDeleted
tags: [sentinela, historico, bootstrap]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: []
---

# Sentinela git history

Source bears date 2026-10-06. Bootstrap copied commits without merges, newest first.
Scope covers fork work on top of WhatsDeleted history.

## Claims

- Commit 5289cfc on 2026-10-06 saves `textLines` line by line. It dedupes reposts in a 10 s window.
- Commit ed4740f on 2026-10-06 adds delete from home, per-contact "Mensagens" switch and schema v6.
- Same commit links media at arrival, not at detection. It adds `MediaStoreWatcher`, skips `Sent`, exempts deleted media from cleanup and opens files through FileProvider.
- Same commit fixes pt-BR detection and pt-BR summary titles saved as contacts.
- Commit 423567e on 2026-10-05 forks Sentinela. It adds allowlist, media only for allowed contacts, auto cleanup and removes Firebase.
- Older commits document edge-to-edge setup and mark delete detection as best-effort.
- Older commits fix bundled notice handling, race duplicates, stale package names and dark theme.
- History before 2025-10 holds upstream WhatsDeleted releases, Room schema and SDK moves.
