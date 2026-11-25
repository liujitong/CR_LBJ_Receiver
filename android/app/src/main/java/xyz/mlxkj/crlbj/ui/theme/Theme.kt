package xyz.mlxkj.crlbj.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// 主题色沿用桌面版（v2.5）
val CrRed = Color(0xFFDA291C)    // CR 红
val CrBlue = Color(0xFF003DA5)   // CR 蓝

private fun lbjDarkScheme() = darkColorScheme(
    primary = CrRed,
    secondary = CrBlue,
    background = Color(0xFF0F1115),
    surface = Color(0xFF141821),
    surfaceVariant = Color(0xFF10131A),
    onPrimary = Color.White,
    onBackground = Color(0xFFE6E9EE),
    onSurface = Color(0xFFE6E9EE),
    onSurfaceVariant = Color(0xFF9AA0A6),
)

private fun lbjLightScheme() = lightColorScheme(
    primary = CrRed,
    secondary = CrBlue,
    background = Color(0xFFF3F4F6),
    surface = Color.White,
    surfaceVariant = Color(0xFFE8EAEE),
    onPrimary = Color.White,
    onBackground = Color(0xFF1A1C20),
    onSurface = Color(0xFF1A1C20),
    onSurfaceVariant = Color(0xFF5A6068),
)

/**
 * 应用主题：FluentTheme 承担 Fluent 视觉基调（深浅跟随系统），
 * MaterialTheme 提供 material3 组件的 CR 配色；业务卡片、频谱条、状态块自绘。
 */
@Composable
fun LbjTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    io.github.composefluent.FluentTheme {
        MaterialTheme(
            colorScheme = if (dark) lbjDarkScheme() else lbjLightScheme(),
            content = content,
        )
    }
}
