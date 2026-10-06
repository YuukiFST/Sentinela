---
title: Sem suporte a view-once sem root
type: decision
summary: Adiar view-once on-device e documentar linked-device como unico caminho viavel
tags: [view-once, escopo]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# Sem suporte a view-once sem root

Do not build on-device single-view capture now.

Reject Xposed hooks. They need root, break on each WhatsApp update and risk bans (source: [[repos-midia-apagada-view-once]]).

Reject Web interception. Server protection already blocks it (source: [[repos-midia-apagada-view-once]]).

Keep linked-device Baileys as a future path. It needs pairing and a 24/7 host (source: [[repos-midia-apagada-view-once]]).
