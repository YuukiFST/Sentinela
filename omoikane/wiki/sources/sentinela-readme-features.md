---
title: Sentinela README features
type: source
summary: Fork sem Firebase com copia antecipada de midia e switches por contato
tags: [sentinela, midia-apagada, bootstrap]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: []
---

# Sentinela README features

Source bears date 2026-10-06 in commit ed4740f. Bootstrap copied `README.md`.
Scope covers fork changes, media permission and honest limits.

## Claims

- Fork removes Firebase. It uses `applicationId dev.vulto.sentinela` and no `google-services.json`.
- Each contact has two switches in "Monitoramento por contato". Default is ON.
- Switch "Mensagens" OFF stops all saves for the contact.
- Switch "Midia" OFF stops media copy and delete alert. Text still saves and flags as deleted.
- Only contacts with changed switches have rows in the database.
- Long-press on a conversation deletes messages and saved media. "Excluir e ignorar" also turns "Mensagens" OFF.
- `MediaObserverService` uses two sources: recursive `FileObserver` on `WhatsApp/Media` and `MediaStoreWatcher` with `ContentObserver`.
- It watches legacy and `Android/media` paths, normal and Business. It ignores `Sent` folders.
- New file copies at once to `getExternalFilesDir/sentinela_media`.
- Copy links at once to the latest message of the sender in the last 5 min through `Chat.mediaPath`.
- Copy without recent message stays ownerless. It links only when a delete notice arrives in 5 min.
- Detail screen opens thumbnails and video or audio actions in the default device app.
- Delete detection matches Portuguese notices such as "Esta mensagem foi apagada".
- Cleanup runs once per day after save. It deletes messages older than N days (default 30) and media above the cap (default 500MB, oldest first). Media of deleted messages never leaves through cleanup.
- Media permission is optional and requested in setup. Without it only text backup works.
- Media copies only when WhatsApp downloads the file. Limited photo access on Android 14+ blocks copy.
- Observer runs as simple START_STICKY without foreground. System can kill it. NLService and MainActivity restart it.
- Attribution is heuristic. Simultaneous messages can link to the wrong sender.
- Silent chats give no notification. Their media stays ownerless.
- Renamed contacts create new conversations. User must set switches again.
