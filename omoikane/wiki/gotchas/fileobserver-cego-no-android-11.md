---
title: FileObserver cego no Android 11
type: gotcha
summary: FileObserver perde arquivos alheios no Android 11, complemente com MediaStore
tags: [android, midia-apagada]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/sentinela-git-history.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserver.kt, app/src/main/java/com/tiriig/whatsdeleted/services/MediaStoreWatcher.kt]
guard: none
---

# FileObserver cego no Android 11

`FileObserver` misses files of other apps on Android 11+ under scoped storage.

Keep `MediaStoreWatcher` with `ContentObserver` beside it (source: [[sentinela-git-history]]).

Start both from `MediaObserverService`. Both start calls stay idempotent.
