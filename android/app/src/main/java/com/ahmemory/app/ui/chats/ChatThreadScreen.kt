package com.ahmemory.app.ui.chats

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import com.ahmemory.app.data.ChatMessage
import com.ahmemory.app.data.ThinkingStep
import com.ahmemory.app.ui.AhViewModel
import com.ahmemory.app.ui.connectionLabel
import com.ahmemory.app.ui.theme.AssistantBubble
import com.ahmemory.app.ui.theme.Black
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.Pulse
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary
import com.ahmemory.app.ui.theme.UserBubble
import com.ahmemory.app.ui.theme.UserText
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.TextButton
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily

@Composable
fun ChatThreadScreen(sessionId: String, viewModel: AhViewModel, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(sessionId) {
        if (state.currentSessionId != sessionId) {
            viewModel.openSession(sessionId)
        }
    }
    var draft by remember { mutableStateOf("") }
    var copied by remember { mutableStateOf(false) }
    val clipboard = LocalClipboardManager.current
    val listState = rememberLazyListState()
    LaunchedEffect(state.messages.size, state.thinking.size, state.sending) {
        val last = state.messages.size + if (state.sending || state.thinking.isNotEmpty()) 1 else 0
        if (last > 0) {
            listState.animateScrollToItem(last - 1)
        }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Black)
            .imePadding(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад", tint = TextPrimary)
            }
            Column(Modifier.weight(1f)) {
                Text(
                    state.sessions.firstOrNull { it.id == sessionId }?.title ?: "Чат",
                    color = TextPrimary,
                    style = androidx.compose.material3.MaterialTheme.typography.titleLarge,
                )
                Text(
                    state.connectionLabel(),
                    color = TextSecondary,
                    style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
                )
            }
            TextButton(onClick = {
                viewModel.copyDebugLog { log ->
                    clipboard.setText(AnnotatedString(log))
                    copied = true
                }
            }) {
                Text(if (copied) "лог скопирован" else "копировать лог", color = TextPrimary)
            }
        }
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(state.messages) { message ->
                MessageBubble(message)
            }
            if (state.sending || state.thinking.isNotEmpty()) {
                item {
                    ReasoningPanel(
                        sending = state.sending,
                        phase = state.phase,
                        steps = state.thinking,
                    )
                }
            }
        }
        val clarification = state.clarification
        if (clarification != null && clarification.options.isNotEmpty()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                clarification.options.forEach { option ->
                    Text(
                        option.label,
                        color = TextPrimary,
                        modifier = Modifier
                            .border(1.dp, Divider, RoundedCornerShape(18.dp))
                            .clickable { viewModel.send(option.label) }
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                    )
                }
            }
        }
        Composer(
            value = draft,
            onValueChange = { draft = it },
            enabled = !state.sending,
            onSend = {
                viewModel.send(draft)
                draft = ""
            },
        )
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.role == "user"
    val isError = message.kind == "error" || message.role == "system"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Box(
            modifier = Modifier
                .then(if (isError) Modifier.fillMaxWidth() else Modifier.widthIn(max = 320.dp))
                .background(
                    color = when {
                        isError -> Black
                        isUser -> UserBubble
                        else -> AssistantBubble
                    },
                    shape = RoundedCornerShape(18.dp),
                )
                .then(if (isError) Modifier.border(1.dp, Divider, RoundedCornerShape(18.dp)) else Modifier)
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            if (isError) {
                SelectionContainer {
                    Text(
                        text = message.text,
                        color = TextSecondary,
                        style = androidx.compose.material3.MaterialTheme.typography.labelSmall.copy(
                            fontFamily = FontFamily.Monospace,
                        ),
                    )
                }
            } else {
                Text(
                    text = message.text,
                    color = if (isUser) UserText else TextPrimary,
                )
            }
        }
    }
}

@Composable
private fun ReasoningPanel(
    sending: Boolean,
    phase: String,
    steps: List<ThinkingStep>,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(AssistantBubble, RoundedCornerShape(18.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (sending) {
            StatusLine(phase.ifBlank { "рассуждение…" })
        } else {
            Text("рассуждение", color = TextSecondary, style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
        }
        val visible = if (steps.size > 14) steps.takeLast(14) else steps
        visible.forEach { step ->
            val line = if (step.preview.isBlank()) step.title else "${step.title} — ${step.preview}"
            Text(
                line,
                color = TextSecondary,
                style = androidx.compose.material3.MaterialTheme.typography.labelSmall,
            )
        }
        if (sending && steps.isEmpty()) {
            Text("ожидаю первый запрос к модели…", color = TextSecondary, style = androidx.compose.material3.MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun StatusLine(phase: String) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val alpha by pulse.animateFloat(
        initialValue = 0.25f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "alpha",
    )
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(
            Modifier
                .size(7.dp)
                .alpha(alpha)
                .background(Pulse, CircleShape),
        )
        Text(phase, color = TextSecondary)
    }
}

@Composable
private fun Composer(
    value: String,
    onValueChange: (String) -> Unit,
    enabled: Boolean,
    onSend: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            enabled = enabled,
            cursorBrush = SolidColor(TextPrimary),
            textStyle = androidx.compose.material3.MaterialTheme.typography.bodyLarge.copy(color = TextPrimary),
            modifier = Modifier
                .weight(1f)
                .heightIn(min = 44.dp, max = 120.dp)
                .background(AssistantBubble, RoundedCornerShape(18.dp))
                .padding(horizontal = 14.dp, vertical = 12.dp),
            decorationBox = { inner ->
                if (value.isEmpty()) {
                    Text("Сообщение", color = TextSecondary)
                }
                inner()
            },
        )
        IconButton(
            onClick = onSend,
            enabled = enabled && value.isNotBlank(),
            modifier = Modifier
                .size(44.dp)
                .background(Black, CircleShape)
                .border(1.dp, TextPrimary, CircleShape),
        ) {
            Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Отправить", tint = TextPrimary)
        }
    }
}
