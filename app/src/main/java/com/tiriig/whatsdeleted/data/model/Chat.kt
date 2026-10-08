package com.tiriig.whatsdeleted.data.model

import androidx.annotation.Keep
import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Keep
@Entity
data class Chat(
    @PrimaryKey
    val id: String,
    val user: String,
    val message: String,
    val dateTime: Long,
    @ColumnInfo(defaultValue = "")
    val app: String,
    val isDeleted: Boolean = false,
    val isGroup: Boolean = false,
    /** Local staged copy of media attached on deletion (nullable, added in v5). */
    val mediaPath: String? = null,
    /** Starred by the user: kept by "Excluir" and by the automatic cleanup (added in v7). */
    @ColumnInfo(defaultValue = "0")
    val isFavorite: Boolean = false,
)
