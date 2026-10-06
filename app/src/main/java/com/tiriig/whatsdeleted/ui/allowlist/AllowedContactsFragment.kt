package com.tiriig.whatsdeleted.ui.allowlist

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.tiriig.whatsdeleted.databinding.FragmentAllowedContactsBinding
import com.tiriig.whatsdeleted.ui.chat.ChatViewModel
import com.tiriig.whatsdeleted.utility.hide
import com.tiriig.whatsdeleted.utility.show
import dagger.hilt.android.AndroidEntryPoint

/**
 * Allowlist (opt-out): every known conversation listed with a switch
 * (default ON). OFF = no staged media + no "deleted" alert for that chat.
 * Text is still saved for everyone.
 */
@AndroidEntryPoint
class AllowedContactsFragment : Fragment() {

    private val viewModel: ChatViewModel by viewModels()
    private lateinit var adapter: AllowedContactAdapter

    private var _binding: FragmentAllowedContactsBinding? = null
    private val binding get() = _binding!!

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentAllowedContactsBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        adapter = AllowedContactAdapter { item, checked ->
            viewModel.setAllowed(item.user, item.app, checked)
        }
        binding.recyclerView.adapter = adapter
        viewModel.allowedUi.observe(viewLifecycleOwner) {
            if (it.isNullOrEmpty()) {
                binding.emptyTv.show()
            } else {
                binding.emptyTv.hide()
            }
            adapter.submitList(it)
            binding.loading.hide()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        binding.recyclerView.adapter = null
        _binding = null
    }
}
