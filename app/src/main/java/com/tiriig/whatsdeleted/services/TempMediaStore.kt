package com.tiriig.whatsdeleted.services

import android.content.Context
import android.util.Log
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
    }

    private val lock = Any()

    // Source paths already copied: both watchers report the same file.
    private val seenSources = LinkedHashSet<String>()

    // Burst uniqueness: currentTimeMillis collides within one ms burst.
    private val nameCounter = AtomicLong(0)

    fun mediaDir(): File =
        File(context.getExternalFilesDir(null), DIR_NAME).apply { mkdirs() }

    /** Reserve [key] once; false when this source was already staged. Lock held briefly. */
    fun tryReserve(key: String): Boolean = synchronized(lock) {
        if (!seenSources.add(key)) return false
        if (seenSources.size > MAX_SEEN) seenSources.remove(seenSources.first())
        true
    }

    private fun uniqueDest(safe: String): File =
        File(mediaDir(), "${System.currentTimeMillis()}_${System.nanoTime()}_${nameCounter.getAndIncrement()}_$safe")

    /** Copy [src] into the media dir; null if it was already copied or the copy failed. */
    fun stage(src: File): File? {
        if (!src.isFile) return null
        // Dedup reservation under a brief lock; the copy itself runs unlocked so
        // a burst of photos does not queue behind one large video.
        if (!tryReserve(src.absolutePath)) return null
        return try {
            val safe = src.name.replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(80)
            val dest = uniqueDest(safe)
            src.copyTo(dest, overwrite = false)
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stage failed for ${src.path}: $e")
            null
        }
    }

    /** Persist notification preview pixels (photo/video/sticker/GIF thumbnails). */
    fun stageBitmap(bitmap: android.graphics.Bitmap): File? {
        // Unique dest per call, no shared state: runs unlocked for burst throughput.
        return try {
            val dest = uniqueDest("notif.jpg")
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
    fun stageStream(input: java.io.InputStream, ext: String, sourceKey: String? = null): File? {
        // Shared dedup with [stage] when the MediaStore row maps to a known path,
        // so the notification path and the watchers do not copy the same file twice.
        if (sourceKey != null && !tryReserve(sourceKey)) return null
        return try {
            val safeExt = ext.replace(Regex("[^A-Za-z0-9]"), "").take(5).ifEmpty { "bin" }
            val dest = uniqueDest("store.$safeExt")
            dest.outputStream().use { out -> input.copyTo(out, bufferSize = 256 * 1024) }
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stageStream failed: $e")
            null
        }
    }

    /** Newest copy not linked to any message ([linked]) and staged within [windowMs]. */
    fun claimOwnerless(linked: Set<String>, windowMs: Long = CLAIM_WINDOW_MS): File? =
        synchronized(lock) {
            val since = System.currentTimeMillis() - windowMs
            mediaDir().listFiles()
                ?.filter { it.lastModified() >= since && it.absolutePath !in linked }
                ?.maxByOrNull { it.lastModified() }
        }

    fun delete(paths: Collection<String>) {
        synchronized(lock) {
            paths.forEach { File(it).delete() }
        }
    }

    /**
     * Delete copies older than [retentionCutoff], then enforce [maxBytes]
     * oldest-first. Copies in [keep] (media of deleted messages, the whole
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
