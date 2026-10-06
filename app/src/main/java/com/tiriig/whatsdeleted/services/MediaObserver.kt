package com.tiriig.whatsdeleted.services

import android.os.Environment
import android.os.FileObserver
import android.util.Log
import java.io.File

/**
 * Sentinela adaptation of the reference WhatsDeleted MediaObserver:
 * recursive [FileObserver] over the WhatsApp (/Business) media trees.
 * Calls [onNewMedia] with CLOSE_WRITE/MOVED_TO files only, so the copy
 * sees a complete file. New subdirs picked up via CREATE are watched too.
 */
class MediaObserver(
    private val onNewMedia: (File) -> Unit
) {
    companion object {
        private const val TAG = "MediaObserver"

        private val MEDIA_EXT = setOf(
            "jpg", "jpeg", "png", "webp", "gif", "bmp",
            "mp4", "mkv", "avi", "mov", "3gp", "webm",
            "mp3", "m4a", "aac", "opus", "ogg", "amr", "wav", "flac"
        )

        private fun candidateRoots(): List<File> {
            val ext = Environment.getExternalStorageDirectory()
            return listOf(
                File(ext, "WhatsApp/Media"),
                File(ext, "Android/media/com.whatsapp/WhatsApp/Media"),
                File(ext, "WhatsApp Business/Media"),
                File(ext, "Android/media/com.whatsapp.w4b/WhatsApp Business/Media")
            )
        }

        fun isMediaFile(f: File): Boolean {
            if (!f.isFile) return false
            val name = f.name
            if (name.startsWith(".") || name.endsWith(".tmp") || name == ".nomedia") return false
            return MEDIA_EXT.contains(name.substringAfterLast('.', "").lowercase())
        }
    }

    private val observers = mutableListOf<FileObserver>()
    private val watched = mutableSetOf<String>()

    fun start() {
        candidateRoots().filter { it.isDirectory }.forEach { watchTree(it) }
        Log.i(TAG, "watching ${watched.size} dirs")
    }

    fun stop() {
        observers.forEach {
            try {
                it.stopWatching()
            } catch (_: Exception) { }
        }
        observers.clear()
        watched.clear()
    }

    @Suppress("DEPRECATION")
    private fun watchTree(dir: File) {
        val key = try {
            dir.canonicalPath
        } catch (_: Exception) {
            dir.absolutePath
        }
        if (!watched.add(key)) return
        try {
            val obs = object : FileObserver(
                dir.absolutePath,
                CLOSE_WRITE or MOVED_TO or CREATE
            ) {
                override fun onEvent(event: Int, path: String?) {
                    if (path == null) return
                    try {
                        val f = File(dir, path)
                        if (event and (CLOSE_WRITE or MOVED_TO) != 0) {
                            if (isMediaFile(f)) onNewMedia(f)
                        } else if (event and CREATE != 0) {
                            if (f.isDirectory) watchTree(f)
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "event failed: $e")
                    }
                }
            }
            obs.startWatching()
            observers.add(obs)
        } catch (e: Exception) {
            Log.w(TAG, "cannot watch $dir: $e")
            return
        }
        try {
            dir.listFiles()
                ?.filter { it.isDirectory && !it.name.startsWith(".") }
                ?.forEach { watchTree(it) }
        } catch (e: Exception) {
            Log.w(TAG, "cannot list $dir: $e")
        }
    }
}
