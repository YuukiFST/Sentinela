package com.tiriig.whatsdeleted.ui.chat.detail

import android.annotation.SuppressLint
import android.text.method.LinkMovementMethod
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.PopupMenu
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.bumptech.glide.Glide
import com.tiriig.whatsdeleted.R
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.model.ChatItem
import com.tiriig.whatsdeleted.databinding.ItemDateBinding
import com.tiriig.whatsdeleted.databinding.ItemMessageBinding
import com.tiriig.whatsdeleted.utility.MediaKind
import com.tiriig.whatsdeleted.utility.copyText
import com.tiriig.whatsdeleted.utility.formatTime
import com.tiriig.whatsdeleted.utility.openMediaFile
import java.io.File

class ChatDetailAdapter(
    private val onToggleFavorite: (Chat) -> Unit
) : ListAdapter<ChatItem, RecyclerView.ViewHolder>(ChatDetailDiffCallback()) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        return when (viewType) {
            VIEW_TYPE_DATE -> {
                val binding = ItemDateBinding.inflate(LayoutInflater.from(parent.context), parent, false)
                DateViewHolder(binding)
            }
            VIEW_TYPE_MESSAGE -> {
                val binding = ItemMessageBinding.inflate(LayoutInflater.from(parent.context), parent, false)
                MessageViewHolder(binding)
            }
            else -> throw IllegalArgumentException("Unknown view type $viewType")
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        val item = getItem(position)

        when (holder) {
            is DateViewHolder -> holder.bind((item as ChatItem.DateItem).date)
            is MessageViewHolder -> holder.bind((item as ChatItem.MessageItem).chat)
        }
    }

    override fun getItemViewType(position: Int): Int {
        return when (getItem(position)) {
            is ChatItem.DateItem -> VIEW_TYPE_DATE
            is ChatItem.MessageItem -> VIEW_TYPE_MESSAGE
        }
    }

    inner class DateViewHolder(private val binding: ItemDateBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(date: String) {
            binding.dateTv.text = date
        }
    }

    inner class MessageViewHolder(private val binding: ItemMessageBinding) :
        RecyclerView.ViewHolder(binding.root) {

        private var currentChat: Chat? = null

        init {
            // Links (autoLink="web" in XML) need a movement method to be tappable.
            binding.message.movementMethod = LinkMovementMethod.getInstance()
            // Long-press anywhere on the bubble: copy the text or (un)favorite it.
            val actionsListener = View.OnLongClickListener { anchor ->
                val chat = currentChat ?: return@OnLongClickListener false
                showActions(anchor, chat)
                true
            }
            binding.root.setOnLongClickListener(actionsListener)
            binding.message.setOnLongClickListener(actionsListener)
        }

        private fun showActions(anchor: View, chat: Chat) {
            val popup = PopupMenu(anchor.context, anchor)
            popup.menu.add(0, ACTION_COPY, 0, R.string.copy_message)
            popup.menu.add(
                0, ACTION_FAVORITE, 1,
                if (chat.isFavorite) R.string.favorite_remove else R.string.favorite_add
            )
            popup.setOnMenuItemClickListener { item ->
                when (item.itemId) {
                    ACTION_COPY -> anchor.context.copyText(chat.message)
                    ACTION_FAVORITE -> onToggleFavorite(chat)
                }
                true
            }
            popup.show()
        }

        @SuppressLint("SetTextI18n")
        fun bind(chat: Chat) {
            currentChat = chat
            binding.favoriteTag.isVisible = chat.isFavorite
            binding.deletedTag.isVisible = chat.isDeleted
            binding.root.setBackgroundResource(
                if (chat.isDeleted) R.drawable.deleted_message_background
                else R.drawable.message_background
            )
            binding.message.text = chat.message
            binding.date.text = chat.dateTime.formatTime()
            bindMedia(chat.mediaPath?.let(::File)?.takeIf { it.exists() })
        }

        // Images and videos get a thumbnail (Glide decodes a video frame);
        // audio has none, so videos and audio also get a text action.
        private fun bindMedia(file: File?) {
            val kind = file?.let { MediaKind.of(it) }
            val hasThumb = kind == MediaKind.IMAGE || kind == MediaKind.VIDEO
            binding.mediaThumb.isVisible = hasThumb
            binding.mediaOpen.isVisible = kind == MediaKind.VIDEO || kind == MediaKind.AUDIO
            if (hasThumb) {
                Glide.with(binding.mediaThumb).load(file).into(binding.mediaThumb)
            } else {
                Glide.with(binding.mediaThumb).clear(binding.mediaThumb)
            }
            if (kind == MediaKind.VIDEO) binding.mediaOpen.setText(R.string.open_video)
            if (kind == MediaKind.AUDIO) binding.mediaOpen.setText(R.string.play_audio)
            val open = file?.let { f -> View.OnClickListener { it.context.openMediaFile(f) } }
            binding.mediaThumb.setOnClickListener(open)
            binding.mediaOpen.setOnClickListener(open)
        }
    }

    class ChatDetailDiffCallback : DiffUtil.ItemCallback<ChatItem>() {
        override fun areItemsTheSame(oldItem: ChatItem, newItem: ChatItem): Boolean {
            return when {
                oldItem is ChatItem.DateItem && newItem is ChatItem.DateItem -> oldItem.date == newItem.date
                oldItem is ChatItem.MessageItem && newItem is ChatItem.MessageItem -> oldItem.chat.id == newItem.chat.id
                else -> false
            }
        }

        @SuppressLint("DiffUtilEquals")
        override fun areContentsTheSame(oldItem: ChatItem, newItem: ChatItem): Boolean {
            return oldItem == newItem
        }
    }

    companion object {
        private const val VIEW_TYPE_DATE = 0
        private const val VIEW_TYPE_MESSAGE = 1
        private const val ACTION_COPY = 1
        private const val ACTION_FAVORITE = 2
    }
}
