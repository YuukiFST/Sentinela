---
title: Media observer service
type: entity
summary: Servico que copia midia do WhatsApp na chegada via duas fontes
tags: [android, midia-apagada]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/sentinela-git-history.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserverService.kt, app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserver.kt, app/src/main/java/com/tiriig/whatsdeleted/services/MediaStoreWatcher.kt, app/src/main/java/com/tiriig/whatsdeleted/services/TempMediaStore.kt]
---

# Media observer service

`MediaObserverService` hosts `MediaObserver` and `MediaStoreWatcher`. It stages copies in `TempMediaStore` (source: [[sentinela-readme-features]]).

`MediaObserver` watches `WhatsApp/Media` recursively. `MediaStoreWatcher` observes MediaStore for Android 11+ (source: [[sentinela-git-history]]).

Service links each copy at once to the recent sender. Ownerless files wait for delete claims (source: [[sentinela-readme-features]]).

See [[recuperacao-de-midia-apagada]] and [[atribuicao-de-midia-por-janela-de-tempo]].
