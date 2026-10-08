package com.tiriig.whatsdeleted.ui.allowlist

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.databinding.FragmentAllowedContactsBinding
import com.tiriig.whatsdeleted.ui.chat.ChatViewModel
import com.tiriig.whatsdeleted.utility.hide
import com.tiriig.whatsdeleted.utility.show
import dagger.hilt.android.AndroidEntryPoint

/**
 * Allowlist (opt-out): every known conversation listed with two switches
 * (default ON). Messages OFF = contact ignored, nothing saved. Media OFF =
 * no media copies + no "deleted" alert, text still saved. With the
 * `ignoredOnly` argument (ignoredContactsFragment) only ignored contacts are
 * listed, so one can be switched back on without searching the whole list.
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
        adapter = AllowedContactAdapter(
            onToggleMedia = { item, checked -> viewModel.setAllowed(item.user, item.app, checked) },
            onToggleMessages = { item, checked -> viewModel.setSaveMessages(item.user, item.app, checked) }
        )
        binding.recyclerView.adapter = adapter
        val ignoredOnly = arguments?.getBoolean("ignoredOnly") == true
        if (ignoredOnly) {
            binding.headerTv.setText(R.string.ignored_sub)
            binding.emptyTv.setText(R.string.ignored_empty)
        }
        viewModel.allowedUi.observe(viewLifecycleOwner) { all ->
            val rows = if (ignoredOnly) all.filter { !it.saveMessages } else all
            if (rows.isEmpty()) {
                binding.emptyTv.show()
            } else {
                binding.emptyTv.hide()
            }
            adapter.submitList(rows)
            binding.loading.hide()
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        binding.recyclerView.adapter = null
        _binding = null
    }
}
