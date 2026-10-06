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

    @Query("SELECT id,message,isDeleted,dateTime from chat where user =:user order by dateTime DESC LIMIT 1")
    fun getLastMessage(user: String): DeletedMessage?

    @Query("SELECT id,message,isDeleted,dateTime from chat where user =:user and app = :app order by dateTime DESC LIMIT 1")
    fun getLastMessageForChat(user: String, app: String): DeletedMessage?

    @Query("SELECT * from chat where dateTime >= :since order by dateTime DESC LIMIT 1")
    fun getMostRecentSince(since: Long): Chat?

    /** Distinct conversations ever seen, for the allowlist screen. */
    @Query("SELECT DISTINCT `user`, app FROM chat ORDER BY `user` COLLATE NOCASE")
    fun getKnownConversations(): LiveData<List<KnownConversation>>

    @Query("UPDATE chat set isDeleted =1 where id =:id")
    fun messageIsDeleted(id: String)

    @Query("UPDATE chat set mediaPath = :path where id = :id")
    suspend fun setMediaPath(id: String, path: String?)

    @Query("SELECT mediaPath FROM chat WHERE mediaPath IS NOT NULL")
    suspend fun getAllMediaPaths(): List<String>

    @Query("DELETE FROM chat WHERE dateTime < :cutoff")
    suspend fun deleteOlderThan(cutoff: Long): Int

    @Query("DELETE FROM Chat")
    fun clear()
}
