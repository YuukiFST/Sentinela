package com.tiriig.whatsdeleted.data.database

import androidx.lifecycle.LiveData
import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.tiriig.whatsdeleted.data.model.AllowedContact

@Dao
interface AllowedContactDao {

    @Upsert
    suspend fun upsert(contact: AllowedContact)

    /** Null when there is no row -> caller treats as allowed (opt-out). */
    @Query("SELECT allowed FROM allowed_contact WHERE `user` = :user AND app = :app")
    suspend fun isAllowedRaw(user: String, app: String): Boolean?

    @Query("SELECT * FROM allowed_contact ORDER BY `user` COLLATE NOCASE")
    fun listAll(): LiveData<List<AllowedContact>>

    @Query("SELECT * FROM allowed_contact ORDER BY `user` COLLATE NOCASE")
    suspend fun listAllSync(): List<AllowedContact>
}
