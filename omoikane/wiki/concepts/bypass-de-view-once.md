---
title: Bypass de view-once
type: concept
summary: Compara Xposed, Baileys, Web e forense para midia de visualizacao unica
tags: [view-once, comparacao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# Bypass de view-once

Xposed hooks run inside WhatsApp. They read decrypted `mediaFile` and clear the view-once flag (source: [[repos-midia-apagada-view-once]]). See [[waenhancer]].

Baileys acts as a linked device. It unwraps `viewOnceMessage` variants and downloads before open (source: [[repos-midia-apagada-view-once]]). See [[whats-recall]].

Web scripts fail now. The server withholds bytes from browsers (source: [[repos-midia-apagada-view-once]]).

Forensics reads stored databases only. It never sees ephemeral bytes (source: [[repos-midia-apagada-view-once]]).

Text-only Android reference is [[whatsdelete-thebotbox]].

Sentinela without root has no channel today. See [[visualizacao-unica]] and [[sem-suporte-a-view-once-sem-root]].
