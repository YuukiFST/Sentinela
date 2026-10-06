---
title: Repos midia apagada view-once
type: source
summary: Sete repos mostram copia antecipada util e view-once sem root inviavel
tags: [midia-apagada, view-once, pesquisa]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: []
---

# Repos midia apagada view-once

Research bears date 2026-10-06. Clones sit under `$env:TEMP/opencode/repo-research/`.
Scope covers deleted image, audio and video plus single-view media.

## Claims

- `TheBotBox/WhatsDelete` saves text from notifications. It reads `android.title` and `android.text` in `ChatService.kt:65-75`.
- Same app filters `FLAG_GROUP_SUMMARY` and `com.whatsapp`. It never detects delete and never copies media.
- `Dev4Mod/waenhancer` needs root plus LSPosed. It hooks revoke and view-once inside WhatsApp process.
- `waenhancer` cancels revoke in `AntiRevoke.kt:131-161`. It forces view-once flag to zero in `ViewOnce.kt:16-28`.
- `waenhancer` copies decrypted `fMessage.mediaFile` in `DownloadViewOnce.kt:104-123`. No code runs without Xposed.
- `tharinduxd0/whatsapp-view-once-bypass-chrome-extension` does not work. README states server-side protection since 2025-12-18.
- Old web bypass cleared `__x_isViewOnce` and IndexedDB in `script.js:97-134`. Server now sends only "Open on your phone".
- `pmrt/whatshidden` is archived and broken on current multidevice Web. It shows the useful pattern of download and decrypt at arrival.
- `whatshidden` injected Webpack hooks in `connect.js:81-104` and decrypted with HKDF in `crypto.js:32-93`.
- `JKc66/whats_recall` runs as linked device with Baileys. It unwraps `viewOnceMessage` variants in `utils.ts:11-41`.
- `whats_recall` downloads media at once in `media.ts:62-164`. It dedupes by `fileSha256` and marks deleted rows instead of erasing them.
- Same server rescues quoted view-once in `processor.ts:582-679`. It still needs QR pairing and a 24/7 host.
- `notamitgamer/WhatsApp-Logger-Self-Hosted-` logs mainly text. It drops media without caption and ignores revoke updates.
- `SecurityRonin/chat4n6` recovers deleted rows from offline images and backups. It reads `msgstore.db`, WAL, freelist and FTS.
- `chat4n6` needs root paths or backup keys. It has no live capture and no ephemeral media.

## Contradictions

- `waenhancer` proves on-device view-once works with Xposed. Web bypass proves client web bypass cannot work now. Both claims hold in separate scopes: process hook against browser script.
- `whats_recall` proves linked devices still receive view-once bytes. Web extension proves browsers no longer receive them. Both hold: Baileys channel differs from Web channel.
