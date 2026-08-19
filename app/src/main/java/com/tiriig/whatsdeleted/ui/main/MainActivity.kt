package com.tiriig.whatsdeleted.ui.main

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.os.bundleOf
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.navigation.findNavController
import androidx.navigation.fragment.NavHostFragment
import androidx.navigation.fragment.findNavController
import androidx.navigation.ui.setupActionBarWithNavController
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.databinding.ActivityMainBinding
import com.tiriig.whatsdeleted.services.NLService
import dagger.hilt.android.AndroidEntryPoint


@AndroidEntryPoint
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var navHost: NavHostFragment

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        binding = ActivityMainBinding.inflate(layoutInflater)
        val view = binding.root
        setContentView(view)
        applyEdgeToEdgeInsets()
        setUpMain()
        navigateToChatDetail()
        requestNotificationPermission()
    }

    private fun setUpMain() {
        setSupportActionBar(binding.toolbar)
        //Start the service
        val intent = Intent(applicationContext, NLService::class.java)
        startService(intent)

        //set up fragment Navigation
        navHost =
            supportFragmentManager.findFragmentById(R.id.nav_host_fragment) as NavHostFragment
        setupActionBarWithNavController(navHost.navController)
    }

    //Draws the toolbar behind the status bar and keeps content clear of both system bars
    private fun applyEdgeToEdgeInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(binding.root) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            binding.appBarLayout.updatePadding(top = bars.top)
            binding.navHostFragment.updatePadding(bottom = bars.bottom)
            insets
        }
    }

    //Needed from Android 13 onwards, otherwise the "message deleted" alert never shows up
    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return

        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun navigateToChatDetail() {
        val notiDeleted = intent.getBooleanExtra("notificationDeleted", false)
        val user = intent.getStringExtra("user")
        val app = intent.getStringExtra("app")
        if (notiDeleted) navHost.findNavController()
            .navigate(R.id.chatDetailFragment, bundleOf("user" to user, "app" to app))
    }

    override fun onSupportNavigateUp(): Boolean {
        return findNavController(R.id.nav_host_fragment).navigateUp()
    }
}