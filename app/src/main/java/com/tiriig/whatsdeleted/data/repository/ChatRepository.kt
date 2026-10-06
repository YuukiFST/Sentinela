package com.tiriig.whatsdeleted.data.repository

import android.content.Context
import android.util.Log
import androidx.lifecycle.LiveData
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
    }

    // WhatsApp/Telegram often re-post the same notification for one message within
    // milliseconds of each other, so the dedup check below needs to run atomically -
    // otherwise two overlapping saves both read "no duplicate yet" and both insert.
    private val saveMutex = Mutex()

    suspend fun saveMessage(chat: Chat) {
        withContext(Dispatchers.IO) {
            if (!chat.message.isValidTitle()) return@withContext

            saveMutex.withLock {
                //fetch last message and make comparison to avoid duplicates
                val lastMessage = database.userDao().getLastMessage(chat.user)
                val isDuplicate = lastMessage != null &&
                    (chat.message == lastMessage.message || chat.dateTime == lastMessage.dateTime)

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

    // ---- Allowlist (opt-out: missing row == allowed) ----

    suspend fun isAllowed(user: String, app: String): Boolean {
        return withContext(Dispatchers.IO) {
            database.allowedContactDao().isAllowedRaw(user, app) ?: true
        }
    }

    suspend fun setAllowed(user: String, app: String, allowed: Boolean) {
        withContext(Dispatchers.IO) {
            database.allowedContactDao().upsert(AllowedContact(user, app, allowed))
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
                val referenced = database.userDao().getAllMediaPaths().toSet()
                tempStore.cleanup(cutoff, CleanupPrefs.maxMediaBytes(appContext), referenced)
                CleanupPrefs.setLastCleanup(appContext, now)
            } catch (e: Exception) {
                Log.w(TAG, "cleanup failed: $e")
            }
        }
    }
}
