---
title: Monitoramento por contato
type: domain
summary: Respeite os dois switches por contato com default ON e sem linha para default
tags: [business-rule]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-readme-features.md, wiki/sources/sentinela-git-history.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/data/repository/ChatRepository.kt]
---

# Monitoramento por contato

Keep both switches ON by default. Create a database row only for changed contacts (source: [[sentinela-readme-features]]).

Obey "Mensagens" OFF by saving nothing for that contact (source: [[sentinela-readme-features]]).

Obey "Midia" OFF by copying no media and sending no delete alert. Keep text flagged for manual lookup (source: [[sentinela-readme-features]]).

Support "Excluir" and "Excluir e ignorar" from home long-press (source: [[sentinela-git-history]]).
