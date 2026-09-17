package com.ahmemory.app.data

import java.time.Instant

class MockAhRepository : AhRepository {
    override val live: Boolean = false

    private val sessions = mutableListOf(
        ChatSession("demo", "Иван купил хлеб", "Запомнил факт и держит его в Workspace", Instant.now().toString()),
    )
    private var currentId = "demo"
    private val threads = mutableMapOf(
        "demo" to mutableListOf(
            ChatMessage("user", "Иван купил хлеб"),
            ChatMessage("assistant", "Запомнил: Иван купил хлеб."),
        ),
    )
    private var lastTurn = TurnPayload(
        userText = "Иван купил хлеб",
        responseText = "Запомнил: Иван купил хлеб.",
        responseError = null,
        status = "ok",
        assertionUids = listOf("N1"),
        clarification = null,
        tick = 4,
        phase = "idle",
    )

    override fun listSessions(): List<ChatSession> = sessions.toList()

    override fun newSession(): ChatSession {
        val id = "s${sessions.size + 1}"
        val session = ChatSession(id, "Новый чат", "", Instant.now().toString())
        sessions.add(0, session)
        threads[id] = mutableListOf()
        currentId = id
        lastTurn = lastTurn.copy(userText = "", responseText = null, assertionUids = emptyList())
        return session
    }

    override fun openSession(id: String) {
        currentId = id
    }

    override fun deleteSession(id: String) {
        sessions.removeAll { it.id == id }
        threads.remove(id)
        if (currentId == id) {
            currentId = sessions.firstOrNull()?.id ?: newSession().id
        }
    }

    override fun messages(): List<ChatMessage> = threads[currentId].orEmpty()

    override fun send(text: String): TurnPayload {
        val thread = threads.getOrPut(currentId) { mutableListOf() }
        thread += ChatMessage("user", text)
        val reply = "Запомнил: $text"
        thread += ChatMessage("assistant", reply)
        val index = sessions.indexOfFirst { it.id == currentId }
        if (index >= 0) {
            sessions[index] = sessions[index].copy(title = text.take(80), preview = reply, updatedAt = Instant.now().toString())
        }
        lastTurn = TurnPayload(
            userText = text,
            responseText = reply,
            responseError = null,
            status = "ok",
            assertionUids = listOf("N${thread.size}"),
            clarification = null,
            tick = 4 + thread.size,
            phase = "idle",
        )
        return lastTurn
    }

    override fun snapshot(): MemorySnapshot {
        val n1 = MemoryNode("N1", "N", "H", lastTurn.userText.ifBlank { "Иван купил хлеб" }, 0.82f, 0.71f, 2, "hot", true)
        val s1 = MemoryNode("S1", "S", null, "Иван", 0.64f, 0.50f, 3, "hot", true)
        val s2 = MemoryNode("S2", "S", null, "хлеб", 0.58f, 0.44f, 3, "hot", true)
        val t1 = MemoryNode("T1", "T", "H", "купить", 0.61f, 0.48f, 3, "hot", true)
        return MemorySnapshot(
            tick = lastTurn.tick ?: 4,
            threshold = 0.35f,
            workspaceCount = 4,
            nodes = listOf(n1, s1, t1, s2),
            links = listOf(
                MemoryLink("L1", "AGENT", "N1", "S1", 0.4f),
                MemoryLink("L2", "PREDICATE", "N1", "T1", 0.4f),
                MemoryLink("L3", "OBJECT", "N1", "S2", 0.4f),
            ),
            lastTurn = lastTurn,
            phase = "idle",
            sessionId = currentId,
            live = false,
        )
    }

    override fun modelStatus(): ModelStatus =
        ModelStatus(ready = false, name = "", label = "заглушка")

    override fun modelVariant(): String = "e2b"

    override fun hasModelChoice(): Boolean = true

    override fun modelOptions(): List<LlmModelOption> = listOf(
        LlmModelOption("e2b-gpu", "Gemma 4 E2B", "заглушка", "≈ 2.6 ГБ"),
        LlmModelOption("e4b-gpu", "Gemma 4 E4B", "заглушка", "≈ 3.7 ГБ"),
    )

    override fun modelInventory(): List<LlmModelFileStatus> = listOf(
        LlmModelFileStatus(
            id = "e2b-gpu",
            variantId = "e2b",
            title = "Gemma 4 E2B",
            detail = "GPU или CPU",
            fileName = "gemma-4-E2B-it.litertlm",
            path = "/data/data/com.ahmemory.app/files/models/gemma-4-E2B-it.litertlm",
            expectedBytes = 2_588_147_712L,
            bytesOnDisk = 0L,
            partBytes = 0L,
            complete = false,
            selected = false,
        ),
        LlmModelFileStatus(
            id = "e2b-npu",
            variantId = "e2b",
            title = "Gemma 4 E2B · TPU",
            detail = "Pixel 10 Tensor G5",
            fileName = "gemma-4-E2B-it_Google_Tensor_G5.litertlm",
            path = "/data/data/com.ahmemory.app/files/models/gemma-4-E2B-it_Google_Tensor_G5.litertlm",
            expectedBytes = 3_113_545_589L,
            bytesOnDisk = 0L,
            partBytes = 0L,
            complete = false,
            selected = false,
        ),
        LlmModelFileStatus(
            id = "e4b-gpu",
            variantId = "e4b",
            title = "Gemma 4 E4B",
            detail = "GPU или CPU",
            fileName = "gemma-4-E4B-it.litertlm",
            path = "/data/data/com.ahmemory.app/files/models/gemma-4-E4B-it.litertlm",
            expectedBytes = 3_659_530_240L,
            bytesOnDisk = 0L,
            partBytes = 0L,
            complete = false,
            selected = false,
        ),
    )

    override fun modelsDirectory(): String = "/data/data/com.ahmemory.app/files/models"

    override fun setModelVariant(id: String) = Unit

    override fun deleteModel(id: String) = Unit

    override fun beginPrepare(variantId: String?) = Unit

    override fun beginDownload(fileId: String) = Unit

    override fun thinkingTrace(): List<ThinkingStep> = emptyList()

    override fun clearThinking() = Unit

    override fun debugLog(): String = "mock runtime, no logs"

    override fun start() = Unit
    override fun stop() = Unit
}
