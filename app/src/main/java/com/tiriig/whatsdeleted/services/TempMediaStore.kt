package com.tiriig.whatsdeleted.services

import android.content.Context
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
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

    fun mediaDir(): File =
        File(context.getExternalFilesDir(null), DIR_NAME).apply { mkdirs() }

    /** Copy [src] into the media dir; null if it was already copied or the copy failed. */
    fun stage(src: File): File? = synchronized(lock) {
        if (!src.isFile) return null
        if (!seenSources.add(src.absolutePath)) return null
        if (seenSources.size > MAX_SEEN) seenSources.remove(seenSources.first())
        try {
            val safe = src.name.replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(80)
            val dest = File(mediaDir(), "${System.currentTimeMillis()}_$safe")
            src.copyTo(dest, overwrite = false)
        } catch (e: Exception) {
            Log.w(TAG, "stage failed for ${src.path}: $e")
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
