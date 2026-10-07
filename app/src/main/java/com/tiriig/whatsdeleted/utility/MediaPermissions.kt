package com.tiriig.whatsdeleted.utility

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat

/**
 * Media permissions backing full-res photo/video/audio capture (text backup
 * needs none of these). Requested on the intro screen and re-requestable
 * from the chat-list banner whenever they are missing or revoked.
 */
fun mediaPermissions(): Array<String> {
    return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        arrayOf(
            Manifest.permission.READ_MEDIA_IMAGES,
            Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_MEDIA_AUDIO
        )
    } else {
        arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
    }
}

fun Context.hasMediaPermissions(): Boolean =
    mediaPermissions().all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

/** Single permission behind one placeholder kind (stickers/GIFs need none). */
fun Context.hasMediaPermissionFor(kind: PlaceholderKind): Boolean {
    val perm = when (kind) {
        PlaceholderKind.PHOTO -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_IMAGES
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }
        PlaceholderKind.VIDEO -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_VIDEO
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }
        PlaceholderKind.AUDIO -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_AUDIO
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }
        PlaceholderKind.STICKER, PlaceholderKind.GIF -> return true
    }
    return ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED
}
