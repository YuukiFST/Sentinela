package com.tiriig.whatsdeleted

import com.tiriig.whatsdeleted.utility.isDeletionNotice
import com.tiriig.whatsdeleted.utility.isValidTitle
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.placeholderKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

// The deletion notice follows the phone's language; matching only English
// meant a pt-BR phone never flagged a deleted message.
class NotificationTextTest {

    @Test
    fun deletionNotice() {
        val cases = mapOf(
            "This message was deleted" to true,
            "This message was deleted." to true,
            "Esta mensagem foi apagada" to true,
            "Esta mensagem foi apagada." to true,
            "🚫 Esta mensagem foi apagada" to true,
            "Essa mensagem foi apagada" to true,
            "Esta mensagem foi eliminada" to true,
            "Se eliminó este mensaje" to true,
            "Apaguei a mensagem errada" to false,
            "📷 Foto" to false,
        )
        cases.forEach { (text, expected) ->
            assertEquals(text, expected, text.isDeletionNotice())
        }
    }

    @Test
    fun summaryTitleIsNotAContact() {
        val cases = mapOf(
            "12 new messages" to false,
            "3 messages" to false,
            "12 novas mensagens" to false,
            "2 mensagens novas" to false,
            "1 nova mensagem" to false,
            "Maria" to true,
        )
        cases.forEach { (title, expected) ->
            assertEquals(title, expected, title.isValidTitle())
        }
    }

    @Test
    fun mediaPlaceholderKind() {
        val cases = mapOf(
            "Sent a photo" to PlaceholderKind.PHOTO,
            "\uD83D\uDCF7 Foto" to PlaceholderKind.PHOTO,
            "Sent a video" to PlaceholderKind.VIDEO,
            "\uD83C\uDFA5 Vídeo" to PlaceholderKind.VIDEO,
            "Voice message (0:02)" to PlaceholderKind.AUDIO,
            "\uD83C\uDFA4 Mensagem de voz" to PlaceholderKind.AUDIO,
            "Sent a sticker" to PlaceholderKind.STICKER,
            "Figurinha" to PlaceholderKind.STICKER,
            "GIF" to PlaceholderKind.GIF,
        )
        cases.forEach { (text, expected) ->
            assertEquals(text, expected, placeholderKind(text))
        }
        listOf(
            "Demoro",
            "https://example.com",
            "Video call",
            "Voice call",
            "This message was deleted",
            "Location",
        ).forEach { text ->
            assertNull(text, placeholderKind(text))
        }
    }
}
