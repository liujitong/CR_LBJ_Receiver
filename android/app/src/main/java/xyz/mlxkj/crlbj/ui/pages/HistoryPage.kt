package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import io.github.composefluent.component.Text

/** 历史页（M3 接入 Room；按趟归档 + 日期分组 + CSV 导出）。 */
@Composable
fun HistoryPage() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("历史记录（M3 接入）", fontSize = 20.sp)
            Text("按趟归档 · 日期分组 · 详情 · CSV 导出", color = Color(0xFF9AA0A6), fontSize = 12.sp)
        }
    }
}
