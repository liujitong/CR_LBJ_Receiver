package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.Divider
import xyz.mlxkj.crlbj.ui.components.InfoRow
import xyz.mlxkj.crlbj.ui.components.LbjTextField
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

private enum class QueryMode(val label: String) { Train("车次查询"), Loco("机车配属") }

/**
 * 车次·配属查询（原「查询」页，v3.1 起并入设置页「查询·数据」分组，不再占 Dock 页签）。
 *
 * 数据来源全部走 `shared/`（与桌面端逐字一致）与公开接口：
 *  · 车次：TrainInfoClient（RailGo 优先，失败自动退 12306；可在设置里锁源）
 *  · 配属：LocoRoster（loco_types.csv + loco_roster.csv，规则与桌面端 1:1）
 *  · 参数：loco_specs.json
 *
 * 所有网络/磁盘动作都在 Dispatchers.IO，失败只出文案不抛异常。
 * 本 composable 不带自己的滚动容器，由设置页的分组滚动承载。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuerySection(vm: ReceiverViewModel) {
    val p = pal()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    // 数据更新后会换成新实例，所以每次重组取当前实例（Holder 内是 volatile 引用，开销可忽略）
    val roster = vm.currentRoster()

    var mode by remember { mutableStateOf(QueryMode.Train) }

    // ---- 车次状态 ----
    var trainInput by remember { mutableStateOf("") }
    var trainLoading by remember { mutableStateOf(false) }
    var trainResult by remember { mutableStateOf<TrainInfoClient.TrainInfo?>(null) }
    var showStops by remember { mutableStateOf(false) }
    val stopsSheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val pickerSheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    // ---- 机车状态 ----
    var locoModel by remember { mutableStateOf("") }
    var locoNumber by remember { mutableStateOf("") }
    var locoLoading by remember { mutableStateOf(false) }
    var locoResult by remember { mutableStateOf<LocoRoster.Lookup?>(null) }
    var locoSpec by remember { mutableStateOf<LocoRoster.Spec?>(null) }
    var modelPicker by remember { mutableStateOf(false) }

    fun runTrainQuery() {
        val q = trainInput
        if (q.isBlank() || trainLoading) return
        trainLoading = true
        trainResult = null
        scope.launch {
            val res = withContext(Dispatchers.IO) {
                TrainInfoClient.query(q, prefer = settings.trainQuerySource)
            }
            trainResult = res
            trainLoading = false
        }
    }

    fun runLocoQuery() {
        if (locoLoading) return
        if (locoModel.isBlank() && locoNumber.isBlank()) return
        locoLoading = true
        locoResult = null
        locoSpec = null
        // 型号框留空、号码框里粘的是「HXD1D-0123」时先拆一次，避免误报「缺少机车型号」
        var model = locoModel
        var number = locoNumber
        if (model.isBlank()) {
            val (m, n) = LocoRoster.parseLocoText(number)
            model = m
            number = n ?: ""
        }
        scope.launch {
            val (lookup, spec) = withContext(Dispatchers.IO) {
                val l = roster.lookup(model, number)
                l to roster.specsFor(l.model.ifEmpty { model })
            }
            locoResult = lookup
            locoSpec = spec
            locoLoading = false
        }
    }

    // ---- 从解码页跳过来时预填并自动查 ----
    val pending by vm.pendingQuery.collectAsStateWithLifecycle()
    LaunchedEffect(pending) {
        val q = pending ?: return@LaunchedEffect
        when (q.kind) {
            ReceiverViewModel.PendingQuery.Kind.TRAIN -> {
                mode = QueryMode.Train
                trainInput = q.text
                vm.consumePendingQuery()
                runTrainQuery()
            }
            ReceiverViewModel.PendingQuery.Kind.LOCO -> {
                mode = QueryMode.Loco
                locoModel = q.text
                locoNumber = q.number
                vm.consumePendingQuery()
                runLocoQuery()
            }
        }
    }

    // v4.0：补统一左右内边距（此前根 Column 无 padding，标题/输入区贴着屏幕左边缘，
    // 和 InfoPage / DecodePage 的 Dim.pagePad 不一致，看起来像整体左偏）
    Column(Modifier.fillMaxWidth().padding(horizontal = Dim.pagePad)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "车次·配属查询",
                color = p.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                QueryMode.entries.forEach { m ->
                    ModePill(m.label, mode == m) { mode = m }
                }
            }
        }
        Spacer(Modifier.height(4.dp))
        Text(
            when (mode) {
                QueryMode.Train -> "车次时刻 / 担当 / 配属（数据源：${sourceWord(settings.trainQuerySource)}）"
                QueryMode.Loco -> "机车配属号段 / 车型参数（内含 ${roster.stats().rows} 行号段表）"
            },
            color = p.textTertiary, fontSize = 11.sp,
        )
        Spacer(Modifier.height(8.dp))
        when (mode) {
            QueryMode.Train -> TrainPanel(
                input = trainInput,
                onInput = { trainInput = it },
                loading = trainLoading,
                result = trainResult,
                onQuery = { runTrainQuery() },
                onShowStops = { showStops = true },
            )
            QueryMode.Loco -> LocoPanel(
                roster = roster,
                model = locoModel,
                number = locoNumber,
                loading = locoLoading,
                result = locoResult,
                spec = locoSpec,
                onModel = { locoModel = it },
                onNumber = { locoNumber = it },
                onQuery = { runLocoQuery() },
                onPickModel = { modelPicker = true },
            )
        }
    }

    if (showStops) {
        val r = trainResult
        if (r != null) {
            ModalBottomSheet(
                onDismissRequest = { showStops = false },
                sheetState = stopsSheet,
                containerColor = p.surface,
            ) {
                TrainStopsSheet(r)
            }
        }
    }

    if (modelPicker) {
        ModalBottomSheet(
            onDismissRequest = { modelPicker = false },
            sheetState = pickerSheet,
            containerColor = p.surface,
        ) {
            ModelPickerSheet(
                models = roster.models(),
                query = locoModel,
                onPick = {
                    locoModel = it
                    modelPicker = false
                },
            )
        }
    }
}

// ------------------------------------------------------------------ 车次面板

@Composable
private fun TrainPanel(
    input: String,
    onInput: (String) -> Unit,
    loading: Boolean,
    result: TrainInfoClient.TrainInfo?,
    onQuery: () -> Unit,
    onShowStops: () -> Unit,
) {
    val p = pal()
    Row(verticalAlignment = Alignment.CenterVertically) {
        LbjTextField(
            value = input,
            onValueChange = onInput,
            placeholder = "车次号，如 G7 / K1234",
            modifier = Modifier.weight(1f),
            onDone = onQuery,
        )
        Spacer(Modifier.width(Dim.gap))
        Button(
            onClick = onQuery,
            enabled = !loading && input.isNotBlank(),
            shape = RoundedCornerShape(50),
            colors = ButtonDefaults.buttonColors(
                containerColor = p.accent, contentColor = p.onAccent),
        ) {
            Text(if (loading) "查询中" else "查询", fontSize = 14.sp)
        }
    }
    Spacer(Modifier.height(Dim.gap))

    if (loading) {
        Row(
            Modifier.fillMaxWidth().padding(vertical = 24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CircularProgressIndicator(modifier = Modifier.height(18.dp).width(18.dp),
                color = p.accent, strokeWidth = 2.dp)
            Spacer(Modifier.width(10.dp))
            Text("正在查询…", color = p.textSecondary, fontSize = 13.sp)
        }
        return
    }

    val r = result ?: return

    if (!r.ok) {
        SectionCard("查询失败") {
            Text(r.error.ifEmpty { "未查询到车次" }, color = p.err, fontSize = 14.sp)
            if (r.fallbackFrom.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text("RailGo 未能返回结果：${r.fallbackFrom}", color = p.textTertiary, fontSize = 11.sp)
            }
            Spacer(Modifier.height(8.dp))
            Text(
                "可以换个车次号重试；若长期失败，检查网络或在设置里切换车次数据源。",
                color = p.textTertiary, fontSize = 11.sp,
            )
        }
        return
    }

    SectionCard(
        title = "车次",
        trailing = {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Chip(if (r.source == "railgo") "RailGo" else "12306", Tone.Neutral)
                if (r.fallbackFrom.isNotEmpty()) Chip("已退回", Tone.Warn)
            }
        },
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(r.train, color = p.text, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(8.dp))
            if (r.category.isNotEmpty()) Chip(r.category, Tone.Neutral)
        }
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(r.start.ifEmpty { "—" }, color = p.text, fontSize = 16.sp,
                fontWeight = FontWeight.Medium)
            Spacer(Modifier.width(6.dp))
            Text(r.startTime, color = p.textSecondary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
            Spacer(Modifier.width(8.dp))
            Text("→", color = p.textTertiary, fontSize = 14.sp)
            Spacer(Modifier.width(8.dp))
            Text(r.end.ifEmpty { "—" }, color = p.text, fontSize = 16.sp,
                fontWeight = FontWeight.Medium)
            Spacer(Modifier.width(6.dp))
            Text(r.endTime, color = p.textSecondary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
        }
        if (r.distance != null) {
            Spacer(Modifier.height(4.dp))
            Text("全程 %.0f km · %d 站".format(Locale.US, r.distance, r.stops.size),
                color = p.textTertiary, fontSize = 11.sp)
        }
    }

    Spacer(Modifier.height(Dim.gap))
    SectionCard("担当与配属") {
        InfoRow("担当局", r.bureau.ifEmpty { "—" })
        InfoRow("客运段", r.runner.ifEmpty { "—" })
        InfoRow("配属段", r.carOwner.ifEmpty { "—" })
        InfoRow("车型", r.car.ifEmpty { "—" })
        if (r.numberFull.isNotEmpty()) {
            InfoRow("车次全称", r.numberFull.joinToString(" / "))
        }
        InfoRow("开行日", if (r.rundays.isEmpty()) "—" else
            "${r.rundaysCount} 天（${r.rundays.take(3).joinToString(",")}"
                + if (r.rundaysCount > 3) "…）" else "）")
        if (r.queryDate.isNotEmpty()) InfoRow("查询日期", r.queryDate, mono = true)
    }

    if (r.diagram.isNotEmpty()) {
        Spacer(Modifier.height(Dim.gap))
        SectionCard(title = "交路${if (r.diagramType.isNotEmpty()) "（${r.diagramType}）" else ""}") {
            r.diagram.forEach { seg ->
                Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                    Text(seg.number, color = p.accent, fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace, modifier = Modifier.width(56.dp))
                    Text(
                        "${seg.fromStation} ${seg.fromTime} → ${seg.toStation} ${seg.toTime}",
                        color = p.textSecondary, fontSize = 12.sp,
                    )
                }
            }
        }
    }

    Spacer(Modifier.height(Dim.gap))
    SectionCard(
        title = "时刻表",
        trailing = { Text("共 ${r.stops.size} 站", color = p.textTertiary, fontSize = 11.sp) },
    ) {
        r.stops.take(4).forEach { StopRow(it) }
        if (r.stops.size > 4) {
            Spacer(Modifier.height(6.dp))
            Text(
                "展开全部 ${r.stops.size} 站",
                color = p.accent, fontSize = 13.sp,
                modifier = Modifier.clip(RoundedCornerShape(6.dp))
                    .clickable(onClick = onShowStops).padding(vertical = 6.dp),
            )
        } else if (r.stops.size > 1) {
            Spacer(Modifier.height(6.dp))
            Text(
                "全屏查看",
                color = p.accent, fontSize = 12.sp,
                modifier = Modifier.clip(RoundedCornerShape(6.dp))
                    .clickable(onClick = onShowStops).padding(vertical = 4.dp),
            )
        }
    }
}

@Composable
internal fun StopRow(s: TrainInfoClient.Stop) {
    val p = pal()
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            s.no.toString().padStart(2, ' '),
            color = p.textTertiary, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
            modifier = Modifier.width(22.dp),
        )
        Text(
            s.station, color = p.text, fontSize = 13.sp,
            fontWeight = if (s.arrive.isBlank() || s.no == 1) FontWeight.Medium else FontWeight.Normal,
            modifier = Modifier.weight(1f),
        )
        Text(
            s.arrive.ifEmpty { "—" }, color = p.textSecondary, fontSize = 11.sp,
            fontFamily = FontFamily.Monospace, modifier = Modifier.width(46.dp),
        )
        Text(
            s.depart.ifEmpty { "—" }, color = p.textSecondary, fontSize = 11.sp,
            fontFamily = FontFamily.Monospace, modifier = Modifier.width(46.dp),
        )
        Text(
            if (s.stopMin > 0) "${s.stopMin}分" else "—",
            color = p.textTertiary, fontSize = 11.sp,
            modifier = Modifier.width(36.dp),
        )
        Text(
            s.distance?.let { "%.0f".format(Locale.US, it) } ?: "—",
            color = p.textTertiary, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
            modifier = Modifier.width(52.dp),
        )
    }
}

@Composable
internal fun TrainStopsSheet(r: TrainInfoClient.TrainInfo) {
    val p = pal()
    Column(Modifier.fillMaxWidth().padding(horizontal = Dim.pagePad)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(r.train, color = p.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(8.dp))
            Text("${r.start} → ${r.end}", color = p.textSecondary, fontSize = 13.sp)
            Spacer(Modifier.weight(1f))
            Text("${r.stops.size} 站", color = p.textTertiary, fontSize = 12.sp)
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth()) {
            Text("序", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.width(22.dp))
            Text("站名", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.weight(1f))
            Text("到", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.width(46.dp))
            Text("发", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.width(46.dp))
            Text("停", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.width(36.dp))
            Text("里程", color = p.textTertiary, fontSize = 10.sp, modifier = Modifier.width(52.dp))
        }
        Divider()
        LazyColumn(Modifier.fillMaxWidth().height(460.dp)) {
            items(r.stops) { StopRow(it) }
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun ModelPickerSheet(
    models: List<String>,
    query: String,
    onPick: (String) -> Unit,
) {
    val p = pal()
    val q = query.trim().uppercase(Locale.US)
    val list = remember(models, q) {
        if (q.isEmpty()) models else models.filter { it.contains(q) }
    }
    Column(Modifier.fillMaxWidth().padding(horizontal = Dim.pagePad)) {
        Text("选择机车型号", color = p.text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Text(
            "共 ${models.size} 个型号" + if (q.isNotEmpty()) "，匹配 ${list.size} 个" else "",
            color = p.textTertiary, fontSize = 11.sp,
        )
        Spacer(Modifier.height(8.dp))
        if (list.isEmpty()) {
            Text("没有匹配的型号", color = p.textSecondary, fontSize = 13.sp,
                modifier = Modifier.padding(vertical = 16.dp))
        } else {
            LazyColumn(Modifier.fillMaxWidth().height(420.dp)) {
                items(list) { m ->
                    Text(
                        m,
                        color = p.text,
                        fontSize = 14.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(6.dp))
                            .clickable { onPick(m) }
                            .padding(vertical = 10.dp, horizontal = 4.dp),
                    )
                }
            }
        }
        Spacer(Modifier.height(20.dp))
    }
}

// ------------------------------------------------------------------ 机车面板

@Composable
private fun LocoPanel(
    roster: LocoRoster,
    model: String,
    number: String,
    loading: Boolean,
    result: LocoRoster.Lookup?,
    spec: LocoRoster.Spec?,
    onModel: (String) -> Unit,
    onNumber: (String) -> Unit,
    onQuery: () -> Unit,
    onPickModel: () -> Unit,
) {
    val p = pal()
    Row(verticalAlignment = Alignment.CenterVertically) {
        LbjTextField(
            value = model,
            onValueChange = onModel,
            placeholder = "型号，如 HXD1D",
            modifier = Modifier.weight(1.2f),
            onDone = onQuery,
        )
        Spacer(Modifier.width(6.dp))
        Text(
            "选",
            color = p.accent,
            fontSize = 13.sp,
            modifier = Modifier
                .clip(RoundedCornerShape(8.dp))
                .background(p.surfaceAlt)
                .clickable(onClick = onPickModel)
                .padding(horizontal = 10.dp, vertical = 10.dp),
        )
    }
    Spacer(Modifier.height(6.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        LbjTextField(
            value = number,
            onValueChange = onNumber,
            placeholder = "机车号，如 0123（可只填型号）",
            modifier = Modifier.weight(1f),
            keyboardType = KeyboardType.Number,
            onDone = onQuery,
        )
        Spacer(Modifier.width(Dim.gap))
        Button(
            onClick = onQuery,
            enabled = !loading && (model.isNotBlank() || number.isNotBlank()),
            shape = RoundedCornerShape(50),
            colors = ButtonDefaults.buttonColors(
                containerColor = p.accent, contentColor = p.onAccent),
        ) { Text(if (loading) "查询中" else "查询", fontSize = 14.sp) }
    }
    Spacer(Modifier.height(6.dp))
    Text(
        "也支持直接粘贴 HXD1D-0123 / HXD1D0123（型号框留空即可）",
        color = p.textTertiary, fontSize = 11.sp,
    )
    Spacer(Modifier.height(Dim.gap))

    if (loading) {
        Row(
            Modifier.fillMaxWidth().padding(vertical = 24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CircularProgressIndicator(modifier = Modifier.height(18.dp).width(18.dp),
                color = p.accent, strokeWidth = 2.dp)
            Spacer(Modifier.width(10.dp))
            Text("正在查号段表…", color = p.textSecondary, fontSize = 13.sp)
        }
        return
    }

    val r = result ?: return

    SectionCard(
        title = "配属",
        trailing = {
            Chip(
                when {
                    r.exact && r.depot.isNotBlank() -> "号段命中"
                    r.ok -> "仅识别型号"
                    else -> "未命中"
                },
                when {
                    r.exact && r.depot.isNotBlank() -> Tone.Ok
                    r.ok -> Tone.Warn
                    else -> Tone.Err
                },
            )
        },
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                listOf(r.model, r.numberText).filter { it.isNotBlank() }.joinToString(" "),
                color = p.text, fontSize = 26.sp, fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace,
            )
            if (r.name.isNotEmpty() && r.name != r.model) {
                Spacer(Modifier.width(8.dp))
                Text(r.name, color = p.textSecondary, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(8.dp))

        when {
            r.exact -> {
                InfoRow("配属单位", r.depot.ifEmpty { "（原表未标注配属）" })
                InfoRow("号段", r.range, mono = true)
                InfoRow("制造厂", r.maker.ifEmpty { "—" })
                InfoRow("备注", r.remark.ifEmpty { "—" })
                if (r.aliasFrom != null) {
                    InfoRow("型号归一", "${r.aliasFrom} → ${r.model}")
                }
                if (r.alternatives.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Text("另有 ${r.alternatives.size} 个重叠号段（按原表顺序取第一条）",
                        color = p.textTertiary, fontSize = 11.sp)
                    r.alternatives.take(3).forEach {
                        Text("· ${it.text} → ${it.depot.ifEmpty { "未标注" }}",
                            color = p.textSecondary, fontSize = 11.sp)
                    }
                }
            }
            r.ok -> {
                InfoRow("配属单位", "未知")
                InfoRow("原因", r.reason)
                if (r.number != null) {
                    val ranges = roster.rangesOf(r.model)
                    Text(
                        "该型号在表里的号段范围：" +
                            (if (ranges.isEmpty()) "（无）"
                            else ranges.take(6).joinToString("，") { it.text } +
                                if (ranges.size > 6) " …" else ""),
                        color = p.textTertiary, fontSize = 11.sp,
                        modifier = Modifier.padding(top = 6.dp),
                    )
                }
            }
            else -> {
                InfoRow("原因", r.reason)
                if (r.suggest.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Text("相近型号：${r.suggest.joinToString("，")}",
                        color = p.textSecondary, fontSize = 12.sp)
                }
            }
        }
    }

    if (spec != null && !spec.empty) {
        Spacer(Modifier.height(Dim.gap))
        SectionCard("车型参数") {
            if (spec.name.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(spec.name, color = p.text, fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    if (spec.type.isNotEmpty()) Chip(spec.type, Tone.Neutral)
                }
                Spacer(Modifier.height(6.dp))
            }
            InfoRow("轴式", spec.axle.ifEmpty { "—" }, mono = true)
            InfoRow("功率", spec.power.ifEmpty { "—" })
            InfoRow("构造速度", spec.speed.ifEmpty { "—" }, mono = true)
            InfoRow("制造", spec.maker.ifEmpty { "—" })
            if (spec.brief.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(spec.brief, color = p.textSecondary, fontSize = 12.sp, lineHeight = 18.sp)
            }
        }
    }
}

// ------------------------------------------------------------------ 小控件

@Composable
private fun ModePill(text: String, active: Boolean, onClick: () -> Unit) {
    val p = pal()
    Box(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(if (active) p.accent.copy(alpha = 0.16f) else p.surfaceAlt)
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 5.dp)
    ) {
        Text(
            text,
            color = if (active) p.accent else p.textSecondary,
            fontSize = 11.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

private fun sourceWord(prefer: String): String = when (prefer) {
    "railgo" -> "仅 RailGo"
    "12306" -> "仅 12306"
    else -> "RailGo→12306"
}
