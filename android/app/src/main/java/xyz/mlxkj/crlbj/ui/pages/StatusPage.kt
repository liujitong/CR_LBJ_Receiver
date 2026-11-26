package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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

        // 日志：可点按折叠/展开；折叠只显示最新一条，展开按条渲染并按前缀着色
        var logsExpanded by rememberSaveable { mutableStateOf(false) }
        SectionCard(
            title = "日志",
            trailing = {
                Text(
                    if (logsExpanded) "收起 ▲" else "展开 ▼",
                    color = p.accent, fontSize = 12.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .clickable { logsExpanded = !logsExpanded }
                        .padding(horizontal = 6.dp, vertical = 2.dp),
                )
            },
        ) {
            val shown = if (logsExpanded) logs.takeLast(40) else logs.takeLast(1)
            Column(
                Modifier
                    .fillMaxWidth()
                    .clickable { logsExpanded = !logsExpanded },
            ) {
                if (shown.isEmpty()) {
                    Text(
                        "（暂无日志）",
                        color = p.textTertiary, fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace, lineHeight = 16.sp,
                    )
                } else {
                    shown.forEach { line ->
                        Text(
                            line,
                            color = logColor(line),
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                            lineHeight = 16.sp,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
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

/**
 * 日志前缀 → 颜色（UI 层判级，不动日志管道）。
 * 前缀集合来自 engine.log / native 实际输出：
 * [错误]→错误色；[监护]/[事件]→警告色；[数据]/[启动]→正常色；
 * [初始化]/[链路]/[USB]/[pipe]→信息色；[停止]→三级灰。
 */
@Composable
private fun logColor(line: String): Color {
    val p = pal()
    return when {
        line.startsWith("[错误]") -> p.err
        line.startsWith("[监护]") || line.startsWith("[事件]") -> p.warn
        line.startsWith("[数据]") || line.startsWith("[启动]") -> p.ok
        line.startsWith("[停止]") -> p.textTertiary
        else -> p.textSecondary
    }
}

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
    Tile("链路", if (f.linkMode == 0) "USB" else "桥"),
)
