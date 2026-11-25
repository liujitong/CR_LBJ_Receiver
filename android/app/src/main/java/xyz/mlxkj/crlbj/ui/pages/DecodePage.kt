package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Button
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.engine.StatusFrame
import xyz.mlxkj.crlbj.ui.theme.CrRed
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale
import kotlin.math.sin

/**
 * 解码页：顶部信号强度条（真实 RSSI 历史 + 门限线 + 有信号/弱信号/静噪判定），
 * 当前解码大卡片，最近解码列表。第一屏"一键开始"。
 */
@Composable
fun DecodePage(vm: ReceiverViewModel) {
    val running by vm.running.collectAsStateWithLifecycle()
    val logs by vm.logs.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()
    val events by vm.events.collectAsStateWithLifecycle()

    // RSSI 历史环形缓冲（轮询帧驱动，最多 240 点 ≈ 36s）
    val rssiHistory = remember { ArrayDeque<Float>(240) }
    LaunchedEffect(Unit) {
        var lastSeq = -1
        while (true) {
            val f = vm.status.value
            if (f != null && f.seq != lastSeq) {
                lastSeq = f.seq
                rssiHistory.addLast(f.rssiDb)
                while (rssiHistory.size > 240) rssiHistory.removeFirst()
            }
            kotlinx.coroutines.delay(150)
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

        // 信号强度条（真实 RSSI 历史）
        val gate = status?.gateState ?: 0
        Box(
            Modifier
                .fillMaxWidth()
                .padding(top = 8.dp)
                .height(60.dp)
                .background(Color(0xFF10131A))
        ) {
            Canvas(Modifier.fillMaxSize()) {
                val onDb = -55f
                fun dbToY(db: Float): Float = size.height * (1f - (db + 140f) / 90f)
                drawLine(Color(0xFFFFB300), Offset(0f, dbToY(onDb)), Offset(size.width, dbToY(onDb)), 2f)
                // 历史 RSSI 曲线（右端为最新）
                if (rssiHistory.isNotEmpty()) {
                    val n = rssiHistory.size
                    val step = if (n > 1) size.width / (n - 1) else size.width
                    rssiHistory.forEachIndexed { i, db ->
                        val x = size.width - (n - 1 - i) * step
                        drawLine(
                            if (db >= onDb) CrRed else Color(0xFF3D6FE0),
                            Offset(x, dbToY(db)),
                            Offset(x, size.height),
                            if (n > 1) 2f else 4f,
                        )
                    }
                } else {
                    // 无数据：静噪基线
                    drawLine(
                        Color(0xFF3D6FE0), Offset(0f, dbToY(-140f)),
                        Offset(size.width, dbToY(-140f)), 2f,
                    )
                }
            }
            Text(
                when {
                    gate >= 2 -> "有信号"
                    gate == 1 -> "待命"
                    running -> "静噪"
                    else -> "停止"
                },
                color = if (gate >= 2) CrRed else Color(0xFF9AA0A6),
                modifier = Modifier.align(Alignment.TopEnd).padding(6.dp),
                fontSize = 12.sp,
            )
            status?.let {
                Text(
                    "RSSI %.1f dB".format(Locale.US, it.rssiDb),
                    color = Color(0xFF9AA0A6),
                    modifier = Modifier.align(Alignment.TopStart).padding(6.dp),
                    fontSize = 12.sp,
                )
            }
        }

        // 当前解码大卡片
        val latest = events.firstOrNull()
        Box(
            Modifier
                .fillMaxWidth()
                .weight(1f)
                .padding(top = 8.dp)
                .background(Color(0xFF141821))
                .verticalScroll(rememberScrollState())
        ) {
            if (latest == null) {
                Column(Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("等待信号...", fontSize = 34.sp, fontWeight = FontWeight.Bold)
                    Text("车次 / 方向 / 速度 / 公里标 / 线路", color = Color(0xFF9AA0A6), fontSize = 13.sp)
                }
            } else {
                DecodeCard(latest, isBig = true)
            }
        }

        // 最近解码列表
        Box(
            Modifier
                .fillMaxWidth()
                .height(180.dp)
                .padding(top = 8.dp)
                .background(Color(0xFF10131A))
        ) {
            if (events.isEmpty()) {
                Text(
                    "日志：\n" + logs.takeLast(6).joinToString("\n"),
                    color = Color(0xFF8BE28B), fontSize = 11.sp,
                    modifier = Modifier.padding(6.dp).verticalScroll(rememberScrollState()),
                )
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(events.drop(1).take(12), key = { it.uid + it.timestamp }) { ev ->
                        DecodeCard(ev, isBig = false)
                    }
                }
            }
        }
    }
}

/** 单条解码卡片（大卡 = 当前，小卡 = 历史） */
@Composable
private fun DecodeCard(ev: DecodeEvent, isBig: Boolean) {
    val titleSize = if (isBig) 34.sp else 18.sp
    val detailSize = if (isBig) 14.sp else 11.sp
    Column(Modifier.fillMaxWidth().padding(if (isBig) 16.dp else 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ev.train.ifEmpty { "----" }, fontSize = titleSize,
                fontWeight = FontWeight.Bold, color = Color(0xFFE8EAED))
            Spacer(Modifier.width(10.dp))
            Text(ev.direction, fontSize = if (isBig) 18.sp else 12.sp, color = CrRed)
            if (ev.hasInterference) {
                Spacer(Modifier.width(8.dp))
                Text("干扰", color = Color(0xFFFFB300), fontSize = detailSize)
            }
        }
        Spacer(Modifier.height(4.dp))
        Text(
            "${ev.category}  速度 ${ev.speed} km/h  公里标 ${ev.position}",
            fontSize = detailSize, color = Color(0xFF9AA0A6),
        )
        if (isBig) {
            Text("线路 ${ev.route.ifEmpty { "未知" }}  机车 ${ev.loco.ifEmpty { "----" }}",
                fontSize = detailSize, color = Color(0xFF9AA0A6))
            ev.latitude?.let { lat ->
                Text("坐标 %.5f, %.5f".format(Locale.US, lat, ev.longitude ?: 0.0),
                    fontSize = detailSize, color = Color(0xFF9AA0A6))
            }
            Text("RSSI %.1f dB  AFC %.0f Hz".format(Locale.US, ev.rssi, ev.afcHz),
                fontSize = detailSize, color = Color(0xFF666E78))
        }
        Spacer(Modifier.height(2.dp))
        Row {
            Text("ETA ${ev.etaTime}  ${ev.etaStatus}" +
                (ev.etaDistanceKm?.let { "  %.1f km".format(Locale.US, it) } ?: ""),
                fontSize = detailSize,
                color = if (ev.etaSeconds != null && ev.etaSeconds <= 600.0) CrRed
                        else Color(0xFF9AA0A6))
            if (isBig) {
                Spacer(Modifier.width(12.dp))
                Text(ev.timeStr, fontSize = detailSize, color = Color(0xFF666E78))
            }
        }
        if (!isBig) {
            Spacer(Modifier.height(2.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFF222833)))
        }
    }
}
