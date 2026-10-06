package com.tiriig.whatsdeleted.ui.allowlist

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.tiriig.whatsdeleted.databinding.ItemAllowedContactBinding
import com.tiriig.whatsdeleted.ui.chat.AllowedUi
import com.tiriig.whatsdeleted.utility.changeBackgroundColor
import com.tiriig.whatsdeleted.utility.name

class AllowedContactAdapter(
    private val onToggleMedia: (AllowedUi, Boolean) -> Unit,
    private val onToggleMessages: (AllowedUi, Boolean) -> Unit
) : ListAdapter<AllowedUi, AllowedContactAdapter.ViewHolder>(Diff()) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemAllowedContactBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ViewHolder(private val binding: ItemAllowedContactBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(item: AllowedUi) {
            binding.user.text = item.user
            binding.fromApp.text = item.app.name()
            binding.fromApp.changeBackgroundColor(item.app)
            // Avoid re-triggering the listeners on rebind.
            binding.messagesSwitch.setOnCheckedChangeListener(null)
            binding.messagesSwitch.isChecked = item.saveMessages
            binding.messagesSwitch.setOnCheckedChangeListener { _, checked ->
                onToggleMessages(item, checked)
            }
            binding.allowSwitch.setOnCheckedChangeListener(null)
            binding.allowSwitch.isChecked = item.allowed
            // An ignored contact has no messages to link media to.
            binding.allowSwitch.isEnabled = item.saveMessages
            binding.allowSwitch.setOnCheckedChangeListener { _, checked ->
                onToggleMedia(item, checked)
            }
        }
    }

    class Diff : DiffUtil.ItemCallback<AllowedUi>() {
        override fun areItemsTheSame(oldItem: AllowedUi, newItem: AllowedUi): Boolean {
            return oldItem.user == newItem.user && oldItem.app == newItem.app
        }

        override fun areContentsTheSame(oldItem: AllowedUi, newItem: AllowedUi): Boolean {
            return oldItem == newItem
        }
    }
}
