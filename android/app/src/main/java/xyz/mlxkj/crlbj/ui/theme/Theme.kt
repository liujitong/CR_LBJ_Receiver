package xyz.mlxkj.crlbj.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// ---------------------------------------------------------------- 品牌色
// 沿用桌面版（v2.5 起）：CR 红 Pantone 485C / CR 蓝 286C
val CrRed = Color(0xFFDA291C)
val CrBlue = Color(0xFF003DA5)

// ---------------------------------------------------------------- 语义色
// 上行/下行/未知与 shared/web/railmap.html 的 colors 默认值一致，
// 保证「地图标记颜色 = 列表方向色」，两端同一套观感。
val DirUp = Color(0xFF4C8DFF)
val DirDown = Color(0xFFF0604F)
val DirUnknown = Color(0xFFE0A400)
val ToneOk = Color(0xFF3FB27F)
val ToneWarn = Color(0xFFE0A400)
val ToneErr = Color(0xFFE5534B)

/**
 * 中性色阶调色板（暗色 / 亮色各一套）。
 *
 * 规则（v3.0 视觉基调）：
 *  - 强调色只有 CR 红 / CR 蓝，其余一律中性灰阶，避免界面花掉；
 *  - 文字三级：主 100% / 次 62% / 三级 38%，用同一基色叠透明度得出；
 *  - 卡片底色比页面底色亮一档（暗色）或纯白（亮色），靠 1dp 描边分层，
 *    不用投影——手机上投影在深色底上几乎看不见，还拖慢滚动。
 */
data class LbjPalette(
    val dark: Boolean,
    val bg: Color,
    val surface: Color,
    val surfaceAlt: Color,
    val border: Color,
    val borderStrong: Color,
    val text: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val accent: Color,
    val accentAlt: Color,
    val onAccent: Color,
    val dockBg: Color,
    val scrim: Color,
    val ok: Color,
    val warn: Color,
    val err: Color,
    val spectrum: Color,
) {
    /** 方向 → 颜色（上行/下行/未知） */
    fun dirColor(direction: String): Color = when {
        direction.contains("上") -> DirUp
        direction.contains("下") -> DirDown
        else -> DirUnknown
    }
}

val DarkPalette = LbjPalette(
    dark = true,
    bg = Color(0xFF0B0C0E),
    surface = Color(0xFF121417),
    surfaceAlt = Color(0xFF1A1D21),
    border = Color(0xFF262A2F),
    borderStrong = Color(0xFF333A41),
    text = Color(0xFFF2F4F7),
    textSecondary = Color(0xFFF2F4F7).copy(alpha = 0.62f),
    textTertiary = Color(0xFFF2F4F7).copy(alpha = 0.38f),
    accent = CrRed,
    accentAlt = Color(0xFF4C8DFF),
    onAccent = Color.White,
    dockBg = Color(0xFF16191D).copy(alpha = 0.90f),
    scrim = Color(0xFF000000).copy(alpha = 0.55f),
    ok = ToneOk,
    warn = ToneWarn,
    err = ToneErr,
    spectrum = Color(0xFF7FB3FF),
)

val LightPalette = LbjPalette(
    dark = false,
    bg = Color(0xFFF2F2F7),
    surface = Color(0xFFFFFFFF),
    surfaceAlt = Color(0xFFF7F7FA),
    border = Color(0xFFE5E5EA),
    borderStrong = Color(0xFFD1D1D6),
    text = Color(0xFF1C1C1E),
    textSecondary = Color(0xFF1C1C1E).copy(alpha = 0.62f),
    textTertiary = Color(0xFF1C1C1E).copy(alpha = 0.38f),
    accent = CrRed,
    accentAlt = CrBlue,
    onAccent = Color.White,
    dockBg = Color(0xFFFFFFFF).copy(alpha = 0.92f),
    scrim = Color(0xFF000000).copy(alpha = 0.35f),
    ok = Color(0xFF2E7D53),
    warn = Color(0xFFA96500),
    err = Color(0xFFC0392B),
    spectrum = Color(0xFF003DA5),
)

val LocalPalette = staticCompositionLocalOf { DarkPalette }

/** 页面统一取色入口：`LbjTheme.palette` 或 `pal()` */
object LbjTheme {
    val palette: LbjPalette
        @Composable get() = LocalPalette.current
}

@Composable
fun pal(): LbjPalette = LocalPalette.current

// ---------------------------------------------------------------- 尺寸
object Dim {
    val cardCorner = 8.dp
    val sheetCorner = 24.dp
    val gap = 8.dp
    val pagePad = 16.dp
    /** 底部悬浮 Dock 占位高度（页面内容需要留出的空白） */
    val dockSpace = 96.dp
}

private fun lbjDarkScheme() = darkColorScheme(
    primary = CrRed,
    secondary = Color(0xFF4C8DFF),
    background = DarkPalette.bg,
    surface = DarkPalette.surface,
    surfaceVariant = DarkPalette.surfaceAlt,
    onPrimary = Color.White,
    onBackground = DarkPalette.text,
    onSurface = DarkPalette.text,
    onSurfaceVariant = DarkPalette.textSecondary,
    outline = DarkPalette.border,
    error = ToneErr,
)

private fun lbjLightScheme() = lightColorScheme(
    primary = CrRed,
    secondary = CrBlue,
    background = LightPalette.bg,
    surface = LightPalette.surface,
    surfaceVariant = LightPalette.surfaceAlt,
    onPrimary = Color.White,
    onBackground = LightPalette.text,
    onSurface = LightPalette.text,
    onSurfaceVariant = LightPalette.textSecondary,
    outline = LightPalette.border,
    error = LightPalette.err,
)

/**
 * 应用主题：FluentTheme 承担 Fluent 视觉基调（深浅跟随系统），
 * MaterialTheme 提供 material3 组件的 CR 配色，LocalPalette 给自绘组件用。
 * 业务卡片、频谱条、状态块自绘——不搬桌面 Qt 布局。
 */
@Composable
fun LbjTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val palette = if (dark) DarkPalette else LightPalette
    io.github.composefluent.FluentTheme {
        CompositionLocalProvider(LocalPalette provides palette) {
            MaterialTheme(
                colorScheme = if (dark) lbjDarkScheme() else lbjLightScheme(),
                content = content,
            )
        }
    }
}
