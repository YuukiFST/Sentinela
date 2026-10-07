package com.tiriig.whatsdeleted.services

import android.content.ContentUris
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.provider.MediaStore
import android.service.notification.StatusBarNotification
import android.util.Log
import android.webkit.MimeTypeMap
import androidx.core.app.NotificationCompat
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.arrivingKind
import com.tiriig.whatsdeleted.utility.canReadWhatsAppFolders
import com.tiriig.whatsdeleted.utility.hasMediaPermissionFor
import com.tiriig.whatsdeleted.utility.whatsAppFolders
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Captures arriving media on the notification path (which is proven alive
 * whenever a text message lands) instead of depending only on the background
 * watchers seeing the file later. Two sources, best first: the fresh WhatsApp
 * file (MediaStore or its folder: full-res photo, playable video/audio,
 * sticker, GIF), then the notification's own preview while the file downloads.
 * The large icon is never used: it is the sender's avatar, not the media.
 */
@Singleton
class ArrivingMedia @Inject constructor(
    private val tempStore: TempMediaStore
) {
    companion object {
        private const val TAG = "ArrivingMedia"

        /** How far back a file may have landed before its notification was handled. */
        const val LOOKUP_WINDOW_MS = 45_000L

        // A file younger than this may still be downloading (see MediaStoreWatcher).
        private const val SETTLE_MS = 800L

        // "WhatsApp Images" in WhatsApp, "WhatsApp Business Images" in Business.
        private val FOLDER_PREFIXES = listOf("WhatsApp", "WhatsApp Business")
    }

    /**
     * Preview straight from the notification, shown until the real file lands
     * (it replaces the preview). No storage permission needed. None for audio:
     * any picture there is not the voice note.
     */
    fun thumbnailPath(sbn: StatusBarNotification, context: Context, kind: PlaceholderKind): String? {
        if (kind == PlaceholderKind.AUDIO) return null
        messageDataPath(sbn, context)?.let { return it }
        val bitmap = extractBitmap(sbn) ?: return null
        return try {
            tempStore.stageBitmap(bitmap)?.absolutePath
        } catch (e: Exception) {
            Log.w(TAG, "thumbnail stage failed: $e")
            null
        }
    }

    /**
     * Newest [max] WhatsApp files of [kind] added since [sinceMs], staged into
     * the media dir. Two sources merged: MediaStore (photo/video/audio, needs
     * the runtime permission) and a direct listing of the kind's folders
     * (stickers, GIFs and voice notes sit behind `.nomedia`, so this is their
     * only source; needs all-files access). Copies in [linked] already belong
     * to a message and are skipped, so a retry never gives one file to two.
     */
    fun storedCopyPaths(
        context: Context,
        kind: PlaceholderKind,
        max: Int,
        sinceMs: Long,
        linked: Set<String>
    ): List<String> {
        if (max <= 0) return emptyList()
        val now = System.currentTimeMillis()
        val candidates = (mediaStoreCandidates(context, kind, sinceMs) + folderCandidates(context, kind, sinceMs))
            .distinctBy { it.file.absolutePath }
            .filter { it.file.arrivingKind() == kind && MediaObserver.isMediaFile(it.file) }
            // Still downloading: its mtime keeps moving; the next retry takes it whole.
            .filter { now - it.file.lastModified() >= SETTLE_MS && it.file.length() > 0 }
            .sortedByDescending { it.file.lastModified() }
        val out = ArrayList<String>(max)
        for (candidate in candidates) {
            if (out.size >= max) break
            val copy = stageCandidate(context, candidate)?.absolutePath ?: continue
            if (copy in linked || copy in out) continue
            out.add(copy)
        }
        return out
    }

    /** A WhatsApp file seen for some kind, plus its MediaStore row when indexed. */
    private class Candidate(val file: File, val uri: Uri?)

    /**
     * Copy of [candidate]: one made earlier by any path (watchers or a previous
     * retry), else a direct file copy, else a stream through its MediaStore row.
     */
    private fun stageCandidate(context: Context, candidate: Candidate): File? {
        val key = candidate.file.absolutePath
        tempStore.copyOf(key)?.let { return it }
        val direct = try {
            tempStore.stage(candidate.file)
        } catch (_: Exception) {
            null
        }
        if (direct != null) return direct
        val uri = candidate.uri ?: return tempStore.copyOf(key)
        val streamed = try {
            context.contentResolver.openInputStream(uri)
                ?.use { input -> tempStore.stageStream(input, candidate.file.extension, sourceKey = key) }
        } catch (_: Exception) {
            null
        }
        return streamed ?: tempStore.copyOf(key)
    }

    private fun mediaStoreCandidates(context: Context, kind: PlaceholderKind, sinceMs: Long): List<Candidate> {
        if (!context.hasMediaPermissionFor(kind)) return emptyList()
        val collection = when (kind) {
            PlaceholderKind.PHOTO, PlaceholderKind.STICKER -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            PlaceholderKind.VIDEO, PlaceholderKind.GIF -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            PlaceholderKind.AUDIO -> MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        }
        return try {
            @Suppress("DEPRECATION") // DATA is still populated and readable on 29+.
            context.contentResolver.query(
                collection,
                arrayOf(MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DATA),
                "${MediaStore.MediaColumns.DATE_ADDED} >= ? AND ${MediaStore.MediaColumns.DATA} LIKE ?",
                arrayOf((sinceMs / 1000).toString(), "%WhatsApp%"),
                "${MediaStore.MediaColumns.DATE_ADDED} DESC"
            )?.use { cursor ->
                val idCol = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
                val dataCol = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATA)
                val out = ArrayList<Candidate>()
                while (cursor.moveToNext()) {
                    val path = cursor.getString(dataCol) ?: continue
                    out.add(Candidate(File(path), ContentUris.withAppendedId(collection, cursor.getLong(idCol))))
                }
                out
            } ?: emptyList()
        } catch (e: Exception) {
            Log.w(TAG, "MediaStore lookup failed: $e")
            emptyList()
        }
    }

    /**
     * Files modified since [sinceMs] in the kind's WhatsApp folders, one level
     * of sub-folders deep (voice notes are filed per week, "WhatsApp Voice
     * Notes/202641/"). Only sub-folders touched since then are opened.
     */
    private fun folderCandidates(context: Context, kind: PlaceholderKind, sinceMs: Long): List<Candidate> {
        if (!context.canReadWhatsAppFolders()) return emptyList()
        val out = ArrayList<Candidate>()
        try {
            for (root in MediaObserver.candidateRoots()) {
                for (prefix in FOLDER_PREFIXES) {
                    for (name in kind.whatsAppFolders()) {
                        File(root, "$prefix $name").listFiles()?.forEach { entry ->
                            if (entry.isFile) {
                                if (entry.lastModified() >= sinceMs) out.add(Candidate(entry, null))
                            } else if (entry.isDirectory && entry.lastModified() >= sinceMs) {
                                entry.listFiles()
                                    ?.filter { it.isFile && it.lastModified() >= sinceMs }
                                    ?.forEach { out.add(Candidate(it, null)) }
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "folder lookup failed: $e")
        }
        return out
    }

    /**
     * Inline media of the newest MessagingStyle message (`Message.setData`):
     * the picture/sticker preview WhatsApp shows in the shade. Newest only, so
     * an older photo in the digest never lands on a new message; keyed by URI
     * so a digest re-posting the same message does not stage it twice.
     */
    private fun messageDataPath(sbn: StatusBarNotification, context: Context): String? {
        val style = NotificationCompat.MessagingStyle
            .extractMessagingStyleFromNotification(sbn.notification) ?: return null
        val message = style.messages.lastOrNull() ?: return null
        val uri = message.dataUri ?: return null
        val ext = MimeTypeMap.getSingleton()
            .getExtensionFromMimeType(message.dataMimeType)
            ?: "jpg"
        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                tempStore.stageStream(input, ext, sourceKey = uri.toString(), name = TempMediaStore.PREVIEW_NAME)
            }?.absolutePath
        } catch (e: Exception) {
            // SecurityException when the sender app did not grant the URI to listeners.
            Log.w(TAG, "message data read failed: $e")
            null
        }
    }

    private fun extractBitmap(sbn: StatusBarNotification): Bitmap? {
        return try {
            val extras = sbn.notification.extras ?: return null
            (extras.get("android.picture") as? Bitmap)
                ?: (extras.get("android.bigPicture") as? Bitmap)
        } catch (e: Exception) {
            Log.w(TAG, "extractBitmap failed: $e")
            null
        }
    }
}
