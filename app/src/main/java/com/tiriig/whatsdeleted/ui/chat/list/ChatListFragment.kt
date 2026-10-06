package com.tiriig.whatsdeleted.ui.chat.list

import android.os.Bundle
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuInflater
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import androidx.appcompat.app.AlertDialog
import androidx.core.view.MenuHost
import androidx.core.view.MenuProvider
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.navigation.fragment.findNavController
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.databinding.FragmentChatListBinding
import com.tiriig.whatsdeleted.ui.chat.ChatViewModel
import com.tiriig.whatsdeleted.utility.hide
import com.tiriig.whatsdeleted.utility.show
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class ChatListFragment : Fragment() {

    private val adapter = ChatListAdapter { confirmDelete(it) }
    private val viewModel: ChatViewModel by viewModels()

    private var _binding: FragmentChatListBinding? = null
    private val binding get() = _binding!!

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
