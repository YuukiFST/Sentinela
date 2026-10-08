package com.tiriig.whatsdeleted.services

import android.content.Context
import android.util.Log
import com.tiriig.whatsdeleted.utility.MediaKind
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.concurrent.atomic.AtomicLong
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Sentinela media folder: copies of WhatsApp media spotted by [MediaObserver]
 * or [MediaStoreWatcher], made the moment they appear on disk (WhatsApp
 * removes the original when the sender deletes the message). A copy is
 * linked to its message right away through `Chat.mediaPath`; copies with no
 * known sender stay "ownerless" until a deletion claims them.
 */
@Singleton
class TempMediaStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private const val TAG = "TempMediaStore"
        const val DIR_NAME = "sentinela_media"
        const val CLAIM_WINDOW_MS = 5L * 60 * 1000 // 5 min, matches "recent sender" rule
        private const val MAX_SEEN = 500

        // File-name stem of notification previews. A real file arriving later
        // replaces a preview link (see UserDao.getMessagesAwaitingMedia).
        const val PREVIEW_NAME = "notif"

        /** True for a notification preview copy, which a real file may replace. */
        fun isPreview(path: String): Boolean = "_$PREVIEW_NAME." in File(path).name
    }

    private val lock = Any()

    // Source path -> its copy (null while copying): both watchers and the
    // notification path report the same file, and a late reporter needs the copy.
    private val seenSources = LinkedHashMap<String, File?>()

    // Burst uniqueness: currentTimeMillis collides within one ms burst.
    private val nameCounter = AtomicLong(0)

    fun mediaDir(): File =
        File(context.getExternalFilesDir(null), DIR_NAME).apply { mkdirs() }

    /** Reserve [key] once; false when this source was already staged. Lock held briefly. */
    fun tryReserve(key: String): Boolean = synchronized(lock) {
        if (seenSources.containsKey(key)) return false
        seenSources[key] = null
        if (seenSources.size > MAX_SEEN) seenSources.remove(seenSources.keys.first())
        true
    }

    /** Store the finished copy of [key]; a failed copy drops the key so a retry can stage it. */
    private fun record(key: String, copy: File?) {
        synchronized(lock) {
            if (copy == null) seenSources.remove(key) else seenSources[key] = copy
        }
    }

    /** Copy already made of source [key] by any path, while it still exists. */
    fun copyOf(key: String): File? =
        synchronized(lock) { seenSources[key] }?.takeIf { it.isFile }

    private fun uniqueDest(safe: String): File =
        File(mediaDir(), "${System.currentTimeMillis()}_${System.nanoTime()}_${nameCounter.getAndIncrement()}_$safe")

    /** Copy [src] into the media dir; null if it was already copied or the copy failed. */
    fun stage(src: File): File? {
        if (!src.isFile) return null
        // Dedup reservation under a brief lock; the copy itself runs unlocked so
        // a burst of photos does not queue behind one large video.
        if (!tryReserve(src.absolutePath)) return null
        val copy = try {
            val safe = src.name.replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(80)
            val dest = uniqueDest(safe)
            src.copyTo(dest, overwrite = false)
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stage failed for ${src.path}: $e")
            null
        }
        record(src.absolutePath, copy)
        return copy
    }

    /** Persist notification preview pixels (photo/video/sticker/GIF thumbnails). */
    fun stageBitmap(bitmap: android.graphics.Bitmap): File? {
        // Unique dest per call, no shared state: runs unlocked for burst throughput.
        return try {
            val dest = uniqueDest("$PREVIEW_NAME.jpg")
            dest.outputStream().use { out ->
                if (!bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 85, out)) {
                    return null
                }
            }
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stageBitmap failed: $e")
            null
        }
    }

    /** Copy an open stream (e.g. a MediaStore row) into the media dir. */
    fun stageStream(
        input: java.io.InputStream,
        ext: String,
        sourceKey: String? = null,
        name: String = "store"
    ): File? {
        // Shared dedup with [stage] when the MediaStore row maps to a known path,
        // so the notification path and the watchers do not copy the same file twice.
        if (sourceKey != null && !tryReserve(sourceKey)) return null
        val copy = try {
            val safeExt = ext.replace(Regex("[^A-Za-z0-9]"), "").take(5).ifEmpty { "bin" }
            val dest = uniqueDest("$name.$safeExt")
            dest.outputStream().use { out -> input.copyTo(out, bufferSize = 256 * 1024) }
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stageStream failed: $e")
            null
        }
        if (sourceKey != null) record(sourceKey, copy)
        return copy
    }

    /**
     * Newest copy of type [kind] not linked to any message ([linked]) and staged
     * within [windowMs]; the type check keeps a deleted voice note from taking a photo.
     */
    fun claimOwnerless(linked: Set<String>, kind: MediaKind, windowMs: Long = CLAIM_WINDOW_MS): File? =
        synchronized(lock) {
            val since = System.currentTimeMillis() - windowMs
            mediaDir().listFiles()
                ?.filter { it.lastModified() >= since && it.absolutePath !in linked && MediaKind.of(it) == kind }
                ?.maxByOrNull { it.lastModified() }
        }

    fun delete(paths: Collection<String>) {
        synchronized(lock) {
            paths.forEach { File(it).delete() }
        }
    }

    /**
     * Delete copies older than [retentionCutoff], then enforce [maxBytes]
     * oldest-first. Copies in [keep] (media linked to stored messages, the whole
     * point of the app) are never deleted here.
     */
    fun cleanup(retentionCutoff: Long, maxBytes: Long, keep: Set<String>) {
        synchronized(lock) {
            try {
                val dir = mediaDir()
                dir.listFiles()?.forEach { f ->
                    if (f.absolutePath !in keep && f.lastModified() < retentionCutoff) f.delete()
                }
                var total = dir.listFiles()?.sumOf { it.length() } ?: 0L
                if (total <= maxBytes) return
                dir.listFiles()
                    ?.filter { it.absolutePath !in keep }
                    ?.sortedBy { it.lastModified() }
                    ?.forEach { f ->
                        if (total <= maxBytes) return
                        val size = f.length()
                        if (f.delete()) total -= size
                    }
            } catch (e: Exception) {
                Log.w(TAG, "cleanup failed: $e")
            }
        }
    }
}
