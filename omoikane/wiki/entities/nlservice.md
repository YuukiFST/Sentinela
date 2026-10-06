---
title: NLService
type: entity
summary: Listener que salva texto, detecta apagada e dispara alerta local
tags: [android, notificacao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-claude-architecture.md, wiki/sources/sentinela-git-history.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/NLService.kt, app/src/main/java/com/tiriig/whatsdeleted/utility/GeneralExtensions.kt]
---

# NLService

`NLService` extends `NotificationListenerService`. It saves text and flags deletes (source: [[sentinela-claude-architecture]]).

It parses `android.title`, `android.text` and `android.textLines`. It handles groups and digests line by line (source: [[sentinela-git-history]]).

It calls `flagLastMessageDeleted()` on localized notices. It claims ownerless media through `TempMediaStore` (source: [[sentinela-claude-architecture]]).

See [[deteccao-de-exclusao-por-notificacao]] for the flow. Obey [[monitoramento-por-contato]] before saving.
