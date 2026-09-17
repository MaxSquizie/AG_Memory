package com.ahmemory.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.ahmemory.app.data.AhRepository
import com.ahmemory.app.data.ChatMessage
import com.ahmemory.app.data.ChatSession
import com.ahmemory.app.data.Clarification
import com.ahmemory.app.data.LlmModelFileStatus
import com.ahmemory.app.data.LlmModelOption
import com.ahmemory.app.data.MemorySnapshot
import com.ahmemory.app.data.ModelStatus
import com.ahmemory.app.data.ThinkingStep
import com.ahmemory.app.data.TurnPayload
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class AhUiState(
    val sessions: List<ChatSession> = emptyList(),
    val currentSessionId: String? = null,
    val messages: List<ChatMessage> = emptyList(),
    val snapshot: MemorySnapshot? = null,
    val phase: String = "idle",
    val sending: Boolean = false,
    val clarification: Clarification? = null,
    val live: Boolean = false,
    val starting: Boolean = true,
    val startError: String? = null,
    val error: String? = null,
    val modelReady: Boolean = false,
    val modelName: String = "",
    val modelLabel: String = "",
    val modelDetail: String = "",
    val modelVariant: String = "",
    val modelOptions: List<LlmModelOption> = emptyList(),
    val modelInventory: List<LlmModelFileStatus> = emptyList(),
    val modelsDir: String = "",
    val needsModelChoice: Boolean = false,
    val thinking: List<ThinkingStep> = emptyList(),
)

fun AhUiState.connectionLabel(): String = when {
    starting -> modelLabel.ifBlank { "проверка ядра и модели…" }
    needsModelChoice -> "выберите модель в настройках"
    startError != null -> "ядро не стартовало"
    !live -> "заглушка"
    modelReady -> "${modelName.ifBlank { "модель" }} · ${modelLabel.ifBlank { "подключена" }}"
    modelLabel.isNotBlank() -> "ядро · $modelLabel"
    else -> "ядро · модель не проверена"
}

class AhViewModel(private val repository: AhRepository) : ViewModel() {
    private val _state = MutableStateFlow(
        AhUiState(
            live = repository.live,
            starting = repository.hasModelChoice(),
            needsModelChoice = !repository.hasModelChoice(),
            modelVariant = repository.modelVariant(),
            modelOptions = repository.modelOptions(),
            modelInventory = repository.modelInventory(),
            modelsDir = repository.modelsDirectory(),
        ),
    )
    val state: StateFlow<AhUiState> = _state
    private var pollJob: Job? = null
    private var settingsPollJob: Job? = null

    init {
        if (repository.hasModelChoice()) boot()
    }

    fun boot() {
        if (!repository.hasModelChoice()) {
            _state.update {
                it.copy(
                    starting = false,
                    needsModelChoice = true,
                    startError = null,
                    modelOptions = repository.modelOptions(),
                    modelInventory = repository.modelInventory(),
                    modelsDir = repository.modelsDirectory(),
                    modelVariant = repository.modelVariant(),
                    modelLabel = "выберите модель",
                )
            }
            return
        }
        viewModelScope.launch {
            awaitPrepare(null)
        }
    }

    fun setModelVariant(id: String) {
        if (_state.value.starting) return
        if (id == _state.value.modelVariant && _state.value.modelReady && _state.value.live) return
        viewModelScope.launch {
            awaitPrepare(id)
        }
    }

    fun downloadModel(id: String) {
        if (_state.value.starting) return
        viewModelScope.launch {
            awaitJob(id, downloadOnly = true)
        }
    }

    fun deleteModel(id: String) {
        if (_state.value.starting) return
        viewModelScope.launch {
            withContext(Dispatchers.IO) { runCatching { repository.deleteModel(id) } }
            refreshModels()
            val model = withContext(Dispatchers.IO) {
                runCatching { repository.modelStatus() }.getOrDefault(ModelStatus(false, "", "нет статуса"))
            }
            _state.update {
                it.copy(
                    modelReady = model.ready,
                    modelName = model.name,
                    modelLabel = model.label,
                    modelDetail = model.detail,
                    modelVariant = repository.modelVariant(),
                    live = repository.live,
                )
            }
        }
    }

    private suspend fun awaitPrepare(variantId: String?) = awaitJob(variantId, downloadOnly = false)

    private suspend fun awaitJob(targetId: String?, downloadOnly: Boolean) {
        _state.update {
            it.copy(
                starting = true,
                needsModelChoice = false,
                startError = null,
                modelReady = if (downloadOnly) it.modelReady else false,
                modelLabel = when {
                    downloadOnly -> "скачивание…"
                    targetId == null -> "проверка ядра и модели…"
                    else -> "переключение модели…"
                },
                modelVariant = if (downloadOnly) it.modelVariant else targetId ?: it.modelVariant,
                modelOptions = repository.modelOptions(),
            )
        }
        val err = withContext(Dispatchers.IO) {
            runCatching {
                if (downloadOnly && !targetId.isNullOrBlank()) {
                    repository.beginDownload(targetId)
                } else {
                    repository.beginPrepare(targetId)
                }
            }.exceptionOrNull()
        }
        if (err != null) {
            _state.update {
                it.copy(
                    starting = false,
                    live = repository.live,
                    startError = if (repository.live || downloadOnly) null else err.message,
                    modelLabel = err.message.orEmpty(),
                    modelVariant = repository.modelVariant(),
                    modelInventory = repository.modelInventory(),
                    modelsDir = repository.modelsDirectory(),
                )
            }
            return
        }
        while (repository.isPreparing()) {
            delay(400)
            val model = repository.modelStatus()
            _state.update {
                it.copy(
                    modelReady = if (downloadOnly) it.modelReady else model.ready,
                    modelName = model.name,
                    modelLabel = model.label.ifBlank { it.modelLabel },
                    modelDetail = model.detail.ifBlank { it.modelDetail },
                    modelVariant = repository.modelVariant(),
                    modelInventory = repository.modelInventory(),
                    modelsDir = repository.modelsDirectory(),
                )
            }
        }
        val model = withContext(Dispatchers.IO) {
            runCatching { repository.modelStatus() }.getOrDefault(ModelStatus(false, "", "нет статуса"))
        }
        val prepareErr = repository.prepareError()
        _state.update {
            it.copy(
                starting = false,
                live = repository.live,
                startError = if (repository.live || downloadOnly) null else prepareErr,
                needsModelChoice = !repository.hasModelChoice(),
                modelReady = if (downloadOnly) it.modelReady || model.ready else model.ready,
                modelName = model.name,
                modelLabel = model.label.ifBlank { prepareErr.orEmpty() },
                modelDetail = model.detail.ifBlank { it.modelDetail },
                modelVariant = repository.modelVariant(),
                modelInventory = repository.modelInventory(),
                modelsDir = repository.modelsDirectory(),
            )
        }
        if (!downloadOnly && prepareErr == null && repository.live) {
            refreshSessions()
            refreshSnapshot()
        }
    }

    fun refreshModels() {
        val model = runCatching { repository.modelStatus() }.getOrNull()
        _state.update {
            it.copy(
                modelInventory = repository.modelInventory(),
                modelsDir = repository.modelsDirectory(),
                modelVariant = repository.modelVariant(),
                modelOptions = repository.modelOptions(),
                modelLabel = model?.label?.ifBlank { it.modelLabel } ?: it.modelLabel,
                modelDetail = model?.detail?.ifBlank { it.modelDetail } ?: it.modelDetail,
                modelName = model?.name?.ifBlank { it.modelName } ?: it.modelName,
                modelReady = model?.ready ?: it.modelReady,
            )
        }
    }

    fun refreshSessions() {
        viewModelScope.launch {
            val sessions = withContext(Dispatchers.IO) {
                runCatching { repository.listSessions() }.getOrDefault(emptyList())
            }
            val current = sessions.firstOrNull()?.id
            val messages = withContext(Dispatchers.IO) {
                runCatching { repository.messages() }.getOrDefault(emptyList())
            }
            _state.update {
                it.copy(sessions = sessions, currentSessionId = current ?: it.currentSessionId, messages = messages)
            }
        }
    }

    fun openSession(id: String) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { runCatching { repository.openSession(id) } }
            val messages = withContext(Dispatchers.IO) { runCatching { repository.messages() }.getOrDefault(emptyList()) }
            _state.update { it.copy(currentSessionId = id, messages = messages, clarification = null) }
            refreshSnapshot()
        }
    }

    fun newChat(onCreated: (String) -> Unit = {}) {
        viewModelScope.launch {
            val session = withContext(Dispatchers.IO) { repository.newSession() }
            _state.update {
                it.copy(
                    sessions = listOf(session) + it.sessions.filterNot { item -> item.id == session.id },
                    currentSessionId = session.id,
                    messages = emptyList(),
                    clarification = null,
                )
            }
            refreshSnapshot()
            onCreated(session.id)
        }
    }

    fun deleteSession(id: String) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { runCatching { repository.deleteSession(id) } }
            refreshSessions()
            refreshSnapshot()
        }
    }

    fun send(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty() || _state.value.sending) return
        viewModelScope.launch {
            withContext(Dispatchers.IO) { runCatching { repository.clearThinking() } }
            _state.update {
                it.copy(
                    sending = true,
                    phase = "формализация…",
                    error = null,
                    thinking = emptyList(),
                    messages = it.messages + ChatMessage("user", trimmed),
                )
            }
            val poll = launch {
                while (isActive) {
                    val steps = withContext(Dispatchers.IO) {
                        runCatching { repository.thinkingTrace() }.getOrDefault(emptyList())
                    }
                    _state.update { state ->
                        state.copy(
                            thinking = steps,
                            phase = steps.lastOrNull()?.title?.let { title -> "$title…" } ?: state.phase,
                        )
                    }
                    delay(280)
                }
            }
            val payload = withContext(Dispatchers.IO) {
                runCatching { repository.send(trimmed) }.getOrElse { err ->
                    TurnPayload(
                        userText = trimmed,
                        responseText = null,
                        responseError = "не разобрал",
                        status = "error",
                        assertionUids = emptyList(),
                        clarification = null,
                        tick = null,
                        phase = "idle",
                        detail = err.message,
                        errorLog = buildString {
                            appendLine("не разобрал")
                            appendLine("слой: exception")
                            append(err.stackTraceToString().take(2000))
                        },
                        failKind = "exception",
                    )
                }
            }
            poll.cancel()
            val steps = withContext(Dispatchers.IO) {
                runCatching { repository.thinkingTrace() }.getOrDefault(_state.value.thinking)
            }
            val loaded = withContext(Dispatchers.IO) { runCatching { repository.messages() }.getOrDefault(_state.value.messages) }
            val log = payload.errorLog
            val messages = when {
                log.isNullOrBlank() -> loaded
                loaded.lastOrNull()?.kind == "error" && loaded.last().text == "не разобрал" ->
                    loaded.dropLast(1) + loaded.last().copy(text = log)
                loaded.any { it.kind == "error" && it.text == log } -> loaded
                payload.status == "error" -> loaded + ChatMessage("system", log, "error")
                else -> loaded
            }
            val sessions = withContext(Dispatchers.IO) { runCatching { repository.listSessions() }.getOrDefault(_state.value.sessions) }
            refreshSnapshot()
            _state.update {
                it.copy(
                    sending = false,
                    phase = "idle",
                    messages = messages,
                    sessions = sessions,
                    thinking = steps,
                    clarification = payload.clarification,
                    error = payload.responseError,
                )
            }
        }
    }

    fun refreshSnapshot() {
        viewModelScope.launch {
            val snap = withContext(Dispatchers.IO) { runCatching { repository.snapshot() }.getOrNull() }
            if (snap == null) return@launch
            _state.update { it.copy(snapshot = snap, phase = snap.phase) }
        }
    }

    fun startMemoryPolling() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            while (isActive) {
                refreshSnapshot()
                delay(1000)
            }
        }
    }

    fun stopMemoryPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    fun startSettingsPolling() {
        if (settingsPollJob?.isActive == true) return
        refreshModels()
        settingsPollJob = viewModelScope.launch {
            while (isActive) {
                refreshModels()
                delay(800)
            }
        }
    }

    fun stopSettingsPolling() {
        settingsPollJob?.cancel()
        settingsPollJob = null
    }

    fun copyDebugLog(onReady: (String) -> Unit) {
        viewModelScope.launch {
            val text = withContext(Dispatchers.IO) { repository.debugLog() }
            onReady(text)
        }
    }

    class Factory(private val repository: AhRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = AhViewModel(repository) as T
    }
}
