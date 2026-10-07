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

/**
 * What kind of viewable content hides behind a notification placeholder
 * ("Sent a photo"). Null for plain text and for placeholders with no capture
 * path (calls, documents, locations). WhatsApp posts no preview for stickers
 * and GIFs, so those come only from their media folders (see [whatsAppFolders]),
 * which sit behind `.nomedia` and need all-files access.
 */
enum class PlaceholderKind { PHOTO, VIDEO, AUDIO, STICKER, GIF }

/**
 * WhatsApp media sub-folder names per kind; WhatsApp Business prefixes them
 * with "WhatsApp Business" ("WhatsApp Business Stickers").
 */
fun PlaceholderKind.whatsAppFolders(): List<String> = when (this) {
    PlaceholderKind.PHOTO -> listOf("Images")
    PlaceholderKind.VIDEO -> listOf("Video")
    PlaceholderKind.AUDIO -> listOf("Voice Notes", "Audio")
    PlaceholderKind.STICKER -> listOf("Stickers")
    PlaceholderKind.GIF -> listOf("Animated Gifs")
}

/**
 * Which placeholder a WhatsApp media file answers. The folder decides first:
 * a sticker is a .webp image and a GIF is an .mp4, so the extension alone would
 * hand them to a photo or video message. Null for non-media files.
 * Example: `File(".../WhatsApp Stickers/STK-1.webp").arrivingKind() == STICKER`
 */
fun File.arrivingKind(): PlaceholderKind? {
    val path = invariantSeparatorsPath
    if (" Stickers/" in path) return PlaceholderKind.STICKER
    if (" Animated Gifs/" in path) return PlaceholderKind.GIF
    return when (MediaKind.of(this)) {
        MediaKind.IMAGE -> PlaceholderKind.PHOTO
        MediaKind.VIDEO -> PlaceholderKind.VIDEO
        MediaKind.AUDIO -> PlaceholderKind.AUDIO
        null -> null
    }
}

private val callWords = listOf("call", "chamada", "ligação", "ligacao")

fun placeholderKind(text: String): PlaceholderKind? {
    val lower = text.trim().trimStart { !it.isLetterOrDigit() }.lowercase()
    if (callWords.any { it in lower }) return null
    if ("sticker" in lower || "figurinha" in lower) return PlaceholderKind.STICKER
    if ("gif" in lower) return PlaceholderKind.GIF
    if ("voice" in lower || "voz" in lower || "audio" in lower || "áudio" in lower ||
        "🎤" in lower
    ) return PlaceholderKind.AUDIO
    if ("photo" in lower || "foto" in lower || "image" in lower || "imagem" in lower ||
        "📷" in lower
    ) return PlaceholderKind.PHOTO
    if ("video" in lower || "vídeo" in lower || "📹" in lower || "🎥" in lower) {
        return PlaceholderKind.VIDEO
    }
    return null
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
