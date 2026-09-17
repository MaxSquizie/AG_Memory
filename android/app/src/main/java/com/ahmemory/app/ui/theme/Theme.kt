package com.ahmemory.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Scheme = darkColorScheme(
    primary = TextPrimary,
    onPrimary = Black,
    background = Black,
    onBackground = TextPrimary,
    surface = Surface,
    onSurface = TextPrimary,
    surfaceVariant = AssistantBubble,
    onSurfaceVariant = TextSecondary,
    outline = Divider,
    error = TextSecondary,
    onError = TextPrimary,
    secondary = TextSecondary,
    onSecondary = TextPrimary,
)

@Composable
fun AhTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Scheme,
        typography = Typography,
        content = content,
    )
}

val RippleWhite = Color(0x33FFFFFF)
