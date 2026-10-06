# Repos de midia apagada e view-once (pesquisa 2026-10-06)

Levantamento de 7 repositorios para o Sentinela (Android Kotlin, sem root, API 23-36).
Objetivo: (1) visualizar imagens, audios e videos apagados; (2) visualizar midia de visualizacao unica.
Clones rasos em $env:TEMP/opencode/repo-research/. Verificacao em codigo, com arquivo:linha.

## 1. TheBotBox/WhatsDelete — app Android Kotlin, texto via NotificationListener

- Faz: salva texto de notificacoes do WhatsApp. minSdk 21, MVVM + Room + RxJava + Koin.
- Tecnica: `WhatsDelete/app/src/main/java/bot/box/whatsdelete/ui/service/ChatService.kt:65` onNotificationPosted; `:69` descarta FLAG_GROUP_SUMMARY; `:71` filtra `sbn.packageName == com.whatsapp` (`Utils.kt:26`); `:72-75` le `android.title` e `android.text`; `:77-81` tenta EXTRA_LARGE_ICON como avatar; `:104-132` dedup ingenuo `chat.lastMessage == message` e insert via Room (`data/repository/RepositoryImpl.kt:15`, `data/database/dao/ChatDao.kt`); Manifest `:34-41` declara NotificationListenerService com BIND_NOTIFICATION_LISTENER_SERVICE.
- Nao tem: `data/database/entity/Conversation.kt:7-11` tem `isDeleted`, mas `ChatService.kt:121-125,138-142` sempre grava false. Nao ha onNotificationRemoved nem deteccao de "This message was deleted" (`Utils.kt:24` define MESSAGE_DELETED e nunca usa).
- Reaproveitavel: esqueleto do pipeline de texto, filtros, Room. Nada de midia (so avatar).
- Nao serve: sem FileObserver/MediaStore; chave por android.title quebra com grupos; perde chat silenciado.
- Estado: funciona para texto, com limites classicos de NotificationListener.

## 2. Dev4Mod/waenhancer — modulo LSPosed, root-only

- Faz: Anti Revoke, Disable View Once, Download View Once, Recover Deleted. Exige root + LSPosed (`docs/README.md:157-164`). Quebra a cada update do WhatsApp (ofuscacao via Unobfuscator/DexKit).
- Tecnica in-process: `AntiRevoke.kt:110,130` hooka `Unobfuscator.loadAntiRevokeMessageMethod`, em `before {:131-161}` retorna true/fake para cancelar revoke (grupo checa deviceJid, DM checa isFromMe). Persiste em DelMessageStore (`:95-104`), marca UI em bindRevokedMessageUI (`:210+`). `ViewOnce.kt:16-28` hooka loadViewOnceMethod; se `args[0]==1 && !isFromMe`, forca `args[0]=0`. `DownloadViewOnce.kt:25-56,58-94` hooka menu + onCreateOptionsMenu, checa `fMessage.isViewOnce (:33)`, pega `fMessage.mediaFile` e copia via downloadFile (`:104-123` para `Utils.getDestination("View Once")`). `FMessageWpp.kt:221-231` define `isViewOnce = mediaType in (82,42,43)`, `mediaFile (:186-209)` via reflexao ou MessageStore.getMediaFromID(rowId).
- Reaproveitavel: so como especificacao do que interceptar (revoke, flag view-once, mediaFile ja descriptografado). Nenhum codigo roda sem LSPosed.
- Nao serve sem root. Risco de ban (README avisa). GPL-3.0 forte. Acoplado a nomes ofuscados.
- Estado: unico que resolve view-once on-device, porque vive dentro do processo do WhatsApp.

## 3. tharinduxd0/whatsapp-view-once-bypass-chrome-extension — morto

- Estado: NAO FUNCIONA. README.md:9-13 (18/12/2025) declara NOT WORKING - Server-Side Protection.
- Tentativa historica: `script.js:97-112` WAWebCollections.Msg.on add, `msg.__x_isViewOnce=false`, get/set IndexedDB model-storage/message, `msg.downloadMedia({rmrReason:1})`. `script.js:115-134` mesmo carimbo no lastMessage. `injector.js:1-3` injeta no web.whatsapp.com. `manifest.json:14-19` MV3.
- Motivo: servidor retorna so "Open on your phone". Bytes nunca chegam ao browser.
- Reaproveitavel: nada para Android. Licao: nao gastar tempo com WebView/IndexedDB para view-once.

## 4. pmrt/whatshidden — arquivado/quebrado (Puppeteer + Web antigo)

- Estado: quebrado contra Web multidevice atual. README.md:3 avisa que precisa reversao nova.
- Tecnica (padrao instrutivo): `src/hook/connect.js:81-104` inject varre webpackJsonp, acha modulo com _events.alert_new_msg e da push. `src/container.js:451-456` _startMiddleman via page.evaluate; `:175-194` _onWAMessage, se isMedia, downloadAndDecrypt, loga por remetente (msg/logger.js:46-53). `src/msg/message.js:173-178` mapa ptt/image/chat/sticker. `Media.downloadAndDecrypt (:99-108)`, `src/crypto.js:32-93` WAMediaDownloader: HKDF(mediaKey) aes-256-cbc, strip 10 bytes MAC, salva em MEDIA_DIR.
- Reaproveitavel: padrao "baixar-e-descriptografar na chegada, antes do delete" e formato HKDF como referencia. Nada de codigo Android.
- Nao serve: servidor 24/7, ocupa sessao Web, nao ve conversa aberta no celular, sem view-once.

## 5. JKc66/whats_recall — melhor referencia de logica (servidor Baileys)

- Faz: arquivador self-host (Bun + Hono + SolidJS + SQLite WAL) como linked device via @whiskeysockets/baileys ^7.0.0-rc13. Funciona enquanto Baileys acompanha protocolo (`connection.ts:69-75` fallback pinado). Exige QR/pairing e maquina 24/7.
- Tecnica: `src/whatsapp/connection.ts:84-92` makeWASocket syncFullHistory; `:268-287` messages.upsert para processor.handleMessage; `:289-296` messages.update para handleMessageUpdate (revoke/edit). `src/whatsapp/utils.ts:11-41` normalizeMessage desembrulha ephemeralMessage/documentWithCaptionMessage/viewOnceMessage/viewOnceMessageV2/viewOnceMessageV2Extension (+ senderKeyDistributionMessage) e seta isViewOnce (tambem via inner.viewOnce `:34-36`). `src/whatsapp/processor.ts:415-446` resolve tipo, trata protocolMessage (revoke) e secretEncryptedMessage (edit com message_secret `:740-741,459-510`); `:359-413` registra stub view-once sem corpo; `:436-441,816-820` marca is_view_once=1. `src/whatsapp/media.ts:62-164` downloadMedia: resolve mediaObj nos wrappers (`:70-75`), checa fileLength, dedup por fileSha256 (`:88-99`), downloadMediaMessage buffer com reuploadRequest, fallback downloadContentFromMessage (`:115-123`), nomeia sha256[0..16] por subdir (images/videos/audio/stickers/documents). `processor.ts:147-185` handleRevoke marca deleted + broadcast; `:582-679` resgate de view-once citado (quoted com viewOnce e baixado `:713-736`); `:843-886` reencaminha view-once para o proprio chat.
- Reaproveitavel: logica pura portavel — lista de wrappers, deteccao isViewOnce, "baixar imediato + dedup SHA-256 + marcar deleted", resgate via quote. Desenho messages (manter original + is_deleted/is_view_once) para o Room do Sentinela.
- Nao serve: servidor, nao app on-device; ocupa linked-device; syncFullHistory + reenvio vistos como automacao.
- Estado: prova que linked-device ainda recebe bytes de view-once se baixar antes de abrir.

## 6. notamitgamer/WhatsApp-Logger-Self-Hosted- — Baileys minimalista, so texto

- Faz: backend Baileys ^6.6.0 para Firestore + viewer PWA. Linked-device passivo. README.md:35 admite text-focused.
- Tecnica: `src/whatsapp.js:38-44` makeWASocket syncFullHistory; `:46-78` QR/reconnect com backoff; `:82-105` contacts.upsert; `:107-156` messages.upsert so notify/append: extrai conversation/extendedTextMessage/imageMessage.caption/videoMessage.caption (`:117-122`), descarta sem texto (`:124` — audio/sticker/view-once sem caption nunca salvos), grava Chats/{jid}/Messages/{id}. Sem handler messages.update (revoke/edit ignorado), sem downloadMediaMessage.
- Reaproveitavel: keep-alive com backoff (`:60-64`), EXCLUDED_JIDS (src/config.js, README.md:100-125), regras Firestore deny-all. Pouco alem disso. whats_recall domina este em tudo.
- Estado: hello world Baileys; ruim como referencia de midia.

## 7. SecurityRonin/chat4n6 — forense offline

- Faz: CLI Rust forense (1066 testes) que recupera apagadas de imagem forense/backup, nao do aparelho ao vivo. Ativo e testado.
- Alvos (README.md:130-138): Android data/data/com.whatsapp/databases/msgstore.db (+ wa.db, WAL, journal, freelist, FTS), iOS ChatStorage.sqlite; .crypt14/.crypt15 com --key-file de /data/data/com.whatsapp/files/key.
- 8 camadas (README.md:67-80; crates/plugins/chat4n6-whatsapp/README.md:12-22): live B-tree, WAL replay/delta, freelist, FTS shadow, intra-page gaps, journal, carving com confidence + dedup SHA-256 + comandos sqlite3/xxd. Codigo: crates/plugins/chat4n6-whatsapp/src/{extractor.rs,schema.rs,decrypt.rs,cdn.rs,orphaned_media.rs}, engine em crates/chat4n6-sqlite-forensics/, saida HTML estatica (index.html/deleted.html/gallery.html/EXHIBIT-INDEX.csv).
- Reaproveitavel: quase nada em runtime. Conceito util: "apagado raramente some" vale para o proprio banco do Sentinela (WAL + soft-delete), nao para ler o banco do WhatsApp.
- Nao serve: sem root nao ha /data/data/com.whatsapp/; sem key nao abre crypt14/15; nada de tempo real, nada de view-once.

## Sintese para o Sentinela

- Texto apagado: WhatsDelete/ChatService.kt:65-164 e molde (trocar RxJava por coroutines/Flow, chavear por StatusBarNotification.getKey em vez de android.title, tratar onNotificationRemoved).
- Imagem/audio/video apagado: nenhum repo Android faz. Padrao correto e copiar bytes na hora via MediaStore/FileObserver nos dirs do WhatsApp + correlacionar por tempo/remetente, como eager download + SHA-256 dedup de whats_recall/media.ts:62-164. Sentinela ja faz isso com janela de 5 min.
- View-once on-device sem root: nenhuma tecnica reaproveitavel. Unicas que funcionam sao waenhancer (in-process/Xposed) e linked-device Baileys (whats_recall). Bypass Web morto (repo 3). Forense nao ve efemero (repo 7). Nao prometer o recurso sem uma dessas arquiteturas.
