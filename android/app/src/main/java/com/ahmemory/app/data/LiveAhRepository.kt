package com.ahmemory.app.data

import android.content.Context
import android.util.Log
import com.ahmemory.app.AhApplication
import com.ahmemory.app.llm.AndroidNpuEngine
import com.ahmemory.app.llm.GemmaCatalog
import com.ahmemory.app.llm.ModelPrepareService
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import java.io.File
import java.io.FileOutputStream

class LiveAhRepository(private val context: Context) : AhRepository {
    override val live: Boolean get() = started
    private val gson = Gson()
    private val root: File = File(context.filesDir, "ah")
    @Volatile private var started = false
    @Volatile private var preparing = false
    @Volatile private var lastPrepareError: String? = null
    private val startLock = Any()

    init {
        AndroidNpuEngine.attach(context)
    }

    override fun start() {
        if (started) return
        synchronized(startLock) {
            if (started) return
            try {
                if (!AndroidNpuEngine.hasModelChoice()) {
                    throw IllegalStateException("модель не выбрана")
                }
                extractAssets()
                AndroidNpuEngine.attach(context)
                AndroidNpuEngine.setLogFile(File(root, "debug/npu.jsonl"))
                AndroidNpuEngine.probe()
                if (!AndroidNpuEngine.status.ready) {
                    val status = AndroidNpuEngine.status
                    throw IllegalStateException(status.label.ifBlank { "модель не готова" })
                }
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(context))
                }
                val py = Python.getInstance()
                val bridge = py.getModule("ah.android_bridge")
                bridge.callAttr("bind_engine", AndroidNpuEngine)
                bridge.callAttr("start", root.absolutePath)
                started = true
                Log.i(AhApplication.TAG, "Chaquopy bridge started at ${root.absolutePath}")
            } catch (error: Throwable) {
                Log.e(AhApplication.TAG, "Live AH core failed to start", error)
                throw error
            }
        }
    }

    override fun stop() {
        if (!started) return
        runCatching {
            Python.getInstance().getModule("ah.android_bridge").callAttr("stop")
        }
        started = false
    }

    override fun listSessions(): List<ChatSession> {
        start()
        val raw = Python.getInstance().getModule("ah.android_bridge").callAttr("list_sessions_json").toString()
        return parseSessions(raw)
    }

    override fun newSession(): ChatSession {
        start()
        val bridge = Python.getInstance().getModule("ah.android_bridge")
        val id = bridge.callAttr("new_session").toString()
        bridge.callAttr("open_session", id)
        return ChatSession(id, "Новый чат", "", "")
    }

    override fun openSession(id: String) {
        start()
        Python.getInstance().getModule("ah.android_bridge").callAttr("open_session", id)
    }

    override fun deleteSession(id: String) {
        start()
        Python.getInstance().getModule("ah.android_bridge").callAttr("delete_session", id)
    }

    override fun messages(): List<ChatMessage> {
        start()
        val raw = Python.getInstance().getModule("ah.android_bridge").callAttr("messages_json").toString()
        return parseMessages(raw)
    }

    override fun send(text: String): TurnPayload {
        start()
        val raw = Python.getInstance().getModule("ah.android_bridge").callAttr("send", text).toString()
        return parseTurn(raw)
    }

    override fun snapshot(): MemorySnapshot {
        if (!started) {
            return MemorySnapshot(
                tick = 0,
                threshold = 0.35f,
                workspaceCount = 0,
                nodes = emptyList(),
                links = emptyList(),
                lastTurn = null,
                phase = "idle",
                sessionId = null,
                live = false,
            )
        }
        val raw = Python.getInstance().getModule("ah.android_bridge").callAttr("snapshot_json").toString()
        return parseSnapshot(raw)
    }

    override fun modelStatus(): ModelStatus = AndroidNpuEngine.status

    override fun modelVariant(): String = AndroidNpuEngine.variant()

    override fun hasModelChoice(): Boolean = AndroidNpuEngine.hasModelChoice()

    override fun modelOptions(): List<LlmModelOption> = GemmaCatalog.options

    override fun modelInventory(): List<LlmModelFileStatus> = AndroidNpuEngine.inventory()

    override fun modelsDirectory(): String = AndroidNpuEngine.modelsDirectory()

    override fun setModelVariant(id: String) {
        AndroidNpuEngine.attach(context)
        AndroidNpuEngine.setVariant(id)
        if (!started) {
            start()
            return
        }
        AndroidNpuEngine.probe()
        if (!AndroidNpuEngine.status.ready) {
            val status = AndroidNpuEngine.status
            throw IllegalStateException(
                listOf(status.label, status.detail).filter { it.isNotBlank() }.joinToString(" — "),
            )
        }
    }

    override fun isPreparing(): Boolean = preparing

    override fun prepareError(): String? = lastPrepareError

    override fun beginPrepare(variantId: String?) {
        lastPrepareError = null
        preparing = true
        try {
            ModelPrepareService.start(context, variantId, downloadOnly = false)
        } catch (error: Throwable) {
            preparing = false
            lastPrepareError = error.message?.ifBlank { error.toString() } ?: error.toString()
            throw error
        }
    }

    override fun beginDownload(fileId: String) {
        lastPrepareError = null
        preparing = true
        try {
            ModelPrepareService.start(context, fileId, downloadOnly = true)
        } catch (error: Throwable) {
            preparing = false
            lastPrepareError = error.message?.ifBlank { error.toString() } ?: error.toString()
            throw error
        }
    }

    override fun deleteModel(id: String) {
        AndroidNpuEngine.attach(context)
        AndroidNpuEngine.deleteFile(id)
    }

    fun runPrepare(targetId: String?, downloadOnly: Boolean) {
        lastPrepareError = null
        preparing = true
        try {
            if (downloadOnly && !targetId.isNullOrBlank()) {
                AndroidNpuEngine.attach(context)
                AndroidNpuEngine.downloadFile(targetId)
            } else if (!targetId.isNullOrBlank()) {
                setModelVariant(targetId)
            } else {
                start()
            }
            lastPrepareError = null
        } catch (error: Throwable) {
            lastPrepareError = error.message?.ifBlank { error.toString() } ?: error.toString()
            throw error
        } finally {
            preparing = false
        }
    }

    override fun thinkingTrace(): List<ThinkingStep> = AndroidNpuEngine.thinkingTrace()

    override fun clearThinking() {
        AndroidNpuEngine.clearThinking()
    }

    override fun debugLog(): String {
        val python = if (started) {
            runCatching {
                Python.getInstance().getModule("ah.android_bridge").callAttr("debug_log").toString()
            }.getOrDefault("")
        } else {
            "ядро не запущено"
        }
        val npu = AndroidNpuEngine.readLogTail()
        return buildString {
            appendLine("## npu.jsonl")
            appendLine(npu.ifBlank { "(empty)" })
            appendLine()
            append(python)
        }
    }

    private fun extractAssets() {
        copyAssetDir("ah", root)
    }

    private fun copyAssetDir(assetPath: String, dest: File) {
        val names = context.assets.list(assetPath) ?: return
        if (names.isEmpty()) {
            dest.parentFile?.mkdirs()
            context.assets.open(assetPath).use { input ->
                FileOutputStream(dest).use { output -> input.copyTo(output) }
            }
            return
        }
        dest.mkdirs()
        for (name in names) {
            copyAssetDir("$assetPath/$name", File(dest, name))
        }
    }

    private fun parseSessions(raw: String): List<ChatSession> {
        val json = runCatching { gson.fromJson(raw, JsonArray::class.java) }.getOrNull()
            ?: return emptyList()
        return json.map { el ->
            val obj = el.asJsonObject
            ChatSession(
                id = obj.str("id"),
                title = obj.str("title").ifBlank { "Новый чат" },
                preview = obj.str("preview"),
                updatedAt = obj.str("updated_at"),
            )
        }
    }

    private fun parseMessages(raw: String): List<ChatMessage> {
        val json = runCatching { gson.fromJson(raw, JsonArray::class.java) }.getOrNull()
            ?: return emptyList()
        return json.map { el ->
            val obj = el.asJsonObject
            ChatMessage(obj.str("role"), obj.str("text"), obj.str("kind").ifBlank { "chat" })
        }
    }

    private fun parseTurn(raw: String): TurnPayload {
        val obj = gson.fromJson(raw, JsonObject::class.java)
        return turnFrom(obj)
    }

    private fun parseSnapshot(raw: String): MemorySnapshot {
        val obj = gson.fromJson(raw, JsonObject::class.java)
        val nodes = obj.arr("nodes").map { el ->
            val n = el.asJsonObject
            MemoryNode(
                uid = n.str("uid"),
                kind = n.optStr("kind"),
                domain = n.optStr("domain"),
                semantic = n.str("semantic"),
                excitation = n.optFloat("excitation"),
                output = n.optFloat("output"),
                decayAge = n.optInt("decay_age"),
                lifecycleState = n.optStr("lifecycle_state"),
                inWorkspace = n.get("in_workspace")?.takeIf { it.isJsonPrimitive }?.asBoolean == true,
            )
        }
        val links = obj.arr("links").map { el ->
            val n = el.asJsonObject
            MemoryLink(
                uid = n.str("uid"),
                relationId = n.str("relation_id"),
                sourceUid = n.str("source_uid"),
                targetUid = n.str("target_uid"),
                weight = n.optFloat("weight") ?: 0f,
            )
        }
        val last = obj.get("last_turn")?.takeIf { it.isJsonObject }?.asJsonObject?.let { turnFrom(it) }
        return MemorySnapshot(
            tick = obj.optInt("tick") ?: 0,
            threshold = obj.optFloat("threshold") ?: 0.35f,
            workspaceCount = obj.optInt("workspace_count") ?: nodes.size,
            nodes = nodes,
            links = links,
            lastTurn = last,
            phase = obj.str("phase").ifBlank { "idle" },
            sessionId = obj.optStr("session_id"),
            live = true,
            snapshotError = obj.optStr("snapshot_error"),
        )
    }

    private fun turnFrom(obj: JsonObject): TurnPayload {
        val clarification = obj.obj("clarification")?.let { c ->
            Clarification(
                mention = c.str("mention"),
                kind = c.str("kind"),
                options = c.arr("options").mapNotNull { el ->
                    val o = el.takeIf { it.isJsonObject }?.asJsonObject ?: return@mapNotNull null
                    ClarificationOption(o.optInt("index") ?: 0, o.str("label"), o.str("uid"))
                },
            )
        }
        return TurnPayload(
            userText = obj.str("user_text"),
            responseText = obj.optStr("response_text"),
            responseError = obj.optStr("response_error"),
            status = obj.str("status").ifBlank { "ok" },
            assertionUids = obj.arr("assertion_uids").mapNotNull {
                it.takeIf { item -> item.isJsonPrimitive }?.asString
            },
            clarification = clarification,
            tick = obj.optInt("tick"),
            phase = obj.str("phase").ifBlank { "idle" },
            detail = obj.optStr("detail"),
            errorLog = obj.optStr("error_log"),
            failKind = obj.optStr("fail_kind"),
        )
    }
}

private fun JsonObject.str(key: String): String =
    if (has(key) && !get(key).isJsonNull) get(key).asString else ""

private fun JsonObject.optStr(key: String): String? =
    if (has(key) && !get(key).isJsonNull) get(key).asString else null

private fun JsonObject.optInt(key: String): Int? =
    if (has(key) && !get(key).isJsonNull) runCatching { get(key).asInt }.getOrNull() else null

private fun JsonObject.optFloat(key: String): Float? =
    if (has(key) && !get(key).isJsonNull) runCatching { get(key).asFloat }.getOrNull() else null

private fun JsonObject.arr(key: String): JsonArray =
    get(key)?.takeIf { it.isJsonArray }?.asJsonArray ?: JsonArray()

private fun JsonObject.obj(key: String): JsonObject? =
    get(key)?.takeIf { it.isJsonObject }?.asJsonObject
