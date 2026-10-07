package com.tiriig.whatsdeleted.services

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import com.tiriig.whatsdeleted.utility.Notifications
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
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class NLService : NotificationListenerService() {

    companion object {
        private const val TAG = "NLService"
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

            val groupChat = Chat(
                getRandomNum(), groupName, "$senderName: $text", time, app,
                isGroup = true, mediaPath = captureFor(groupName, app, text, sbn)
            )
            repository.saveMessage(groupChat)
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

            // Standard direct message
            val chat = Chat(
                getRandomNum(), title, text, time, app,
                mediaPath = captureFor(title, app, text, sbn)
            )
            repository.saveMessage(chat)
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
        // Only the newest line owns this notification's media.
        val newestIndex = clean.indices.last
        clean.forEachIndexed { index, line ->
            val body =
                if (isGroup && senderName != null && !line.startsWith("$senderName:")) {
                    "$senderName: $line"
                } else {
                    line
                }
            val mediaPath = if (index == newestIndex) {
                captureFor(user, app, line, sbn)
            } else {
                null
            }
            repository.saveMessage(Chat(getRandomNum(), user, body, time, app, isGroup = isGroup, mediaPath = mediaPath))
        }
    }

    /**
     * Attach viewable content to a media placeholder at arrival time, on the
     * message itself: fresh MediaStore file first (full-res/playable), then
     * the notification thumbnail (the only path for stickers/GIFs). Plain
     * text and opted-out contacts get nothing.
     */
    private suspend fun captureFor(
        user: String,
        app: String,
        text: String,
        sbn: StatusBarNotification
    ): String? {
        val kind = placeholderKind(text) ?: return null
        if (!repository.isAllowed(user, app)) return null
        return try {
            arrivingMedia.storedCopyPath(applicationContext, kind)
                ?: arrivingMedia.thumbnailPath(sbn, applicationContext)
        } catch (_: Exception) {
            null
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
