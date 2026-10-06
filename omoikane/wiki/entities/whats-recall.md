---
title: Whats recall
type: entity
summary: Arquivador Baileys cuja logica de download imediato guia o Sentinela
tags: [baileys, referencia-externa, midia-apagada]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: [wiki/sources/repos-midia-apagada-view-once.md]
---

# Whats recall

`whats_recall` archives as a linked device with Baileys. It needs pairing and a host (source: [[repos-midia-apagada-view-once]]).

It unwraps ephemeral and `viewOnceMessage` variants before typing (source: [[repos-midia-apagada-view-once]]).

It downloads media at once, dedupes by SHA-256 and marks deleted rows (source: [[repos-midia-apagada-view-once]]).

Copy its logic, not its runtime: eager download, wrapper list and soft delete (source: [[repos-midia-apagada-view-once]]).
