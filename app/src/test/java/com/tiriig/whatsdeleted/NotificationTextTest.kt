package com.tiriig.whatsdeleted

import com.tiriig.whatsdeleted.utility.isDeletionNotice
import com.tiriig.whatsdeleted.utility.arrivingKind
import com.tiriig.whatsdeleted.utility.isValidTitle
import com.tiriig.whatsdeleted.utility.newDigestLines
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.placeholderKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

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
            // View-once media never lands in the WhatsApp folders: any file
            // taken for it was an unrelated photo.
            "📷 Foto de visualização única",
            "🎥 Vídeo de visualização única",
            "View once photo",
        ).forEach { text ->
            assertNull(text, placeholderKind(text))
        }
    }

    // A late WhatsApp file is linked to the message whose placeholder equals the
    // file's kind. By extension alone a sticker (.webp) went to a photo and a GIF
    // (.mp4) to a video, and "ok" sent after "📷 Foto" took the photo.
    @Test
    fun arrivingFileMatchesItsPlaceholder() {
        val media = "/storage/emulated/0/Android/media/com.whatsapp/WhatsApp/Media"
        val business = "/storage/emulated/0/Android/media/com.whatsapp.w4b/WhatsApp Business/Media"
        val cases = mapOf(
            "$media/WhatsApp Images/IMG-20261007-WA0001.jpg" to "📷 Foto",
            "$media/WhatsApp Video/VID-20261007-WA0002.mp4" to "🎥 Vídeo",
            "$media/WhatsApp Voice Notes/202641/PTT-20261007-WA0003.opus" to "🎤 Mensagem de voz (0:05)",
            "$media/WhatsApp Stickers/STK-20261007-WA0004.webp" to "Maria: Figurinha",
            "$media/WhatsApp Animated Gifs/VID-20261007-WA0005.mp4" to "GIF",
            "$business/WhatsApp Business Stickers/STK-20261007-WA0006.webp" to "Sent a sticker",
        )
        cases.forEach { (path, message) ->
            assertEquals(path, placeholderKind(message), File(path).arrivingKind())
        }
        assertNull(placeholderKind("ok"))
        assertNull(File("$media/WhatsApp Documents/report.pdf").arrivingKind())
        // Not chat media: a profile photo once landed on a view-once message.
        assertNull(File("$media/WhatsApp Profile Photos/Maria.jpg").arrivingKind())
        assertNull(File("$media/WhatsApp Documents/scan.jpg").arrivingKind())
    }

    // A digest re-lists recent history on every update; deduping only against
    // the last stored text saved the older lines again.
    @Test
    fun digestKeepsOnlyNewLines() {
        assertEquals(listOf("c"), newDigestLines(listOf("x", "a", "b"), listOf("a", "b", "c")))
        assertEquals(listOf("d"), newDigestLines(listOf("a", "b", "c"), listOf("b", "c", "d")))
        assertEquals(emptyList<String>(), newDigestLines(listOf("a", "b", "c"), listOf("a", "b", "c")))
        assertEquals(listOf("a", "b"), newDigestLines(emptyList(), listOf("a", "b")))
        // The same text in a row is several messages once past the stored one.
        assertEquals(listOf("ok", "ok"), newDigestLines(listOf("oi", "ok"), listOf("oi", "ok", "ok", "ok")))
    }
}
