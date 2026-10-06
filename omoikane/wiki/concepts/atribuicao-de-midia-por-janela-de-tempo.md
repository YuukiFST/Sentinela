---
title: Atribuicao de midia por janela de tempo
type: concept
summary: Sem id comum, o remetente mais recente em 5 min recebe a copia da midia
tags: [midia-apagada, heuristica]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserverService.kt, app/src/main/java/com/tiriig/whatsdeleted/services/TempMediaStore.kt]
---

# Atribuicao de midia por janela de tempo

No shared id links notification text and media file. System uses latest sender in 5 min (source: [[sentinela-readme-features]]).

Ownerless copies wait for a delete notice. Claim uses the same 5 min window (source: [[sentinela-readme-features]]).

Silent chats break the link. No notification means no recent sender (source: [[sentinela-readme-features]]).

Simultaneous senders can mislink. The window trades precision for survival.
