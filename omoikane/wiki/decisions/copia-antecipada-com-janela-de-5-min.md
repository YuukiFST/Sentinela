---
title: Copia antecipada com janela de 5 min
type: decision
summary: Vincular na chegada evita perder midia quando o aviso chega tarde ou nunca
tags: [midia-apagada, atribuicao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/sentinela-git-history.md, wiki/sources/repos-midia-apagada-view-once.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/MediaObserverService.kt, app/src/main/java/com/tiriig/whatsdeleted/services/NLService.kt]
---

# Copia antecipada com janela de 5 min

Link media at arrival to the latest sender message in 5 min.

Reject link at delete time only. Old code linked only when notice arrived and lost late deletes (source: [[sentinela-git-history]]).

Accept wrong links under simultaneous messages. Late or missing notices cost more than wrong attribution (source: [[sentinela-readme-features]]).

Mirror eager download from `whats_recall` (source: [[repos-midia-apagada-view-once]]).
