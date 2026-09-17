package com.ahmemory.app.data

data class ChatSession(
    val id: String,
    val title: String,
    val preview: String,
    val updatedAt: String,
)

data class ChatMessage(
    val role: String,
    val text: String,
    val kind: String = "chat",
)

data class ClarificationOption(
    val index: Int,
    val label: String,
    val uid: String,
)

data class Clarification(
    val mention: String,
    val kind: String,
    val options: List<ClarificationOption>,
)

data class TurnPayload(
    val userText: String,
    val responseText: String?,
    val responseError: String?,
    val status: String,
    val assertionUids: List<String>,
    val clarification: Clarification?,
    val tick: Int?,
    val phase: String,
    val detail: String? = null,
    val errorLog: String? = null,
    val failKind: String? = null,
)

data class MemoryNode(
    val uid: String,
    val kind: String?,
    val domain: String?,
    val semantic: String,
    val excitation: Float?,
    val output: Float?,
    val decayAge: Int?,
    val lifecycleState: String?,
    val inWorkspace: Boolean = false,
)

data class MemoryLink(
    val uid: String,
    val relationId: String,
    val sourceUid: String,
    val targetUid: String,
    val weight: Float,
)

data class ModelStatus(
    val ready: Boolean,
    val name: String,
    val label: String,
    val detail: String = "",
)

data class LlmModelOption(
    val id: String,
    val title: String,
    val detail: String,
    val sizeLabel: String,
)

data class LlmModelFileStatus(
    val id: String,
    val variantId: String,
    val title: String,
    val detail: String,
    val fileName: String,
    val path: String,
    val expectedBytes: Long,
    val bytesOnDisk: Long,
    val partBytes: Long,
    val complete: Boolean,
    val selected: Boolean,
)

data class ThinkingStep(
    val role: String,
    val title: String,
    val preview: String,
)

data class MemorySnapshot(
    val tick: Int,
    val threshold: Float,
    val workspaceCount: Int,
    val nodes: List<MemoryNode>,
    val links: List<MemoryLink>,
    val lastTurn: TurnPayload?,
    val phase: String,
    val sessionId: String?,
    val live: Boolean,
    val snapshotError: String? = null,
)

interface AhRepository {
    val live: Boolean
    fun listSessions(): List<ChatSession>
    fun newSession(): ChatSession
    fun openSession(id: String)
    fun deleteSession(id: String)
    fun messages(): List<ChatMessage>
    fun send(text: String): TurnPayload
    fun snapshot(): MemorySnapshot
    fun modelStatus(): ModelStatus
    fun modelVariant(): String = "e2b"
    fun hasModelChoice(): Boolean = true
    fun modelOptions(): List<LlmModelOption> = emptyList()
    fun modelInventory(): List<LlmModelFileStatus> = emptyList()
    fun modelsDirectory(): String = ""
    fun setModelVariant(id: String) = Unit
    fun deleteModel(id: String) = Unit
    fun isPreparing(): Boolean = false
    fun prepareError(): String? = null
    fun beginPrepare(variantId: String? = null) = start()
    fun beginDownload(fileId: String) = Unit
    fun thinkingTrace(): List<ThinkingStep>
    fun clearThinking()
    fun debugLog(): String
    fun start()
    fun stop()
}
