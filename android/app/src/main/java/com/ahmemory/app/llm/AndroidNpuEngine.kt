package com.ahmemory.app.llm

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Process
import android.os.SystemClock
import android.util.Log
import com.ahmemory.app.AhApplication
import com.ahmemory.app.data.LlmModelFileStatus
import com.ahmemory.app.data.ModelStatus
import com.ahmemory.app.data.ThinkingStep
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.ExperimentalApi
import com.google.ai.edge.litertlm.ExperimentalFlags
import com.google.ai.edge.litertlm.LogSeverity
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import com.google.gson.Gson
import com.google.gson.JsonObject
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong

/**
 * On-device generator called from Python AndroidNpuBackend.generate().
 * Runs Gemma 4 E2B/E4B through LiteRT-LM (NPU on Pixel 10, else GPU, else CPU).
 */
object AndroidNpuEngine {
    private const val PREFS = "ah_llm"
    private const val PREF_VARIANT = "gemma_variant"
    private const val PREF_FILE = "gemma_file"
    private const val DOWNLOAD_PARTS = 8
    private const val USER_AGENT =
        "Mozilla/5.0 (Linux; Android 15; Pixel 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
    private val probeLock = Any()
    private val probeLog = StringBuilder()
    @Volatile private var nativeLogDumped = false
    private val statusLock = Any()
    @Volatile private var lastStatusAt = 0L
    private val gson = Gson()
    private val traces = CopyOnWriteArrayList<ThinkingStep>()
    private val logLock = Any()
    private val engineLock = Any()
    @Volatile private var logFile: File? = null
    @Volatile private var appContext: Context? = null
    @Volatile private var engine: Engine? = null
    @Volatile private var backendLabel = ""
    @Volatile private var variantId = ""
    @Volatile private var fileId = ""
    @Volatile var status: ModelStatus = ModelStatus(
        ready = false,
        name = GemmaCatalog.E2B_GPU.title,
        label = "не проверена",
    )
        private set

    fun attach(context: Context) {
        appContext = context.applicationContext
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        variantId = prefs.getString(PREF_VARIANT, "").orEmpty()
        fileId = prefs.getString(PREF_FILE, "").orEmpty()
        if (fileId.isBlank() && variantId.isNotBlank()) {
            fileId = GemmaCatalog.fileById(variantId).id
        }
        if (fileId.isNotBlank() && !status.ready) {
            status = status.copy(name = GemmaCatalog.fileById(fileId).title)
        }
    }

    fun variant(): String = fileId.ifBlank { variantId }

    fun hasModelChoice(): Boolean = fileId.isNotBlank() || variantId.isNotBlank()

    fun setVariant(id: String) {
        val file = GemmaCatalog.fileById(id)
        rememberChoice(file)
        closeEngine()
        status = ModelStatus(ready = false, name = file.title, label = "переключение…")
    }

    private fun rememberChoice(file: GemmaFile) {
        variantId = file.variantId
        fileId = file.id
        appContext?.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            ?.edit()
            ?.putString(PREF_VARIANT, file.variantId)
            ?.putString(PREF_FILE, file.id)
            ?.apply()
    }

    fun modelsDirectory(): String {
        val context = appContext ?: return ""
        return modelsDir(context).absolutePath
    }

    fun inventory(): List<LlmModelFileStatus> {
        val dir = appContext?.let { modelsDir(it) }
        return GemmaCatalog.files.map { spec ->
            val dest = dir?.let { File(it, spec.fileName) }
            LlmModelFileStatus(
                id = spec.id,
                variantId = spec.variantId,
                title = spec.title,
                detail = spec.detail,
                fileName = spec.fileName,
                path = dest?.absolutePath.orEmpty(),
                expectedBytes = spec.expectedBytes,
                bytesOnDisk = dest?.takeIf { it.isFile }?.length() ?: 0L,
                partBytes = dir?.let { partialBytes(it, spec.fileName) } ?: 0L,
                complete = dest != null && fileLooksComplete(dest, spec.expectedBytes),
                selected = fileId.isNotBlank() && spec.id == fileId,
            )
        }
    }

    fun deleteFile(id: String) {
        val context = appContext ?: return
        val spec = GemmaCatalog.fileById(id)
        deleteModelFiles(modelsDir(context), spec.fileName)
        if (fileId == spec.id) {
            closeEngine()
            status = ModelStatus(ready = false, name = spec.title, label = "файл удалён")
        }
    }

    fun downloadFile(id: String) {
        val context = appContext ?: throw IllegalStateException("нет контекста")
        val spec = GemmaCatalog.fileById(id)
        status = ModelStatus(ready = false, name = spec.title, label = "скачивается ${spec.title}…")
        download(spec.url, File(modelsDir(context), spec.fileName), spec.expectedBytes, spec.title)
        if (fileId != spec.id || engine == null) {
            status = ModelStatus(ready = false, name = spec.title, label = "скачан ${spec.title}")
        }
    }

    @JvmStatic
    fun generate(prompt: String, system: String, overrideJson: String, role: String): String {
        val override = runCatching { gson.fromJson(overrideJson, JsonObject::class.java) }.getOrNull()
        val maxTokens = override?.intOr("max_new_tokens")
            ?: if (role.startsWith("perception_")) 24 else 256
        val temperature = override?.floatOr("temperature")
            ?: if (role.startsWith("perception_") || role.startsWith("semantic_")) 0f else 0.2f
        val topP = override?.floatOr("top_p") ?: if (temperature <= 0f) 1f else 0.9f
        val topK = override?.intOr("top_k") ?: if (temperature <= 0f) 1 else 40
        val title = humanizeRole(role)
        pushTrace(role, title, "запрос…")
        val started = SystemClock.elapsedRealtime()
        return try {
            val text = complete(prompt, system, maxTokens, temperature, topP, topK)
            val elapsed = SystemClock.elapsedRealtime() - started
            pushTrace(role, title, "${compact(text)}  ·  ${elapsed}мс")
            appendLog(role, prompt, text, null, elapsed, maxTokens)
            Log.i(
                AhApplication.TAG,
                "npu role=$role backend=$backendLabel ms=$elapsed len=${text.length} first=${compact(text.lineSequence().firstOrNull().orEmpty())}",
            )
            text
        } catch (error: Throwable) {
            val elapsed = SystemClock.elapsedRealtime() - started
            pushTrace(role, title, "ошибка: ${error.message?.take(80).orEmpty()}")
            appendLog(role, prompt, "", error.message, elapsed, maxTokens)
            throw error
        }
    }

    fun probe(): ModelStatus {
        traces.clear()
        if (variantId.isBlank() && fileId.isBlank()) {
            status = ModelStatus(ready = false, name = "", label = "модель не выбрана")
            return status
        }
        val file = GemmaCatalog.fileById(fileId.ifBlank { variantId })
        status = ModelStatus(ready = false, name = file.title, label = "проверка…")
        status = probeOnDevice()
        Log.i(AhApplication.TAG, "model probe: ready=${status.ready} label=${status.label} detail=${status.detail}")
        return status
    }

    fun thinkingTrace(): List<ThinkingStep> = traces.toList()

    fun clearThinking() {
        traces.clear()
    }

    fun setLogFile(file: File) {
        file.parentFile?.mkdirs()
        logFile = file
    }

    fun readLogTail(limit: Int = 16000): String {
        val file = logFile ?: return ""
        if (!file.isFile) return ""
        val text = runCatching { file.readText() }.getOrDefault("")
        return if (text.length <= limit) text else text.takeLast(limit)
    }

    private fun probeOnDevice(): ModelStatus {
        val context = appContext
            ?: return ModelStatus(false, GemmaCatalog.fileById(fileId.ifBlank { variantId }).title, "нет контекста")
        val file = GemmaCatalog.fileById(fileId.ifBlank { variantId })
        resetProbeLog()
        noteProbe(deviceBanner(context))
        noteProbe("файл ${file.id}  ${file.fileName}  backend=${file.backend}")
        val dest = File(modelsDir(context), file.fileName)
        noteProbe("path ${dest.absolutePath}")
        noteProbe("size ${if (dest.isFile) dest.length() else 0} / ${file.expectedBytes}")
        val attempts = loadAttempts(context, file)
        noteProbe("попытки: ${attempts.joinToString { it.backendName }}")
        for (attempt in attempts) {
            try {
                val loaded = File(modelsDir(context), attempt.spec.fileName)
                if (fileLooksComplete(loaded, attempt.spec.expectedBytes)) {
                    publish("файл на диске, загрузка в ${attempt.backendName}…")
                } else {
                    publish("скачивается ${attempt.spec.title} для ${attempt.backendName}…")
                    noteProbe("догрузка ${attempt.spec.fileName}")
                }
                val modelFile = download(attempt.spec.url, loaded, attempt.spec.expectedBytes, attempt.spec.title)
                noteProbe("диск ${modelFile.length()} байт, initialize ${attempt.backendName}")
                publish("загрузка в ${attempt.backendName}…")
                openEngine(context, modelFile, attempt.backend)
                backendLabel = attempt.backendName
                if (attempt.spec.id != file.id) {
                    rememberChoice(attempt.spec)
                }
                noteProbe("engine ok, ping…")
                return ping(attempt.spec)
            } catch (error: Throwable) {
                closeEngine()
                val reason = error.fullText()
                noteProbe("FAIL ${attempt.backendName}: $reason")
                Log.w(AhApplication.TAG, "LiteRT ${attempt.backendName} failed for ${attempt.spec.id}", error)
                publish("ошибка ${attempt.backendName}")
            }
        }
        publish("не загрузилась")
        return ModelStatus(
            ready = false,
            name = file.title,
            label = "не загрузилась",
            detail = probeText(),
        )
    }

    private fun ping(file: GemmaFile): ModelStatus {
        return try {
            val text = complete("Reply with the single word OK.", "", 8, 0f, 1f, 1)
            noteProbe("ping ok: ${compact(text)}")
            ModelStatus(
                ready = true,
                name = file.title,
                label = "$backendLabel · отвечает",
                detail = probeText(),
            )
        } catch (error: Throwable) {
            closeEngine()
            noteProbe("FAIL ping: ${error.fullText()}")
            ModelStatus(
                ready = false,
                name = file.title,
                label = "движок есть, ping не прошёл",
                detail = probeText(),
            )
        }
    }

    private fun complete(
        prompt: String,
        system: String,
        maxTokens: Int,
        temperature: Float,
        topP: Float,
        topK: Int,
    ): String {
        val active = synchronized(engineLock) {
            engine ?: throw IllegalStateException("LiteRT-LM engine is not loaded")
        }
        val greedy = temperature <= 0f
        val sampler = if (backendLabel == "NPU") {
            null
        } else {
            SamplerConfig(
                topK = (if (topK <= 0) 1 else topK).coerceAtLeast(1),
                topP = (if (greedy) 1.0 else topP.toDouble().coerceIn(0.0, 1.0)),
                temperature = if (greedy) 0.0 else temperature.toDouble().coerceAtLeast(0.0),
            )
        }
        val config = if (backendLabel == "NPU") {
            ConversationConfig(
                systemInstruction = system.trim().takeIf { it.isNotEmpty() }?.let { Contents.of(it) },
                samplerConfig = null,
                maxOutputToken = maxTokens.coerceIn(1, 512),
            )
        } else {
            ConversationConfig(
                systemInstruction = system.trim().takeIf { it.isNotEmpty() }?.let { Contents.of(it) },
                samplerConfig = sampler,
                extraContext = mapOf("enable_thinking" to false),
                maxOutputToken = maxTokens.coerceIn(1, 4096),
                thinkingConfig = ThinkingConfig(enableThinking = false, thinkingTokenBudget = 0),
            )
        }
        active.createConversation(config).use { conversation ->
            val message = conversation.sendMessage(prompt.trim())
            val raw = message.toString()
            val text = messageText(message)
            Log.i(
                AhApplication.TAG,
                "npu raw class=${message.javaClass.name} rawLen=${raw.length} textLen=${text.length} raw=${compact(raw)}",
            )
            if (text.isEmpty()) {
                throw IllegalStateException("LiteRT-LM returned an empty completion raw=${compact(raw)}")
            }
            return text
        }
    }

    @OptIn(ExperimentalApi::class)
    private fun openEngine(context: Context, modelFile: File, backend: Backend) {
        synchronized(engineLock) {
            closeEngineLocked()
            val npu = backend is Backend.NPU
            val gpu = backend is Backend.GPU
            if (npu) clearLiteRtCaches(context, modelFile)
            val tries = if (npu) {
                listOf(
                    EngineTry(tokens = null, cacheDir = null),
                    EngineTry(tokens = 1024, cacheDir = null),
                    EngineTry(tokens = 1280, cacheDir = null),
                    EngineTry(tokens = 2048, cacheDir = ":nocache"),
                )
            } else if (gpu) {
                listOf(
                    EngineTry(tokens = 2048, cacheDir = null, mtp = true),
                    EngineTry(tokens = 2048, cacheDir = null, mtp = false),
                    EngineTry(tokens = 4096, cacheDir = null, mtp = false),
                )
            } else {
                listOf(EngineTry(tokens = 2048, cacheDir = null))
            }
            var lastError: Throwable? = null
            for (tryCfg in tries) {
                ExperimentalFlags.enableSpeculativeDecoding = tryCfg.mtp
                var candidate: Engine? = null
                val startedAt = SystemClock.elapsedRealtime()
                val step = buildString {
                    append("${backendName(backend)} tokens=${tryCfg.tokens ?: "default"} cache=${tryCfg.cacheDir ?: "рядом с моделью"}")
                    if (tryCfg.mtp) append(" mtp")
                }
                try {
                    if (npu) Engine.setNativeMinLogSeverity(LogSeverity.INFO)
                    publish("initialize $step")
                    noteProbe("try $step")
                    candidate = Engine(
                        EngineConfig(
                            modelPath = modelFile.absolutePath,
                            backend = backend,
                            maxNumTokens = tryCfg.tokens,
                            cacheDir = tryCfg.cacheDir,
                        ),
                    )
                    candidate.initialize()
                    engine = candidate
                    noteProbe("ok $step  ${SystemClock.elapsedRealtime() - startedAt}мс")
                    return
                } catch (error: Throwable) {
                    lastError = error
                    runCatching { candidate?.close() }
                    noteProbe("fail $step  ${SystemClock.elapsedRealtime() - startedAt}мс")
                    noteProbe("  ${error.fullText()}")
                    if (npu) noteNativeLogs()
                    Log.w(AhApplication.TAG, "engine init $step failed", error)
                }
            }
            throw lastError ?: IllegalStateException("LiteRT-LM engine failed to initialize")
        }
    }

    private data class EngineTry(
        val tokens: Int?,
        val cacheDir: String?,
        val mtp: Boolean = false,
    )

    private fun clearLiteRtCaches(context: Context, modelFile: File) {
        modelFile.parentFile?.listFiles()?.filter { file ->
            file.name.startsWith(modelFile.name) &&
                file.name != modelFile.name &&
                !file.name.endsWith(".part") &&
                !file.name.startsWith(modelFile.name + ".s") &&
                file.name != modelFile.name + ".dl"
        }?.forEach { it.delete() }
        context.cacheDir.listFiles()?.filter { it.name.startsWith("litertlm") }?.forEach {
            it.deleteRecursively()
        }
    }

    private fun npuLibraryDir(context: Context): String {
        // Gallery / LiteRT: pass the extracted APK lib dir. Do not copy a subset into
        // files/npu-libs — Android 12+ linker namespaces often refuse .so from there,
        // and a leftover JNI-only copy hid the Tensor dispatch library.
        File(context.filesDir, "npu-libs").deleteRecursively()
        val dir = File(context.applicationInfo.nativeLibraryDir)
        val so = dir.list()?.sorted().orEmpty()
        noteProbe("nativeLibDir ${dir.absolutePath}")
        noteProbe("so: ${so.joinToString().ifBlank { "(пусто)" }}")
        val dispatch = File(dir, "libLiteRtDispatch_GoogleTensor.so")
        val plugin = File(dir, "libLiteRtCompilerPlugin_google_tensor.so")
        if (dispatch.isFile) {
            noteProbe("dispatch ${dispatch.length()} байт  LiteRT 2.2.0")
        } else {
            noteProbe("dispatch НЕТ — пересоберите APK")
        }
        if (plugin.isFile) {
            noteProbe("plugin ${plugin.length()} байт")
        } else {
            noteProbe("plugin НЕТ libLiteRtCompilerPlugin_google_tensor.so")
        }
        noteProbe("preload dispatch: ${preloadNative("LiteRtDispatch_GoogleTensor")}")
        noteProbe("preload plugin: ${preloadNative("LiteRtCompilerPlugin_google_tensor")}")
        noteProbe("preload edgetpu: ${preloadNative("edgetpu_litert")}")
        return dir.absolutePath
    }

    private fun preloadNative(name: String): String {
        return runCatching {
            System.loadLibrary(name)
            "ok"
        }.getOrElse { error -> error.fullText() }
    }

    private fun noteNativeLogs() {
        if (nativeLogDumped) return
        nativeLogDumped = true
        val lines = runCatching {
            val proc = Runtime.getRuntime().exec(
                arrayOf("logcat", "-d", "-t", "200", "--pid", Process.myPid().toString()),
            )
            proc.inputStream.bufferedReader().use { it.readText() }
        }.getOrElse { error ->
            noteProbe("logcat: ${error.fullText()}")
            return
        }
        val keep = lines.lineSequence().filter { line ->
            val lower = line.lowercase()
            listOf(
                "litert", "edgetpu", "tachyon", "dispatch", "npu", "tpu",
                "enospc", "dma", "southbound", "compiled model", "warmup",
            ).any { it in lower }
        }.take(50).toList()
        if (keep.isEmpty()) {
            noteProbe("logcat: нет строк litert/edgetpu")
        } else {
            noteProbe("logcat:")
            keep.forEach { noteProbe("  $it") }
        }
    }

    private fun backendName(backend: Backend): String = when (backend) {
        is Backend.NPU -> "npu"
        is Backend.GPU -> "gpu"
        else -> "cpu"
    }

    private fun closeEngine() {
        synchronized(engineLock) { closeEngineLocked() }
    }

    private fun closeEngineLocked() {
        runCatching { engine?.close() }
        engine = null
        backendLabel = ""
    }

    private data class LoadAttempt(
        val backendName: String,
        val backend: Backend,
        val spec: GemmaFile,
    )

    private fun loadAttempts(context: Context, file: GemmaFile): List<LoadAttempt> {
        if (file.backend == "NPU") {
            return listOf(
                LoadAttempt(
                    "NPU",
                    Backend.NPU(nativeLibraryDir = npuLibraryDir(context)),
                    file,
                ),
            )
        }
        return listOf(
            LoadAttempt("GPU", Backend.GPU(), file),
            LoadAttempt("CPU", Backend.CPU(), file),
        )
    }

    private fun resetProbeLog() {
        synchronized(probeLock) {
            probeLog.setLength(0)
            nativeLogDumped = false
        }
    }

    private fun probeText(): String = synchronized(probeLock) { probeLog.toString() }

    private fun noteProbe(line: String) {
        synchronized(probeLock) {
            if (probeLog.isNotEmpty()) probeLog.append('\n')
            probeLog.append(line)
        }
        Log.i(AhApplication.TAG, line)
        status = status.copy(detail = probeText())
    }

    private fun publish(label: String) {
        val name = GemmaCatalog.fileById(fileId.ifBlank { variantId }).title
        status = ModelStatus(ready = false, name = name, label = label, detail = probeText())
    }

    private fun deviceBanner(context: Context): String {
        val soc = if (Build.VERSION.SDK_INT >= 31) Build.SOC_MODEL.orEmpty() else ""
        val mi = ActivityManager.MemoryInfo()
        (context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(mi)
        return buildString {
            append("Android ${Build.VERSION.RELEASE} sdk=${Build.VERSION.SDK_INT}")
            append("  ${Build.MODEL} / ${Build.DEVICE}")
            if (soc.isNotBlank()) append("  soc=$soc")
            append("  ram ${mi.availMem / 1_000_000} / ${mi.totalMem / 1_000_000} МБ")
            if (mi.lowMemory || mi.availMem < 2_000_000_000L) append("  мало RAM — закройте приложения перед TPU")
        }
    }

    private fun Throwable.fullText(): String {
        val parts = mutableListOf<String>()
        var current: Throwable? = this
        var depth = 0
        while (current != null && depth < 6) {
            val msg = current.message?.trim().orEmpty()
            parts += if (msg.isBlank()) current.javaClass.simpleName else "${current.javaClass.simpleName}: $msg"
            current = current.cause
            depth += 1
        }
        return parts.joinToString(" → ")
    }

    private fun isTensorG5(): Boolean {
        val soc = if (Build.VERSION.SDK_INT >= 31) Build.SOC_MODEL.orEmpty() else ""
        val haystack = listOf(
            soc,
            Build.MODEL,
            Build.DEVICE,
            Build.PRODUCT,
            Build.HARDWARE,
            Build.BOARD,
        ).joinToString(" ").lowercase()
        return haystack.contains("g5") ||
            haystack.contains("pixel 10") ||
            haystack.contains("frankel") ||
            haystack.contains("blazer") ||
            haystack.contains("mustang")
    }

    private fun modelsDir(context: Context): File =
        File(context.filesDir, "models").apply { mkdirs() }

    private fun download(url: String, dest: File, expectedBytes: Long, name: String): File {
        System.setProperty("http.keepAlive", "true")
        System.setProperty("http.maxConnections", "16")
        var lastError: Throwable? = null
        repeat(5) { attempt ->
            try {
                return downloadOnce(url, dest, expectedBytes, name)
            } catch (error: Throwable) {
                lastError = error
                Log.w(AhApplication.TAG, "download attempt ${attempt + 1} failed", error)
                status = ModelStatus(
                    ready = false,
                    name = name,
                    label = "повтор скачивания ${attempt + 1}/5…",
                    detail = error.message.orEmpty(),
                )
                Thread.sleep(2_000L * (attempt + 1))
            }
        }
        throw lastError ?: IllegalStateException("download failed")
    }

    private data class RemoteFile(val url: String, val size: Long, val ranges: Boolean)
    private data class DownloadPlan(val total: Long, val offset: Long, val count: Int)
    private data class DownloadSegment(val index: Int, val start: Long, val end: Long, val file: File) {
        val size: Long get() = end - start + 1
    }

    private fun downloadOnce(url: String, dest: File, expectedBytes: Long, name: String): File {
        if (fileLooksComplete(dest, expectedBytes)) return dest
        dest.parentFile?.mkdirs()
        val prefix = File(dest.parentFile, dest.name + ".part")
        if (fileLooksComplete(prefix, expectedBytes)) {
            return promotePart(prefix, dest)
        }
        if (dest.isFile && !fileLooksComplete(dest, expectedBytes)) {
            dest.delete()
        }
        val remote = resolveDownload(url, expectedBytes)
        val total = remote.size.takeIf { it > 0 } ?: expectedBytes
        if (!remote.ranges || total < 16L * 1024 * 1024) {
            return downloadSingle(remote.url, dest, prefix, total, name)
        }
        val plan = planParallel(dest, prefix, total)
        val remaining = plan.total - plan.offset
        val partSize = (remaining + plan.count - 1) / plan.count
        val segments = (0 until plan.count).map { index ->
            val start = plan.offset + index * partSize
            val end = (start + partSize - 1).coerceAtMost(plan.total - 1)
            DownloadSegment(index, start, end, File(dest.parentFile, "${dest.name}.s${index}of${plan.count}"))
        }.filter { it.start <= it.end }
        val copied = AtomicLong(
            plan.offset + segments.sumOf { seg ->
                seg.file.takeIf { it.isFile }?.length()?.coerceAtMost(seg.size) ?: 0L
            },
        )
        val startedAt = SystemClock.elapsedRealtime()
        val sessionStart = copied.get()
        publishDownloadProgress(name, copied.get(), plan.total, startedAt, sessionStart, plan.count)
        val pool = Executors.newFixedThreadPool(segments.size.coerceAtMost(DOWNLOAD_PARTS))
        try {
            val futures = segments.map { seg ->
                pool.submit {
                    downloadSegment(remote.url, seg, copied, plan.total, name, startedAt, sessionStart, plan.count)
                }
            }
            futures.forEach { future ->
                try {
                    future.get()
                } catch (error: java.util.concurrent.ExecutionException) {
                    throw error.cause ?: error
                }
            }
        } catch (error: Throwable) {
            val reason = error.message.orEmpty()
            if (reason.contains("ignored Range") || reason.contains("segment HTTP 400")) {
                Log.w(AhApplication.TAG, "parallel download unsupported, single stream", error)
                return downloadSingle(remote.url, dest, prefix, total, name)
            }
            throw error
        } finally {
            pool.shutdownNow()
        }
        status = ModelStatus(ready = false, name = name, label = "сборка файла…")
        val parts = buildList {
            if (plan.offset > 0L) add(prefix)
            addAll(segments.map { it.file })
        }
        concatFiles(parts, dest)
        cleanupTemps(dest)
        if (!fileLooksComplete(dest, expectedBytes) && dest.length() < 1_000_000_000L) {
            throw IllegalStateException("download incomplete: ${dest.length()} bytes")
        }
        return dest
    }

    private fun planParallel(dest: File, prefix: File, total: Long): DownloadPlan {
        val planFile = File(dest.parentFile, dest.name + ".dl")
        val existing = readPlan(planFile)
        val hasSegments = dest.parentFile?.listFiles()?.any {
            it.name.startsWith(dest.name + ".s") && it.name.contains("of")
        } == true
        if (existing != null && existing.total == total) {
            val prefixOk = existing.offset == 0L || (prefix.isFile && prefix.length() >= existing.offset)
            if (prefixOk) return existing
        }
        dest.parentFile?.listFiles()?.filter {
            it.name.startsWith(dest.name + ".s")
        }?.forEach { it.delete() }
        val offset = if (!hasSegments && prefix.isFile) prefix.length().coerceAtMost(total) else 0L
        val remaining = (total - offset).coerceAtLeast(0L)
        val count = when {
            remaining < 8L * 1024 * 1024 -> 1
            remaining < 64L * 1024 * 1024 -> 2
            else -> DOWNLOAD_PARTS
        }
        val plan = DownloadPlan(total, offset, count)
        planFile.writeText("total=$total\noffset=$offset\ncount=$count\n")
        return plan
    }

    private fun readPlan(file: File): DownloadPlan? {
        if (!file.isFile) return null
        val map = file.readLines().mapNotNull { line ->
            val i = line.indexOf('=')
            if (i <= 0) null else line.substring(0, i).trim() to line.substring(i + 1).trim()
        }.toMap()
        val total = map["total"]?.toLongOrNull() ?: return null
        val offset = map["offset"]?.toLongOrNull() ?: 0L
        val count = map["count"]?.toIntOrNull() ?: return null
        if (total <= 0L || count !in 1..16 || offset !in 0L..total) return null
        return DownloadPlan(total, offset, count)
    }

    private fun downloadSegment(
        url: String,
        seg: DownloadSegment,
        copied: AtomicLong,
        total: Long,
        name: String,
        startedAt: Long,
        sessionStart: Long,
        parts: Int,
    ) {
        var have = seg.file.takeIf { it.isFile }?.length()?.coerceAtMost(seg.size) ?: 0L
        if (have >= seg.size) return
        var lastError: Throwable? = null
        repeat(5) { attempt ->
            have = seg.file.takeIf { it.isFile }?.length()?.coerceAtMost(seg.size) ?: 0L
            if (have >= seg.size) return
            try {
                val from = seg.start + have
                val connection = openConnection(url, start = from, end = seg.end)
                try {
                    val code = connection.responseCode
                    if (code == 416 && have > 0L && seg.file.length() >= (seg.size * 8) / 10) return
                    if (code != 206 && !(code == 200 && from == seg.start && have == 0L)) {
                        throw IllegalStateException("segment HTTP $code")
                    }
                    if (code == 200 && connection.contentLengthLong > seg.size * 2) {
                        throw IllegalStateException("server ignored Range")
                    }
                    connection.inputStream.use { input ->
                        FileOutputStream(seg.file, have > 0L).use { output ->
                            val buf = ByteArray(1024 * 1024)
                            while (have < seg.size) {
                                val want = (seg.size - have).coerceAtMost(buf.size.toLong()).toInt()
                                val n = input.read(buf, 0, want)
                                if (n < 0) break
                                output.write(buf, 0, n)
                                have += n
                                copied.addAndGet(n.toLong())
                                publishDownloadProgress(name, copied.get(), total, startedAt, sessionStart, parts)
                            }
                        }
                    }
                } finally {
                    connection.disconnect()
                }
                if (have >= seg.size) return
                lastError = IllegalStateException("segment ${seg.index} short: $have/${seg.size}")
            } catch (error: Throwable) {
                lastError = error
                Log.w(AhApplication.TAG, "segment ${seg.index} attempt ${attempt + 1} failed", error)
                Thread.sleep(1_000L * (attempt + 1))
            }
        }
        throw lastError ?: IllegalStateException("segment ${seg.index} failed")
    }

    private fun downloadSingle(url: String, dest: File, tmp: File, total: Long, name: String): File {
        if (fileLooksComplete(tmp, total)) return promotePart(tmp, dest)
        if (tmp.isFile && total > 0 && tmp.length() > total * 2) tmp.delete()
        var copied = tmp.takeIf { it.isFile }?.length() ?: 0L
        val startedAt = SystemClock.elapsedRealtime()
        val sessionStart = copied
        val connection = openDownload(url, copied)
        try {
            val code = connection.responseCode
            if (code == 416) {
                if (fileLooksComplete(tmp, total) || tmp.length() > 1_000_000_000L) {
                    return promotePart(tmp, dest)
                }
                tmp.delete()
                return downloadSingle(url, dest, tmp, total, name)
            }
            val append = code == 206 && copied > 0
            if (!append && copied > 0) {
                connection.disconnect()
                tmp.delete()
                return downloadSingle(url, dest, tmp, total, name)
            }
            val knownTotal = connection.getHeaderField("Content-Range")?.substringAfter('/')?.toLongOrNull()
                ?: if (connection.contentLengthLong > 0) copied + connection.contentLengthLong else total
            connection.inputStream.use { input ->
                FileOutputStream(tmp, append).use { output ->
                    val buf = ByteArray(1024 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        output.write(buf, 0, n)
                        copied += n
                        publishDownloadProgress(name, copied, knownTotal, startedAt, sessionStart, 1)
                    }
                }
            }
        } finally {
            connection.disconnect()
        }
        if (!fileLooksComplete(tmp, total) && tmp.length() < 1_000_000_000L) {
            throw IllegalStateException("download incomplete: ${tmp.length()} bytes")
        }
        return promotePart(tmp, dest)
    }

    private fun concatFiles(parts: List<File>, dest: File) {
        val tmp = File(dest.parentFile, dest.name + ".assembling")
        tmp.delete()
        FileOutputStream(tmp).channel.use { out ->
            for (part in parts) {
                FileInputStream(part).channel.use { inn ->
                    var pos = 0L
                    val size = inn.size()
                    while (pos < size) {
                        val moved = inn.transferTo(pos, size - pos, out)
                        if (moved <= 0L) break
                        pos += moved
                    }
                }
            }
        }
        dest.delete()
        if (!tmp.renameTo(dest)) {
            tmp.copyTo(dest, overwrite = true)
            tmp.delete()
        }
    }

    private fun promotePart(tmp: File, dest: File): File {
        if (dest.absolutePath == tmp.absolutePath) return dest
        if (fileLooksComplete(dest, tmp.length()) && dest.length() >= tmp.length()) {
            tmp.delete()
            return dest
        }
        dest.delete()
        if (!tmp.renameTo(dest)) {
            tmp.copyTo(dest, overwrite = true)
            tmp.delete()
        }
        cleanupTemps(dest)
        return dest
    }

    private fun publishDownloadProgress(
        name: String,
        copied: Long,
        total: Long,
        startedAt: Long,
        sessionStart: Long,
        parts: Int,
    ) {
        val now = SystemClock.elapsedRealtime()
        synchronized(statusLock) {
            if (now - lastStatusAt < 250 && copied < total) return
            lastStatusAt = now
        }
        val pct = if (total > 0) ((copied * 100) / total).toInt().coerceIn(0, 100) else 0
        val elapsed = (now - startedAt).coerceAtLeast(1L)
        val bps = ((copied - sessionStart).coerceAtLeast(0L) * 1000.0) / elapsed
        val speed = formatSpeed(bps)
        val streams = if (parts > 1) " · $parts потоков" else ""
        status = ModelStatus(
            ready = false,
            name = name,
            label = "скачивается $name… $pct% · $speed$streams",
            detail = "$copied/$total",
        )
    }

    private fun formatSpeed(bps: Double): String = when {
        bps >= 1_000_000 -> "${"%.1f".format(bps / 1_000_000.0)} МБ/с"
        bps >= 1_000 -> "${"%.0f".format(bps / 1_000.0)} КБ/с"
        else -> "0 КБ/с"
    }

    private fun resolveDownload(url: String, expectedBytes: Long): RemoteFile {
        var current = url
        repeat(8) {
            val connection = openConnection(current, start = 0, end = 0)
            try {
                val code = connection.responseCode
                if (code in 300..399) {
                    current = nextLocation(current, connection)
                } else if (code == 200 || code == 206) {
                    val size = contentSize(connection, expectedBytes)
                    val acceptRanges = connection.getHeaderField("Accept-Ranges")
                        ?.contains("bytes", ignoreCase = true) == true
                    val onCdn = current.contains("cdn-lfs") ||
                        current.contains("cas-bridge") ||
                        current.contains("xethub") ||
                        current.contains("hf.co")
                    return RemoteFile(current, size, code == 206 || acceptRanges || onCdn)
                } else {
                    throw IllegalStateException("probe HTTP $code")
                }
            } finally {
                runCatching { connection.inputStream.close() }
                connection.disconnect()
            }
        }
        throw IllegalStateException("too many redirects")
    }

    private fun openDownload(url: String, resumeFrom: Long): HttpURLConnection {
        var current = url
        repeat(8) {
            val connection = openConnection(current, start = resumeFrom.takeIf { it > 0 }, end = null)
            val code = connection.responseCode
            if (code in 300..399) {
                current = nextLocation(current, connection)
                connection.disconnect()
            } else if (code == 200 || code == 206 || code == 416) {
                return connection
            } else {
                connection.disconnect()
                throw IllegalStateException("download HTTP $code")
            }
        }
        throw IllegalStateException("too many redirects")
    }

    private fun openConnection(url: String, start: Long? = null, end: Long? = null): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = 20_000
            readTimeout = 120_000
            useCaches = false
            setRequestProperty("User-Agent", USER_AGENT)
            setRequestProperty("Accept", "*/*")
            setRequestProperty("Accept-Encoding", "identity")
            setRequestProperty("Connection", "keep-alive")
            if (start != null) {
                val range = if (end != null) "bytes=$start-$end" else "bytes=$start-"
                setRequestProperty("Range", range)
            }
        }
    }

    private fun nextLocation(current: String, connection: HttpURLConnection): String {
        val next = connection.getHeaderField("Location")
            ?: throw IllegalStateException("redirect without Location (${connection.responseCode})")
        return if (next.startsWith("http")) next else URL(URL(current), next).toString()
    }

    private fun contentSize(connection: HttpURLConnection, expectedBytes: Long): Long {
        val ranged = connection.getHeaderField("Content-Range")?.substringAfter('/')?.toLongOrNull()
        val length = connection.contentLengthLong
        return when {
            ranged != null && ranged > 1_000_000L -> ranged
            length > 1_000_000L -> length
            else -> expectedBytes
        }
    }

    private fun partialBytes(dir: File, fileName: String): Long =
        dir.listFiles()?.asSequence()
            ?.filter { it.isFile && (it.name == "$fileName.part" || it.name.startsWith("$fileName.s")) }
            ?.sumOf { it.length() }
            ?: 0L

    private fun deleteModelFiles(dir: File, fileName: String) {
        File(dir, fileName).delete()
        cleanupTemps(File(dir, fileName))
    }

    private fun cleanupTemps(dest: File) {
        dest.parentFile?.listFiles()?.filter { file ->
            file.name == dest.name + ".part" ||
                file.name == dest.name + ".dl" ||
                file.name == dest.name + ".assembling" ||
                (file.name.startsWith(dest.name + ".s") && file.name.contains("of"))
        }?.forEach { it.delete() }
    }

    private fun fileLooksComplete(file: File, expectedBytes: Long): Boolean {
        if (!file.isFile) return false
        val size = file.length()
        if (size < 1_000_000_000L) return false
        if (expectedBytes <= 0L) return true
        val min = (expectedBytes * 8) / 10
        val max = expectedBytes * 2
        return size in min..max
    }

    private fun messageText(message: Message): String = message.toString().trim()

    private fun appendLog(role: String, prompt: String, response: String, error: String?, elapsedMs: Long, maxTokens: Int) {
        val file = logFile ?: return
        val first = response.trim().lineSequence().firstOrNull().orEmpty()
        val token = first.split(Regex("\\s+")).firstOrNull().orEmpty()
        val line = gson.toJson(
            mapOf(
                "ts" to System.currentTimeMillis(),
                "role" to role,
                "backend" to backendLabel,
                "variant" to variantId,
                "max_tokens" to maxTokens,
                "ms" to elapsedMs,
                "prompt" to prompt.take(800),
                "response" to response.take(800),
                "response_len" to response.length,
                "first_line" to first.take(120),
                "token" to token.take(80),
                "error" to (error ?: ""),
            )
        )
        synchronized(logLock) {
            runCatching { file.appendText(line + "\n") }
        }
        Log.i(AhApplication.TAG, "npu role=$role backend=$backendLabel ms=$elapsedMs err=${error ?: ""} out=${compact(response)}")
    }

    private fun pushTrace(role: String, title: String, preview: String) {
        traces += ThinkingStep(role = role, title = title, preview = preview)
        while (traces.size > 48) {
            traces.removeAt(0)
        }
    }

    private fun compact(text: String): String =
        text.replace('\n', ' ').trim().take(72)

    private fun humanizeRole(role: String): String {
        val key = role
            .removePrefix("perception_")
            .removePrefix("semantic_")
        return titles[role] ?: titles[key] ?: key.replace('_', ' ')
    }

    private val titles = mapOf(
        "agent" to "ответ",
        "agent_repair" to "повтор ответа",
        "agent_clarification" to "уточнение",
        "act_type" to "тип акта",
        "predicate_start" to "начало предиката",
        "predicate_end" to "конец предиката",
        "predicate_symbol" to "символ предиката",
        "predicate_symbol_verify" to "проверка предиката",
        "actant_start" to "начало актанта",
        "actant_end" to "конец актанта",
        "actant_role" to "роль актанта",
        "negation" to "отрицание",
        "query_mode" to "режим вопроса",
        "factivity" to "фактивность",
        "quantifier" to "квантор",
        "modal_operator" to "модальность",
        "discourse_relation" to "связь реплик",
        "lexeme_identity" to "лексема",
        "pronoun_coreference" to "местоимение",
        "frame_relation" to "отношение кадров",
    )
}

private fun JsonObject.intOr(key: String): Int? =
    if (has(key) && !get(key).isJsonNull) runCatching { get(key).asInt }.getOrNull() else null

private fun JsonObject.floatOr(key: String): Float? =
    if (has(key) && !get(key).isJsonNull) runCatching { get(key).asFloat }.getOrNull() else null
