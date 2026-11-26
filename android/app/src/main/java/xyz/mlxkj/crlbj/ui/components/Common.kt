package xyz.mlxkj.crlbj.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal

/** 语义色调：正常 / 注意 / 异常 / 中性 */
enum class Tone { Ok, Warn, Err, Neutral }

/** 圆角小胶囊标签 */
@Composable
fun Chip(
    text: String,
    tone: Tone = Tone.Neutral,
    modifier: Modifier = Modifier,
) {
    val p = pal()
    val (fg, bg) = when (tone) {
        Tone.Ok -> p.ok to p.ok.copy(alpha = 0.14f)
        Tone.Warn -> p.warn to p.warn.copy(alpha = 0.16f)
        Tone.Err -> p.err to p.err.copy(alpha = 0.16f)
        Tone.Neutral -> p.textSecondary to p.textSecondary.copy(alpha = 0.10f)
    }
    Box(
        modifier
            .clip(RoundedCornerShape(50))
            .background(bg)
            .padding(horizontal = 8.dp, vertical = 3.dp)
    ) {
        Text(text, color = fg, fontSize = 11.sp, fontWeight = FontWeight.Medium, maxLines = 1)
    }
}

/**
 * 页面头：大标题 + 右侧状态胶囊（数据源 / 连接状态 / 相对时间）。
 * 没有重顶栏——标题就是顶栏，滚动内容从标题下方开始。
 */
@Composable
fun PageHeader(
    title: String,
    subtitle: String? = null,
    trailing: @Composable (() -> Unit)? = null,
) {
    val p = pal()
    Row(
        Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                title,
                color = p.text,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.4).sp,
            )
            if (!subtitle.isNullOrEmpty()) {
                Text(subtitle, color = p.textTertiary, fontSize = 12.sp, maxLines = 1)
            }
        }
        trailing?.invoke()
    }
}

/** 数据源 / 连接状态胶囊，点开有「开始·停止接收」等快捷项 */
@Composable
fun StatusCapsule(
    sourceLabel: String,
    running: Boolean,
    lastEventTs: Double?,
    onToggle: () -> Unit,
    onClear: (() -> Unit)? = null,
    /**
     * 非空时：点胶囊直接执行该动作（解码页用它打开「信号瀑布」小弹层），
     * 不再弹下拉菜单；为空时保持原行为（弹出开始/停止菜单）。
     */
    onOpen: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    val p = pal()
    var open by remember { mutableStateOf(false) }
    // 相对时间每秒刷新
    val nowSec = rememberTickerSeconds()
    val ago = remember(lastEventTs, nowSec) {
        if (lastEventTs == null) "等待首帧"
        else {
            val d = (nowSec - lastEventTs).toInt().coerceAtLeast(0)
            when {
                d < 5 -> "刚刚"
                d < 60 -> "${d} 秒前"
                d < 3600 -> "${d / 60} 分钟前"
                else -> "${d / 3600} 小时前"
            }
        }
    }
    val dot = if (running) p.ok else p.textTertiary
    Box(modifier) {
        Row(
            Modifier
                .clip(RoundedCornerShape(50))
                .background(p.surfaceAlt)
                .border(1.dp, p.border, RoundedCornerShape(50))
                .clickable { if (onOpen != null) onOpen() else open = true }
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.width(7.dp).height(7.dp).clip(RoundedCornerShape(50)).background(dot))
            Spacer(Modifier.width(6.dp))
            Text(
                "$sourceLabel · ${if (running) "接收中" else "已停止"} · $ago",
                color = p.textSecondary, fontSize = 11.sp, maxLines = 1,
            )
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            DropdownMenuItem(
                text = { Text(if (running) "停止接收" else "开始接收", fontSize = 14.sp) },
                onClick = { open = false; onToggle() },
            )
            if (onClear != null) {
                DropdownMenuItem(
                    text = { Text("清空当前解码列表", fontSize = 14.sp) },
                    onClick = { open = false; onClear() },
                )
            }
            DropdownMenuItem(
                text = { Text("数据源：$sourceLabel", fontSize = 13.sp) },
                enabled = false,
                onClick = { },
            )
        }
    }
}

/** 每秒递增的秒计时（相对时间文案用），页面离开自动停 */
@Composable
fun rememberTickerSeconds(): Double {
    val state = remember { mutableStateOf(System.currentTimeMillis() / 1000.0) }
    androidx.compose.runtime.LaunchedEffect(Unit) {
        while (true) {
            state.value = System.currentTimeMillis() / 1000.0
            kotlinx.coroutines.delay(1000)
        }
    }
    return state.value
}

/** 分组卡片：标题 13sp 次级色 + 内容，圆角 8dp，1dp 描边 */
@Composable
fun SectionCard(
    title: String? = null,
    trailing: @Composable (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    val p = pal()
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(Dim.cardCorner))
            .background(p.surface)
            .border(1.dp, p.border, RoundedCornerShape(Dim.cardCorner))
            .padding(horizontal = 14.dp, vertical = 12.dp),
    ) {
        if (title != null || trailing != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (title != null) {
                    Text(
                        title,
                        color = p.textSecondary,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
                Spacer(Modifier.weight(1f))
                trailing?.invoke()
            }
            Spacer(Modifier.height(Dim.gap))
        }
        content()
    }
}

/** 一行「标签 …… 值」；mono=true 时值用等宽字体（数字列对齐） */
@Composable
fun InfoRow(
    label: String,
    value: String,
    mono: Boolean = false,
    valueColor: Color? = null,
    labelWidth: Int = 84,
) {
    val p = pal()
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(
            label,
            color = p.textSecondary,
            fontSize = 13.sp,
            modifier = Modifier.width(labelWidth.dp),
        )
        Text(
            value.ifEmpty { "—" },
            color = valueColor ?: p.text,
            fontSize = 13.sp,
            fontFamily = if (mono) FontFamily.Monospace else FontFamily.Default,
            modifier = Modifier.weight(1f),
        )
    }
}

/** 指标块（状态页网格用）：小标签 + 大数字 + 单位；large=true 用于第一层级的主指标 */
@Composable
fun MetricTile(
    label: String,
    value: String,
    unit: String = "",
    tone: Tone = Tone.Neutral,
    modifier: Modifier = Modifier,
    large: Boolean = false,
) {
    val p = pal()
    val color = when (tone) {
        Tone.Ok -> p.ok
        Tone.Warn -> p.warn
        Tone.Err -> p.err
        Tone.Neutral -> p.text
    }
    Column(
        modifier
            .clip(RoundedCornerShape(Dim.cardCorner))
            .background(p.surfaceAlt)
            .padding(horizontal = if (large) 12.dp else 10.dp,
                vertical = if (large) 9.dp else 7.dp),
    ) {
        Text(label, color = p.textTertiary, fontSize = if (large) 12.sp else 11.sp, maxLines = 1)
        Spacer(Modifier.height(if (large) 3.dp else 2.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                value,
                color = color,
                fontSize = if (large) 24.sp else 19.sp,
                fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace,
                maxLines = 1,
                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                // 权重 + Ellipsis：长数字（如调谐 821.2375 MHz）只截断数字，
                // 绝不会把单位挤成 0 宽而把整块撑高（v3.1.1 状态页修复）
                modifier = Modifier.weight(1f, fill = false),
            )
            if (unit.isNotEmpty()) {
                Spacer(Modifier.width(2.dp))
                Text(unit, color = p.textTertiary, fontSize = if (large) 11.sp else 10.sp,
                    maxLines = 1, softWrap = false,
                    modifier = Modifier.padding(bottom = 2.dp))
            }
        }
    }
}

/** 空态：一句主文案 + 一句提示，居中（不要大白块）；文案克制，别用大字压屏 */
@Composable
fun EmptyState(
    title: String,
    hint: String? = null,
    modifier: Modifier = Modifier,
    action: @Composable (() -> Unit)? = null,
) {
    val p = pal()
    Column(
        modifier.fillMaxWidth().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(title, color = p.textSecondary, fontSize = 13.sp, textAlign = TextAlign.Center)
        if (!hint.isNullOrEmpty()) {
            Spacer(Modifier.height(5.dp))
            Text(hint, color = p.textTertiary, fontSize = 11.sp, textAlign = TextAlign.Center)
        }
        if (action != null) {
            Spacer(Modifier.height(12.dp))
            action()
        }
    }
}

/** 等宽文本（速度/公里标/坐标） */
@Composable
fun MonoText(
    text: String,
    fontSize: Int = 13,
    color: Color? = null,
    modifier: Modifier = Modifier,
) {
    Text(
        text,
        color = color ?: pal().text,
        fontSize = fontSize.sp,
        fontFamily = FontFamily.Monospace,
        modifier = modifier,
    )
}

/** 细分割线（卡片内部用） */
@Composable
fun Divider() {
    val p = pal()
    Box(Modifier.fillMaxWidth().height(1.dp).background(p.border))
}

/**
 * 统一风格输入框：1dp 描边 + 卡片底 + 主色光标。
 * 用 BasicTextField 自绘，避免 material3 OutlinedTextField 的浮动标签在紧凑表单里占高度。
 */
@Composable
fun LbjTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    singleLine: Boolean = true,
    keyboardType: androidx.compose.ui.text.input.KeyboardType =
        androidx.compose.ui.text.input.KeyboardType.Text,
    imeAction: androidx.compose.ui.text.input.ImeAction =
        androidx.compose.ui.text.input.ImeAction.Done,
    onDone: (() -> Unit)? = null,
) {
    val p = pal()
    val colors = androidx.compose.foundation.text.KeyboardOptions(
        keyboardType = keyboardType, imeAction = imeAction)
    androidx.compose.foundation.text.BasicTextField(
        value = value,
        onValueChange = onValueChange,
        singleLine = singleLine,
        textStyle = androidx.compose.ui.text.TextStyle(
            color = p.text, fontSize = 14.sp,
            fontFamily = if (keyboardType == androidx.compose.ui.text.input.KeyboardType.Number)
                FontFamily.Monospace else FontFamily.Default,
        ),
        cursorBrush = androidx.compose.ui.graphics.SolidColor(p.accent),
        keyboardOptions = colors,
        keyboardActions = androidx.compose.foundation.text.KeyboardActions(
            onDone = { onDone?.invoke() },
            onSearch = { onDone?.invoke() },
            onGo = { onDone?.invoke() },
        ),
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(p.surfaceAlt)
            .border(1.dp, p.border, RoundedCornerShape(8.dp))
            .padding(horizontal = 10.dp, vertical = 10.dp),
        decorationBox = { inner ->
            Box {
                if (value.isEmpty() && !placeholder.isNullOrEmpty()) {
                    Text(placeholder, color = p.textTertiary, fontSize = 14.sp)
                }
                inner()
            }
        },
    )
}
