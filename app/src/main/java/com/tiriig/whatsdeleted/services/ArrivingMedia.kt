package com.tiriig.whatsdeleted.services

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.BitmapDrawable
import android.os.Build
import android.provider.MediaStore
import android.service.notification.StatusBarNotification
import android.util.Log
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.hasMediaPermissionFor
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Captures arriving media synchronously on the notification path (which is
 * proven alive whenever a text message lands) instead of depending only on
 * the background watchers seeing the file later. Two sources, best first:
 * the fresh WhatsApp file from MediaStore (full-res photo, playable
 * video/audio), then the notification's own preview pixels (the only path
 * for stickers/GIFs, whose files live in WhatsApp private storage).
 */
@Singleton
class ArrivingMedia @Inject constructor(
    private val tempStore: TempMediaStore
) {
    companion object {
        private const val TAG = "ArrivingMedia"
        private const val LOOKUP_WINDOW_MS = 45_000L
    }

    /** Preview pixels straight from the notification. No storage permission needed. */
    fun thumbnailPath(sbn: StatusBarNotification, context: Context): String? {
        val bitmap = extractBitmap(sbn, context) ?: return null
        return try {
            tempStore.stageBitmap(bitmap)?.absolutePath
        } catch (e: Exception) {
            Log.w(TAG, "thumbnail stage failed: $e")
            null
        }
    }

    /** Fresh WhatsApp file from MediaStore. Null without permission or file. */
    fun storedCopyPath(context: Context, kind: PlaceholderKind): String? =
        storedCopyPaths(context, kind, max = 1).firstOrNull()

    /**
     * Newest [max] WhatsApp files of [kind] staged in one MediaStore scan.
     * One query per notification (not one per message line) keeps a burst of
     * photos/videos/audios fast; direct file copy first, stream fallback next.
     */
    fun storedCopyPaths(context: Context, kind: PlaceholderKind, max: Int): List<String> {
        if (kind == PlaceholderKind.STICKER || kind == PlaceholderKind.GIF) return emptyList()
        if (!context.hasMediaPermissionFor(kind)) return emptyList()
        if (max <= 0) return emptyList()
        val collection = when (kind) {
            PlaceholderKind.PHOTO -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            PlaceholderKind.VIDEO -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            PlaceholderKind.AUDIO -> MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
            else -> return emptyList()
        }
        return try {
            val sinceSec = (System.currentTimeMillis() - LOOKUP_WINDOW_MS) / 1000
            @Suppress("DEPRECATION")
            context.contentResolver.query(
                collection,
                arrayOf(
                    MediaStore.MediaColumns._ID,
                    MediaStore.MediaColumns.DATA,
                    MediaStore.MediaColumns.DISPLAY_NAME
                ),
                "${MediaStore.MediaColumns.DATE_ADDED} >= ? AND ${MediaStore.MediaColumns.DATA} LIKE ?",
                arrayOf(sinceSec.toString(), "%WhatsApp%"),
                "${MediaStore.MediaColumns.DATE_ADDED} DESC"
            )?.use { cursor ->
                val idCol = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID)
                val dataCol = cursor.getColumnIndex(MediaStore.MediaColumns.DATA)
                val nameCol = cursor.getColumnIndex(MediaStore.MediaColumns.DISPLAY_NAME)
                val out = ArrayList<String>(max)
                while (cursor.moveToNext() && out.size < max) {
                    val path = if (dataCol >= 0) cursor.getString(dataCol) else null
                    val file = path?.let { java.io.File(it) }
                    if (file == null || !MediaObserver.isMediaFile(file)) continue
                    // Fast path: direct file copy avoids a ContentResolver round-trip
                    // when the file is already readable; TempMediaStore dedups it.
                    val direct = try {
                        tempStore.stage(file)?.absolutePath
                    } catch (_: Exception) {
                        null
                    }
                    if (direct != null) {
                        out.add(direct)
                        continue
                    }
                    val itemUri = android.content.ContentUris.withAppendedId(
                        collection,
                        cursor.getLong(idCol)
                    )
                    val ext = (if (nameCol >= 0) cursor.getString(nameCol) else null)
                        ?.substringAfterLast('.', "")
                        .orEmpty()
                    val staged = try {
                        context.contentResolver.openInputStream(itemUri)
                            ?.use { input -> tempStore.stageStream(input, ext, sourceKey = path) }
                    } catch (_: Exception) {
                        null
                    }
                    if (staged != null) out.add(staged.absolutePath)
                }
                out
            } ?: emptyList()
        } catch (e: Exception) {
            Log.w(TAG, "MediaStore lookup failed: $e")
            emptyList()
        }
    }

    private fun extractBitmap(sbn: StatusBarNotification, context: Context): Bitmap? {
        return try {
            val extras = sbn.notification.extras ?: return null
            (extras.get("android.picture") as? Bitmap)
                ?: (extras.get("android.bigPicture") as? Bitmap)
                ?: (extras.get("android.largeIcon") as? Bitmap)
                ?: iconBitmap(sbn, context)
        } catch (e: Exception) {
            Log.w(TAG, "extractBitmap failed: $e")
            null
        }
    }

    private fun iconBitmap(sbn: StatusBarNotification, context: Context): Bitmap? {
        return try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return null
            val drawable = sbn.notification.getLargeIcon()?.loadDrawable(context) ?: return null
            when (drawable) {
                is BitmapDrawable -> drawable.bitmap
                else -> {
                    val w = drawable.intrinsicWidth.takeIf { it > 0 } ?: 192
                    val h = drawable.intrinsicHeight.takeIf { it > 0 } ?: 192
                    val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                    val canvas = Canvas(bmp)
                    drawable.setBounds(0, 0, w, h)
                    drawable.draw(canvas)
                    bmp
                }
            }
        } catch (_: Exception) {
            null
        }
    }
}
