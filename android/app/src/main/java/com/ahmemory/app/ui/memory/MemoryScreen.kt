package com.ahmemory.app.ui.memory

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
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
import com.ahmemory.app.data.MemoryNode
import com.ahmemory.app.ui.AhViewModel
import com.ahmemory.app.ui.connectionLabel
import com.ahmemory.app.ui.theme.Black
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.Surface
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.material3.HorizontalDivider

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MemoryScreen(viewModel: AhViewModel) {
    val state by viewModel.state.collectAsState()
    DisposableEffect(Unit) {
        viewModel.startMemoryPolling()
        onDispose { viewModel.stopMemoryPolling() }
    }
    val snap = state.snapshot
    var selected by remember { mutableStateOf<MemoryNode?>(null) }
    var copied by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Black)
            .padding(horizontal = 20.dp, vertical = 16.dp),
    ) {
        Text("Память", color = TextPrimary, style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
        val tick = snap?.tick ?: 0
        val threshold = snap?.threshold ?: 0.35f
        val workspaceCount = snap?.workspaceCount ?: 0
        val total = snap?.nodes?.size ?: 0
        Text(
            "tick $tick  ·  x > ${"%.2f".format(threshold)}  ·  $total узлов  ·  $workspaceCount в workspace",
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(top = 6.dp, bottom = 8.dp),
        )
        if (!snap?.snapshotError.isNullOrBlank()) {
            Text(
                snap?.snapshotError.orEmpty(),
                color = TextSecondary,
                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                state.connectionLabel(),
                color = TextSecondary,
                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            )
            TextButton(onClick = {
                viewModel.copyDebugLog { log ->
                    clipboard.setText(AnnotatedString(log))
                    copied = true
                }
            }) {
                Text(if (copied) "лог скопирован" else "копировать лог", color = TextPrimary)
            }
        }
        Text(
            "яркие узлы — workspace, остальные — вся память",
            color = TextSecondary,
            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        when {
            state.starting -> {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text(
                        state.modelLabel.ifBlank { "загрузка модели…" },
                        color = TextSecondary,
                    )
                }
            }
            !state.live -> {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("память пуста — ядро не запущено", color = TextPrimary)
                        Text(
                            state.modelLabel.ifBlank { state.startError.orEmpty().ifBlank { "выберите модель в настройках" } },
                            color = TextSecondary,
                            style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                        )
                    }
                }
            }
            snap == null || snap.nodes.isEmpty() -> {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text("пока пусто — после диалога здесь появятся узлы", color = TextSecondary)
                }
            }
            else -> {
                WorkspaceGraph(
                    snapshot = snap,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(320.dp)
                        .padding(vertical = 8.dp),
                    onNodeClick = { selected = it },
                )
                Text("Память", color = TextPrimary, modifier = Modifier.padding(top = 8.dp, bottom = 8.dp))
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(snap.nodes, key = { it.uid }) { node ->
                        WorkspaceRow(node)
                        HorizontalDivider(color = Divider, thickness = 1.dp)
                    }
                }
            }
        }
        val last = snap?.lastTurn
        Column(Modifier.fillMaxWidth().padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Последний ход", color = TextSecondary, style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
            Text("вход: ${last?.userText ?: "—"}", color = TextPrimary, maxLines = 2)
            Text("N: ${last?.assertionUids?.joinToString().orEmpty().ifBlank { "—" }}", color = TextSecondary, maxLines = 1)
            Text(
                "ответ: ${last?.responseText ?: last?.responseError ?: "—"}",
                color = TextPrimary,
                maxLines = 2,
            )
            val log = last?.errorLog ?: last?.detail
            if (!log.isNullOrBlank()) {
                Text(
                    log,
                    color = TextSecondary,
                    style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                    maxLines = 16,
                )
            }
        }
    }
    val node = selected
    if (node != null) {
        ModalBottomSheet(
            onDismissRequest = { selected = null },
            sheetState = rememberModalBottomSheetState(),
            containerColor = Surface,
            contentColor = TextPrimary,
        ) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(node.semantic.ifBlank { node.uid }, color = TextPrimary)
                Text("uid ${node.uid}", color = TextSecondary)
                Text("kind ${node.kind ?: "—"}  ·  domain ${node.domain ?: "—"}", color = TextSecondary)
                Text(if (node.inWorkspace) "в workspace" else "вне workspace", color = TextSecondary)
                Text("x ${node.excitation?.let { "%.3f".format(it) } ?: "—"}", color = TextSecondary)
                Text("age ${node.decayAge ?: "—"}  ·  ${node.lifecycleState ?: "—"}", color = TextSecondary)
                Box(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
private fun WorkspaceRow(node: MemoryNode) {
    val x = (node.excitation ?: 0f).coerceIn(0f, 1f)
    val labelColor = if (node.inWorkspace) TextPrimary else TextSecondary
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                buildString {
                    if (node.inWorkspace) append("● ")
                    append(node.semantic.ifBlank { node.uid })
                },
                color = labelColor,
                modifier = Modifier.weight(1f).padding(end = 12.dp),
                maxLines = 1,
            )
            Text(node.domain ?: node.kind ?: "", color = TextSecondary, style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
        }
        Box(
            Modifier
                .fillMaxWidth()
                .padding(top = 6.dp)
                .height(2.dp)
                .background(Divider),
        ) {
            Box(
                Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(x)
                    .background(if (node.inWorkspace) TextPrimary else TextSecondary.copy(alpha = 0.45f)),
            )
        }
    }
}
