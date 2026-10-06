package com.tiriig.whatsdeleted.data.model

import androidx.annotation.Keep
import androidx.room.ColumnInfo
import androidx.room.Entity

/**
 * Sentinela per-conversation settings (opt-out, absence of a row = all ON).
 * [allowed]: media copies + "deleted" alerts. [saveMessages]: text capture;
 * OFF means the contact is ignored entirely (added in v6).
 */
@Keep
@Entity(tableName = "allowed_contact", primaryKeys = ["user", "app"])
data class AllowedContact(
    val user: String,
    val app: String,
    val allowed: Boolean = true,
    @ColumnInfo(defaultValue = "1")
    val saveMessages: Boolean = true
)
