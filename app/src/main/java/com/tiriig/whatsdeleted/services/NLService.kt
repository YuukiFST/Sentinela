package com.tiriig.whatsdeleted.services

import android.content.Intent
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import com.tiriig.whatsdeleted.utility.Notifications
import com.tiriig.whatsdeleted.utility.PlaceholderKind
import com.tiriig.whatsdeleted.utility.getRandomNum
import com.tiriig.whatsdeleted.utility.isDeletionNotice
import com.tiriig.whatsdeleted.utility.isValidApp
import com.tiriig.whatsdeleted.utility.isValidTitle
import com.tiriig.whatsdeleted.utility.mediaKind
import com.tiriig.whatsdeleted.utility.newDigestLines
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

        // Newest messages read from one notification; older ones were saved by earlier posts.
        private const val MAX_DIGEST_MESSAGES = 10
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
        val styleMessages = styleMessages(sbn, time)

        // Ignore notifications with invalid titles (e.g., "Checking for new messages").
        if (!title.isValidTitle()) return
        if (text.isEmpty() && lines.isEmpty() && styleMessages.isEmpty()) return

        // Launch a coroutine on our background-threaded scope to do the heavy lifting.
        serviceScope.launch {
            saveNewMessage(title, text, lines, styleMessages, time, app, sbn)
        }
    }

    /** One message of a MessagingStyle notification; [sentAt] stays the same on every re-post. */
    private class StyleMessage(val sender: String, val text: String, val sentAt: Long, val inGroup: Boolean)

    /**
     * Messages the notification lists with their own send time, oldest first.
     * Messages without a sender are the user's own replies and are skipped.
     */
    private fun styleMessages(sbn: StatusBarNotification, fallbackTime: Long): List<StyleMessage> {
        val style = try {
            NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(sbn.notification)
        } catch (e: Exception) {
            Log.w(TAG, "MessagingStyle read failed: $e")
            null
        } ?: return emptyList()
        // A group title may lack the "Group: Sender" colon; the style still knows.
        val inGroup = style.isGroupConversation
        return style.messages.mapNotNull { message ->
            val sender = message.person?.name?.toString()?.takeIf { it.isNotBlank() }
                ?: return@mapNotNull null
            val body = message.text?.toString()?.trim()?.takeIf { it.isNotEmpty() }
                ?: return@mapNotNull null
            StyleMessage(sender, body, message.timestamp.takeIf { it > 0 } ?: fallbackTime, inGroup)
        }
    }

    private suspend fun saveNewMessage(
        title: String,
        text: String,
        lines: List<String>,
        styleMessages: List<StyleMessage>,
        time: Long,
        app: String,
        sbn: StatusBarNotification
    ) {
        // Sentinela rule: TEXT is saved for everyone except contacts the user
        // ignored (saveMessages = false). The media switch only gates media
        // copies and the "deleted" alert (see flagDeleted).
        val isGroup = title.contains(":")
        // Assumes "GroupName: SenderName" format; message counts are stripped
        // from the group name (e.g., "My Group (2 messages)").
        val user = if (isGroup) title.substringBefore(":").substringBefore("(").trim() else title
        val senderName = if (isGroup) title.substringAfter(": ").trim() else null

        if (!repository.shouldSaveMessages(user, app)) return

        when {
            styleMessages.isNotEmpty() -> saveStyleMessages(user, styleMessages, app, isGroup, sbn)
            text.isDeletionNotice() -> {
                flagDeleted(user, app)
                return
            }
            lines.size > 1 -> saveLines(user, senderName, lines, time, app, isGroup, sbn)
            text.isEmpty() -> return
            else -> {
                // Save text immediately so a burst appears instantly; media attaches
                // async via setMediaPath without blocking this save or the next one.
                val id = getRandomNum()
                val body = if (isGroup) "$senderName: $text" else text
                val saved = repository.saveMessage(Chat(id, user, body, time, app, isGroup = isGroup))
                if (saved) placeholderKind(text)?.let { attachMediaAsync(id, user, app, it, sbn) }
            }
        }
        repository.runCleanupIfDue()
    }

    /**
     * Saving the notification's latest text under the notification time
     * repeated a message whenever WhatsApp re-posted it later. Each listed
     * message is saved with its own send time instead, so a re-post matches
     * the stored row exactly and is skipped. A message replaced by the
     * deletion notice flags the stored row with that send time.
     */
    private suspend fun saveStyleMessages(
        user: String,
        messages: List<StyleMessage>,
        app: String,
        isGroup: Boolean,
        sbn: StatusBarNotification
    ) {
        val recent = messages.takeLast(MAX_DIGEST_MESSAGES)
        val pending = ArrayList<Pair<String, PlaceholderKind>>()
        recent.forEachIndexed { index, message ->
            if (message.text.isDeletionNotice()) {
                // Send time not stored: only the newest notice may fall back to
                // the last stored message, as the plain-text path does.
                flagDeleted(user, app, message.sentAt, orLast = index == recent.lastIndex)
                return@forEachIndexed
            }
            val group = isGroup || message.inGroup
            val body = if (group) "${message.sender}: ${message.text}" else message.text
            val id = getRandomNum()
            if (repository.saveMessage(Chat(id, user, body, message.sentAt, app, isGroup = group))) {
                placeholderKind(message.text)?.let { pending.add(id to it) }
            }
        }
        if (pending.isNotEmpty()) attachBurstMediaAsync(pending, user, app, sbn)
    }

    /**
     * Fallback for digests without MessagingStyle: every line shares one
     * timestamp, so the overlap with what is stored is found by text order
     * ([newDigestLines]) and only the new suffix is saved.
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
        val bodies = lines.map { it.trim() }
            .filter { it.isNotEmpty() && it.isValidTitle() && !it.isDeletionNotice() }
            .takeLast(MAX_DIGEST_MESSAGES)
            .map { line ->
                if (isGroup && senderName != null && !line.startsWith("$senderName:")) "$senderName: $line" else line
            }
        if (bodies.isEmpty()) return
        val fresh = newDigestLines(repository.recentTexts(user, app, bodies.size), bodies)
        // Save every line's text first (burst-visible instantly), then attach
        // media newest-first in one batch per kind: previously only the newest
        // line got media, so all but one photo in a burst lost their copy.
        val pending = ArrayList<Pair<String, PlaceholderKind>>(fresh.size)
        fresh.forEach { body ->
            val id = getRandomNum()
            if (repository.saveMessage(Chat(id, user, body, time, app, isGroup = isGroup))) {
                placeholderKind(body)?.let { pending.add(id to it) }
            }
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

    /**
     * The notification content is replaced rather than removed when a message
     * is deleted. Flags the stored message sent at [sentAt] when known, else
     * (if [orLast]) the chat's most recent one, and lets the user know.
     */
    private suspend fun flagDeleted(user: String, app: String, sentAt: Long? = null, orLast: Boolean = true) {
        val target = sentAt?.let { repository.messageAt(user, app, it) }
            ?: (if (orLast) repository.lastMessageForChat(user, app) else null)
            ?: return
        if (target.isDeleted) return

        repository.messageIsDeleted(target.id)

        if (!repository.isAllowed(user, app)) {
            // Opted out: no media was copied for this chat; stay silent
            // (the text stays flagged in the DB for manual lookup).
            repository.runCleanupIfDue()
            return
        }

        // Media is normally linked when the file shows up (MediaObserverService);
        // a file with no message in the 5 min before it stays ownerless, so claim
        // a recent one, but only for a media message and only of its type: a
        // deleted text or view-once message used to take an unrelated photo.
        val kind = placeholderKind(target.message)
        if (target.mediaPath == null && kind != null) {
            val ownerless = tempStore.claimOwnerless(repository.linkedMediaPaths(), kind.mediaKind())
            if (ownerless != null) repository.setMediaPath(target.id, ownerless.absolutePath)
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
