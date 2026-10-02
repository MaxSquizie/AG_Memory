package com.ahmemory.app.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.ahmemory.app.data.LlmModelFileStatus
import com.ahmemory.app.ui.AhViewModel
import com.ahmemory.app.ui.connectionLabel
import com.ahmemory.app.ui.theme.Black
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary

@Composable
fun SettingsScreen(viewModel: AhViewModel) {
    val state by viewModel.state.collectAsState()
    DisposableEffect(Unit) {
        viewModel.startSettingsPolling()
        onDispose { viewModel.stopSettingsPolling() }
    }
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Black)
            .padding(horizontal = 20.dp, vertical = 16.dp),
    ) {
        Text("Настройки", color = TextPrimary, style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
        Text(
            state.connectionLabel(),
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(top = 6.dp, bottom = 16.dp),
        )
        Text("Папка моделей", color = TextPrimary)
        Text(
            state.modelsDir.ifBlank { "ещё не создана" },
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(top = 4.dp),
        )
        TextButton(
            onClick = {
                if (state.modelsDir.isNotBlank()) {
                    clipboard.setText(AnnotatedString(state.modelsDir))
                    copied = true
                }
            },
            enabled = state.modelsDir.isNotBlank(),
        ) {
            Text(if (copied) "путь скопирован" else "копировать путь", color = TextPrimary)
        }
        Text(
            "Файлы",
            color = TextPrimary,
            modifier = Modifier.padding(top = 8.dp, bottom = 4.dp),
        )
        Text(
            "скачать можно заранее, использовать — выбрать и загрузить в память",
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
        ) {
            if (state.modelInventory.isEmpty()) {
                Text("список моделей пуст", color = TextSecondary)
            } else {
                state.modelInventory.forEachIndexed { index, file ->
                    if (index > 0) HorizontalDivider(color = Divider, thickness = 1.dp)
                    ModelFileRow(
                        file = file,
                        busy = state.starting,
                        onUse = { viewModel.setModelVariant(file.id) },
                        onDownload = { viewModel.downloadModel(file.id) },
                        onDelete = { viewModel.deleteModel(file.id) },
                    )
                }
            }
            val log = state.modelDetail.ifBlank { state.startError.orEmpty() }
            if (log.isNotBlank() || state.starting) {
                HorizontalDivider(color = Divider, thickness = 1.dp, modifier = Modifier.padding(top = 16.dp))
                Row(
                    Modifier.fillMaxWidth().padding(top = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("лог загрузки", color = TextPrimary)
                    TextButton(
                        onClick = {
                            if (log.isNotBlank()) {
                                clipboard.setText(AnnotatedString(log))
                                copied = true
                            }
                        },
                        enabled = log.isNotBlank(),
                    ) {
                        Text(if (copied) "лог скопирован" else "копировать лог", color = TextPrimary)
                    }
                }
                Text(
                    state.modelLabel.ifBlank { if (state.starting) "загрузка модели…" else "—" },
                    color = TextPrimary,
                    style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
                if (log.isNotBlank()) {
                    Text(
                        log,
                        color = TextSecondary,
                        style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                        modifier = Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 24.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun ModelFileRow(
    file: LlmModelFileStatus,
    busy: Boolean,
    onUse: () -> Unit,
    onDownload: () -> Unit,
    onDelete: () -> Unit,
) {
    Column(Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(file.title, color = TextPrimary)
            Text(
                if (file.selected) "используется" else file.detail,
                color = if (file.selected) TextPrimary else TextSecondary,
                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            )
        }
        Text(
            file.path.ifBlank { file.fileName },
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(top = 4.dp),
        )
        Text(
            diskLabel(file),
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(top = 4.dp),
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onUse, enabled = !busy) {
                Text(if (file.selected && file.complete) "загрузить" else "использовать", color = TextPrimary)
            }
            TextButton(onClick = onDownload, enabled = !busy && !file.complete) {
                Text(if (file.partBytes > 0) "докачать" else "скачать", color = TextPrimary)
            }
            TextButton(onClick = onDelete, enabled = !busy && (file.complete || file.partBytes > 0 || file.bytesOnDisk > 0)) {
                Text("удалить", color = TextSecondary)
            }
        }
    }
}

private fun diskLabel(file: LlmModelFileStatus): String {
    val expected = gb(file.expectedBytes)
    return when {
        file.complete -> "на диске ${gb(file.bytesOnDisk)} из $expected"
        file.partBytes > 0 -> "недокачано ${gb(file.partBytes)} из $expected"
        file.bytesOnDisk > 0 -> "битый файл ${gb(file.bytesOnDisk)}, нужно $expected"
        else -> "нет на диске · $expected"
    }
}

private fun gb(bytes: Long): String =
    if (bytes <= 0L) "0 ГБ" else "${"%.2f".format(bytes / 1_000_000_000.0)} ГБ"
