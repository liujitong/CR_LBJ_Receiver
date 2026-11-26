package xyz.mlxkj.crlbj.ui.pages

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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.core.DepotNames
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.EmptyState
import xyz.mlxkj.crlbj.ui.components.InfoRow
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.RecordDetailSheet
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/**
 * 信息页（v3.2.8 取代底部「历史」页签）——承担 PC 端「车次信息 + 机车信息」两块面板的职能：
 *
 *  * 顶部横滑选择条：最近解码记录（默认选中最新一条），可翻看近几次解码；
 *  * **列车信息**卡：车次/方向/速度/公里标/线路/类别/到达时间/距离/经纬度/本站
 *    —— 字段与桌面 `TrainInfoPanel.FIELDS` 一一对应；
 *  * **车次信息**卡：RailGo/12306 结果（等级、担当全称、客运段、配属段、车型、
 *    始发终到+时刻、全程里程、开行日、交路、主要停站），担当/配属走 `DepotNames`
 *    全称化（与桌面同一张表）；
 *  * **机车信息**卡：机车型号+号段、中文名称、配属单位（全称）、制造厂（全称）、
 *    轴式/功率/最高速度、简介——对齐桌面 `LocoInfoPanel` 的 名称/配属/详情/简介 四段；
 *  * 底部动作：查看记录详情（五页签弹层，与桌面双击详情一致）、时刻表、历史管理跳转提示。
 *
 * 历史记录本身的增删改查已移入「设置 → 历史记录」。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InfoPage(vm: ReceiverViewModel) {
    val records by vm.records.collectAsStateWithLifecycle()
    val trainInfos by vm.trainInfos.collectAsStateWithLifecycle()
    val trainErrors by vm.trainInfoErrors.collectAsStateWithLifecycle()
    val locoInfos by vm.locoInfos.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val p = pal()

    // 选中记录：默认最新；新记录到来不打断用户手选的旧记录
    var pickedUid by remember { mutableStateOf<String?>(null) }
    val recent = remember(records) { records.take(12) }
    val current: RecordEntity? = remember(pickedUid, recent) {
        recent.firstOrNull { it.uid == pickedUid } ?: recent.firstOrNull()
    }
    // 选中即触发 RailGo 补查（已缓存则 no-op；与桌面详情同口径）
    LaunchedEffect(current?.uid) { current?.let { vm.ensureTrainInfo(it.train) } }

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var showDetail by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        PageHeader(
            title = "信息",
            subtitle = if (records.isEmpty()) "等待解码记录…"
            else "近 ${recent.size} 次解码的车次/机车具体信息",
        )

        if (recent.isEmpty()) {
            Box(Modifier.fillMaxSize()) {
                EmptyState(
                    title = "暂无解码记录",
                    hint = "到「解码」页一键开始；解出报文后这里显示车次信息、担当/配属全称、" +
                        "机车号段与技术参数。历史记录管理在「设置 → 历史记录」。",
                )
            }
            return@Column
        }

        // ---- 近几次解码选择条 ----
        LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            items(recent, key = { it.uid }) { r ->
                val active = r.uid == current?.uid
                Column(
                    Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(if (active) p.accent.copy(alpha = 0.14f) else p.surface)
                        .border(1.dp, if (active) p.accent else p.border,
                            RoundedCornerShape(10.dp))
                        .clickable { pickedUid = r.uid }
                        .padding(horizontal = 10.dp, vertical = 7.dp),
                ) {
                    Text(
                        r.train.ifEmpty { "----" },
                        color = if (active) p.accent else p.text,
                        fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        r.timeStr.takeLast(8),
                        color = p.textTertiary, fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
        }
        Spacer(Modifier.height(Dim.gap))

        val sel = current ?: return@Column
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
        ) {
            // ---- 列车信息（对齐桌面 TrainInfoPanel.FIELDS 11 项）----
            SectionCard(
                title = "列车信息",
                trailing = {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        if (sel.latitude != null) Chip("含坐标", Tone.Ok)
                        Chip(if (sel.isDetailed) "详细报文" else "短报文", Tone.Neutral)
                    }
                },
            ) {
                InfoRow("车次", sel.train.ifEmpty { "----" })
                InfoRow("方向", sel.direction.ifEmpty { "未知" })
                InfoRow("速度",
                    if (sel.speed == "---" || sel.speed.isEmpty()) "---"
                    else "${sel.speed} km/h", mono = true)
                InfoRow("公里标",
                    if (sel.position == "---.-" || sel.position.isEmpty()) "---.-"
                    else "${sel.position} KM", mono = true)
                InfoRow("机车", sel.loco.ifEmpty { "----" }, mono = true)
                InfoRow("线路", sel.route.ifEmpty { "----" })
                InfoRow("类别", sel.category.ifEmpty { "未知" })
                InfoRow("到达时间", sel.etaTime, mono = true)
                InfoRow("距离",
                    sel.etaDistanceKm?.let { "%.1f km".format(Locale.US, it) } ?: "---",
                    mono = true)
                InfoRow("经纬度",
                    if (sel.latitude != null && sel.longitude != null)
                        "%.5f, %.5f".format(Locale.US, sel.latitude, sel.longitude)
                    else "—",
                    mono = true)
                val userKm = settings.userKm.trim()
                InfoRow("本站", if (userKm.isEmpty()) "未设置" else "K$userKm", mono = true)
            }

            // ---- 车次信息（RailGo / 12306，全称化对齐桌面）----
            val ti = trainInfos[TrainInfoClient.normalizeTrain(sel.train)]
            Spacer(Modifier.height(Dim.gap))
            SectionCard(
                title = "车次信息",
                trailing = {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        if (ti != null && ti.ok)
                            Chip(if (ti.source == "railgo") "RailGo" else "12306", Tone.Neutral)
                        else Chip("查询中…", Tone.Neutral)
                    }
                },
            ) {
                if (ti == null || !ti.ok) {
                    Text(
                        when {
                            !sel.isDetailed -> "非详细报文，不查询车次信息"
                            trainErrors.containsKey(
                                TrainInfoClient.normalizeTrain(sel.train)) ->
                                "未查询到 ${sel.train} 的车次信息（" +
                                    trainErrors[TrainInfoClient.normalizeTrain(sel.train)] + "）"
                            else -> "车次信息自动查询中（RailGo → 12306 兜底）…"
                        },
                        color = p.textTertiary, fontSize = 11.sp,
                    )
                } else {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(ti.train.ifEmpty { sel.train }, color = p.text,
                            fontSize = 22.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.width(8.dp))
                        if (ti.category.isNotEmpty()) Chip(ti.category, Tone.Neutral)
                    }
                    Spacer(Modifier.height(6.dp))
                    if (ti.start.isNotEmpty() || ti.end.isNotEmpty()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(ti.start.ifEmpty { "—" }, color = p.text, fontSize = 14.sp,
                                fontWeight = FontWeight.Medium)
                            if (ti.startTime.isNotEmpty()) {
                                Spacer(Modifier.width(4.dp))
                                Text(ti.startTime, color = p.textSecondary, fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace)
                            }
                            Spacer(Modifier.width(6.dp))
                            Text("→", color = p.textTertiary, fontSize = 13.sp)
                            Spacer(Modifier.width(6.dp))
                            Text(ti.end.ifEmpty { "—" }, color = p.text, fontSize = 14.sp,
                                fontWeight = FontWeight.Medium)
                            if (ti.endTime.isNotEmpty()) {
                                Spacer(Modifier.width(4.dp))
                                Text(ti.endTime, color = p.textSecondary, fontSize = 11.sp,
                                    fontFamily = FontFamily.Monospace)
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                    }
                    if (ti.distance != null) {
                        Text("全程 %.0f km · %d 站".format(Locale.US, ti.distance, ti.stops.size),
                            color = p.textTertiary, fontSize = 11.sp)
                        Spacer(Modifier.height(4.dp))
                    }
                    InfoRow("担当", DepotNames.formatDuty(ti.bureau, ti.runner).ifEmpty { "—" })
                    InfoRow("客运段", DepotNames.fullBureau(ti.runner).ifEmpty { "—" })
                    InfoRow("配属段", DepotNames.fullDepot(ti.carOwner).ifEmpty { "—" })
                    InfoRow("车型", ti.car.ifEmpty { "—" })
                    if (ti.rundays.isNotEmpty()) {
                        InfoRow("开行日", "${ti.rundaysCount} 天（" +
                            ti.rundays.take(3).joinToString(",") +
                            if (ti.rundaysCount > 3) "…）" else "）")
                    }
                    if (ti.diagram.isNotEmpty()) {
                        Spacer(Modifier.height(4.dp))
                        Text("交路${if (ti.diagramType.isNotEmpty()) "（${ti.diagramType}）" else ""}",
                            color = p.accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        ti.diagram.forEach { seg ->
                            Text(
                                "${seg.number}  ${seg.fromStation} ${seg.fromTime} → " +
                                    "${seg.toStation} ${seg.toTime}",
                                color = p.textSecondary, fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace,
                            )
                        }
                    }
                }
            }

            // ---- 机车信息（对齐桌面 LocoInfoPanel：名称/配属/详情/简介）----
            val roster = vm.currentRoster()
            val lk = locoInfos[ReceiverViewModel.locoKey(sel.loco, sel.locoCode)]
                ?: runCatching { roster.lookupLoco(sel.loco, sel.locoCode) }
                    .getOrNull()?.takeIf { it.ok }
            val short = roster.shortCode(sel.locoCode, sel.loco)
            val spec = roster.specsFor(short.ifEmpty { sel.loco.trim().uppercase(Locale.US) })
            Spacer(Modifier.height(Dim.gap))
            SectionCard(
                title = "机车信息",
                trailing = {
                    Chip(
                        when {
                            lk == null -> "未查号段"
                            lk.exact && lk.depot.isNotBlank() -> "号段命中"
                            lk.ok -> "仅识别型号"
                            else -> "未命中"
                        },
                        when {
                            lk == null -> Tone.Neutral
                            lk.exact && lk.depot.isNotBlank() -> Tone.Ok
                            lk.ok -> Tone.Warn
                            else -> Tone.Err
                        },
                    )
                },
            ) {
                // 标题：型号 + 机车号（去重，避免 native 的「未知型号-xxx」重复两遍）
                val headParts = listOfNotNull(
                    lk?.model ?: short,
                    sel.loco.takeIf { it.isNotBlank() && it != "----" } ?: lk?.numberText,
                ).map { it.trim() }.filter { it.isNotEmpty() }.distinct()
                Text(
                    headParts.joinToString(" ").ifEmpty { "----" },
                    color = p.text, fontSize = 20.sp,
                    fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace,
                )
                val cnName = lk?.name?.ifEmpty { null } ?: roster.modelDisplayName(short)
                if (!cnName.isNullOrEmpty() && cnName != short) {
                    Spacer(Modifier.height(2.dp))
                    Text(cnName, color = p.textSecondary, fontSize = 12.sp)
                }
                Spacer(Modifier.height(6.dp))
                InfoRow("机车代号", sel.locoCode.ifEmpty { "---" }, mono = true)
                InfoRow("配属单位",
                    when {
                        lk == null -> "—"
                        lk.exact -> DepotNames.fullDepot(lk.depot)
                            .ifEmpty { "（原表未标注配属）" }
                        else -> "未知（${lk.reason.ifEmpty { "号段未收录" }}）"
                    })
                InfoRow("号段", lk?.range?.ifEmpty { "—" } ?: "—", mono = true)
                InfoRow("制造厂", DepotNames.fullMaker(
                    (spec?.maker?.ifEmpty { null } ?: lk?.maker).orEmpty()
                ).ifEmpty { "—" })
                if (spec != null && (spec.axle.isNotEmpty() || spec.power.isNotEmpty() ||
                        spec.speed.isNotEmpty())) {
                    InfoRow("牵引参数", listOfNotNull(
                        spec.power.ifEmpty { null },
                        spec.axle.ifEmpty { null },
                        spec.speed.ifEmpty { null },
                    ).joinToString(" · "))
                }
                if (lk != null && lk.remark.isNotEmpty()) {
                    InfoRow("备注", lk.remark)
                }
                if (spec != null && spec.brief.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        spec.brief,
                        color = p.textSecondary, fontSize = 11.sp,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(6.dp))
                            .background(p.bg)
                            .padding(8.dp),
                    )
                }
            }

            Spacer(Modifier.height(Dim.gap))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(
                    Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(p.accent)
                        .clickable { showDetail = true }
                        .padding(horizontal = 16.dp, vertical = 11.dp),
                ) {
                    Text("查看记录详情", color = p.onAccent, fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold)
                }
                Box(
                    Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(p.surfaceAlt)
                        .border(1.dp, p.border, RoundedCornerShape(10.dp))
                        .clickable { vm.requestGotoHistory() }
                        .padding(horizontal = 16.dp, vertical = 11.dp),
                ) {
                    Text("历史记录管理", color = p.textSecondary, fontSize = 13.sp)
                }
            }
            Spacer(Modifier.height(Dim.dockSpace))
        }
    }

    if (showDetail && current != null) {
        ModalBottomSheet(
            onDismissRequest = { showDetail = false },
            sheetState = sheetState,
            containerColor = p.surface,
        ) {
            val roster = vm.currentRoster()
            val short = roster.shortCode(current.locoCode, current.loco)
            RecordDetailSheet(
                r = current,
                trainInfo = trainInfos[TrainInfoClient.normalizeTrain(current.train)],
                trainError = trainErrors[TrainInfoClient.normalizeTrain(current.train)],
                onEnsure = { vm.ensureTrainInfo(current.train) },
                loco = locoInfos[ReceiverViewModel.locoKey(current.loco, current.locoCode)]
                    ?: runCatching { roster.lookupLoco(current.loco, current.locoCode) }
                        .getOrNull()?.takeIf { it.ok },
                spec = roster.specsFor(short.ifEmpty { current.loco.trim() }),
                onClose = { showDetail = false },
            )
        }
    }
}