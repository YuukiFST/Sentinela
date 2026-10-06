---
title: WhatsDelete TheBotBox
type: entity
summary: App Android de texto via notificacao, molde parcial sem midia nem delete
tags: [android, referencia-externa]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# WhatsDelete TheBotBox

`WhatsDelete` saves WhatsApp text from notifications with Room (source: [[repos-midia-apagada-view-once]]).

It filters summaries and `com.whatsapp`. It keys chats by `android.title` (source: [[repos-midia-apagada-view-once]]).

It stores `isDeleted` always false. It never detects delete and never copies media (source: [[repos-midia-apagada-view-once]]).

Reuse only its text pipeline shape. Prefer Sentinela keys and delete flow (source: [[repos-midia-apagada-view-once]]).
