package com.tiriig.whatsdeleted.utility

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.core.content.FileProvider
import com.tiriig.whatsdeleted.R
import java.io.File

/** What a staged media copy is, decided by file extension (WhatsApp keeps them). */
enum class MediaKind(val extensions: Set<String>, val mimeFallback: String) {
    IMAGE(setOf("jpg", "jpeg", "png", "webp", "gif", "bmp"), "image/*"),
    VIDEO(setOf("mp4", "mkv", "avi", "mov", "3gp", "webm"), "video/*"),
    AUDIO(setOf("mp3", "m4a", "aac", "opus", "ogg", "amr", "wav", "flac"), "audio/*");

    companion object {
        fun of(file: File): MediaKind? {
            val ext = file.extension.lowercase()
            return entries.firstOrNull { ext in it.extensions }
        }
    }
}

fun File.mediaMimeType(): String {
    val ext = extension.lowercase()
    return MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext)
        ?: MediaKind.of(this)?.mimeFallback
        ?: "*/*"
}

/**
 * Opens a staged copy in whatever viewer/player the device has, through the
 * app's FileProvider (raw file:// URIs throw FileUriExposedException on 24+).
 * Example: `context.openMediaFile(File(chat.mediaPath))`
 */
fun Context.openMediaFile(file: File) {
    val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
    val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(uri, file.mediaMimeType())
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    try {
        startActivity(intent)
    } catch (_: ActivityNotFoundException) {
        Toast.makeText(this, R.string.media_no_viewer, Toast.LENGTH_SHORT).show()
    }
}

/** Copy plain text to the clipboard with a short confirmation. */
fun Context.copyText(text: String) {
    val cm = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
    cm.setPrimaryClip(android.content.ClipData.newPlainText("message", text))
    Toast.makeText(this, R.string.message_copied, Toast.LENGTH_SHORT).show()
}
