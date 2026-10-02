package com.ahmemory.app.llm

import com.ahmemory.app.data.LlmModelOption

internal data class GemmaFile(
    val id: String,
    val variantId: String,
    val title: String,
    val detail: String,
    val fileName: String,
    val url: String,
    val expectedBytes: Long,
    val backend: String,
)

internal object GemmaCatalog {
    val E2B_GPU = GemmaFile(
        id = "e2b-gpu",
        variantId = "e2b",
        title = "Gemma 4 E2B",
        detail = "GPU или CPU",
        fileName = "gemma-4-E2B-it.litertlm",
        url = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm?download=true",
        expectedBytes = 2_588_147_712L,
        backend = "GPU",
    )

    val E2B_NPU = GemmaFile(
        id = "e2b-npu",
        variantId = "e2b",
        title = "Gemma 4 E2B · TPU",
        detail = "Pixel 10 Tensor G5",
        fileName = "gemma-4-E2B-it_Google_Tensor_G5.litertlm",
        url = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it_Google_Tensor_G5.litertlm?download=true",
        expectedBytes = 3_113_545_589L,
        backend = "NPU",
    )

    val E4B_GPU = GemmaFile(
        id = "e4b-gpu",
        variantId = "e4b",
        title = "Gemma 4 E4B",
        detail = "GPU или CPU",
        fileName = "gemma-4-E4B-it.litertlm",
        url = "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it.litertlm?download=true",
        expectedBytes = 3_659_530_240L,
        backend = "GPU",
    )

    val files = listOf(E2B_GPU, E2B_NPU, E4B_GPU)

    fun fileById(id: String): GemmaFile {
        val key = id.trim()
        return files.firstOrNull { it.id.equals(key, ignoreCase = true) }
            ?: files.firstOrNull { it.variantId.equals(key, ignoreCase = true) }
            ?: E2B_GPU
    }

    val options = files.map { file ->
        LlmModelOption(
            id = file.id,
            title = file.title,
            detail = file.detail,
            sizeLabel = "≈ ${"%.1f".format(file.expectedBytes / 1_000_000_000.0)} ГБ",
        )
    }
}
