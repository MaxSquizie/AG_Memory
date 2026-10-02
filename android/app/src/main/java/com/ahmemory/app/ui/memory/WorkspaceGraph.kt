package com.ahmemory.app.ui.memory

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import com.ahmemory.app.data.MemoryNode
import com.ahmemory.app.data.MemorySnapshot
import com.ahmemory.app.ui.theme.Divider
import com.ahmemory.app.ui.theme.TextPrimary
import com.ahmemory.app.ui.theme.TextSecondary
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun WorkspaceGraph(
    snapshot: MemorySnapshot?,
    modifier: Modifier = Modifier,
    onNodeClick: (MemoryNode) -> Unit,
) {
    val nodes = snapshot?.nodes.orEmpty()
    val links = snapshot?.links.orEmpty()
    val measurer = rememberTextMeasurer()
    val positions = remember(nodes.map { it.uid to it.inWorkspace }) {
        layoutGraph(nodes)
    }
    Canvas(
        modifier = modifier
            .fillMaxSize()
            .pointerInput(nodes, positions) {
                detectTapGestures { tap ->
                    val hit = positions.minByOrNull { (_, pos) ->
                        val dx = pos.x * size.width - tap.x
                        val dy = pos.y * size.height - tap.y
                        dx * dx + dy * dy
                    } ?: return@detectTapGestures
                    val distX = hit.value.x * size.width - tap.x
                    val distY = hit.value.y * size.height - tap.y
                    if (distX * distX + distY * distY < 48f * 48f) {
                        nodes.firstOrNull { it.uid == hit.key }?.let(onNodeClick)
                    }
                }
            },
    ) {
        val w = size.width
        val h = size.height
        links.forEach { link ->
            val a = positions[link.sourceUid] ?: return@forEach
            val b = positions[link.targetUid] ?: return@forEach
            val hot = (nodes.firstOrNull { it.uid == link.sourceUid }?.inWorkspace == true) &&
                (nodes.firstOrNull { it.uid == link.targetUid }?.inWorkspace == true)
            drawLine(
                color = if (hot) TextPrimary.copy(alpha = 0.45f) else Divider,
                start = Offset(a.x * w, a.y * h),
                end = Offset(b.x * w, b.y * h),
                strokeWidth = if (hot) 2f else 1f,
            )
        }
        nodes.forEach { node ->
            val pos = positions[node.uid] ?: return@forEach
            val center = Offset(pos.x * w, pos.y * h)
            val x = (node.excitation ?: 0.25f).coerceIn(0.12f, 1f)
            val radius = if (node.inWorkspace) 7f + 16f * x else 5f + 8f * x
            val ring = if (node.inWorkspace) TextPrimary else TextSecondary.copy(alpha = 0.55f)
            drawCircle(color = ring, radius = radius, center = center, style = Stroke(width = if (node.inWorkspace) 2.4f else 1f))
            drawCircle(
                color = Color.White.copy(alpha = if (node.inWorkspace) 0.16f * x + 0.12f else 0.05f),
                radius = radius,
                center = center,
            )
            val showLabel = node.inWorkspace || nodes.size <= 24
            if (showLabel) {
                val label = node.semantic.ifBlank { node.uid }.take(16)
                val layout = measurer.measure(
                    label,
                    TextStyle(color = if (node.inWorkspace) TextPrimary else TextSecondary, fontSize = 11.sp),
                )
                drawText(layout, topLeft = Offset(center.x - layout.size.width / 2f, center.y + radius + 5f))
            }
        }
    }
}

private fun layoutGraph(nodes: List<MemoryNode>): Map<String, Offset> {
    if (nodes.isEmpty()) return emptyMap()
    val hot = nodes.filter { it.inWorkspace }
    val cold = nodes.filter { !it.inWorkspace }
    if (cold.isEmpty()) return layoutCircle(hot, 0.5f, 0.48f, 0.32f)
    if (hot.isEmpty()) return layoutCircle(cold, 0.5f, 0.48f, 0.34f)
    return layoutCircle(hot, 0.5f, 0.48f, 0.20f) + layoutCircle(cold, 0.5f, 0.48f, 0.38f)
}

private fun layoutCircle(
    nodes: List<MemoryNode>,
    cx: Float,
    cy: Float,
    radius: Float,
): Map<String, Offset> {
    if (nodes.isEmpty()) return emptyMap()
    if (nodes.size == 1) return mapOf(nodes[0].uid to Offset(cx, cy))
    val n = nodes.size
    return nodes.mapIndexed { index, node ->
        val angle = (2.0 * Math.PI * index / n) - Math.PI / 2
        node.uid to Offset(
            (cx + radius * cos(angle)).toFloat(),
            (cy + radius * sin(angle)).toFloat(),
        )
    }.toMap()
}
