package com.tiriig.whatsdeleted.data.model

import androidx.annotation.Keep
import androidx.room.Entity

/**
 * Sentinela allowlist (opt-out): a conversation is monitored for media +
 * "deleted" alerts unless the user explicitly switched it OFF.
 * Absence of a row means "allowed" (default ON).
 */
@Keep
@Entity(tableName = "allowed_contact", primaryKeys = ["user", "app"])
data class AllowedContact(
    val user: String,
    val app: String,
    val allowed: Boolean = true
)
