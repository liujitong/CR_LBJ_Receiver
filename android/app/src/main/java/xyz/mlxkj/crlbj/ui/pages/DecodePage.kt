package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.Divider
import xyz.mlxkj.crlbj.ui.components.EmptyState
import xyz.mlxkj.crlbj.ui.components.InfoRow
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.StatusCapsule
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/**
 * 解码页：一键开始 + 信号强度（真实 RSSI 历史 + 门限线）+ 当前解码大卡 + 最近列表。
 *
 * v3.0 视觉：状态胶囊 / 分组卡片 / 方向方块 / 等宽数字；点卡片看详情（底部弹层）。
 * 新解码自动后台查询车次/配属并内联展示；点「车次」「机车」跳设置页查询分组并预填。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DecodePage(
    vm: ReceiverViewModel,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val running by vm.running.collectAsStateWithLifecycle()
    val logs by vm.logs.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()
    val events by vm.events.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val trainInfos by vm.trainInfos.collectAsStateWithLifecycle()
    val locoInfos by vm.locoInfos.collectAsStateWithLifecycle()
    val p = pal()

    // RSSI 历史环形缓冲（轮询帧驱动，最多 240 点 ≈ 36s）
    // 用不可变快照驱动重组：ArrayDeque 本身不是 snapshot 状态，改它不会触发重绘。
    val rssi = remember { ArrayDeque<Float>(240) }
    var rssiSnapshot by remember { mutableStateOf(FloatArray(0)) }
    LaunchedEffect(Unit) {
        var lastSeq = -1
        while (true) {
            val f = vm.status.value
            if (f != null && f.seq != lastSeq) {
                lastSeq = f.seq
                rssi.addLast(f.rssiDb)
                while (rssi.size > 240) rssi.removeFirst()
                rssiSnapshot = rssi.toFloatArray()
            }
            kotlinx.coroutines.delay(150)
        }
    }

    var detail by remember { mutableStateOf<DecodeEvent?>(null) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val latest = events.firstOrNull()

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        PageHeader(
            title = "解码",
            subtitle = latest?.let { it.category } ?: "等待第一条报文",
            trailing = {
                StatusCapsule(
                    sourceLabel = sourceLabelOf(settings.sourceType),
                    running = running,
                    lastEventTs = latest?.timestamp,
                    onToggle = { vm.toggleStartStop() },
                )
            },
        )

        // ---- 一键开始 / 停止 ----
        Button(
            onClick = { vm.toggleStartStop() },
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(50),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (running) p.surfaceAlt else p.accent,
                contentColor = if (running) p.text else p.onAccent,
            ),
        ) {
            Text(
                if (running) "■  停止接收" else "▶  一键开始",
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }

        Spacer(Modifier.height(Dim.gap))

        // ---- 信号强度卡 ----
        SectionCard(
            title = "信号",
            trailing = {
                val f = status
                if (f != null) {
                    val tone = when {
                        f.gateState >= 2 -> Tone.Ok
                        f.gateState == 1 -> Tone.Warn
                        else -> Tone.Neutral
                    }
                    Chip(
                        when (f.gateState) {
                            0 -> "门控关闭"; 1 -> "待命"; 2 -> "有信号"
                            3 -> "保持"; 4 -> "旁路"; else -> "未知"
                        },
                        tone,
                    )
                }
            },
        ) {
            Box(Modifier.fillMaxWidth().height(64.dp)) {
                Canvas(Modifier.fillMaxSize()) {
                    val gateDb = -55f
                    fun dbToY(db: Float): Float =
                        size.height * (1f - ((db + 140f) / 90f).coerceIn(0f, 1f))

                    // 门限线
                    drawLine(
                        p.warn.copy(alpha = 0.75f),
                        Offset(0f, dbToY(gateDb)),
                        Offset(size.width, dbToY(gateDb)),
                        1.5f,
                    )
                    val n = rssiSnapshot.size
                    if (n == 0) {
                        drawLine(
                            p.textTertiary.copy(alpha = 0.5f),
                            Offset(0f, dbToY(-140f)),
                            Offset(size.width, dbToY(-140f)),
                            2f,
                        )
                    } else {
                        val step = if (n > 1) size.width / (n - 1) else size.width
                        rssiSnapshot.forEachIndexed { i, db ->
                            val x = size.width - (n - 1 - i) * step
                            val on = db >= gateDb
                            drawLine(
                                if (on) p.accent else p.spectrum.copy(alpha = 0.55f),
                                Offset(x, dbToY(db)),
                                Offset(x, size.height),
                                if (n > 1) 2f else 4f,
                            )
                        }
                    }
                }
                status?.let {
                    Text(
                        "%.1f dB".format(Locale.US, it.rssiDb),
                        color = p.textSecondary, fontSize = 11.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.align(Alignment.TopStart),
                    )
                }
            }
        }

        Spacer(Modifier.height(Dim.gap))

        // ---- 当前解码 ----
        Box(Modifier.weight(1f)) {
            if (latest == null) {
                EmptyState(
                    title = if (running) "等待信号…" else "未开始接收",
                    hint = if (running)
                        "收到报文后这里显示 车次 / 方向 / 速度 / 公里标 / 线路 / 机车"
                    else
                        "点上方「一键开始」，或用状态胶囊切换数据源",
                )
            } else {
                CurrentCard(
                    ev = latest,
                    trainInfo = trainInfos[TrainInfoClient.normalizeTrain(latest.train)],
                    locoInfo = locoInfos[ReceiverViewModel.locoKey(latest.loco, latest.locoCode)],
                    onDetail = { detail = latest },
                    onQueryTrain = onQueryTrain,
                    onQueryLoco = onQueryLoco,
                )
            }
        }

        // ---- 最近解码 ----
        SectionCard(title = "最近解码", modifier = Modifier.padding(top = Dim.gap)) {
            if (events.size <= 1) {
                Text(
                    logs.takeLast(3).joinToString("\n").ifEmpty { "—" },
                    color = p.textTertiary,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                )
            } else {
                LazyColumn(Modifier.fillMaxWidth().height(150.dp)) {
                    items(events.drop(1).take(30), key = { it.uid + it.timestamp }) { ev ->
                        RecentRow(
                            ev = ev,
                            onClick = { detail = ev },
                            onQueryLoco = onQueryLoco,
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(Dim.dockSpace))
    }

    detail?.let { ev ->
        ModalBottomSheet(
            onDismissRequest = { detail = null },
            sheetState = sheetState,
            containerColor = p.surface,
        ) {
            DecodeDetailSheet(
                ev = ev,
                onQueryTrain = { onQueryTrain(it); detail = null },
                onQueryLoco = { m, n -> onQueryLoco(m, n); detail = null },
            )
        }
    }
}

/** 当前解码大卡：车次大号 + 方向方块 + 速度/公里标/线路/机车/时间 + 自动查询的车次/配属信息 */
@Composable
private fun CurrentCard(
    ev: DecodeEvent,
    trainInfo: TrainInfoClient.TrainInfo?,
    locoInfo: LocoRoster.Lookup?,
    onDetail: () -> Unit,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(Dim.cardCorner))
            .background(p.surface)
            .border(1.dp, p.border, RoundedCornerShape(Dim.cardCorner))
            .clickable(onClick = onDetail)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                ev.train.ifEmpty { "----" },
                color = p.text,
                fontSize = 38.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.5).sp,
                modifier = Modifier.clickable { if (ev.train.isNotBlank()) onQueryTrain(ev.train) },
            )
            Spacer(Modifier.width(10.dp))
            DirectionBadge(ev.direction)
            Spacer(Modifier.weight(1f))
            if (ev.hasInterference) Chip("干扰", Tone.Warn)
            Chip(
                if (ev.latitude != null) "含坐标" else "无坐标",
                if (ev.latitude != null) Tone.Ok else Tone.Neutral,
            )
        }
        Spacer(Modifier.height(6.dp))
        Text(ev.category, color = p.textSecondary, fontSize = 13.sp)

        Spacer(Modifier.height(12.dp))
        Row {
            BigMetric("速度", ev.speed.ifEmpty { "---" }, "km/h", Modifier.weight(1f))
            BigMetric("公里标", ev.position.ifEmpty { "---.-" }, "km", Modifier.weight(1f))
            BigMetric(
                label = "剩距/到达",
                value = ev.etaDistanceKm?.let { "%.1f".format(Locale.US, it) } ?: ev.etaTime,
                unit = if (ev.etaDistanceKm != null) "km" else "",
                modifier = Modifier.weight(1f),
            )
        }

        Spacer(Modifier.height(12.dp))
        Divider()
        Spacer(Modifier.height(8.dp))

        InfoRow("线路", ev.route.ifEmpty { "未知" })
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
            Text("机车", color = p.textSecondary, fontSize = 13.sp, modifier = Modifier.width(84.dp))
            Text(
                ev.loco.ifEmpty { "----" },
                color = p.accent,
                fontSize = 13.sp,
                modifier = Modifier.clickable {
                    if (ev.loco.isNotBlank()) {
                        val (m, n) = xyz.mlxkj.crlbj.data.LocoRoster.parseLocoText(ev.loco)
                        onQueryLoco(m, n ?: "")
                    }
                },
            )
        }
        // ---- 自动查询内联结果（收到新解码后台查好即显示；失败静默不显示） ----
        trainInfo?.let { ti ->
            // v3.2：等级 · 担当局 · 担当段/客运段 · 配属段/车辆段 · 车型 · 始发→终到
            val bits = listOf(ti.category, ti.bureau, ti.runner, ti.carOwner, ti.car)
                .filter { it.isNotBlank() }
            if (bits.isNotEmpty()) InfoRow("车次", bits.joinToString(" · "))
            if (ti.start.isNotBlank() || ti.end.isNotBlank()) {
                InfoRow("区间", "${ti.start.ifBlank { "?" }} → ${ti.end.ifBlank { "?" }}")
            }
        }
        locoInfo?.let { li ->
            if (li.ok) {
                val bits = listOf(
                    li.model,
                    li.depot.ifEmpty { "配属未知" },
                    li.maker,
                ).filter { it.isNotBlank() }
                if (bits.isNotEmpty()) InfoRow("配属", bits.joinToString(" · "))
            }
        }
        ev.latitude?.let {
            InfoRow(
                "坐标",
                "%.5f, %.5f".format(Locale.US, it, ev.longitude ?: 0.0),
                mono = true,
            )
        }
        InfoRow("ETA", "${ev.etaTime}  ${ev.etaStatus}")
        InfoRow("收到时间", ev.timeStr, mono = true)
    }
}

/** 最近解码列表的一行 */
@Composable
private fun RecentRow(
    ev: DecodeEvent,
    onClick: () -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            ev.train.ifEmpty { "----" },
            color = p.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.width(72.dp),
        )
        DirectionBadge(ev.direction, small = true)
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "%s km/h · K%s".format(
                    Locale.US, ev.speed.ifEmpty { "---" }, ev.position.ifEmpty { "---.-" }),
                color = p.textSecondary, fontSize = 12.sp, fontFamily = FontFamily.Monospace,
            )
            Text(
                listOfNotNull(
                    ev.route.takeIf { it.isNotBlank() }?.let { "线路 $it" },
                    ev.loco.takeIf { it.isNotBlank() }?.let { "机车 $it" },
                ).joinToString(" · ").ifEmpty { ev.category },
                color = p.textTertiary, fontSize = 11.sp, maxLines = 1,
            )
        }
        Text(ev.timeStr, color = p.textTertiary, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
    }
}

/** 方向方块（上/下行用带底色的方标签，比小字更醒目） */
@Composable
fun DirectionBadge(direction: String, small: Boolean = false) {
    val p = pal()
    val color = p.dirColor(direction)
    Box(
        Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(color.copy(alpha = 0.16f))
            .padding(horizontal = if (small) 4.dp else 6.dp, vertical = if (small) 1.dp else 2.dp)
    ) {
        Text(
            direction.ifEmpty { "未知" },
            color = color,
            fontSize = if (small) 10.sp else 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

/** 大号指标（速度/公里标/距到达） */
@Composable
private fun BigMetric(label: String, value: String, unit: String, modifier: Modifier = Modifier) {
    val p = pal()
    Column(modifier) {
        Text(label, color = p.textTertiary, fontSize = 11.sp)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                value,
                color = p.text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace,
            )
            if (unit.isNotEmpty()) {
                Spacer(Modifier.width(2.dp))
                Text(unit, color = p.textTertiary, fontSize = 10.sp,
                    modifier = Modifier.padding(bottom = 3.dp))
            }
        }
    }
}

/** 兼容重载：把 (label to value) 直接当指标用（距到达没有单位） */
@Composable
private fun BigMetric(pair: Pair<String, String>, unit: String, modifier: Modifier) {
    BigMetric(pair.first, pair.second, unit, modifier)
}/** 解码记录详情（底部弹层，不做整页跳转） */
@Composable
private fun DecodeDetailSheet(
    ev: DecodeEvent,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Dim.pagePad)
            .padding(bottom = 28.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ev.train.ifEmpty { "----" }, color = p.text, fontSize = 26.sp,
                fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(10.dp))
            DirectionBadge(ev.direction)
            Spacer(Modifier.weight(1f))
            Text(ev.timeStr, color = p.textTertiary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(10.dp))
        SectionCard("基本") {
            InfoRow("类别", ev.category)
            InfoRow("速度", "${ev.speed} km/h", mono = true)
            InfoRow("公里标", ev.position, mono = true)
            InfoRow("线路", ev.route.ifEmpty { "未知" })
            InfoRow("机车", ev.loco.ifEmpty { "----" }, mono = true)
            InfoRow("机车代号", ev.locoCode.ifEmpty { "----" }, mono = true)
            InfoRow("报文类型", if (ev.isDetailed) "详细长报文" else "基础短报文")
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("到达估算") {
            InfoRow("预计到达", ev.etaTime, mono = true)
            InfoRow("剩余里程", ev.etaDistanceKm?.let { "%.1f km".format(Locale.US, it) } ?: "—",
                mono = true)
            InfoRow("状态", ev.etaStatus)
            InfoRow("剩余秒数", ev.etaSeconds?.let { "%.0f s".format(Locale.US, it) } ?: "—",
                mono = true)
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("链路") {
            InfoRow("RSSI", "%.1f dB".format(Locale.US, ev.rssi), mono = true)
            InfoRow("AFC", "%.0f Hz（评分 %.2f）".format(Locale.US, ev.afcHz, ev.afcScore), mono = true)
            ev.latitude?.let {
                InfoRow("坐标", "%.5f, %.5f".format(Locale.US, it, ev.longitude ?: 0.0), mono = true)
            }
            InfoRow("BCH 错", if (ev.msgTypeError) "有" else "无")
            InfoRow("原始 BCD", ev.rawBcd.ifEmpty { "—" }, mono = true)
            InfoRow("地址", "0x%X".format(ev.rawAddr), mono = true)
            InfoRow("合并/独立", listOfNotNull(
                "合并".takeIf { ev.rawIsMerged },
                "独立".takeIf { ev.rawIsStandalone },
                "短报文".takeIf { ev.rawIsShort },
            ).joinToString(" / ").ifEmpty { "—" })
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(Dim.gap)) {
            Button(
                onClick = { if (ev.train.isNotBlank()) onQueryTrain(ev.train) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(containerColor = p.accent),
            ) { Text("查这趟车", fontSize = 13.sp) }
            Button(
                onClick = {
                    if (ev.loco.isNotBlank()) {
                        val (m, n) = xyz.mlxkj.crlbj.data.LocoRoster.parseLocoText(ev.loco)
                        onQueryLoco(m, n ?: "")
                    }
                },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(
                    containerColor = p.surfaceAlt, contentColor = p.text),
            ) { Text("查这台机车", fontSize = 13.sp) }
        }
    }
}

/** 数据源显示名（与地图页同一套文案） */
internal fun sourceLabelOf(type: String): String = when (type) {
    "usb" -> "USB 直连"
    "rtl_tcp" -> "rtl_tcp"
    "owrx" -> "OWRX"
    else -> type
}
