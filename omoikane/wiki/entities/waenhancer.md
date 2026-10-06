---
title: Waenhancer
type: entity
summary: Modulo LSPosed com anti-revoke e download de view-once, apenas com root
tags: [xposed, view-once, referencia-externa]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# Waenhancer

`waenhancer` is an LSPosed module. It requires root and breaks on WhatsApp updates (source: [[repos-midia-apagada-view-once]]).

It cancels revoke and forces view-once flags to zero inside the process (source: [[repos-midia-apagada-view-once]]).

It copies decrypted `mediaFile` to a "View Once" folder (source: [[repos-midia-apagada-view-once]]).

Use it only as a spec. Sentinela without root cannot reuse its code (source: [[repos-midia-apagada-view-once]]).
