package com.tiriig.whatsdeleted.services

import android.content.Context
import android.database.ContentObserver
import android.net.Uri
import android.os.Handler
import android.os.HandlerThread
import android.provider.MediaStore
import android.util.Log
import java.io.File

/**
 * Second media source next to [MediaObserver]. On Android 11+ shared storage
 * sits behind FUSE and inotify (FileObserver) does not reliably see files
 * written by other apps, while MediaStore change notifications do fire.
 * Reports settled WhatsApp files through [onNewMedia]; duplicates with
 * [MediaObserver] are dropped by [TempMediaStore.stage].
 */
class MediaStoreWatcher(
    private val context: Context,
    private val onNewMedia: (File) -> Unit
) {
    companion object {
        private const val TAG = "MediaStoreWatcher"
        private const val DEBOUNCE_MS = 2_000L

        // A file still being downloaded keeps getting its mtime bumped.
        private const val SETTLE_MS = 2_000L

        private val COLLECTIONS = listOf(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        )
    }

    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var observer: ContentObserver? = null
    private var lastScanSec = 0L

    private val scanRunnable = Runnable { scan() }

    fun start() {
        if (observer != null) return
        val t = HandlerThread(TAG).apply { start() }
        val h = Handler(t.looper)
        val obs = object : ContentObserver(h) {
            override fun onChange(selfChange: Boolean, uri: Uri?) {
                h.removeCallbacks(scanRunnable)
                h.postDelayed(scanRunnable, DEBOUNCE_MS)
            }
        }
        lastScanSec = System.currentTimeMillis() / 1000
        COLLECTIONS.forEach { context.contentResolver.registerContentObserver(it, true, obs) }
        thread = t
        handler = h
        observer = obs
    }

    fun stop() {
        observer?.let { context.contentResolver.unregisterContentObserver(it) }
        handler?.removeCallbacks(scanRunnable)
        thread?.quitSafely()
        observer = null
        handler = null
        thread = null
    }

    @Suppress("DEPRECATION") // DATA is still populated and readable on 29+.
    private fun scan() {
        val startedSec = System.currentTimeMillis() / 1000
        var unsettled = false
        COLLECTIONS.forEach { uri ->
            try {
                context.contentResolver.query(
                    uri,
                    arrayOf(MediaStore.MediaColumns.DATA),
                    "${MediaStore.MediaColumns.DATE_ADDED} >= ? AND ${MediaStore.MediaColumns.DATA} LIKE ?",
                    arrayOf((lastScanSec - 1).toString(), "%WhatsApp%"),
                    null
                )?.use { cursor ->
                    while (cursor.moveToNext()) {
                        val file = File(cursor.getString(0) ?: continue)
                        if (!MediaObserver.isMediaFile(file)) continue
                        if (System.currentTimeMillis() - file.lastModified() < SETTLE_MS) {
                            unsettled = true
                            continue
                        }
                        onNewMedia(file)
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "query $uri failed (missing media permission?): $e")
            }
        }
        // Keep the window open until every new file has settled.
        if (unsettled) {
            handler?.postDelayed(scanRunnable, SETTLE_MS)
        } else {
            lastScanSec = startedSec
        }
    }
}
