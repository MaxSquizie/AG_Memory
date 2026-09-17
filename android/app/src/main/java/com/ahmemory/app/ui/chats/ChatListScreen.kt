package com.ahmemory.app.ui.chats

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.ahmemory.app.data.ChatSession
import com.ahmemory.app.ui.AhViewModel
import com.ahmemory.app.ui.connectionLabel
import com.ahmemory.app.ui.theme.Black
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary

@Composable
fun ChatListScreen(viewModel: AhViewModel, onOpen: (String) -> Unit, onOpenSettings: () -> Unit = {}) {
    val state by viewModel.state.collectAsState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Black)
            .padding(horizontal = 20.dp, vertical = 16.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                Text("Чаты", color = TextPrimary, style = androidx.compose.material3.MaterialTheme.typography.titleLarge)
                Text(
                    state.connectionLabel(),
                    color = TextSecondary,
                    style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                )
            }
            TextButton(onClick = { viewModel.newChat(onOpen) }, enabled = !state.starting && state.startError == null && !state.needsModelChoice) {
                Text("Новый чат", color = TextPrimary)
            }
        }
        when {
            state.starting -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            state.modelLabel.ifBlank { "проверка ядра и модели…" },
                            color = TextSecondary,
                        )
                        if (state.modelLabel.contains("скачивается")) {
                            Text(
                                "первый запуск: 2.6–3.7 ГБ по сети",
                                color = TextSecondary,
                                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(top = 8.dp),
                            )
                        }
                    }
                }
            }
            state.needsModelChoice -> {
                Column(
                    Modifier.fillMaxSize().padding(top = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("Сначала выберите модель", color = TextPrimary)
                    Text("Gemma 4 E2B или E4B качается на телефон и работает без облака.", color = TextSecondary)
                    TextButton(onClick = onOpenSettings) {
                        Text("Открыть настройки", color = TextPrimary)
                    }
                }
            }
            state.startError != null -> {
                Column(
                    Modifier.fillMaxSize().padding(top = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("Ядро не стартовало", color = TextPrimary)
                    Text(state.startError.orEmpty(), color = TextSecondary)
                    TextButton(onClick = { viewModel.boot() }) {
                        Text("Повторить", color = TextPrimary)
                    }
                }
            }
            state.sessions.isEmpty() -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("Начните диалог", color = TextSecondary)
                }
            }
            else -> {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(state.sessions, key = { it.id }) { session ->
                        SessionRow(
                            session = session,
                            onOpen = {
                                viewModel.openSession(session.id)
                                onOpen(session.id)
                            },
                            onDelete = { viewModel.deleteSession(session.id) },
                        )
                        HorizontalDivider(color = Divider, thickness = 1.dp)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SessionRow(session: ChatSession, onOpen: () -> Unit, onDelete: () -> Unit) {
    val dismiss = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value == SwipeToDismissBoxValue.EndToStart || value == SwipeToDismissBoxValue.StartToEnd) {
                onDelete()
                true
            } else {
                false
            }
        },
    )
    SwipeToDismissBox(
        state = dismiss,
        backgroundContent = {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Black)
                    .padding(horizontal = 20.dp),
                contentAlignment = Alignment.CenterEnd,
            ) {
                Text("Удалить", color = TextSecondary)
            }
        },
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Black)
                .clickable(onClick = onOpen)
                .padding(vertical = 16.dp),
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    session.title.ifBlank { "Новый чат" },
                    color = TextPrimary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f).padding(end = 12.dp),
                )
                Text(formatTime(session.updatedAt), color = TextSecondary, style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
            }
            if (session.preview.isNotBlank()) {
                Text(
                    session.preview,
                    color = TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

private fun formatTime(raw: String): String {
    if (raw.length >= 16) return raw.substring(11, 16)
    return ""
}
