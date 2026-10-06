package com.tiriig.whatsdeleted.utility

import android.content.Context

/** Simple SharedPreferences backing the automatic cleanup (Tarefa 4). No UI: defaults apply. */
object CleanupPrefs {
    private const val NAME = "sentinela_prefs"
    private const val KEY_RETENTION_DAYS = "retention_days"
    private const val KEY_MAX_MEDIA_BYTES = "max_media_bytes"
    private const val KEY_LAST_CLEANUP = "last_cleanup"
    private const val DAY_MS = 24L * 60 * 60 * 1000

    const val DEFAULT_RETENTION_DAYS = 30
    const val DEFAULT_MAX_MEDIA_BYTES = 500L * 1024 * 1024 // 500MB

    private fun prefs(context: Context) =
        context.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    fun retentionDays(context: Context): Int =
        prefs(context).getInt(KEY_RETENTION_DAYS, DEFAULT_RETENTION_DAYS).takeIf { it > 0 }
            ?: DEFAULT_RETENTION_DAYS

    fun setRetentionDays(context: Context, days: Int) {
        prefs(context).edit().putInt(KEY_RETENTION_DAYS, days).apply()
    }

    fun maxMediaBytes(context: Context): Long =
        prefs(context).getLong(KEY_MAX_MEDIA_BYTES, DEFAULT_MAX_MEDIA_BYTES).takeIf { it > 0 }
            ?: DEFAULT_MAX_MEDIA_BYTES

    fun setMaxMediaBytes(context: Context, bytes: Long) {
        prefs(context).edit().putLong(KEY_MAX_MEDIA_BYTES, bytes).apply()
    }

    fun lastCleanup(context: Context): Long =
        prefs(context).getLong(KEY_LAST_CLEANUP, 0L)

    fun setLastCleanup(context: Context, now: Long) {
        prefs(context).edit().putLong(KEY_LAST_CLEANUP, now).apply()
    }

    fun retentionCutoff(context: Context, now: Long): Long =
        now - retentionDays(context) * DAY_MS
}
