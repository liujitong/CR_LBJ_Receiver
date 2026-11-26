package xyz.mlxkj.crlbj.ui.components

import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import xyz.mlxkj.crlbj.core.DepotNames
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.ui.pages.TrainStopsSheet
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import java.util.Locale

/**
 * 记录详情弹层 —— **与桌面 `RecordDetailDialog` 逐项对齐**（v3.2.8）。
 *
 * 五个页签与桌面同名同序：解码结果 / 原始数据 / BCD 原始数据 / 解码过程 / 纠错码字。
 * 字段标签、取值格式（`%.6f`、`----`/`—` 兜底、"通过/未通过"）、RailGo 区块文案、
 * 解码过程推演文本、底部「在地图中查看 / 关闭」全部对齐桌面实现；
 * 桌面是双击弹窗，安卓是底部弹层 + TabRow——展示形式不同，内容一致。
 *
 * 用法：`ModalBottomSheet { RecordDetailSheet(...) }`。
 *
 * @param r          记录（当前解码事件用 RecordEntity.fromEvent 现场转换即可复用）
 * @param trainInfo  RailGo 车次结果缓存（null = 尚未返回）
 * @param trainError ensure 查询失败原因（无缓存时展示，避免永远"查询中"）
 * @param onEnsure   触发一次车次查询（页面接 vm.ensureTrainInfo）
 * @param loco       号段表查询结果（可空）
 * @param spec       车型技术参数（loco_specs，可空）
 * @param onClose    关闭整个弹层
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordDetailSheet(
    r: RecordEntity,
    trainInfo: TrainInfoClient.TrainInfo?,
    trainError: String?,
    onEnsure: () -> Unit,
    loco: LocoRoster.Lookup?,
    spec: LocoRoster.Spec?,
    onClose: () -> Unit,
) {
    val p = pal()
    var tab by remember(r.uid) { mutableIntStateOf(0) }
    var showLocoDetail by remember(r.uid) { mutableStateOf(false) }
    var showTimetable by remember(r.uid) { mutableStateOf(false) }
    val ctx = LocalContext.current
    val locoSheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val stopsSheet = rememberModalBottomSheetState()

    // 打开详情即触发一次 RailGo 查询（桌面同款：仅详细报文查询）
    LaunchedEffect(r.uid) { if (r.isDetailed) onEnsure() }

    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Dim.pagePad)
            .padding(bottom = 16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                r.train.ifEmpty { "----" },
                color = p.text, fontSize = 24.sp, fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.width(10.dp))
            Text(r.timeStr, color = p.textTertiary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(8.dp))

        TabRow(
            selectedTabIndex = tab,
            containerColor = p.surfaceAlt,
            contentColor = p.accent,
            modifier = Modifier.clip(RoundedCornerShape(topStart = 8.dp, topEnd = 8.dp)),
        ) {
            DETAIL_TABS.forEachIndexed { i, t ->
                Tab(
                    selected = tab == i,
                    onClick = { tab = i },
                    text = {
                        Text(t, fontSize = 11.sp, maxLines = 1,
                            fontWeight = if (tab == i) FontWeight.SemiBold
                            else FontWeight.Normal)
                    },
                )
            }
        }
        Box(
            Modifier
                .fillMaxWidth()
                .height(400.dp)
                .clip(RoundedCornerShape(bottomStart = 8.dp, bottomEnd = 8.dp))
                .background(p.surface)
                .verticalScroll(rememberScrollState()),
        ) {
            when (tab) {
                0 -> ResultTab(r, trainInfo, trainError, loco, spec,
                    onLocoDetail = { showLocoDetail = true },
                    onTimetable = { showTimetable = true })
                1 -> RawTab(r)
                2 -> BcdTab(r)
                3 -> ProcessTab(r)
                4 -> CodewordTab(r)
            }
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            val hasCoord = r.latitude != null && r.longitude != null
            ActionBtn("在地图中查看", enabled = hasCoord) {
                // 与桌面一致：打开天地图（WGS-84 零偏移系）
                val url = "https://map.tianditu.gov.cn/#/map?center=" +
                    "%.6f,%.6f".format(Locale.US, r.longitude, r.latitude) + "&zoom=15"
                runCatching {
                    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                }
            }
            Spacer(Modifier.weight(1f))
            ActionBtn("关闭", primary = true, onClick = onClose)
        }
    }

    if (showLocoDetail && spec != null) {
        ModalBottomSheet(
            onDismissRequest = { showLocoDetail = false },
            sheetState = locoSheet,
            containerColor = p.surface,
        ) {
            LocoDetailSheetContent(spec, loco, onDismiss = { showLocoDetail = false })
        }
    }
    if (showTimetable && trainInfo != null && trainInfo.stops.isNotEmpty()) {
        ModalBottomSheet(
            onDismissRequest = { showTimetable = false },
            sheetState = stopsSheet,
            containerColor = p.surface,
        ) {
            TrainStopsSheet(trainInfo)
        }
    }
}

private val DETAIL_TABS =
    listOf("解码结果", "原始数据", "BCD", "解码过程", "纠错码字")

// ------------------------------------------------------------------ ① 解码结果
@Composable
private fun ResultTab(
    r: RecordEntity,
    ti: TrainInfoClient.TrainInfo?,
    tiErr: String?,
    loco: LocoRoster.Lookup?,
    spec: LocoRoster.Spec?,
    onLocoDetail: () -> Unit,
    onTimetable: () -> Unit,
) {
    val p = pal()
    // 配属文本（对齐桌面 depot_text 三分支；全称化与 PC 同表 DepotNames）
    val depotText = when {
        loco == null -> "—（配属表未收录）"
        loco.exact -> DepotNames.fullDepot(loco.depot).ifEmpty { "（原表未标注配属）" }
        loco.ok -> "未知（${loco.reason.ifEmpty { "号段未收录" }}）"
        else -> "—（${loco.reason.ifEmpty { "配属表未收录" }}）"
    }
    val rangeText = loco?.range?.ifEmpty { "—" } ?: "—"
    val paramText = listOfNotNull(
        spec?.power?.ifEmpty { null }, spec?.axle?.ifEmpty { null },
        spec?.speed?.ifEmpty { null },
    ).joinToString(" · ").ifEmpty { "—" }

    val items = listOf(
        "时间" to r.timeStr,
        "车次" to r.train.ifEmpty { "----" },
        "纯数字车次" to r.baseTrain.ifEmpty { "----" },
        "前缀" to r.prefix.ifEmpty { "无" },
        "方向" to r.direction.ifEmpty { "未知" },
        "速度" to "${r.speed.ifEmpty { "---" }} km/h",
        "公里标" to "${r.position.ifEmpty { "---.-" }} km",
        "线路" to r.route.ifEmpty { "----" },
        "机车号" to r.loco.ifEmpty { "----" },
        "机车代号" to r.locoCode.ifEmpty { "---" },
        "配属" to depotText,
        "号段" to rangeText,
        "车型参数" to paramText,
        "类别" to r.category.ifEmpty { "未知" },
        "报文类型" to msgTypeLabel(r),
        "经度" to (r.longitude?.let { "%.6f".format(Locale.US, it) } ?: "----"),
        "纬度" to (r.latitude?.let { "%.6f".format(Locale.US, it) } ?: "----"),
        "线路校验" to if (r.routeValid) "通过" else "未通过",
        "BCH 纠错" to if (r.msgTypeError) "有错误" else "正常",
        "预计到达" to r.etaTime,
        "预计距离" to (r.etaDistanceKm?.let { "${fmtKm(it)} km" } ?: "---"),
    )
    Column {
        PairGrid(items)
        Spacer(Modifier.height(8.dp))
        // 机车简介行（对齐桌面 locoBox：名称|类型|功率|速度 + 简介 + 按钮）
        Row(verticalAlignment = Alignment.Top) {
            Text(
                if (spec != null) {
                    "${spec.name}  |  ${spec.type}  |  ${spec.power}  |  ${spec.speed}\n" +
                        spec.brief
                } else "暂无该车型资料",
                color = p.text, fontSize = 11.sp, modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(8.dp))
            ActionBtn("机车详情", enabled = spec != null, compact = true,
                onClick = onLocoDetail)
        }
        Spacer(Modifier.height(8.dp))
        // RailGo 区块（对齐桌面 qBox + _onRailgoResult 文案分支）
        val railgoText = when {
            !r.isDetailed -> "非详细报文，不查询车次信息"
            r.train.isEmpty() || r.train in setOf("----", "未知") ->
                "无车次号，不查询车次信息"
            ti != null && ti.ok -> railgoLines(ti)
            ti != null -> "未查询到 ${ti.train.ifEmpty { r.train }} 的车次信息" +
                "（${ti.error.ifEmpty { "未查询到车次信息" }}）"
            tiErr != null -> "未查询到 ${r.train} 的车次信息（$tiErr）"
            else -> "车次信息查询中…"
        }
        val railgoColor = when {
            ti != null && ti.ok -> p.text
            ti != null || tiErr != null -> p.warn
            r.isDetailed -> p.textSecondary
            else -> p.textTertiary
        }
        Row(verticalAlignment = Alignment.Top) {
            Text("RailGo", color = p.accentAlt, fontSize = 11.sp,
                fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(8.dp))
            Text(railgoText, color = railgoColor, fontSize = 11.sp,
                modifier = Modifier.weight(1f))
            Spacer(Modifier.width(8.dp))
            ActionBtn("时刻表", compact = true,
                enabled = ti != null && ti.ok && ti.stops.isNotEmpty(),
                onClick = onTimetable)
        }
        Spacer(Modifier.height(6.dp))
    }
}

/** RailGo 展示行（与桌面 _onRailgoResult 的 lines 拼接逐条一致） */
private fun railgoLines(ti: TrainInfoClient.TrainInfo): String {
    val lines = ArrayList<String>()
    val head = ArrayList<String>()
    if (ti.category.isNotEmpty()) head.add(ti.category)
    val duty = DepotNames.formatDuty(ti.bureau, ti.runner)
    if (duty.isNotEmpty()) head.add("担当 $duty")
    if (head.isNotEmpty()) lines.add(head.joinToString(" · "))
    val owner = ArrayList<String>()
    if (ti.carOwner.isNotEmpty()) owner.add("配属 " + DepotNames.fullDepot(ti.carOwner))
    if (ti.car.isNotEmpty()) owner.add("车型 " + ti.car)
    if (owner.isNotEmpty()) lines.add(owner.joinToString(" · "))
    if (ti.start.isNotEmpty() || ti.end.isNotEmpty()) {
        val tS = if (ti.startTime.isNotEmpty()) "（${ti.startTime}）" else ""
        val tE = if (ti.endTime.isNotEmpty()) "（${ti.endTime}）" else ""
        lines.add("${ti.start}$tS → ${ti.end}$tE")
    }
    // 主要停站：中间站取有到/发时刻的，最多 6 个（与桌面一致，避免撑爆详情）
    if (ti.stops.size >= 3) {
        val mids = ti.stops.subList(1, ti.stops.size - 1)
            .filter { it.arrive !in setOf("----", "") || it.depart !in setOf("----", "") }
        if (mids.isNotEmpty()) {
            val shots = mids.take(6).map { s ->
                when {
                    s.arrive !in setOf("----", "") && s.depart !in setOf("----", "") ->
                        "${s.station} ${s.arrive}/${s.depart}"
                    s.depart !in setOf("----", "") -> "${s.station} 发${s.depart}"
                    else -> "${s.station} 到${s.arrive}"
                }
            }
            lines.add("主要停站：" + shots.joinToString(" · ") +
                if (mids.size > 6) " 等" else "")
        }
    }
    lines.add("来源 " + if (ti.source == "railgo") "RailGo" else "12306")
    return lines.joinToString("\n")
}

// ------------------------------------------------------------------ ② 原始数据
@Composable
private fun RawTab(r: RecordEntity) {
    val items = listOf(
        "报文地址" to r.rawAddr.toString(),
        "功能码" to funcLabel(r.rawFunc),
        "信号强度" to "%.1f dB".format(Locale.US, r.rssi),
        "AFC 补偿" to "%+.0f Hz".format(Locale.US, r.afcHz),
        "频率误差" to "%+.0f Hz".format(Locale.US, r.afcErrHz),
        "AFC 置信度" to "%.2f".format(Locale.US, r.afcScore),
        "短报文" to if (r.rawIsShort) "是" else "否",
        "合并报文" to if (r.rawIsMerged) "是" else "否",
        "独立长报文" to if (r.rawIsStandalone) "是" else "否",
        "到达状态" to r.etaStatus,
    )
    Column(Modifier.padding(4.dp)) { PairGrid(items) }
}

private fun funcLabel(func: Int): String = when (func) {
    1 -> "下行 (1)"
    3 -> "上行 (3)"
    else -> func.toString()
}

private fun msgTypeLabel(r: RecordEntity): String = when {
    r.isDetailed -> "详细报文"
    r.rawIsMerged -> "合并报文"
    r.rawIsStandalone -> "独立长报文"
    r.rawIsShort -> "短报文"
    else -> "未知"
}

// ------------------------------------------------------------------ ③ BCD
@Composable
private fun BcdTab(r: RecordEntity) {
    val p = pal()
    val text = if (r.rawBcd.isNotEmpty()) {
        val lines = ArrayList<String>()
        var i = 0
        var idx = 0
        while (i < r.rawBcd.length) {
            lines.add("%4d: %s".format(Locale.US, idx * 20,
                r.rawBcd.substring(i, minOf(i + 20, r.rawBcd.length))))
            i += 20; idx++
        }
        "长度：${r.rawBcd.length} 字符（BCD 十进制数，每 2 位 1 字节）\n\n" +
            lines.joinToString("\n")
    } else "（无 BCD 数据）"
    MonoBlock(text, p.ok)
}

// ------------------------------------------------------------------ ④ 解码过程
@Composable
private fun ProcessTab(r: RecordEntity) {
    val p = pal()
    MonoBlock(decodeProcessText(r), p.textSecondary)
}

/** 与桌面 RecordDetailDialog._buildDecodeProcess 同文案（7 段推演） */
private fun decodeProcessText(r: RecordEntity): String {
    val lines = ArrayList<String>()
    lines.add("=== 1. 接收与信号检测 ===")
    lines.add("  信号强度 RSSI = %.1f dB".format(Locale.US, r.rssi))
    lines.add("  AFC 频偏估计 = %+.0f Hz".format(Locale.US, r.afcErrHz))
    lines.add(if (r.rssi > -55) "  → RSSI 超过阈值，触发接收门控"
        else "  → RSSI 低于阈值，信号微弱但已捕获")
    lines.add("")
    lines.add("=== 2. DPLL 比特恢复 ===")
    lines.add("  从 IQ 基带流中恢复比特序列")
    lines.add("  波特率: 1200 bps, 基带采样率: 48000 Hz")
    lines.add("  每比特采样数: ${48000 / 1200} samples/bit")
    lines.add("")
    lines.add("=== 3. 帧同步 ===")
    lines.add("  搜索 LBJ 帧同步字 (18 bit 地址 + 2 bit 功能码)")
    lines.add("  地址码: ${r.rawAddr} (0x%05X)".format(Locale.US, r.rawAddr))
    lines.add("  功能码: ${r.rawFunc} (${funcLabel(r.rawFunc)})")
    lines.add("")
    lines.add("=== 4. BCH(31,21) 译码 ===")
    if (r.msgTypeError) {
        lines.add("  ⚠ BCH 译码检测到不可纠错位")
        lines.add("  码字可能存在错误，解码结果仅供参考")
    } else {
        lines.add("  ✓ BCH 译码通过，最多纠正 2 bit 错误")
    }
    lines.add("  码字数: ${codewordList(r).size}")
    lines.add("")
    lines.add("=== 5. BCD 数据提取 ===")
    if (r.rawBcd.isNotEmpty()) {
        lines.add("  BCD 字符串长度: ${r.rawBcd.length} 字符")
        lines.add("  BCD 内容: " + r.rawBcd.take(60) +
            if (r.rawBcd.length > 60) "..." else "")
    } else {
        lines.add("  （无 BCD 数据）")
    }
    lines.add("")
    lines.add("=== 6. 报文类型判断 ===")
    lines.add("  → " + when {
        r.rawIsShort -> "短报文 (仅含车次、方向)"
        r.rawIsMerged -> "合并报文 (短报文 + 后续详细数据)"
        r.rawIsStandalone -> "独立长报文 (单次发送完整数据)"
        r.isDetailed -> "详细报文 (含机车、线路、公里标等)"
        else -> "报文类型未确定"
    })
    lines.add("")
    lines.add("=== 7. 字段解析 ===")
    lines.add("  车次号: ${r.train}")
    lines.add("  方向:   ${r.direction}")
    if (r.speed != "---" && r.speed.isNotEmpty())
        lines.add("  速度:   ${r.speed} km/h")
    if (r.position != "---.-" && r.position.isNotEmpty())
        lines.add("  公里标: ${r.position} km")
    if (r.loco != "----" && r.loco.isNotEmpty())
        lines.add("  机车:   ${r.loco}")
    if (r.route != "----" && r.route.isNotEmpty())
        lines.add("  线路:   ${r.route}")
    val lat = r.latitude
    val lon = r.longitude
    if (lat != null && lon != null) {
        lines.add("  经度:   %.6f (WGS-84)".format(Locale.US, lon))
        lines.add("  纬度:   %.6f (WGS-84)".format(Locale.US, lat))
        lines.add("  说明:   长报文字符 30..38 经度 / 39..46 纬度，" +
            "格式为“度 + 分/60”")
    }
    lines.add("")
    lines.add("=== 完成 ===")
    return lines.joinToString("\n")
}

// ------------------------------------------------------------------ ⑤ 纠错码字
@Composable
private fun CodewordTab(r: RecordEntity) {
    val p = pal()
    val cws = codewordList(r)
    val text = if (cws.isNotEmpty()) {
        "共 ${cws.size} 个码字（BCH(31,21) 纠错后）\n\n" +
            cws.mapIndexed { i, cw ->
                "  [%2d] %s  (0x%08X)".format(
                    Locale.US, i,
                    Integer.toBinaryString(cw).padStart(31, '0'), cw)
            }.joinToString("\n")
    } else "（本条记录没有保存码字）"
    MonoBlock(text, p.warn)
}

private fun codewordList(r: RecordEntity): List<Int> =
    if (r.rawCodewords.isEmpty()) emptyList()
    else r.rawCodewords.split(',').mapNotNull { it.trim().toIntOrNull() }

// ------------------------------------------------------------------ 公共小件
@Composable
private fun PairGrid(items: List<Pair<String, String>>) {
    val p = pal()
    Column(
        Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        items.forEach { (k, v) ->
            Row {
                Text(
                    k, color = p.accent, fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.End,
                    modifier = Modifier.width(78.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(v, color = p.text, fontSize = 11.sp,
                    modifier = Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MonoBlock(text: String, color: Color) {
    val p = pal()
    Text(
        text,
        color = color, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
        modifier = Modifier
            .fillMaxWidth()
            .padding(10.dp)
            .clip(RoundedCornerShape(6.dp))
            .background(p.bg)
            .border(1.dp, p.border, RoundedCornerShape(6.dp))
            .padding(8.dp),
    )
}

@Composable
private fun ActionBtn(
    text: String,
    enabled: Boolean = true,
    primary: Boolean = false,
    compact: Boolean = false,
    onClick: () -> Unit,
) {
    val p = pal()
    Text(
        text,
        color = when {
            !enabled -> p.textTertiary
            primary -> p.onAccent
            else -> p.accent
        },
        fontSize = if (compact) 12.sp else 13.sp,
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (primary) p.accent else p.surfaceAlt)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(
                horizontal = if (compact) 10.dp else 14.dp,
                vertical = if (compact) 6.dp else 9.dp,
            ),
    )
}

/** 机车详情（对齐桌面 LocoDetailDialog：技术参数 2 列 + 号段 + 简介 + 资料来源） */
@Composable
private fun LocoDetailSheetContent(
    spec: LocoRoster.Spec,
    lookup: LocoRoster.Lookup?,
    onDismiss: () -> Unit,
) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Dim.pagePad)
            .padding(bottom = 28.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        Text(
            "机车详情 — ${spec.name.ifEmpty { lookup?.model ?: "未知机车" }}",
            color = p.accent, fontSize = 16.sp, fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(10.dp))
        val items = ArrayList<Pair<String, String>>()
        items.add("机型名称" to spec.name.ifEmpty { "—" })
        items.add("机车类型" to spec.type.ifEmpty { "—" })
        items.add("制造厂商" to DepotNames.fullMaker(
            spec.maker.ifEmpty { lookup?.maker.orEmpty() }).ifEmpty { "—" })
        items.add("轴式" to spec.axle.ifEmpty { "—" })
        items.add("功率" to spec.power.ifEmpty { "—" })
        items.add("最高速度" to spec.speed.ifEmpty { "—" })
        if (lookup != null) {
            if (lookup.exact) {
                items.add("配属单位" to DepotNames.fullDepot(lookup.depot)
                    .ifEmpty { "（原表未标注）" })
            } else if (lookup.ok) {
                items.add("配属单位" to
                    "未知（${lookup.reason.ifEmpty { "号段未收录" }}）")
            }
            items.add("号段" to lookup.range.ifEmpty { "—" })
            if (lookup.remark.isNotEmpty()) items.add("备注" to lookup.remark)
        }
        PairGrid(items)
        if (spec.brief.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text("简介:", color = p.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(spec.brief, color = p.text, fontSize = 11.sp)
        }
        Spacer(Modifier.height(10.dp))
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(6.dp))
                .background(p.bg)
                .border(1.dp, p.border, RoundedCornerShape(6.dp))
                .padding(horizontal = 8.dp, vertical = 6.dp),
        ) {
            Text("资料来源: ", color = p.textTertiary, fontSize = 10.sp)
            Text("loco_specs.json（公开资料核对，见 docs/NOTICE.md）",
                color = p.accentAlt, fontSize = 10.sp, modifier = Modifier.weight(1f))
        }
        Spacer(Modifier.height(12.dp))
        Row {
            Spacer(Modifier.weight(1f))
            ActionBtn("关闭", primary = true, onClick = onDismiss)
        }
    }
}

private fun fmtKm(v: Double): String = "%.1f".format(Locale.US, v)