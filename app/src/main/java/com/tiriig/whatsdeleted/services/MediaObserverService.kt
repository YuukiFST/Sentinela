package com.tiriig.whatsdeleted.services

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * Hosts the [MediaObserver]: stages fresh WhatsApp media into
 * [TempMediaStore], attributing each file to the most recent sender
 * (message in the last 5 min) or leaving it ownerless ("unknown").
 * Started piggyback on [NLService] and [MainActivity]; START_STICKY.
 */
@AndroidEntryPoint
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
    private var observer: MediaObserver? = null

    override fun onCreate() {
        super.onCreate()
        observer = MediaObserver { file -> onMediaFile(file) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            observer?.start()
        } catch (e: Exception) {
            Log.w(TAG, "observer start failed (missing media permission?): $e")
        }
        return START_STICKY
    }

    private fun onMediaFile(file: File) {
        serviceScope.launch {
            try {
                val since = System.currentTimeMillis() - ATTRIBUTION_WINDOW_MS
                val recent = repository.mostRecentSince(since)
                tempStore.stage(file, recent?.user, recent?.app)
            } catch (e: Exception) {
                Log.w(TAG, "stage failed: $e")
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        try {
            observer?.stop()
        } catch (_: Exception) { }
        serviceScope.cancel()
        super.onDestroy()
    }
}
