package com.tiriig.whatsdeleted.data.model

import androidx.annotation.Keep

/** Projection for "SELECT DISTINCT user, app FROM chat". */
@Keep
data class KnownConversation(
    val user: String,
    val app: String
)
