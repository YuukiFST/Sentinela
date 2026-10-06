---
title: Aviso de apagada nem sempre chega
type: gotcha
summary: WhatsApp omite o aviso de apagada, confie na copia previa e na consulta manual
tags: [notificacao, exclusao]
created: 2026-10-06
updated: 2026-10-06
sources: [wiki/sources/sentinela-claude-architecture.md]
code: [app/src/main/java/com/tiriig/whatsdeleted/services/NLService.kt]
guard: none
---

# Aviso de apagada nem sempre chega

WhatsApp often skips the delete notice. Detection cannot promise each delete (source: [[sentinela-claude-architecture]]).

Keep the original copy from the first notification. User finds gaps by manual lookup (source: [[sentinela-claude-architecture]]).

Do not remove `flagLastMessageDeleted()`. It stays free when it works.
