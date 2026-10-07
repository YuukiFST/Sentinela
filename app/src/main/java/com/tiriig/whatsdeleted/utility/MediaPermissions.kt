package com.tiriig.whatsdeleted.utility

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
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

/**
 * Direct reads of the WhatsApp media folders. Stickers, GIFs and voice notes
 * sit behind `.nomedia`, so MediaStore never lists them; on Android 11+ only
 * "All files access" (MANAGE_EXTERNAL_STORAGE) can open them by path.
 */
fun Context.canReadWhatsAppFolders(): Boolean =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        Environment.isExternalStorageManager()
    } else {
        ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) ==
            PackageManager.PERMISSION_GRANTED
    }

/** Everything media capture needs: runtime media permissions plus folder access. */
fun Context.hasFullMediaAccess(): Boolean = hasMediaPermissions() && canReadWhatsAppFolders()

/**
 * Opens the settings screen granting "All files access" to this app (Android
 * 11+; older versions get folder access from READ_EXTERNAL_STORAGE). Some OEM
 * builds lack the per-app screen, so it falls back to the global list.
 * Example: `requireContext().openAllFilesAccessSettings()`
 */
fun Context.openAllFilesAccessSettings() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return
    try {
        startActivity(
            Intent(
                Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:$packageName")
            )
        )
    } catch (_: ActivityNotFoundException) {
        startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
    }
}

/**
 * Runtime permission behind one placeholder kind's MediaStore lookup. Stickers
 * live in the images collection and GIFs (.mp4) in the video one, when indexed.
 */
fun Context.hasMediaPermissionFor(kind: PlaceholderKind): Boolean {
    val tiramisu = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
    val perm = when {
        !tiramisu -> Manifest.permission.READ_EXTERNAL_STORAGE
        kind == PlaceholderKind.PHOTO || kind == PlaceholderKind.STICKER ->
            Manifest.permission.READ_MEDIA_IMAGES
        kind == PlaceholderKind.VIDEO || kind == PlaceholderKind.GIF ->
            Manifest.permission.READ_MEDIA_VIDEO
        else -> Manifest.permission.READ_MEDIA_AUDIO
    }
    return ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED
}
