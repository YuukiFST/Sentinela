---
title: Deteccao de exclusao por notificacao
type: concept
summary: Exclusao nao e evento, e nova notificacao com texto localizado best-effort
tags: [notificacao, exclusao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-claude-architecture.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/NLService.kt, app/src/main/java/com/tiriig/whatsdeleted/utility/GeneralExtensions.kt]
---

# Deteccao de exclusao por notificacao

Deletion has no system event. The app posts a new notice for the same chat (source: [[sentinela-claude-architecture]]).

`isDeletionNotice()` matches localized texts and strips icons and periods (source: [[sentinela-claude-architecture]]).

`flagLastMessageDeleted()` marks the latest stored row instead of saving the notice (source: [[sentinela-claude-architecture]]). Implemented in [[nlservice]].

Detection is best-effort. WhatsApp often skips the notice now. Manual lookup remains the fallback (source: [[sentinela-claude-architecture]]). See [[aviso-de-apagada-nem-sempre-chega]].
