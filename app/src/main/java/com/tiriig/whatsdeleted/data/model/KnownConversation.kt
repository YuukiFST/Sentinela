package com.tiriig.whatsdeleted.data.model

import androidx.annotation.Keep

/** Projection for the (user, app) pairs listed on the allowlist screen. */
@Keep
data class KnownConversation(
    val user: String,
    val app: String
)
