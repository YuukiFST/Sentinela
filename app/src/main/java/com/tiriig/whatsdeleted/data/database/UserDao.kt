package com.tiriig.whatsdeleted.data.database

import androidx.lifecycle.LiveData
import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.model.DeletedMessage
import com.tiriig.whatsdeleted.data.model.KnownConversation

@Dao
interface UserDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun save(data: Chat)

    @Query("SELECT * from chat group by user,app order by MAX(dateTime) DESC")
    fun getChats(): LiveData<List<Chat>>

    @Query("SELECT * from chat where user =:user and app = :app order by dateTime DESC")
    fun getMessagesByUser(user: String,app: String): LiveData<List<Chat>>

    @Query("SELECT id,message,isDeleted,dateTime,mediaPath from chat where user =:user order by dateTime DESC LIMIT 1")
    fun getLastMessage(user: String): DeletedMessage?

    @Query("SELECT id,message,isDeleted,dateTime,mediaPath from chat where user =:user and app = :app order by dateTime DESC LIMIT 1")
    fun getLastMessageForChat(user: String, app: String): DeletedMessage?

    @Query("SELECT * from chat where dateTime >= :since order by dateTime DESC LIMIT 1")
    fun getMostRecentSince(since: Long): Chat?

    /**
     * Messages of the chat since [since] still open for a real file, newest
     * first: no media yet, or only a notification preview (`*_notif.*`,
     * see TempMediaStore.PREVIEW_NAME), which the full file replaces.
     */
    @Query("SELECT id,message,isDeleted,dateTime,mediaPath FROM chat WHERE `user` = :user AND app = :app AND dateTime >= :since AND (mediaPath IS NULL OR mediaPath LIKE '%_notif.%') ORDER BY dateTime DESC")
    suspend fun getMessagesAwaitingMedia(user: String, app: String, since: Long): List<DeletedMessage>

    /**
     * Conversations with messages plus those with settings, so a contact
     * whose history was deleted can still be switched back on.
     */
    @Query("SELECT `user`, app FROM chat UNION SELECT `user`, app FROM allowed_contact ORDER BY `user` COLLATE NOCASE")
    fun getKnownConversations(): LiveData<List<KnownConversation>>

    @Query("UPDATE chat set isDeleted =1 where id =:id")
    fun messageIsDeleted(id: String)

    @Query("UPDATE chat set mediaPath = :path where id = :id")
    suspend fun setMediaPath(id: String, path: String?)

    @Query("UPDATE chat set mediaPath = :path where id = :id AND mediaPath IS NULL")
    suspend fun setMediaPathIfEmpty(id: String, path: String)

    @Query("SELECT mediaPath FROM chat WHERE id = :id")
    suspend fun getMediaPath(id: String): String?

    @Query("SELECT mediaPath FROM chat WHERE mediaPath IS NOT NULL")
    suspend fun getAllMediaPaths(): List<String>

    @Query("SELECT mediaPath FROM chat WHERE mediaPath IS NOT NULL AND isDeleted = 1")
    suspend fun getDeletedMediaPaths(): List<String>

    @Query("SELECT mediaPath FROM chat WHERE `user` = :user AND app = :app AND mediaPath IS NOT NULL")
    suspend fun getMediaPathsForChat(user: String, app: String): List<String>

    @Query("DELETE FROM chat WHERE `user` = :user AND app = :app")
    suspend fun deleteChat(user: String, app: String)

    @Query("DELETE FROM chat WHERE dateTime < :cutoff")
    suspend fun deleteOlderThan(cutoff: Long): Int

    @Query("DELETE FROM Chat")
    fun clear()
}
