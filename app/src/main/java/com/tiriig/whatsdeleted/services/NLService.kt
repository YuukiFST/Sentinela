package com.tiriig.whatsdeleted.services

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import com.tiriig.whatsdeleted.utility.Notifications
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.getRandomNum
import com.tiriig.whatsdeleted.utility.isDeletionNotice
import com.tiriig.whatsdeleted.utility.isValidApp
import com.tiriig.whatsdeleted.utility.isValidTitle
import com.tiriig.whatsdeleted.utility.placeholderKind
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class NLService : NotificationListenerService() {

    companion object {
        private const val TAG = "NLService"

        // 15 x 2s = 30s: covers a sticker, GIF, photo or voice note download on
        // a slow connection; larger videos are still caught by MediaStoreWatcher.
        private const val FILE_POLL_ATTEMPTS = 15
        private const val FILE_POLL_INTERVAL_MS = 2_000L
    }

    @Inject
    lateinit var repository: ChatRepository

    @Inject
    lateinit var notifications: Notifications

    @Inject
    lateinit var tempStore: TempMediaStore

    @Inject
    lateinit var arrivingMedia: ArrivingMedia

    // This scope is tied to the service's lifecycle and uses a background thread.
    // A SupervisorJob ensures that if one child coroutine fails, the others are not cancelled.
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        // Piggyback: keep the media observer alive alongside the listener.
        try {
            startService(Intent(this, MediaObserverService::class.java))
        } catch (e: Exception) {
            Log.w(TAG, "could not start MediaObserverService: $e")
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Return STICKY to ensure the service restarts if the system kills it.
        return START_STICKY
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        // Filter for valid notifications from the apps you support.
        if (sbn != null && sbn.packageName.isValidApp()) {
            processNotification(sbn)
        }
    }

    private fun processNotification(sbn: StatusBarNotification) {
        val extras = sbn.notification.extras
        val title = extras.getString("android.title") ?: return
        val text = extras.getCharSequence("android.text")?.toString() ?: ""
        // `when` is 0 on some devices/versions — fall back to the post time so
        // every stored message still gets a usable, dedupable timestamp.
        var time = sbn.notification.`when`
        if (time == 0L) time = sbn.postTime
        if (time == 0L) time = System.currentTimeMillis()
        val app = sbn.packageName
        // Bundled MessagingStyle digests re-list recent history on every update.
        val lines = extras.getCharSequenceArray("android.textLines")
            ?.mapNotNull { it?.toString()?.takeIf { s -> s.isNotEmpty() } }
            ?: emptyList()

        // Ignore notifications with invalid titles (e.g., "Checking for new messages").
        if (!title.isValidTitle()) return
        if (text.isEmpty() && lines.isEmpty()) return

        // Launch a coroutine on our background-threaded scope to do the heavy lifting.
        serviceScope.launch {
            saveNewMessage(title, text, lines, time, app, sbn)
        }
    }

    private suspend fun saveNewMessage(
        title: String,
        text: String,
        lines: List<String>,
        time: Long,
        app: String,
        sbn: StatusBarNotification
    ) {
        // Sentinela rule: TEXT is saved for everyone except contacts the user
        // ignored (saveMessages = false). The media switch only gates media
        // copies and the "deleted" alert (see flagLastMessageDeleted).
        if (title.contains(":")) {
            // Assumes "GroupName: SenderName" format
            var groupName = title.substringBefore(":")
            val senderName = title.substringAfter(": ").trim()

            // Clean up group name if it contains message counts (e.g., "My Group (2 messages)")
            if (groupName.contains("(")) {
                groupName = groupName.substringBefore("(").trim()
            }

            if (!repository.shouldSaveMessages(groupName, app)) return

            if (text.isDeletionNotice()) {
                flagLastMessageDeleted(groupName, app)
                return
            }

            if (lines.size > 1) {
                saveLines(groupName, senderName, lines, time, app, isGroup = true, sbn = sbn)
                repository.runCleanupIfDue()
                return
            }
            if (text.isEmpty()) return

            // Save text immediately so a burst appears instantly; media attaches
            // async via setMediaPath without blocking this save or the next one.
            val groupId = getRandomNum()
            val groupChat = Chat(
                groupId, groupName, "$senderName: $text", time, app,
                isGroup = true, mediaPath = null
            )
            repository.saveMessage(groupChat)
            placeholderKind(text)?.let { attachMediaAsync(groupId, groupName, app, it, sbn) }
        } else {
            if (!repository.shouldSaveMessages(title, app)) return

            if (text.isDeletionNotice()) {
                flagLastMessageDeleted(title, app)
                return
            }

            if (lines.size > 1) {
                saveLines(title, null, lines, time, app, isGroup = false, sbn = sbn)
                repository.runCleanupIfDue()
                return
            }
            if (text.isEmpty()) return

            // Standard direct message: same non-blocking media attach.
            val id = getRandomNum()
            val chat = Chat(
                id, title, text, time, app,
                mediaPath = null
            )
            repository.saveMessage(chat)
            placeholderKind(text)?.let { attachMediaAsync(id, title, app, it, sbn) }
        }
        repository.runCleanupIfDue()
    }

    /**
     * Saving the whole digest on every update is what rendered one message
     * several times. Save line-by-line (oldest first) and let the repository's
     * 10s dedup window drop the overlap, keeping only the genuinely new suffix.
     */
    private suspend fun saveLines(
        user: String,
        senderName: String?,
        lines: List<String>,
        time: Long,
        app: String,
        isGroup: Boolean,
        sbn: StatusBarNotification
    ) {
        if (!repository.shouldSaveMessages(user, app)) return
        val clean = lines.map { it.trim() }
            .filter { it.isNotEmpty() && it.isValidTitle() && !it.isDeletionNotice() }
            .takeLast(10)
        if (clean.isEmpty()) return
        // Save every line's text first (burst-visible instantly), then attach
        // media newest-first in one batch per kind: previously only the newest
        // line got media, so all but one photo in a burst lost their copy.
        val pending = ArrayList<Pair<String, PlaceholderKind>>(clean.size)
        clean.forEach { line ->
            val body =
                if (isGroup && senderName != null && !line.startsWith("$senderName:")) {
                    "$senderName: $line"
                } else {
                    line
                }
            val id = getRandomNum()
            repository.saveMessage(Chat(id, user, body, time, app, isGroup = isGroup, mediaPath = null))
            placeholderKind(line)?.let { pending.add(id to it) }
        }
        if (pending.isNotEmpty()) attachBurstMediaAsync(pending, user, app, sbn)
    }

    /** Async media attach for one message; see [attachMedia]. */
    private fun attachMediaAsync(
        id: String,
        user: String,
        app: String,
        kind: PlaceholderKind,
        sbn: StatusBarNotification
    ) {
        serviceScope.launch {
            try {
                if (!repository.isAllowed(user, app)) return@launch
                attachMedia(listOf(id), kind, sbn)
            } catch (e: Exception) {
                Log.w(TAG, "attach media failed: $e")
            }
        }
    }

    /**
     * Async batch attach for a digest burst, one job per kind so a slow video
     * does not hold back the stickers. Newest message takes the newest file.
     * Newest-first also protects the new line from digest overlap: re-posted
     * old lines are dedup-skipped on insert, so their link hits zero rows.
     */
    private fun attachBurstMediaAsync(
        pendingOldestFirst: List<Pair<String, PlaceholderKind>>,
        user: String,
        app: String,
        sbn: StatusBarNotification
    ) {
        val byKind = pendingOldestFirst.asReversed()
            .groupBy(keySelector = { it.second }, valueTransform = { it.first })
        for ((kind, idsNewestFirst) in byKind) {
            serviceScope.launch {
                try {
                    if (!repository.isAllowed(user, app)) return@launch
                    attachMedia(idsNewestFirst, kind, sbn)
                } catch (e: Exception) {
                    Log.w(TAG, "attach burst media failed: $e")
                }
            }
        }
    }

    /**
     * Links the real WhatsApp file to each message in [idsNewestFirst]. WhatsApp
     * posts the notification before the download ends, and stickers, GIFs and
     * voice notes give the watchers no signal (`.nomedia`), so the folders are
     * polled for [FILE_POLL_ATTEMPTS] rounds. The notification preview (if
     * any) is shown meanwhile and replaced once the file lands.
     */
    private suspend fun attachMedia(
        idsNewestFirst: List<String>,
        kind: PlaceholderKind,
        sbn: StatusBarNotification
    ) {
        val since = System.currentTimeMillis() - ArrivingMedia.LOOKUP_WINDOW_MS
        var waiting = idsNewestFirst
        for (attempt in 0 until FILE_POLL_ATTEMPTS) {
            if (attempt > 0) delay(FILE_POLL_INTERVAL_MS)
            val files = arrivingMedia.storedCopyPaths(
                applicationContext, kind, waiting.size, since, repository.linkedMediaPaths()
            )
            files.forEachIndexed { index, path -> repository.linkFile(waiting[index], path) }
            waiting = waiting.drop(files.size)
            if (waiting.isEmpty()) return
            if (attempt == 0) {
                waiting.forEach { id ->
                    arrivingMedia.thumbnailPath(sbn, applicationContext, kind)
                        ?.let { repository.linkPreview(id, it) }
                }
            }
        }
    }

    // The notification content is replaced rather than removed when a message is
    // deleted, so we just flag the chat's most recent message and let the user know.
    private suspend fun flagLastMessageDeleted(user: String, app: String) {
        val lastMessage = repository.lastMessageForChat(user, app) ?: return
        if (lastMessage.isDeleted) return

        repository.messageIsDeleted(lastMessage.id)

        if (!repository.isAllowed(user, app)) {
            // Opted out: no media was copied for this chat; stay silent
            // (the text stays flagged in the DB for manual lookup).
            repository.runCleanupIfDue()
            return
        }

        // Media is normally linked when the file shows up (MediaObserverService);
        // a file with no message in the 5 min before it stays ownerless, so claim a recent one.
        if (lastMessage.mediaPath == null) {
            val ownerless = tempStore.claimOwnerless(repository.linkedMediaPaths())
            if (ownerless != null) repository.setMediaPath(lastMessage.id, ownerless.absolutePath)
        }

        notifications.notify(
            user,
            getString(R.string.deleted_message_title),
            getString(R.string.deleted_message_body, user),
            app
        )
        repository.runCleanupIfDue()
    }

    override fun onDestroy() {
        super.onDestroy()
        // Cancelling this is crucial to prevent memory leaks by stopping all ongoing coroutines
        serviceScope.cancel()
    }
}
