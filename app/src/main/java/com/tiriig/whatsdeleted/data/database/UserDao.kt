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

    /** Newest message of the chat since [since] that has no media linked yet. */
    @Query("SELECT id FROM chat WHERE `user` = :user AND app = :app AND dateTime >= :since AND mediaPath IS NULL ORDER BY dateTime DESC LIMIT 1")
    suspend fun getMessageAwaitingMedia(user: String, app: String, since: Long): String?

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
