package xyz.mlxkj.crlbj.ui.pages

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.ui.components.EmptyState
import xyz.mlxkj.crlbj.ui.components.LbjTextField
import xyz.mlxkj.crlbj.ui.components.RecordDetailSheet
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/** 历史分组方式 */
private enum class GroupMode(val label: String) { Train("按车次"), Loco("按机车") }

/**
 * 历史记录管理（v3.2.8 起从底部页签移入「设置 → 历史记录」）——增删改查全套：
 *
 *  * **增**：解码成功自动入库（按 uid 去重 REPLACE，无需手工）；
 *  * **查**：实时关键词过滤（车次/机车/线路/备注）+ 按车次/按机车分组；点行看详情
 *    （RecordDetailSheet 与桌面记录详情一致）；
 *  * **改**：长按行编辑备注（note 列，Room v2 迁移新增；CSV 不含该列，双端一致）；
 *  * **删**：多选删除（含全选）+ 删除全部（带确认）；
 *  * 另：导出 CSV（列与桌面 HistoryDb.exportToCsv 完全一致）、条数统计。
 *
 * 嵌在设置页里渲染（外层给全高 Column），原底部「历史」页签已改为「信息」页。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistorySection(vm: ReceiverViewModel) {
    val records by vm.records.collectAsStateWithLifecycle()
    val count by vm.recordCount.collectAsStateWithLifecycle()
    val csvMsg by vm.csvMsg.collectAsStateWithLifecycle()
    val trainInfos by vm.trainInfos.collectAsStateWithLifecycle()
    val trainErrors by vm.trainInfoErrors.collectAsStateWithLifecycle()
    val locoInfos by vm.locoInfos.collectAsStateWithLifecycle()
    val p = pal()

    var mode by remember { mutableStateOf(GroupMode.Train) }
    var query by remember { mutableStateOf("") }
    var selecting by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Set<String>>(emptySet()) }
    var detail by remember { mutableStateOf<RecordEntity?>(null) }
    var noteEdit by remember { mutableStateOf<RecordEntity?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri -> uri?.let { vm.exportCsv(it) } }

    val filtered = remember(records, query) {
        if (query.isBlank()) records
        else {
            val q = query.trim()
            records.filter {
                it.train.contains(q, true) || it.baseTrain.contains(q, true) ||
                    it.loco.contains(q, true) || it.route.contains(q, true) ||
                    it.note.contains(q, true)
            }
        }
    }
    val groups: List<Pair<String, List<RecordEntity>>> = remember(filtered, mode) {
        when (mode) {
            GroupMode.Train ->
                filtered.groupBy { it.train.ifEmpty { it.baseTrain }.ifEmpty { "未知车次" } }
            GroupMode.Loco -> filtered.groupBy { it.loco.ifEmpty { "未知机车" } }
        }.toList()
    }

    Column(Modifier.fillMaxSize()) {
        // ---- 查询框 ----
        LbjTextField(
            value = query,
            onValueChange = { query = it },
            placeholder = "搜索 车次 / 机车 / 线路 / 备注",
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))

        // ---- 工具行 ----
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "共 $count 条" + if (query.isNotBlank()) " · 命中 ${filtered.size} 条" else "",
                color = p.textTertiary, fontSize = 11.sp,
            )
            Spacer(Modifier.weight(1f))
            GroupMode.entries.forEach { m ->
                TogglePill(m.label, mode == m) {
                    mode = m; selected = emptySet()
                }
                Spacer(Modifier.width(6.dp))
            }
            SmallAction(if (selecting) "取消" else "选择") {
                selecting = !selecting
                selected = emptySet()
            }
            Spacer(Modifier.width(2.dp))
            SmallAction("导出") { exportLauncher.launch("lbj_history.csv") }
            Spacer(Modifier.width(2.dp))
            SmallAction("删全部", danger = true, enabled = records.isNotEmpty()) {
                confirmClear = true
            }
        }
        csvMsg?.let {
            Text(it, color = p.ok, fontSize = 11.sp,
                modifier = Modifier.padding(top = 4.dp))
        }
        Spacer(Modifier.height(6.dp))

        if (filtered.isEmpty()) {
            Box(Modifier.weight(1f)) {
                EmptyState(
                    title = if (records.isEmpty()) "暂无历史记录" else "无匹配记录",
                    hint = if (records.isEmpty())
                        "开始接收后，解码成功且去重后的记录会自动入库；点行看详情，长按改备注"
                    else "换个关键词试试（车次/机车/线路/备注）",
                )
            }
        } else {
            LazyColumn(Modifier.weight(1f)) {
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
                                // 长按 = 编辑备注（增删改查的「改」）
                                noteEdit = r
                            },
                        )
                    }
                }
                item { Spacer(Modifier.height(Dim.dockSpace) ) }
            }
        }

        // ---- 多选工具条 ----
        if (selecting) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 6.dp)
                    .clip(RoundedCornerShape(50))
                    .background(p.surfaceAlt)
                    .border(1.dp, p.border, RoundedCornerShape(50))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("已选 ${selected.size} 条", color = p.text, fontSize = 13.sp)
                Spacer(Modifier.weight(1f))
                SmallAction("全选", enabled = selected.size < filtered.size) {
                    selected = filtered.map { it.uid }.toSet()
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

    // ---- 详情（与桌面 RecordDetailDialog 五页签一致）----
    detail?.let { r ->
        ModalBottomSheet(
            onDismissRequest = { detail = null },
            sheetState = sheetState,
            containerColor = p.surface,
        ) {
            val roster = vm.currentRoster()
            val short = roster.shortCode(r.locoCode, r.loco).ifEmpty { r.loco.trim() }
            RecordDetailSheet(
                r = r,
                trainInfo = trainInfos[xyz.mlxkj.crlbj.data.TrainInfoClient
                    .normalizeTrain(r.train)],
                trainError = trainErrors[xyz.mlxkj.crlbj.data.TrainInfoClient
                    .normalizeTrain(r.train)],
                onEnsure = { vm.ensureTrainInfo(r.train) },
                loco = locoInfos[ReceiverViewModel.locoKey(r.loco, r.locoCode)]
                    ?: runCatching { roster.lookupLoco(r.loco, r.locoCode) }
                        .getOrNull()?.takeIf { it.ok },
                spec = roster.specsFor(short),
                onClose = { detail = null },
            )
        }
    }

    // ---- 编辑备注 ----
    noteEdit?.let { r ->
        var text by remember(r.uid) { mutableStateOf(r.note) }
        AlertDialog(
            onDismissRequest = { noteEdit = null },
            containerColor = p.surface,
            title = { Text("备注 · ${r.train.ifEmpty { "----" }} ${r.timeStr.takeLast(8)}",
                color = p.text, fontSize = 15.sp) },
            text = {
                LbjTextField(
                    value = text,
                    onValueChange = { text = it },
                    placeholder = "给这条记录写点备注（本地保存，不导出 CSV）",
                    keyboardType = KeyboardType.Text,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    vm.updateNote(r.uid, text)
                    noteEdit = null
                }) { Text("保存", color = p.accent) }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = {
                        vm.updateNote(r.uid, "")
                        noteEdit = null
                    }) { Text("清空", color = p.textTertiary) }
                    TextButton(onClick = { noteEdit = null }) {
                        Text("取消", color = p.textSecondary)
                    }
                }
            },
        )
    }

    // ---- 删除全部确认 ----
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            containerColor = p.surface,
            title = { Text("删除全部历史记录？", color = p.text, fontSize = 15.sp) },
            text = {
                Text("将清空全部 $count 条记录（含备注），不可恢复。建议先「导出」备份。",
                    color = p.textSecondary, fontSize = 13.sp)
            },
            confirmButton = {
                TextButton(onClick = {
                    vm.clearHistory()
                    confirmClear = false
                    selecting = false
                    selected = emptySet()
                }) { Text("全部删除", color = p.err) }
            },
            dismissButton = {
                TextButton(onClick = { confirmClear = false }) {
                    Text("取消", color = p.textSecondary)
                }
            },
        )
    }
}

/** 一条历史记录（卡片行；备注非空时显示标注） */
@OptIn(ExperimentalFoundationApi::class)
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
                    r.note.takeIf { it.isNotBlank() }?.let { "备注：$it" },
                ).joinToString(" · "),
                color = if (r.note.isNotBlank()) p.warn else p.textTertiary,
                fontSize = 11.sp, maxLines = 1,
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

/** 圆角小开关（分组方式） */
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

/** 文字动作（导出/选择/删全部…） */
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