package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import java.util.Locale

/** 状态页：当下体检（RSSI/块率/丢块/重连/CPU/缓冲/tuner/日志尾部）。 */
@Composable
fun StatusPage(vm: ReceiverViewModel) {
    val logs by vm.logs.collectAsStateWithLifecycle()
    val f by vm.status.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize().padding(12.dp).verticalScroll(rememberScrollState())) {
        Text("状态体检", fontSize = 20.sp)
        Spacer(Modifier.height(8.dp))

        Box(
            Modifier
                .fillMaxWidth()
                .background(Color(0xFF10131A))
                .padding(10.dp)
        ) {
            Column {
                val fr = f
                if (fr == null) {
                    Text("引擎未运行 / 暂无状态帧", color = Color(0xFF9AA0A6), fontSize = 13.sp)
                } else {
                    @Composable
                    fun row(name: String, value: String) =
                        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                            Text(name, color = Color(0xFF9AA0A6), fontSize = 13.sp,
                                modifier = Modifier.width(120.dp))
                            Text(value, color = Color(0xFFE8EAED), fontSize = 13.sp,
                                fontFamily = FontFamily.Monospace)
                        }
                    row("信号强度", "%.1f dB".format(Locale.US, fr.rssiDb))
                    row("门控状态", when (fr.gateState) {
                        0 -> "关闭"; 1 -> "待命"; 2 -> "开启"
                        3 -> "保持"; 4 -> "旁路"; else -> "未知(${fr.gateState})"
                    })
                    row("AFC 补偿", "%.0f Hz（估计 %.0f Hz，评分 %.2f）".format(
                        Locale.US, fr.afcHz, fr.afcErrHz, fr.afcScore))
                    row("实际采样率", "%d Hz".format(fr.actualSampleRate))
                    row("调谐频率", "%.4f MHz".format(fr.hwFreqHz / 1e6))
                    row("增益", "%.2f dB".format(fr.appliedGainCentiDb / 100.0))
                    row("tuner 类型", "ID %d".format(fr.tunerTypeId))
                    row("块率", "%.1f 块/秒".format(Locale.US, fr.blocksPerSec))
                    row("累计/丢块", "%d / %d".format(fr.totalBlocks, fr.droppedBlocks))
                    row("重连次数", fr.reconnectCount.toString())
                    row("解码 CPU", "%.1f%%".format(Locale.US, fr.decodeCpuPct))
                    row("缓冲水位", "%.0f%%".format(Locale.US, fr.bufferLevel * 100f))
                    row("链路模式", if (fr.linkMode == 0) "USB 直连" else "pipe 桥")
                    row("运行状态", if (fr.running != 0) "运行中" else "停止")
                    row("错误状态", if (fr.errorState == 0) "正常" else "数据流中断")
                }
            }
        }

        Spacer(Modifier.height(8.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .height(160.dp)
                .background(Color(0xFF10131A))
        ) {
            Text(
                text = logs.takeLast(14).joinToString("\n"),
                color = Color(0xFF8BE28B),
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(8.dp).verticalScroll(rememberScrollState()),
            )
        }
    }
}
