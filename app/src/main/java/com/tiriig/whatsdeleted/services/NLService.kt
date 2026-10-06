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
        val time = sbn.notification.`when`
        val app = sbn.packageName

        // Ignore notifications with invalid titles or empty text (e.g., "Checking for new messages")
        if (!title.isValidTitle() || text.isEmpty()) return

        // Launch a coroutine on our background-threaded scope to do the heavy lifting.
        serviceScope.launch {
            saveNewMessage(title, text, time, app)
        }
    }

    private suspend fun saveNewMessage(title: String, text: String, time: Long, app: String) {
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

            val groupChat = Chat(getRandomNum(), groupName, "$senderName: $text", time, app, isGroup = true)
            repository.saveMessage(groupChat)
        } else {
            if (!repository.shouldSaveMessages(title, app)) return

            if (text.isDeletionNotice()) {
                flagLastMessageDeleted(title, app)
                return
            }

            // Standard direct message
            val chat = Chat(getRandomNum(), title, text, time, app)
            repository.saveMessage(chat)
        }
        repository.runCleanupIfDue()
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
