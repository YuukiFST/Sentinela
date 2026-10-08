package com.tiriig.whatsdeleted.utility

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.ImageView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.bumptech.glide.Glide
import com.bumptech.glide.load.resource.bitmap.CircleCrop
import com.google.android.material.chip.Chip
import com.tiriig.whatsdeleted.R


// WhatsApp bundles unread messages from several chats under one summary
// notification titled e.g. "12 new messages" / "12 novas mensagens" - that's not a real contact.
private val messageCountTitle = Regex(
    """^\d+\s+((new\s+)?messages?|(novas?\s+)?mensage(m|ns)(\s+novas?)?)$""",
    RegexOption.IGNORE_CASE
)

fun String.isValidTitle(): Boolean {
    if (messageCountTitle.matches(this)) return false

    return when (this) {
        "" -> false
        "WhatsApp" -> false
        "Telegram" -> false
        "DiscussBot" -> false
        "Checking for messages…" -> false
        "Signal" -> false
        "Calling…" -> false
        "Ringing…" -> false
        "Deleting messages…" -> false
        "Ongoing voice call" -> false
        "WhatsApp Web" -> false
        "Finished backup" -> false
        "Backup in progress" -> false
        "Backup paused" -> false
        "Restoring media" -> false
        "Checking for new messages" -> false
        "WhatsApp Web is currently active" -> false
        "Tap for more info" -> false
        "Waiting for Wi-Fi" -> false
        else -> true
    }
}

// WhatsApp/Telegram replace the notification body with this text once the
// original message is deleted, Signal does the same with a trailing period.
// The text follows the phone's language: a pt-BR phone never shows the English one.
private val deletionNotices = setOf(
    "this message was deleted",
    "esta mensagem foi apagada",
    "essa mensagem foi apagada",
    "esta mensagem foi eliminada",
    "se eliminó este mensaje",
    "este mensaje fue eliminado"
)

fun String.isDeletionNotice(): Boolean {
    val normalized = trim()
        .trimStart { !it.isLetter() } // WhatsApp may prefix an icon
        .trimEnd('.')
        .lowercase()
    return normalized in deletionNotices
}

/**
 * Lines of a re-posted digest ([digest], oldest first) not stored yet. A digest
 * re-lists recent history under one new timestamp, so its overlap is found by
 * aligning the newest end of [storedTail] (the chat's last texts, oldest first)
 * with the digest; the lines after the latest alignment are new.
 * Example: `newDigestLines(listOf("a", "b"), listOf("a", "b", "c")) == listOf("c")`
 */
fun newDigestLines(storedTail: List<String>, digest: List<String>): List<String> {
    if (storedTail.isEmpty()) return digest
    for (end in digest.indices.reversed()) {
        val n = minOf(end + 1, storedTail.size)
        if (digest.subList(end + 1 - n, end + 1) == storedTail.takeLast(n)) return digest.drop(end + 1)
    }
    return digest
}

fun String.isValidApp(): Boolean {
    return when (this) {
        "com.whatsapp" -> true
        "com.whatsapp.w4b" -> true
        "org.thoughtcrime.securesms" -> true
        "org.telegram.messenger" -> true
        else -> false
    }
}


fun String.name(): String {
    return when (this) {
        "com.whatsapp" -> "WhatsApp"
        "com.whatsapp.w4b" -> "WhatsApp business"
        "org.thoughtcrime.securesms" -> "Signal"
        "org.telegram.messenger" -> "Telegram"
        else -> "Undefined"
    }
}

fun View.hide() {
    visibility = View.GONE
}

fun View.show() {
    visibility = View.VISIBLE
}


//fun String.fromJson(): List<Chat?>? {
//    val listType = object : TypeToken<List<Chat?>?>() {}.type
//    return Gson().fromJson<List<Chat?>>(this, listType)
//}

fun ImageView.loadImage(url: Int) {
    Glide.with(this)
        .load(url)
        .placeholder(R.drawable.chat_user)
        .transform(CircleCrop())
        .into(this)
}

fun Fragment.toast(message: String) {
    Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show()
}

fun <T> Activity.startActivity(activity: Class<T>) {
    startActivity(Intent(this, activity))
    overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
    finish()
}

fun Context.finishedIntro() {
    val editor = this.getSharedPreferences("DATA_STORE", Context.MODE_PRIVATE).edit()
    editor.putBoolean("finishedIntro", true)
    editor.apply()
}

fun Context.isFinishedIntro(): Boolean {
    val sharedPref = this.getSharedPreferences("DATA_STORE", Context.MODE_PRIVATE)
    return sharedPref.getBoolean("finishedIntro", false)
}

fun Chip.changeBackgroundColor(app: String?) {
    this.show()
    when (app) {
        "com.whatsapp" -> setChipBackgroundColorResource(R.color.whatsapp)
        "com.whatsapp.w4b" -> setChipBackgroundColorResource(R.color.whatsapp_business)
        "org.thoughtcrime.securesms" -> setChipBackgroundColorResource(R.color.signal)
        "org.telegram.messenger" -> setChipBackgroundColorResource(R.color.telegram)
        else -> this.hide()
    }
}