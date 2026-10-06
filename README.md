# WhatsDeleted
**WhatsDeleted** recovers deleted messages from (**WhatsApp,Telegram and Signal**) by scanning your device notifications, You can also read your messages and chat anonymously.

### Screenshots

 <p align="center">
 <img src="/screenshots/one.png"/>

</p>

## Download :
[<img src="https://play.google.com/intl/en_us/badges/images/generic/en-play-badge.png"
alt="Get it on Google Play"
height="100">](https://play.google.com/store/apps/details?id=com.tiriig.whatsdeleted)


## Features :

-   Recover deleted **WhatsApp** messages
-   Recover deleted **WhatsApp Business** messages
-   Recover deleted **Telegram** messages
-   Recover deleted **Signal** messages
-   Read your messages and chat anonymously
-   ... more to come in the near future

## Target platforms :

API 21 or later

---

# Sentinela (fork)

Fork sem Firebase (`applicationId dev.vulto.sentinela`, sem `google-services.json`).

## O que mudou

- **Texto de todos, mídia só de permitidos**: todo texto de notificação continua salvo; a allowlist (menu "Monitoramento de mídia" na lista de conversas, switch por conversa, default ON) controla mídia e o alerta de "apagada". Opt-out: só existe linha no banco para quem foi desligado; contato desligado tem a cópia temporária descartada e não gera notificação (o texto segue marcado para consulta manual).
- **Observador de mídia**: `MediaObserverService` com `FileObserver` recursivo em `WhatsApp/Media` (legado e `Android/media/...`, normal e Business). Arquivo novo é copiado na hora para `getExternalFilesDir/sentinela_media` e atribuído ao remetente mais recente (mensagem nos últimos 5 min) ou fica sem dono. Ao detectar "apagada" de contato permitido, a cópia recente é vinculada à mensagem (`Chat.mediaPath`, visível no detalhe).
- **Limpeza automática**: `ChatRepository.runCleanupIfDue()` (1x/dia, após salvar) apaga mensagens com mais de N dias (default 30, `CleanupPrefs`) e arquivos órfãos/antigos além do teto (default 500MB, mais antigos primeiro).

## Permissões de mídia

Pedidas na tela de setup (botão "Permitir mídia", opcional). Sem elas, só o backup de texto funciona. Concessão manual: Configurações > Apps > Sentinela > Permissões > Fotos e vídeos (Android 13+) ou Armazenamento (Android 12-).

## Limitações honestas

- Atribuição de mídia é heurística (remetente mais recente em 5 min); pode vincular errado com mensagens simultâneas.
- Chat silenciado não gera notificação: sem texto salvo, a mídia fica sem dono e só vincula se for a cópia recente não atribuída a outro chat.
- Em Android 10+ com escopo de armazenamento, observar `/sdcard/WhatsApp/Media` pode não ver nada sem "Todas as mídias"/`MANAGE_EXTERNAL_STORAGE` (não solicitado); funciona melhor onde o WhatsApp ainda usa pastas legadas acessíveis.
- Serviço de observação é simples (START_STICKY, sem foreground): o sistema pode matá-lo; ele é reiniciado junto ao NLService/MainActivity.
- Renomear contato no WhatsApp cria uma "conversa" nova: remarque o switch na allowlist.
