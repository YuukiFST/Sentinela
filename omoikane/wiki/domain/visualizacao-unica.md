---
title: Visualizacao unica
type: domain
summary: Nao prometa abrir midia de visualizacao unica sem root ou linked-device
tags: [business-rule]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# Visualizacao unica

Do not promise single-view image, audio or video without root or linked device (source: [[repos-midia-apagada-view-once]]).

On-device capture works only inside WhatsApp process through Xposed (source: [[repos-midia-apagada-view-once]]).

Linked-device archives still receive bytes when they download before open (source: [[repos-midia-apagada-view-once]]).

Web bypass is dead. Server sends only "Open on your phone" (source: [[repos-midia-apagada-view-once]]).

Forensics sees no ephemeral media. It reads only stored databases and backups (source: [[repos-midia-apagada-view-once]]).

Compare techniques in [[bypass-de-view-once]]. Enforce with [[sem-suporte-a-view-once-sem-root]].
