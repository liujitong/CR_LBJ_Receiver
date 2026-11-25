package xyz.mlxkj.crlbj.ui.pages

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.RadioButtonUnchecked
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
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
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.EmptyState
import xyz.mlxkj.crlbj.ui.components.InfoRow
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/** 历史分组方式 */
private enum class GroupMode(val label: String) { Train("按车次"), Loco("按机车") }

/**
 * 历史页：Room 里的解码记录（uid 去重后的最终记录）。
 *
 * v3.0：分组（按车次号 / 按机车号）+ 多选删除 + 卡片列表 + 点开详情底部弹层 + CSV 导出。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryPage(vm: ReceiverViewModel) {
    val records by vm.records.collectAsStateWithLifecycle()
    val count by vm.recordCount.collectAsStateWithLifecycle()
    val csvMsg by vm.csvMsg.collectAsStateWithLifecycle()
    val p = pal()

    var mode by remember { mutableStateOf(GroupMode.Train) }
    var selecting by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Set<String>>(emptySet()) }
    var detail by remember { mutableStateOf<RecordEntity?>(null) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri -> uri?.let { vm.exportCsv(it) } }

    val groups: List<Pair<String, List<RecordEntity>>> = remember(records, mode) {
        when (mode) {
            GroupMode.Train -> records.groupBy { it.train.ifEmpty { it.baseTrain }.ifEmpty { "未知车次" } }
            GroupMode.Loco -> records.groupBy { it.loco.ifEmpty { "未知机车" } }
        }.toList()
    }

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        PageHeader(
            title = "历史",
            subtitle = "共 $count 条 · ${groups.size} 组",
            trailing = {
                Chip(
                    if (selecting) "已选 ${selected.size}" else "长按可多选",
                    if (selecting) Tone.Warn else Tone.Neutral,
                )
            },
        )

        // ---- 工具行 ----
        Row(verticalAlignment = Alignment.CenterVertically) {
            GroupMode.entries.forEach { m ->
                TogglePill(m.label, mode == m) {
                    mode = m
                    selected = emptySet()
                }
                Spacer(Modifier.width(6.dp))
            }
            Spacer(Modifier.weight(1f))
            SmallAction(if (selecting) "取消" else "选择") {
                selecting = !selecting
                selected = emptySet()
            }
            Spacer(Modifier.width(6.dp))
            SmallAction("导出") { exportLauncher.launch("lbj_history.csv") }
        }
        Spacer(Modifier.height(Dim.gap))

        csvMsg?.let {
            Text(it, color = p.ok, fontSize = 12.sp)
            Spacer(Modifier.height(4.dp))
        }

        if (records.isEmpty()) {
            Box(Modifier.fillMaxSize()) {
                EmptyState(
                    title = "暂无历史记录",
                    hint = "开始接收后，解码成功且去重后的记录会自动入库（按 uid 更新，不是每次原始报文都入库）",
                )
            }
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                groups.forEach { (key, list) ->
                    item(key = "hd-$key") {
                        Row(
                            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                key,
                                color = p.textSecondary,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                                fontFamily = if (mode == GroupMode.Train) FontFamily.Default
                                else FontFamily.Monospace,
                            )
                            Spacer(Modifier.width(6.dp))
                            Text("${list.size} 条", color = p.textTertiary, fontSize = 11.sp)
                        }
                    }
                    items(list, key = { it.uid }) { r ->
                        RecordRow(
                            r = r,
                            selecting = selecting,
                            checked = selected.contains(r.uid),
                            onClick = {
                                if (selecting) {
                                    selected = if (selected.contains(r.uid)) selected - r.uid
                                    else selected + r.uid
                                } else {
                                    detail = r
                                }
                            },
                            onLongClick = {
                                if (!selecting) {
                                    selecting = true
                                    selected = setOf(r.uid)
                                }
                            },
                        )
                    }
                }
                item { Spacer(Modifier.height(Dim.dockSpace)) }
            }
        }

        // ---- 多选工具条（悬浮在 Dock 上方）----
        if (selecting) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = Dim.dockSpace)
                    .clip(RoundedCornerShape(50))
                    .background(p.surfaceAlt)
                    .border(1.dp, p.border, RoundedCornerShape(50))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("已选 ${selected.size} 条", color = p.text, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                SmallAction("全选", enabled = selected.size < records.size) {
                    selected = records.map { it.uid }.toSet()
                }
                Spacer(Modifier.width(8.dp))
                SmallAction("删除", danger = true, enabled = selected.isNotEmpty()) {
                    vm.deleteRecords(selected)
                    selected = emptySet()
                    selecting = false
                }
            }
        }
    }

    detail?.let { r ->
        ModalBottomSheet(
            onDismissRequest = { detail = null },
            sheetState = sheetState,
            containerColor = p.surface,
        ) {
            RecordDetail(r)
        }
    }
}

/** 一条历史记录（卡片行） */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun RecordRow(
    r: RecordEntity,
    selecting: Boolean,
    checked: Boolean,
    onClick: () -> Unit,
    onLongClick: () -> Unit,
) {
    val p = pal()
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp)
            .clip(RoundedCornerShape(Dim.cardCorner))
            .background(p.surface)
            .combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (selecting) {
            Icon(
                if (checked) Icons.Filled.CheckCircle else Icons.Outlined.RadioButtonUnchecked,
                contentDescription = if (checked) "已选" else "未选",
                tint = if (checked) p.accent else p.textTertiary,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.width(8.dp))
        }
        Text(
            r.train.ifEmpty { "----" },
            color = p.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.width(66.dp),
        )
        DirectionBadge(r.direction, small = true)
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "%s km/h · K%s · %s".format(
                    Locale.US, r.speed.ifEmpty { "---" }, r.position.ifEmpty { "---.-" },
                    r.route.ifEmpty { "线路未知" }),
                color = p.textSecondary, fontSize = 11.sp, fontFamily = FontFamily.Monospace,
                maxLines = 1,
            )
            Text(
                listOfNotNull(
                    r.loco.takeIf { it.isNotBlank() }?.let { "机车 $it" },
                    r.category.takeIf { it.isNotBlank() },
                ).joinToString(" · "),
                color = p.textTertiary, fontSize = 11.sp, maxLines = 1,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(r.timeStr.takeLast(8), color = p.textTertiary, fontSize = 10.sp,
                fontFamily = FontFamily.Monospace)
            if (r.latitude != null) {
                Text("有坐标", color = p.ok, fontSize = 9.sp)
            }
        }
    }
}

/** 记录详情（底部弹层） */
@Composable
private fun RecordDetail(r: RecordEntity) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Dim.pagePad)
            .padding(bottom = 28.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(r.train.ifEmpty { "----" }, color = p.text, fontSize = 26.sp,
                fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(10.dp))
            DirectionBadge(r.direction)
            Spacer(Modifier.weight(1f))
            Text(r.timeStr, color = p.textTertiary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(10.dp))
        SectionCard("解码结果") {
            InfoRow("类别", r.category)
            InfoRow("速度", "${r.speed} km/h", mono = true)
            InfoRow("公里标", r.position, mono = true)
            InfoRow("线路", r.route.ifEmpty { "未知" })
            InfoRow("机车", r.loco.ifEmpty { "----" }, mono = true)
            InfoRow("报文", if (r.isDetailed) "详细长报文" else "基础短报文")
            InfoRow("BCH 错", if (r.msgTypeError) "有" else "无")
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("到达估算") {
            InfoRow("预计到达", r.etaTime, mono = true)
            InfoRow("剩余里程", r.etaDistanceKm?.let { "%.1f km".format(Locale.US, it) } ?: "—",
                mono = true)
            InfoRow("状态", r.etaStatus)
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("链路") {
            InfoRow("RSSI", "%.1f dB".format(Locale.US, r.rssi), mono = true)
            InfoRow("AFC", "%.0f Hz".format(Locale.US, r.afcHz), mono = true)
            r.latitude?.let {
                InfoRow("坐标", "%.5f, %.5f".format(Locale.US, it, r.longitude ?: 0.0), mono = true)
            }
            InfoRow("地址", "0x%X".format(r.rawAddr), mono = true)
            InfoRow("原始 BCD", r.rawBcd.ifEmpty { "—" }, mono = true)
            InfoRow("uid", r.uid, mono = true)
        }
    }
}

/** 圆角小开关（分组方式 / 工具动作） */
@Composable
private fun TogglePill(text: String, active: Boolean, onClick: () -> Unit) {
    val p = pal()
    Box(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(if (active) p.accent.copy(alpha = 0.16f) else p.surfaceAlt)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp)
    ) {
        Text(
            text,
            color = if (active) p.accent else p.textSecondary,
            fontSize = 12.sp,
            fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

/** 文字动作（导出/选择/删除…） */
@Composable
private fun SmallAction(
    text: String,
    enabled: Boolean = true,
    danger: Boolean = false,
    onClick: () -> Unit,
) {
    val p = pal()
    Text(
        text,
        color = when {
            !enabled -> p.textTertiary
            danger -> p.err
            else -> p.textSecondary
        },
        fontSize = 12.sp,
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 6.dp),
    )
}
