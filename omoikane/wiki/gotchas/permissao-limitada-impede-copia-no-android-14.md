---
title: Permissao limitada impede copia no Android 14
type: gotcha
summary: Acesso limitado a fotos no Android 14 bloqueia a copia de midia nova
tags: [android, permissao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/utility/MediaPermissions.kt]
guard: none
---

# Permissao limitada impede copia no Android 14

Limited photo access on Android 14+ blocks new media copies (source: [[sentinela-readme-features]]).

Ask full access in setup. Media works only with automatic WhatsApp download on (source: [[sentinela-readme-features]]).

Without permission only text backup runs. Show the banner again from the list (source: [[sentinela-readme-features]]).
