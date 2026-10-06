package com.tiriig.whatsdeleted.data.repository

import android.content.Context
import android.util.Log
import androidx.lifecycle.LiveData
import androidx.room.withTransaction
import com.tiriig.whatsdeleted.data.database.Database
import com.tiriig.whatsdeleted.data.model.AllowedContact
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.model.DeletedMessage
import com.tiriig.whatsdeleted.data.model.KnownConversation
import com.tiriig.whatsdeleted.services.TempMediaStore
import com.tiriig.whatsdeleted.utility.CleanupPrefs
import com.tiriig.whatsdeleted.utility.isValidTitle
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ChatRepository @Inject constructor(
    private val database: Database,
    @ApplicationContext private val appContext: Context,
    private val tempStore: TempMediaStore
) {

    companion object {
        private const val TAG = "ChatRepository"
        private const val CLEANUP_INTERVAL_MS = 24L * 60 * 60 * 1000 // 1x/dia
        /** Re-posts of one notification arrive within seconds; the same text sent
         * minutes later is a new message and must be kept. */
        const val DEDUP_WINDOW_MS = 10_000L
    }

    // WhatsApp/Telegram often re-post the same notification for one message within
    // milliseconds of each other, so the dedup check below needs to run atomically -
    // otherwise two overlapping saves both read "no duplicate yet" and both insert.
    private val saveMutex = Mutex()

    suspend fun saveMessage(chat: Chat) {
        withContext(Dispatchers.IO) {
            if (!chat.message.isValidTitle()) return@withContext

            saveMutex.withLock {
                // Scope to this conversation (user + app): the same contact name
                // can exist in two apps, and comparing across apps both hides
                // real messages and lets re-posts slip through.
                val lastMessage = try {
                    database.userDao().getLastMessageForChat(chat.user, chat.app)
                        ?: database.userDao().getLastMessage(chat.user)
                } catch (_: Exception) {
                    null
                }
                val isDuplicate = lastMessage != null &&
                    chat.message == lastMessage.message &&
                    kotlin.math.abs(chat.dateTime - lastMessage.dateTime) < DEDUP_WINDOW_MS

                if (!isDuplicate) database.userDao().save(chat)
            }
        }
    }

    suspend fun fetchChats(): LiveData<List<Chat>> {
        return withContext(Dispatchers.IO) {
            database.userDao().getChats()
        }
    }

    suspend fun fetchMessagesByUser(user: String,app: String): LiveData<List<Chat>> {
        return withContext(Dispatchers.IO) {
            database.userDao().getMessagesByUser(user,app)
        }
    }

    suspend fun lastMessage(user: String): DeletedMessage? {
        return withContext(Dispatchers.IO) {
            database.userDao().getLastMessage(user)
        }
    }

    suspend fun lastMessageForChat(user: String, app: String): DeletedMessage? {
        return withContext(Dispatchers.IO) {
            database.userDao().getLastMessageForChat(user, app)
                ?: database.userDao().getLastMessage(user)
        }
    }

    /** Most recent message overall since [since] — media attribution heuristic. */
    suspend fun mostRecentSince(since: Long): Chat? {
        return withContext(Dispatchers.IO) {
            database.userDao().getMostRecentSince(since)
        }
    }

    suspend fun messageIsDeleted(id: String) {
        withContext(Dispatchers.IO) {
            database.userDao().messageIsDeleted(id)
        }
    }

    suspend fun setMediaPath(id: String, path: String?) {
        withContext(Dispatchers.IO) {
            database.userDao().setMediaPath(id, path)
        }
    }

    /**
     * Links a fresh media copy to the newest message of (user, app) since
     * [since] that has none yet. No such message: the copy stays ownerless.
     */
    suspend fun linkMediaToRecentMessage(user: String, app: String, since: Long, path: String) {
        withContext(Dispatchers.IO) {
            val id = database.userDao().getMessageAwaitingMedia(user, app, since) ?: return@withContext
            database.userDao().setMediaPath(id, path)
        }
    }

    suspend fun linkedMediaPaths(): Set<String> {
        return withContext(Dispatchers.IO) {
            database.userDao().getAllMediaPaths().toSet()
        }
    }

    /** Removes the conversation from the chat list: its messages and media copies. */
    suspend fun deleteConversation(user: String, app: String) {
        withContext(Dispatchers.IO) {
            val paths = database.userDao().getMediaPathsForChat(user, app)
            database.userDao().deleteChat(user, app)
            tempStore.delete(paths)
        }
    }

    // ---- Allowlist (opt-out: missing row == allowed) ----

    suspend fun isAllowed(user: String, app: String): Boolean {
        return withContext(Dispatchers.IO) {
            database.allowedContactDao().isAllowedRaw(user, app) ?: true
        }
    }

    suspend fun setAllowed(user: String, app: String, allowed: Boolean) {
        updateContact(user, app) { it.copy(allowed = allowed) }
    }

    suspend fun shouldSaveMessages(user: String, app: String): Boolean {
        return withContext(Dispatchers.IO) {
            database.allowedContactDao().get(user, app)?.saveMessages ?: true
        }
    }

    suspend fun setSaveMessages(user: String, app: String, save: Boolean) {
        updateContact(user, app) { it.copy(saveMessages = save) }
    }

    // Read-modify-write so flipping one switch keeps the other one's value.
    private suspend fun updateContact(user: String, app: String, change: (AllowedContact) -> AllowedContact) {
        withContext(Dispatchers.IO) {
            database.withTransaction {
                val dao = database.allowedContactDao()
                dao.upsert(change(dao.get(user, app) ?: AllowedContact(user, app)))
            }
        }
    }

    fun knownConversations(): LiveData<List<KnownConversation>> =
        database.userDao().getKnownConversations()

    fun allowlist(): LiveData<List<AllowedContact>> =
        database.allowedContactDao().listAll()

    // ---- Tarefa 4: automatic cleanup (Room + staged media), throttled to 1x/day ----

    suspend fun runCleanupIfDue() {
        withContext(Dispatchers.IO) {
            try {
                val now = System.currentTimeMillis()
                if (now - CleanupPrefs.lastCleanup(appContext) < CLEANUP_INTERVAL_MS) return@withContext
                val cutoff = CleanupPrefs.retentionCutoff(appContext, now)
                database.userDao().deleteOlderThan(cutoff)
                val keep = database.userDao().getDeletedMediaPaths().toSet()
                tempStore.cleanup(cutoff, CleanupPrefs.maxMediaBytes(appContext), keep)
                CleanupPrefs.setLastCleanup(appContext, now)
            } catch (e: Exception) {
                Log.w(TAG, "cleanup failed: $e")
            }
        }
    }
}
