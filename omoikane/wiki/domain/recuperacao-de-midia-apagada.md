---
title: Recuperacao de midia apagada
type: domain
summary: Copie toda midia na chegada e vincule ao remetente recente em 5 minutos
tags: [business-rule]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/repos-midia-apagada-view-once.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserverService.kt]
---

# Recuperacao de midia apagada

Copy each new WhatsApp file at arrival. Link it at once to the latest message of the sender in the last 5 min (source: [[sentinela-readme-features]]).

Keep ownerless copies for 5 min. Claim one only when a delete notice arrives (source: [[sentinela-readme-features]]).

Use both `FileObserver` and `MediaStoreWatcher`. Ignore `Sent` folders (source: [[sentinela-readme-features]]).

Never delete media of deleted messages during cleanup (source: [[sentinela-readme-features]]).

Download eager plus SHA dedup is the proven pattern from linked-device archives (source: [[repos-midia-apagada-view-once]]).

Implement with [[media-observer-service]] under [[copia-antecipada-com-janela-de-5-min]] and [[dupla-fonte-fileobserver-e-mediastore]]. Watch [[permissao-limitada-impede-copia-no-android-14]].
