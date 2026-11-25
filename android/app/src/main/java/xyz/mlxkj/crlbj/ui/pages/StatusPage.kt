package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.engine.StatusFrame
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.MetricTile
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.StatusCapsule
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/**
 * 状态页：指标块网格（信号/门控/AFC/块率/丢块/重连/CPU/缓冲/采样/增益/tuner/链路）
 * + 图文日志尾巴。深度排查仍以仪表板式罗列为主——手机上不玩图表。
 */
@Composable
fun StatusPage(vm: ReceiverViewModel) {
    val logs by vm.logs.collectAsStateWithLifecycle()
    val f by vm.status.collectAsStateWithLifecycle()
    val running by vm.running.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val p = pal()

    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = Dim.pagePad)
            .verticalScroll(rememberScrollState()),
    ) {
        PageHeader(
            title = "状态",
            subtitle = "RTL-SDR · ${settings.sourceType.uppercase(Locale.US)} · " +
                "${settings.sampleRate / 1000} kS/s",
            trailing = {
                StatusCapsule(
                    sourceLabel = sourceLabelOf(settings.sourceType),
                    running = running,
                    lastEventTs = vm.events.value.firstOrNull()?.timestamp,
                    onToggle = { vm.toggleStartStop() },
                )
            },
        )

        val fr = f
        if (fr == null) {
            SectionCard("引擎") {
                Text(
                    if (running) "已开始接收，等待第一帧状态…" else "引擎未运行 / 暂无状态帧",
                    color = p.textSecondary, fontSize = 13.sp,
                )
            }
        } else {
            SectionCard(
                title = "链路体检",
                trailing = {
                    Chip(
                        when {
                            fr.errorState != 0 -> "数据流中断"
                            fr.running != 0 -> "运行中"
                            else -> "已停止"
                        },
                        when {
                            fr.errorState != 0 -> Tone.Err
                            fr.running != 0 -> Tone.Ok
                            else -> Tone.Neutral
                        },
                    )
                },
            ) {
                val tiles = metricTiles(fr)
                tiles.chunked(3).forEach { row ->
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        row.forEach { t ->
                            MetricTile(
                                label = t.label,
                                value = t.value,
                                unit = t.unit,
                                tone = t.tone,
                                modifier = Modifier.weight(1f),
                            )
                        }
                        // 补齐末行，保证格子等宽
                        repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                    }
                    Spacer(Modifier.height(6.dp))
                }
            }
        }

        Spacer(Modifier.height(Dim.gap))

        SectionCard("日志") {
            Text(
                text = logs.takeLast(40).joinToString("\n").ifEmpty { "（暂无日志）" },
                color = p.textSecondary,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                lineHeight = 16.sp,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Spacer(Modifier.height(Dim.dockSpace))
    }
}

private data class Tile(
    val label: String,
    val value: String,
    val unit: String = "",
    val tone: Tone = Tone.Neutral,
)

private fun metricTiles(f: StatusFrame): List<Tile> = listOf(
    Tile("信号", "%.0f".format(Locale.US, f.rssiDb), "dB",
        when {
            f.gateState >= 2 -> Tone.Ok
            f.gateState == 1 -> Tone.Warn
            else -> Tone.Neutral
        }),
    Tile("门控", when (f.gateState) {
        0 -> "关闭"; 1 -> "待命"; 2 -> "开启"; 3 -> "保持"; 4 -> "旁路"; else -> "?"
    }),
    Tile("块率", "%.1f".format(Locale.US, f.blocksPerSec), "块/s"),
    Tile("累计块", f.totalBlocks.toString()),
    Tile("丢块", f.droppedBlocks.toString(), "",
        if (f.droppedBlocks > 0) Tone.Warn else Tone.Neutral),
    Tile("重连", f.reconnectCount.toString(), "次",
        if (f.reconnectCount > 0) Tone.Warn else Tone.Neutral),
    Tile("AFC", "%.0f".format(Locale.US, f.afcHz), "Hz"),
    Tile("AFC 评分", "%.2f".format(Locale.US, f.afcScore)),
    Tile("解码 CPU", "%.1f".format(Locale.US, f.decodeCpuPct), "%",
        if (f.decodeCpuPct > 60f) Tone.Warn else Tone.Ok),
    Tile("缓冲", "%.0f".format(Locale.US, f.bufferLevel * 100f), "%",
        if (f.bufferLevel > 0.85f) Tone.Err else Tone.Neutral),
    Tile("采样率", "%.0f".format(Locale.US, f.actualSampleRate / 1000.0), "kS/s"),
    Tile("调谐", "%.4f".format(Locale.US, f.hwFreqHz / 1e6), "MHz"),
    Tile("增益", "%.1f".format(Locale.US, f.appliedGainCentiDb / 100.0), "dB"),
    Tile("tuner", "ID ${f.tunerTypeId}"),
    Tile("链路", if (f.linkMode == 0) "USB 直连" else "pipe 桥"),
)
