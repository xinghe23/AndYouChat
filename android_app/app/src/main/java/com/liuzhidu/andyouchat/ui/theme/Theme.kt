package com.liuzhidu.andyouchat.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/* ---- 配色：与 web/src/styles.css 逐项对齐 ---- */
val Brand = Color(0xFF2F6BFF)        // --brand
val BrandSoft = Color(0xFFEAF0FF)    // --brand-soft
val PageBg = Color(0xFFF5F6F8)       // --bg
val Panel = Color(0xFFFFFFFF)        // --panel
val Line = Color(0xFFE5E7EB)         // --line
val TextMain = Color(0xFF1F2329)     // --text
val TextMuted = Color(0xFF8A9099)    // --muted
val BubbleMeColor = Brand            // --bubble-me
val BubbleOther = Color(0xFFFFFFFF)  // --bubble-other
val OkGreen = Color(0xFF12B76A)      // --ok
val DangerRed = Color(0xFFE24B4A)    // --danger
val RowHover = Color(0xFFFAFBFC)

private val LightScheme = lightColorScheme(
    primary = Brand,
    onPrimary = Panel,
    primaryContainer = BrandSoft,
    onPrimaryContainer = Brand,
    secondary = Brand,
    background = PageBg,
    onBackground = TextMain,
    surface = Panel,
    onSurface = TextMain,
    surfaceVariant = BrandSoft,
    onSurfaceVariant = TextMuted,
    outline = Line,
    outlineVariant = Line,
    error = DangerRed,
)

@Composable
fun AndYouTheme(content: @Composable () -> Unit) {
    // v1 视觉与网页版一致：仅浅色。深色主题待 v1.1 跟随系统。
    MaterialTheme(
        colorScheme = LightScheme,
        content = content,
    )
}
