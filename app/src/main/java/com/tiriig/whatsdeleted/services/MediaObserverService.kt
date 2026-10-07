package com.tiriig.whatsdeleted.services

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import com.tiriig.whatsdeleted.utility.arrivingKind
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * Hosts [MediaObserver] and [MediaStoreWatcher]: copies fresh WhatsApp media
 * into [TempMediaStore] and links each copy to the most recent message
 * (last 5 min) right away, so it survives the original being deleted no
 * matter when the deletion happens. Media of contacts switched OFF is never
 * copied; media with no recent message stays ownerless.
 * Started piggyback on [NLService] and [MainActivity]; START_STICKY.
 */
@AndroidEntryPoint
@OptIn(ExperimentalCoroutinesApi::class)
class MediaObserverService : Service() {

    companion object {
        private const val TAG = "MediaObserverService"
        private const val ATTRIBUTION_WINDOW_MS = 5L * 60 * 1000
    }

    @Inject
    lateinit var repository: ChatRepository

    @Inject
    lateinit var tempStore: TempMediaStore

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    // Burst bound: watchers fire once per file, and each job copies. Unbounded
    // launches let 10 rapid photos each open DB + copy at once; 3 workers keep
    // latency flat without starving the notification path sharing Dispatchers.IO.
    private val copyDispatcher = Dispatchers.IO.limitedParallelism(3)
    private var observer: MediaObserver? = null
    private var storeWatcher: MediaStoreWatcher? = null

    override fun onCreate() {
        super.onCreate()
        observer = MediaObserver { file -> onMediaFile(file) }
        storeWatcher = MediaStoreWatcher(applicationContext) { file -> onMediaFile(file) }
    }

    // Called again by MainActivity after the media permission is granted:
    // both start() calls are idempotent and pick up what is now readable.
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            observer?.start()
            storeWatcher?.start()
        } catch (e: Exception) {
            Log.w(TAG, "observer start failed (missing media permission?): $e")
        }
        return START_STICKY
    }

    private fun onMediaFile(file: File) {
        serviceScope.launch(copyDispatcher) {
            try {
                val kind = file.arrivingKind() ?: return@launch
                val since = System.currentTimeMillis() - ATTRIBUTION_WINDOW_MS
                val recent = repository.mostRecentSince(since)
                if (recent != null && !repository.isAllowed(recent.user, recent.app)) return@launch
                val copy = tempStore.stage(file) ?: return@launch
                if (recent == null) return@launch
                repository.linkMediaToRecentMessage(recent.user, recent.app, since, copy.absolutePath, kind)
            } catch (e: Exception) {
                Log.w(TAG, "stage failed: $e")
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        try {
            observer?.stop()
            storeWatcher?.stop()
        } catch (_: Exception) { }
        serviceScope.cancel()
        super.onDestroy()
    }
}
