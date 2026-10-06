---
title: Dupla fonte FileObserver e MediaStore
type: decision
summary: Manter FileObserver e MediaStoreWatcher porque um cobre a falha do outro
tags: [midia-apagada, android]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/sentinela-git-history.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserver.kt, app/src/main/java/com/tiriig/whatsdeleted/services/MediaStoreWatcher.kt, app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserverService.kt]
---

# Dupla fonte FileObserver e MediaStore

Keep recursive `FileObserver` on `WhatsApp/Media` plus `MediaStoreWatcher` on MediaStore.

Reject `FileObserver` alone. It misses files of other apps on Android 11+ under FUSE (source: [[sentinela-git-history]]). See [[fileobserver-cego-no-android-11]].

Start both through `MediaObserverService` as START_STICKY. Restart it from `NLService` and `MainActivity` (source: [[sentinela-readme-features]]). See [[media-observer-service]].
