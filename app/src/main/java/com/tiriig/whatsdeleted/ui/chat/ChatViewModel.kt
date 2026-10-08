package com.tiriig.whatsdeleted.ui.chat

import androidx.lifecycle.LiveData
import androidx.lifecycle.MediatorLiveData
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.liveData
import androidx.lifecycle.viewModelScope
import com.tiriig.whatsdeleted.data.model.Chat
import com.tiriig.whatsdeleted.data.model.ChatItem
import com.tiriig.whatsdeleted.data.repository.ChatRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import java.util.Date
import javax.inject.Inject

/** One known conversation + its effective switches (default ON). */
data class AllowedUi(
    val user: String,
    val app: String,
    val allowed: Boolean,
    val saveMessages: Boolean
)

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: ChatRepository,
    private val savedStateHandle: SavedStateHandle
) : ViewModel() {

    val getChatList: LiveData<List<Chat>> = liveData {
        val response = repository.fetchChats()
        emitSource(response)
    }

    val getChatByUser: LiveData<List<Chat>> = liveData {
        val user = savedStateHandle.get<String>("user") ?: ""
        val app = savedStateHandle.get<String>("app") ?: ""
        val response = repository.fetchMessagesByUser(user,app)
        emitSource(response)
    }

    /** Known conversations merged with the opt-out allowlist (missing row = ON). */
    val allowedUi: LiveData<List<AllowedUi>> = MediatorLiveData<List<AllowedUi>>().apply {
        var known: List<com.tiriig.whatsdeleted.data.model.KnownConversation> = emptyList()
        var allow: List<com.tiriig.whatsdeleted.data.model.AllowedContact> = emptyList()
        fun merge() {
            value = known.map { k ->
                val row = allow.find { it.user == k.user && it.app == k.app }
                AllowedUi(k.user, k.app, row?.allowed ?: true, row?.saveMessages ?: true)
            }
        }
        addSource(repository.knownConversations()) { known = it ?: emptyList(); merge() }
        addSource(repository.allowlist()) { allow = it ?: emptyList(); merge() }
    }

    fun setAllowed(user: String, app: String, allowed: Boolean) {
        viewModelScope.launch {
            repository.setAllowed(user, app, allowed)
        }
    }

    fun setSaveMessages(user: String, app: String, save: Boolean) {
        viewModelScope.launch {
            repository.setSaveMessages(user, app, save)
        }
    }

    fun setFavorite(id: String, favorite: Boolean) {
        viewModelScope.launch {
            repository.setFavorite(id, favorite)
        }
    }

    /** [ignore] also stops saving anything new from this contact. Favorites stay. */
    fun deleteConversation(user: String, app: String, ignore: Boolean) {
        viewModelScope.launch {
            if (ignore) repository.setSaveMessages(user, app, false)
            repository.deleteConversation(user, app)
        }
    }
}
