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

- **Dois switches por contato**: menu "Monitoramento por contato" na lista de conversas, default ON. "Mensagens" desligado ignora o contato (nada é salvo). "Mídia" desligado não copia mídia nem alerta quando ele apaga mensagem; o texto segue salvo e marcado como apagado para consulta manual. Opt-out: só existe linha no banco para quem mudou algum switch.
- **Excluir conversa**: toque e segure na conversa da tela inicial. "Excluir" apaga mensagens e mídias salvas (a conversa volta se o contato mandar mensagem de novo); "Excluir e ignorar" também desliga "Mensagens" desse contato.
- **Observador de mídia**: `MediaObserverService` usa duas fontes: `FileObserver` recursivo em `WhatsApp/Media` (legado e `Android/media/...`, normal e Business) e `MediaStoreWatcher` (`ContentObserver` no MediaStore, que funciona no Android 11+, onde o `FileObserver` pode não ver arquivos de outros apps). Pastas `Sent` são ignoradas. Arquivo novo é copiado na hora para `getExternalFilesDir/sentinela_media` e vinculado já à mensagem mais recente do remetente (últimos 5 min, `Chat.mediaPath`), então a mídia fica visível mesmo se a exclusão não for detectada ou acontecer horas depois. Sem mensagem recente, a cópia fica sem dono e só é vinculada se um "apagada" chegar em até 5 min.
- **Ver mídia**: no detalhe da conversa, toque na miniatura (foto/vídeo) ou em "Abrir vídeo"/"Ouvir áudio" para abrir no app padrão do aparelho.
- **Detecção de "apagada" em português**: reconhece "Esta mensagem foi apagada" (e variantes), não só o texto em inglês.
- **Contatos ignorados**: menu "Contatos ignorados" na lista de conversas mostra só quem foi ignorado; ligue "Mensagens" para voltar a salvar. Após "Excluir e ignorar", um aviso oferece "Desfazer".
- **Favoritos**: toque e segure numa mensagem para copiar ou favoritar. Mensagem favorita (e sua mídia) não é apagada por "Excluir" nem pela limpeza automática.
- **Sem mensagens repetidas**: cada mensagem é salva com o horário de envio que o app de mensagens informa na notificação, então uma notificação repostada não duplica o que já foi salvo.
- **Limpeza automática**: `ChatRepository.runCleanupIfDue()` (1x/dia, após salvar) apaga mensagens com mais de N dias (default 30, `CleanupPrefs`) e mídias antigas além do teto (default 500MB, mais antigas primeiro). Mídia de mensagem apagada nunca é removida pela limpeza.

## Permissões de mídia

Pedidas na tela de setup (botão "Permitir mídia", opcional). Sem elas, só o backup de texto funciona. Concessão manual: Configurações > Apps > Sentinela > Permissões > Fotos e vídeos (Android 13+) ou Armazenamento (Android 12-).

## Limitações honestas

- Atribuição de mídia é heurística (remetente mais recente em 5 min); pode vincular errado com mensagens simultâneas.
- Foto, vídeo e áudio de visualização única não são salvos: o WhatsApp não grava esses arquivos nas pastas de mídia.
- Chat silenciado não gera notificação: sem texto salvo, a mídia fica sem dono e só vincula se for a cópia recente não atribuída a outro chat.
- Mídia só é copiada se o WhatsApp baixar o arquivo (download automático ligado para o tipo de mídia e a rede atual). No Android 14+, escolher "Permitir acesso limitado" nas permissões de fotos/vídeos impede a cópia: conceda acesso a todas.
- Serviço de observação é simples (START_STICKY, sem foreground): o sistema pode matá-lo; ele é reiniciado junto ao NLService/MainActivity.
- Renomear contato no WhatsApp cria uma "conversa" nova: remarque o switch na allowlist.
