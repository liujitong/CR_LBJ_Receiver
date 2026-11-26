package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
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
import kotlinx.coroutines.delay

/**
 * 状态页 v3.2.1：指标按「信号·门控 / 数据流 / 射频·链路」三组重排。
 *
 *  · 第一组是主指标（2 列大块，24sp 数字），一眼能读；其余两组 3 列紧凑块，
 *    同组内格子等宽等号，不再出现大小参差；
 *  · 日志区折叠时显示最近 2 条、展开限高 240dp 内部滚动并自动跟到最新，
 *    不会再把整页撑长或挤成一条缝；
 *  · 没有状态帧时给「引擎 + 一键开始」，避免上半屏空白。
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
            EngineIdleCard(
                running = running,
                sourceLabel = sourceLabelOf(settings.sourceType),
                sampleRate = settings.sampleRate,
                onToggle = { vm.toggleStartStop() },
            )
        } else {
            val groups = metricGroups(fr)
            groups.forEachIndexed { i, g ->
                if (i > 0) Spacer(Modifier.height(6.dp))
                MetricSection(
                    title = g.title,
                    tiles = g.tiles,
                    columns = g.columns,
                    large = g.large,
                    trailing = if (i == 0) {
                        {
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
                        }
                    } else null,
                )
            }
        }

        Spacer(Modifier.height(6.dp))
        LogCard(logs)
        Spacer(Modifier.height(Dim.dockSpace))
    }
}

// ------------------------------------------------------------------ 指标分组

private data class Tile(
    val label: String,
    val value: String,
    val unit: String = "",
    val tone: Tone = Tone.Neutral,
)

private data class MetricGroup(
    val title: String,
    val columns: Int,
    val large: Boolean,
    val tiles: List<Tile>,
)

/**
 * 15 项指标一个不丢，只按「主 → 次」重新分组：
 *  信号·门控（主，2 列）→ 数据流（3 列）→ 射频·链路（3 列）。
 */
private fun metricGroups(f: StatusFrame): List<MetricGroup> = listOf(
    MetricGroup(
        title = "信号 · 门控", columns = 2, large = true,
        tiles = listOf(
            Tile("信号强度", "%.0f".format(Locale.US, f.rssiDb), "dB",
                when {
                    f.gateState >= 2 -> Tone.Ok
                    f.gateState == 1 -> Tone.Warn
                    else -> Tone.Neutral
                }),
            Tile("门控", gateText(f.gateState),
                tone = when (f.gateState) {
                    1 -> Tone.Warn
                    2, 3 -> Tone.Ok
                    else -> Tone.Neutral
                }),
            Tile("AFC", "%.0f".format(Locale.US, f.afcHz), "Hz"),
            Tile("AFC 评分", "%.2f".format(Locale.US, f.afcScore)),
        ),
    ),
    MetricGroup(
        title = "数据流", columns = 3, large = false,
        tiles = listOf(
            Tile("块率", "%.1f".format(Locale.US, f.blocksPerSec), "块/s"),
            Tile("累计块", bigCount(f.totalBlocks)),
            Tile("丢块", bigCount(f.droppedBlocks), "",
                if (f.droppedBlocks > 0) Tone.Warn else Tone.Neutral),
            Tile("重连", f.reconnectCount.toString(), "次",
                if (f.reconnectCount > 0) Tone.Warn else Tone.Neutral),
            Tile("缓冲", "%.0f".format(Locale.US, f.bufferLevel * 100f), "%",
                if (f.bufferLevel > 0.85f) Tone.Err else Tone.Neutral),
            Tile("解码 CPU", "%.1f".format(Locale.US, f.decodeCpuPct), "%",
                if (f.decodeCpuPct > 60f) Tone.Warn else Tone.Ok),
            // v3.2.9：解析不出车次的帧按功能码判上/下行，计入干扰（只统计、不入库）
            Tile("干扰 上行", bigCount(f.interferenceUp), "帧",
                if (f.interferenceUp > 0) Tone.Warn else Tone.Neutral),
            Tile("干扰 下行", bigCount(f.interferenceDown), "帧",
                if (f.interferenceDown > 0) Tone.Warn else Tone.Neutral),
        ),
    ),
    MetricGroup(
        title = "射频 · 链路", columns = 3, large = false,
        tiles = listOf(
            Tile("采样率", "%.0f".format(Locale.US, f.actualSampleRate / 1000.0), "kS/s"),
            // 4 位小数 + 单位会撑破 1/3 宽格子（v3.2.1 实测会把整行撑高），
            // 单位并入标签、数值保留 3 位小数（1 kHz 精度，48k 带宽下足够）
            Tile("调谐 MHz", "%.3f".format(Locale.US, f.hwFreqHz / 1e6)),
            Tile("增益", "%.1f".format(Locale.US, f.appliedGainCentiDb / 100.0), "dB"),
            Tile("tuner", "ID ${f.tunerTypeId}"),
            Tile("链路", if (f.linkMode == 0) "USB" else "桥"),
        ),
    ),
)

private fun gateText(gate: Int): String = when (gate) {
    0 -> "关闭"; 1 -> "待命"; 2 -> "开启"; 3 -> "保持"; 4 -> "旁路"; else -> "?"
}

/** 大整数紧凑显示（累计块/丢块长期运行会到百万级，1/3 宽格子放不下 8 位数字） */
private fun bigCount(n: Int): String = when {
    n >= 10_000_000 -> "%.1fM".format(Locale.US, n / 1_000_000.0)
    n >= 1_000_000 -> "%.2fM".format(Locale.US, n / 1_000_000.0)
    else -> n.toString()
}

@Composable
private fun MetricSection(
    title: String,
    tiles: List<Tile>,
    columns: Int,
    large: Boolean,
    trailing: (@Composable () -> Unit)? = null,
) {
    SectionCard(title = title, trailing = trailing) {
        val rows = tiles.chunked(columns)
        rows.forEachIndexed { idx, row ->
            Row(
                Modifier.fillMaxWidth().height(IntrinsicSize.Min),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                row.forEach { t ->
                    MetricTile(
                        label = t.label,
                        value = t.value,
                        unit = t.unit,
                        tone = t.tone,
                        large = large,
                        // fillMaxHeight：同一行格子等高，不再出现「大小参差」的突兀感
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                    )
                }
                // 补齐末行，保证格子等宽（末行不满时右侧留空而不是拉宽）
                repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
            }
            if (idx < rows.lastIndex) Spacer(Modifier.height(if (large) 6.dp else 5.dp))
        }
    }
}

// ------------------------------------------------------------------ 无状态帧

@Composable
private fun EngineIdleCard(
    running: Boolean,
    sourceLabel: String,
    sampleRate: Int,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val p = pal()
    SectionCard(
        title = "引擎",
        modifier = modifier,
        trailing = {
            Chip(if (running) "等待首帧" else "未运行",
                if (running) Tone.Warn else Tone.Neutral)
        },
    ) {
        Text(
            if (running) "已开始接收，等待第一帧状态…" else "引擎未运行，暂无状态帧。",
            color = p.textSecondary, fontSize = 13.sp,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "$sourceLabel · ${sampleRate / 1000} kS/s · 状态帧每 150 ms 上报一次",
            color = p.textTertiary, fontSize = 11.sp,
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = onToggle,
            modifier = Modifier.fillMaxWidth().height(44.dp),
            shape = RoundedCornerShape(50),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (running) p.surfaceAlt else p.accent,
                contentColor = if (running) p.text else p.onAccent,
            ),
        ) {
            Text(
                if (running) "■  停止接收" else "▶  开始接收",
                fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

// -------------------------------------------------------------------- 日志区

/**
 * 日志卡：折叠显示最近 2 条；展开限高 240dp、内部滚动并自动跟到最新。
 * 点标题右侧或日志正文都能折叠/展开。
 */
@Composable
private fun LogCard(logs: List<String>) {
    val p = pal()
    var expanded by rememberSaveable { mutableStateOf(false) }
    val scroll = rememberScrollState()
    val shown = if (expanded) logs.takeLast(60) else logs.takeLast(2)

    SectionCard(
        title = "日志",
        trailing = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${logs.size} 条", color = p.textTertiary, fontSize = 11.sp)
                Text(
                    if (expanded) "收起 ▲" else "展开 ▼",
                    color = p.accent, fontSize = 12.sp,
                    modifier = Modifier
                        .padding(start = 8.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .clickable { expanded = !expanded }
                        .padding(horizontal = 6.dp, vertical = 2.dp),
                )
            }
        },
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(6.dp))
                .background(p.surfaceAlt.copy(alpha = 0.55f))
                .clickable { expanded = !expanded }
                .then(
                    if (expanded) Modifier.heightIn(max = 240.dp).verticalScroll(scroll)
                    else Modifier
                )
                .padding(horizontal = 8.dp, vertical = 5.dp),
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
        if (expanded) {
            // 展开后滚到最新；等一帧让 maxValue 量好
            LaunchedEffect(expanded, logs.size) {
                delay(50)
                scroll.scrollTo(scroll.maxValue)
            }
        }
    }
}

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