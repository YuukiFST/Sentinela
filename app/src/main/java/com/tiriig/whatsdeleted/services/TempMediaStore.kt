package com.tiriig.whatsdeleted.services

import android.content.Context
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Sentinela staging area for media files spotted by [MediaObserver].
 * Files are copied here the moment they appear on disk; ownership is a
 * best-effort heuristic (most recent sender), claiming happens on deletion.
 */
@Singleton
class TempMediaStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    data class PendingMedia(
        val file: File,
        val stagedAt: Long,
        var ownerUser: String?,
        var ownerApp: String?,
        var claimed: Boolean = false
    )

    companion object {
        private const val TAG = "TempMediaStore"
        const val DIR_NAME = "sentinela_media"
        const val CLAIM_WINDOW_MS = 5L * 60 * 1000 // 5 min, matches "recent sender" rule
        private const val MAX_TRACKED = 200
    }

    private val lock = Any()
    private val pending = mutableListOf<PendingMedia>()

    fun pendingDir(): File =
        File(context.getExternalFilesDir(null), DIR_NAME).apply { mkdirs() }

    /** Copy [src] into the staging dir, attributing it to [ownerUser]/[ownerApp] (nullable = unknown). */
    fun stage(src: File, ownerUser: String?, ownerApp: String?): File? = synchronized(lock) {
        try {
            if (!src.isFile || !src.exists()) return null
            val safe = src.name.replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(80)
            val dest = File(pendingDir(), "${System.currentTimeMillis()}_$safe")
            src.copyTo(dest, overwrite = false)
            pending.add(PendingMedia(dest, System.currentTimeMillis(), ownerUser, ownerApp))
            pruneTrackedLocked()
            dest
        } catch (e: Exception) {
            Log.w(TAG, "stage failed for ${src.path}: $e")
            null
        }
    }

    /**
     * Newest unclaimed copy usable for (user, app): owned by them, or still
     * ownerless (not attributed to another chat) and inside [windowMs].
     */
    fun claimFor(user: String, app: String, windowMs: Long = CLAIM_WINDOW_MS): File? =
        synchronized(lock) {
            val now = System.currentTimeMillis()
            val cand = pending
                .filter {
                    !it.claimed && it.file.exists() && now - it.stagedAt <= windowMs &&
                        (it.ownerUser == null || (it.ownerUser == user && it.ownerApp == app))
                }
                .maxByOrNull { it.stagedAt }
            cand?.claimed = true
            cand?.file
        }

    /**
     * Contact opted out: drop staged copies owned by them. Ownerless copies
     * staged in the last 60s are probably theirs too — best effort.
     */
    fun discardFor(user: String, app: String): Int = synchronized(lock) {
        val now = System.currentTimeMillis()
        val victims = pending.filter {
            !it.claimed && it.file.exists() &&
                ((it.ownerUser == user && it.ownerApp == app) ||
                    (it.ownerUser == null && now - it.stagedAt <= 60_000))
        }
        var n = 0
        victims.forEach {
            try {
                if (it.file.delete()) n++
            } catch (_: Exception) { }
            pending.remove(it)
        }
        n
    }

    /**
     * Tarefa 4: delete orphans (files no Chat references via mediaPath) older
     * than [retentionCutoff], then enforce [maxBytes] oldest-first.
     * Files still referenced by the DB are never deleted here.
     */
    fun cleanup(retentionCutoff: Long, maxBytes: Long, referenced: Set<String>) {
        synchronized(lock) {
            try {
                val dir = pendingDir()
                val files = dir.listFiles()?.toList() ?: emptyList()
                files.forEach { f ->
                    if (!referenced.contains(f.absolutePath) && f.lastModified() < retentionCutoff) {
                        try {
                            f.delete()
                        } catch (_: Exception) { }
                    }
                }
                var total = dir.listFiles()?.sumOf { it.length() } ?: 0L
                if (total > maxBytes) {
                    dir.listFiles()
                        ?.filter { !referenced.contains(it.absolutePath) }
                        ?.sortedBy { it.lastModified() }
                        ?.forEach { f ->
                            if (total <= maxBytes) return@forEach
                            try {
                                val size = f.length()
                                if (f.delete()) total -= size
                            } catch (_: Exception) { }
                        }
                }
                pending.removeAll { !it.file.exists() }
                pruneTrackedLocked()
            } catch (e: Exception) {
                Log.w(TAG, "cleanup failed: $e")
            }
        }
    }

    private fun pruneTrackedLocked() {
        if (pending.size <= MAX_TRACKED) return
        pending.sortBy { it.stagedAt }
        val overflow = pending.size - MAX_TRACKED
        repeat(overflow) { pending.removeFirstOrNull() }
    }
}
