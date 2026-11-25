package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Button
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.ui.theme.CrRed
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

/**
 * 解码页：顶部 40~80px 信号强度条（含门限线 + 有信号/弱信号/静噪判定），
 * 当前解码大卡片，最近解码列表。第一屏"一键开始"入口。
 *
 * M0：信号条为占位动画（证明 Canvas 30fps 刷新链路可用），解码卡片显示骨架。
 * M1：RSSI 来自 StatusFrame 轮询；M2：解码事件流填充列表。
 */
@Composable
fun DecodePage(vm: ReceiverViewModel) {
    val running by vm.running.collectAsStateWithLifecycle()
    val logs by vm.logs.collectAsStateWithLifecycle()
    val state by vm.engine.state.collectAsStateWithLifecycle()

    // 占位动画相位（30fps 重绘证明）
    var phase by remember { mutableStateOf(0f) }
    LaunchedEffect(Unit) {
        while (true) {
            withFrameMillis { t -> phase = (t % 1500L) / 1500f }
        }
    }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        // 一键开始
        Row(verticalAlignment = Alignment.CenterVertically) {
            Button(
                onClick = { vm.toggleStartStop() },
                modifier = Modifier.weight(1f).height(52.dp),
            ) {
                Text(if (running) "■ 停止接收" else "▶ 一键开始", fontWeight = FontWeight.Bold)
            }
        }

        // 信号强度条（40~80px）
        Box(
            Modifier
                .fillMaxWidth()
                .padding(top = 8.dp)
                .height(60.dp)
                .background(Color(0xFF10131A))
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val onDb = -55f              // 门限（与桌面版 DEFAULT_RSSI_THRESHOLD_DB 一致）
                fun dbToY(db: Float): Float = size.height * (1f - (db + 140f) / 90f)
                // 门限线
                drawLine(Color(0xFFFFB300), Offset(0f, dbToY(onDb)), Offset(size.width, dbToY(onDb)), 2f)
                // 占位扫描波纹（M1 换成真实 RSSI 历史）
                val w = size.width
                for (x in 0..(w.toInt()) step 4) {
                    val t = x / w + phase
                    val db = -120f + 60f * (0.5f + 0.5f * kotlin.math.sin(t * 12.56f)) * (1f - phase * 0.0f)
                    drawLine(
                        if (db >= onDb) CrRed else Color(0xFF3D6FE0),
                        Offset(x.toFloat(), dbToY(db)),
                        Offset(x.toFloat(), size.height),
                        2f
                    )
                }
            }
            Text(
                if (running) "有信号" else "静噪",
                color = if (running) CrRed else Color(0xFF9AA0A6),
                modifier = Modifier.align(Alignment.TopEnd).padding(6.dp),
                fontSize = 12.sp,
            )
        }

        // 当前解码大卡片（M2 填充）
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .padding(top = 8.dp)
                .background(Color(0xFF141821))
        ) {
            Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("等待信号...", fontSize = 34.sp, fontWeight = FontWeight.Bold)
                Text("车次 / 方向 / 速度 / 公里标 / 线路", color = Color(0xFF9AA0A6), fontSize = 13.sp)
                Text("状态: $state", color = Color(0xFF666E78), fontSize = 12.sp)
            }
        }

        // 日志尾部（M0 用于验收 native init ok）
        Box(
            Modifier
                .fillMaxWidth()
                .height(120.dp)
                .padding(top = 8.dp)
                .background(Color(0xFF10131A))
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                text = logs.takeLast(8).joinToString("\n"),
                color = Color(0xFF8BE28B),
                fontSize = 11.sp,
                modifier = Modifier.padding(6.dp),
            )
        }
    }
}
