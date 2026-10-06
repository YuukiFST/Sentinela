---
title: Sentinela CLAUDE architecture
type: source
summary: Captura por NotificationListener com parse fragil e deteccao best-effort
tags: [sentinela, arquitetura, bootstrap]
created: 2026-10-06
updated: 2026-10-06
dated: 2026-10-06
sources: []
---

# Sentinela CLAUDE architecture

Source bears date 2026-10-06 in commit ed4740f. Bootstrap copied `CLAUDE.md`.
Scope covers capture flow, package layout, database, permissions and build.

## Claims

- `NLService` extends `NotificationListenerService`. It filters packages with `isValidApp()` in `utility/GeneralExtensions.kt`.
- It reads `android.title` as contact or group and `android.text` as body. No structured API exists.
- Group chat uses `GroupName: SenderName` in the title. Code strips `(N messages)` suffixes.
- Delete has no system event. App posts a new notice such as "This message was deleted".
- Text follows phone language. `String.isDeletionNotice()` matches localized notices. New language needs a row in `NotificationTextTest`.
- `NLService.flagLastMessageDeleted()` marks the latest stored message with `isDeleted = true`.
- `Notifications.notify()` posts a local alert. Tap opens the chat detail with `user`, `app` and `notificationDeleted`.
- `ChatRepository.saveMessage()` dedupes against the last stored message for the user. Bad user key breaks dedup and delete detection.
- Delete detection is best-effort. WhatsApp no longer reposts the notice for each delete.
- Manual fallback rules: user sees the gap in WhatsApp and reads the stored copy in Sentinela.
- Code lives in `com.tiriig.whatsdeleted`, Kotlin, single `app` module. Hilt wires all classes.
- `ChatRepository` alone talks to `UserDao`. ViewModels and services never call DAO directly.
- Navigation uses one Activity with two destinations: `chatListFragment` and `chatDetailFragment`.
- App draws edge to edge. New top containers need the same inset treatment.
- Room holds `Chat` and `AllowedContact`. Schema is version 6 with exported schemas.
- `MIGRATION_2_3` rebuilds tables by hand. New migrations follow one manual object per hard change.
- `BIND_NOTIFICATION_LISTENER_SERVICE` needs manual grant in system settings. Intro enforces it on the last slide.
- `POST_NOTIFICATIONS` on API 33+ is a soft ask from MainActivity. Store works without it.
- Build needs `google-services.json` in the fork upstream. Sentinela fork removes Firebase.
- `minSdk 23`, `targetSdk` and `compileSdk 36`.
- Branches are `main` for work and `production` for releases.
