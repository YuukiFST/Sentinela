package com.tiriig.whatsdeleted

import com.tiriig.whatsdeleted.utility.isDeletionNotice
import com.tiriig.whatsdeleted.utility.isValidTitle
import org.junit.Assert.assertEquals
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
}
