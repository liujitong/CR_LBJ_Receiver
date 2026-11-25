package xyz.mlxkj.crlbj.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import xyz.mlxkj.crlbj.ui.theme.pal

/** 悬浮 Dock 的一项 */
data class DockTab(val title: String, val icon: ImageVector)

/**
 * 悬浮玻璃胶囊 Dock（替代 Material NavigationBar）。
 *
 * 视觉：圆角药丸 + 半透明底 + 1dp 描边，选中项是强调色的浅底小药丸；
 * 内容滚动到 Dock 底下会隐约透出来（半透明 + 描边模拟毛玻璃，不用真模糊，
 * 因为真模糊需要 RenderEffect（API 31+），低端机反而掉帧）。
 *
 * 布局：调用方把它放在 Box 底部居中，页面内容用 [xyz.mlxkj.crlbj.ui.theme.Dim.dockSpace] 留白。
 */
@Composable
fun LbjDock(
    tabs: List<DockTab>,
    current: Int,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val p = pal()
    Row(
        modifier
            .fillMaxWidth()
            .padding(horizontal = 14.dp)
            .clip(RoundedCornerShape(30.dp))
            .background(p.dockBg)
            .border(1.dp, p.border, RoundedCornerShape(30.dp))
            .padding(horizontal = 6.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        tabs.forEachIndexed { i, tab ->
            val selected = i == current
            Column(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(24.dp))
                    .background(
                        if (selected) p.accent.copy(alpha = 0.15f) else p.surface.copy(alpha = 0f)
                    )
                    .clickable { onSelect(i) }
                    .padding(vertical = 6.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Icon(
                    tab.icon,
                    contentDescription = tab.title,
                    tint = if (selected) p.accent else p.textTertiary,
                    modifier = Modifier.size(21.dp),
                )
                Spacer(Modifier.height(3.dp))
                Text(
                    tab.title,
                    color = if (selected) p.accent else p.textTertiary,
                    fontSize = 10.sp,
                    fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                )
            }
        }
    }
}

/** Dock 上方的半透明浮层按钮（地图页「跟随」等） */
@Composable
fun FloatPill(
    text: String,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val p = pal()
    Box(
        modifier
            .clip(RoundedCornerShape(50))
            .background(if (active) p.accent else p.dockBg)
            .border(1.dp, if (active) p.accent else p.border, RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
    ) {
        Text(
            text,
            color = if (active) p.onAccent else p.text,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}
