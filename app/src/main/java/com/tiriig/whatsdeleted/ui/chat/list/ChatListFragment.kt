package com.tiriig.whatsdeleted.ui.chat.list

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuInflater
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.view.MenuHost
import androidx.core.view.MenuProvider
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.navigation.fragment.findNavController
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.databinding.FragmentChatListBinding
import com.tiriig.whatsdeleted.services.MediaObserverService
import com.tiriig.whatsdeleted.ui.chat.ChatViewModel
import com.tiriig.whatsdeleted.utility.canReadWhatsAppFolders
import com.tiriig.whatsdeleted.utility.hasFullMediaAccess
import com.tiriig.whatsdeleted.utility.hasMediaPermissions
import com.tiriig.whatsdeleted.utility.hide
import com.tiriig.whatsdeleted.utility.mediaPermissions
import com.tiriig.whatsdeleted.utility.openAllFilesAccessSettings
import com.tiriig.whatsdeleted.utility.show
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class ChatListFragment : Fragment() {

    private val adapter = ChatListAdapter { confirmDelete(it) }
    private val viewModel: ChatViewModel by viewModels()

    private var _binding: FragmentChatListBinding? = null
    private val binding get() = _binding!!

    private val mediaPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
            refreshMediaBanner()
        }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentChatListBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        setupMenu()
        fetchChat()
        binding.mediaBannerBtn.setOnClickListener {
            if (!requireContext().hasMediaPermissions()) {
                mediaPermissionLauncher.launch(mediaPermissions())
            } else {
                requireContext().openAllFilesAccessSettings()
            }
        }
        refreshMediaBanner()
        setVersionLabel()
    }

    override fun onResume() {
        super.onResume()
        // Permission can be revoked in system Settings while we are away.
        if (_binding != null) refreshMediaBanner()
    }

    /**
     * Media capture needs the runtime permissions, then "All files access" for
     * stickers/GIFs/voice notes; text backup works without either. One step at
     * a time: the banner asks for whichever is still missing.
     */
    private fun refreshMediaBanner() {
        val context = requireContext()
        val runtimeGranted = context.hasMediaPermissions()
        binding.mediaBanner.isVisible = !runtimeGranted || !context.canReadWhatsAppFolders()
        binding.mediaBannerText.setText(
            if (runtimeGranted) R.string.media_perm_files_notice else R.string.media_perm_notice
        )
        binding.mediaBannerBtn.setText(
            if (runtimeGranted) R.string.media_perm_files_allow else R.string.media_perm_allow
        )
        // Watchers only attach to folders readable at start; restart after a grant.
        if (context.hasFullMediaAccess()) {
            try {
                context.startService(Intent(context, MediaObserverService::class.java))
            } catch (_: Exception) { }
        }
    }

    private fun setVersionLabel() {
        val version = try {
            val pm = requireContext().packageManager
            val info = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                pm.getPackageInfo(
                    requireContext().packageName,
                    PackageManager.PackageInfoFlags.of(0)
                )
            } else {
                @Suppress("DEPRECATION")
                pm.getPackageInfo(requireContext().packageName, 0)
            }
            info.versionName ?: ""
        } catch (_: Exception) {
            ""
        }
        binding.versionTv.text = if (version.isNotEmpty()) "v$version" else ""
    }

    private fun setupMenu() {
        (requireActivity() as MenuHost).addMenuProvider(
            object : MenuProvider {
                override fun onCreateMenu(menu: Menu, menuInflater: MenuInflater) {
                    menuInflater.inflate(R.menu.chat_list_menu, menu)
                }

                override fun onMenuItemSelected(menuItem: MenuItem): Boolean {
                    return if (menuItem.itemId == R.id.action_allowlist) {
                        findNavController().navigate(R.id.allowedContactsFragment)
                        true
                    } else false
                }
            },
            viewLifecycleOwner,
            Lifecycle.State.RESUMED
        )
    }

    private fun confirmDelete(chat: Chat) {
        AlertDialog.Builder(requireContext())
            .setTitle(getString(R.string.delete_chat_title, chat.user))
            .setMessage(R.string.delete_chat_body)
            .setPositiveButton(R.string.delete_chat) { _, _ ->
                viewModel.deleteConversation(chat.user, chat.app, ignore = false)
            }
            .setNeutralButton(R.string.delete_chat_and_ignore) { _, _ ->
                viewModel.deleteConversation(chat.user, chat.app, ignore = true)
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun fetchChat() {
        viewModel.getChatList.observe(viewLifecycleOwner) {
            if (it.isNullOrEmpty()) {
                binding.emptyIcon.show()
                binding.emptyTv.show()
            } else {
                binding.emptyIcon.hide()
                binding.emptyTv.hide()
            }
            adapter.submitList(it)
            binding.recyclerView.adapter = adapter
            binding.loading.hide()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        binding.recyclerView.adapter = null
        _binding = null
    }
}
