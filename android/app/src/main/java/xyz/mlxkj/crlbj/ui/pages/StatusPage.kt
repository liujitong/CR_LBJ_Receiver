package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

/** 状态页：当下体检（RSSI/块率/丢块/重连/CPU/缓冲/tuner/日志尾部）。 */
@Composable
fun StatusPage(vm: ReceiverViewModel) {
    val logs by vm.logs.collectAsStateWithLifecycle()
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Text("状态体检", fontSize = 20.sp)
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .padding(top = 8.dp)
                .background(Color(0xFF10131A))
        ) {
            Text(
                text = "M1 起显示：RSSI / 块率 / 丢块 / 重连次数 / 解码 CPU /\n" +
                       "缓冲水位 / tuner 型号与增益 / 当前采样率与频偏\n\n" +
                       "日志尾部：\n" + logs.takeLast(12).joinToString("\n"),
                color = Color(0xFF8BE28B),
                fontSize = 12.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(8.dp),
            )
        }
    }
}
