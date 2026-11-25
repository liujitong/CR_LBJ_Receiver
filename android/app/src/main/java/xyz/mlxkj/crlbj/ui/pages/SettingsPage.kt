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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
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
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.ui.components.LbjTextField
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/** 底图候选（id 与 railmap.html 的 BASE_SOURCES 对齐） */
private val MAP_BASES = listOf(
    "osm" to "OSM 标准",
    "carto_light" to "Carto 浅色",
    "carto_dark" to "Carto 深色",
    "carto_voyager" to "Carto 路由",
    "esri_img" to "Esri 卫星",
    "esri_street" to "Esri 街道",
    "opentopo" to "OpenTopoMap 地形",
    "tdt_vec" to "天地图 矢量",
    "tdt_img" to "天地图 影像",
    "amap" to "高德 街道（GCJ-02）",
    "amap_img" to "高德 卫星（GCJ-02）",
)

/** 铁路图层候选（ORM = OpenRailwayMap） */
private val MAP_RAILS = listOf(
    "off" to "不显示",
    "orm_standard" to "ORM 标准（线路+信号）",
    "orm_maxspeed" to "ORM 限速",
    "orm_signals" to "ORM 信号",
    "orm_electrified" to "ORM 电气化",
    "orm_gauge" to "ORM 轨距",
)

/**
 * 设置页（v3.0）：数据源 / 射频 / 门控与 AFC / 解码业务 / 地图 / 查询与数据。
 *
 * 交互：整页是**草稿**，底部「保存」一次性提交（连接类参数会重建 DSP 链路）；
 * 地图项保存后立即下发到地图页，不需要重启。
 */
@Composable
fun SettingsPage(vm: ReceiverViewModel) {
    val current by vm.settings.collectAsStateWithLifecycle()
    val places by vm.places.collectAsStateWithLifecycle()
    val dataInfo by vm.dataInfo.collectAsStateWithLifecycle()
    val update by vm.dataUpdate.collectAsStateWithLifecycle()
    val p = pal()

    // 本地草稿：设置变化（例如地图内改了图层）时重新快照
    var s by remember(current) { mutableStateOf(current) }
    var saved by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        PageHeader(
            title = "设置",
            subtitle = "v3.0.0 · 桌面版与安卓版同版本号",
            trailing = {
                Text(
                    "保存",
                    color = p.accent, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(p.accent.copy(alpha = 0.14f))
                        .clickable {
                            vm.updateSettings(s)
                            saved = true
                        }
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                )
            },
        )

        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            // ---------------------------------------------------------- 数据源
            SectionCard("数据源") {
                ChipRow(
                    options = listOf("usb" to "本机 USB", "rtl_tcp" to "rtl_tcp", "owrx" to "OWRX"),
                    selected = s.sourceType,
                    onPick = { s = s.copy(sourceType = it) },
                )
                Spacer(Modifier.height(8.dp))
                if (s.isUsb) {
                    Text(
                        "USB 直连：手机 OTG 接 RTL-SDR 电视棒，设备查找与权限由系统弹窗确认。",
                        color = p.textTertiary, fontSize = 11.sp,
                    )
                    Spacer(Modifier.height(6.dp))
                } else {
                    Field("主机", s.host) { s = s.copy(host = it.trim()) }
                    Field("端口", s.port.toString(), KeyboardType.Number) {
                        s = s.copy(port = it.toIntOrNull() ?: s.port)
                    }
                }
                Field("采样率 Hz", s.sampleRate.toString(), KeyboardType.Number) {
                    s = s.copy(sampleRate = it.toIntOrNull() ?: s.sampleRate)
                }
            }
            Spacer(Modifier.height(Dim.gap))

            // ------------------------------------------------------------ 射频
            SectionCard("射频") {
                Field("频率 MHz", fmt(s.freqMhz), KeyboardType.Decimal) {
                    s = s.copy(freqMhz = it.toDoubleOrNull() ?: s.freqMhz)
                }
                Field("增益 dB", fmt(s.gainDb), KeyboardType.Decimal) {
                    s = s.copy(gainDb = it.toDoubleOrNull() ?: s.gainDb)
                }
                Field("PPM 校正", fmt(s.ppm), KeyboardType.Decimal) {
                    s = s.copy(ppm = it.toDoubleOrNull() ?: s.ppm)
                }
                Field("信道带宽 kHz", fmt(s.bwKhz), KeyboardType.Decimal) {
                    s = s.copy(bwKhz = it.toDoubleOrNull() ?: s.bwKhz)
                }
                Field("DC 偏移 Hz", fmt(s.dcOffsetHz), KeyboardType.Decimal) {
                    s = s.copy(dcOffsetHz = it.toDoubleOrNull() ?: s.dcOffsetHz)
                }
                Text(
                    "USB 直连建议 DC 偏移 50000 Hz（让目标频点落在 DDC 之后），OWRX 保持 0。",
                    color = p.textTertiary, fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(Dim.gap))

            // ------------------------------------------------------- 门控与 AFC
            SectionCard("RSSI 门控与 AFC") {
                Field("开启门限 dB", fmt(s.rssiThresholdDb), KeyboardType.Decimal) {
                    s = s.copy(rssiThresholdDb = it.toDoubleOrNull() ?: s.rssiThresholdDb)
                }
                Field("释放迟滞 dB", fmt(s.rssiHystDb), KeyboardType.Decimal) {
                    s = s.copy(rssiHystDb = it.toDoubleOrNull() ?: s.rssiHystDb)
                }
                Field("保持时长 ms", fmt(s.rssiHoldMs), KeyboardType.Decimal) {
                    s = s.copy(rssiHoldMs = it.toDoubleOrNull() ?: s.rssiHoldMs)
                }
                SwitchRow("AFC 自动频率补偿", s.afcEnable) { s = s.copy(afcEnable = it) }
                Field("AFC 最大修正 Hz", fmt(s.afcMaxHz), KeyboardType.Decimal) {
                    s = s.copy(afcMaxHz = it.toDoubleOrNull() ?: s.afcMaxHz)
                }
                Field("AFC 环路增益", fmt(s.afcGain), KeyboardType.Decimal) {
                    s = s.copy(afcGain = it.toDoubleOrNull() ?: s.afcGain)
                }
                SwitchRow("报文后保持 AFC", s.keepAfcAfterPacket) {
                    s = s.copy(keepAfcAfterPacket = it)
                }
            }
            Spacer(Modifier.height(Dim.gap))

            // --------------------------------------------------------- 解码业务
            SectionCard("解码业务") {
                ChipRow(
                    options = listOf("auto" to "车次规则 自动", "2026" to "2026 表", "legacy" to "旧表"),
                    selected = s.trainScheme,
                    onPick = { s = s.copy(trainScheme = it) },
                )
                Spacer(Modifier.height(8.dp))
                Field("去重窗口 秒", fmt(s.dedupeWindow), KeyboardType.Decimal) {
                    s = s.copy(dedupeWindow = it.toDoubleOrNull() ?: s.dedupeWindow)
                }
                Field("ETA 上限 分钟", fmt(s.etaMaxMin), KeyboardType.Decimal) {
                    s = s.copy(etaMaxMin = it.toDoubleOrNull() ?: s.etaMaxMin)
                }
                Field("本站公里标 km", s.userKm, KeyboardType.Decimal) {
                    s = s.copy(userKm = it.trim())
                }
                Field("线路公里标", s.routeKmText) { s = s.copy(routeKmText = it) }
                Text(
                    "线路公里标格式：线路=km，多条用逗号分隔，例如 京九线=1420,沪昆线=730",
                    color = p.textTertiary, fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(Dim.gap))

            // ------------------------------------------------------------- 地图
            SectionCard("地图") {
                SelectRow(
                    label = "底图",
                    value = MAP_BASES.firstOrNull { it.first == s.mapBase }?.second ?: s.mapBase,
                    options = MAP_BASES,
                ) { s = s.copy(mapBase = it) }
                SelectRow(
                    label = "铁路图层",
                    value = MAP_RAILS.firstOrNull { it.first == s.mapRail }?.second ?: s.mapRail,
                    options = MAP_RAILS,
                ) { s = s.copy(mapRail = it) }
                Text(
                    "铁路不透明度 %.0f%%".format(Locale.US, s.mapRailOpacity * 100),
                    color = p.textSecondary, fontSize = 12.sp,
                    modifier = Modifier.padding(top = 6.dp),
                )
                Slider(
                    value = s.mapRailOpacity.toFloat(),
                    onValueChange = { s = s.copy(mapRailOpacity = it.toDouble()) },
                    valueRange = 0.2f..1f,
                )
                SwitchRow("夜间底图", s.mapNight) { s = s.copy(mapNight = it) }
                SwitchRow("自动跟随最新列车", s.mapFollow) { s = s.copy(mapFollow = it) }
                Field("缩放级别", s.mapZoom.toString(), KeyboardType.Number) {
                    s = s.copy(mapZoom = it.toIntOrNull() ?: s.mapZoom)
                }
                Field("天地图 tk", s.mapTdtKey) { s = s.copy(mapTdtKey = it.trim()) }
                Text(
                    "天地图底图需要「浏览器端」tk（tianditu.gov.cn 免费申请）；留空时选中该底图只会提示不加载。",
                    color = p.textTertiary, fontSize = 11.sp,
                )
                Spacer(Modifier.height(8.dp))
                if (places.isNotEmpty()) {
                    SelectRow(
                        label = "默认中心",
                        value = s.mapCenterName.ifEmpty { "未设置" },
                        options = places.map { it.name to it.name },
                    ) { name ->
                        val pl = places.firstOrNull { it.name == name }
                        if (pl != null) {
                            s = s.copy(mapCenterName = pl.name, mapCenterLat = pl.lat,
                                mapCenterLng = pl.lng)
                        }
                    }
                }
                Field("中心纬度", fmt(s.mapCenterLat), KeyboardType.Decimal) {
                    s = s.copy(mapCenterLat = it.toDoubleOrNull() ?: s.mapCenterLat)
                }
                Field("中心经度", fmt(s.mapCenterLng), KeyboardType.Decimal) {
                    s = s.copy(mapCenterLng = it.toDoubleOrNull() ?: s.mapCenterLng)
                }
            }
            Spacer(Modifier.height(Dim.gap))

            // ------------------------------------------------------- 查询与数据
            SectionCard("查询") {
                ChipRow(
                    options = listOf(
                        "auto" to "自动（RailGo→12306）",
                        "railgo" to "仅 RailGo",
                        "12306" to "仅 12306",
                    ),
                    selected = s.trainQuerySource,
                    onPick = { s = s.copy(trainQuerySource = it) },
                )
            }
            Spacer(Modifier.height(Dim.gap))

            SectionCard("第三方数据") {
                SwitchRow("自动检查配属表更新（7 天一次）", s.dataAutoUpdate) {
                    s = s.copy(dataAutoUpdate = it)
                }
                Spacer(Modifier.height(4.dp))
                Text(dataInfo.ifEmpty { "读取中…" }, color = p.textSecondary, fontSize = 12.sp)
                if (update.message.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        update.message,
                        color = when {
                            update.running -> p.textSecondary
                            update.ok -> p.ok
                            else -> p.err
                        },
                        fontSize = 11.sp,
                    )
                }
                Spacer(Modifier.height(8.dp))
                Button(
                    onClick = { vm.checkDataUpdate(force = true) },
                    enabled = !update.running,
                    shape = RoundedCornerShape(50),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = p.surfaceAlt, contentColor = p.text),
                ) {
                    Text(if (update.running) "检查中…" else "立即检查更新", fontSize = 13.sp)
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "来源：gitcode CCCccc233/LBJ_Console@resources（与桌面端同一份）。" +
                        "校验行数/型号数通过才替换，失败保留旧数据。",
                    color = p.textTertiary, fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(Dim.gap))

            SectionCard("关于") {
                Text("CR 列车预警器 · Android v3.0.0", color = p.text, fontSize = 13.sp)
                Text(
                    "桌面版 v2.6.1 → v3.0.0 与本次安卓版同时发版；地图页与桌面端共用 " +
                        "shared/web/railmap.html，数据共用 shared/data/*。",
                    color = p.textTertiary, fontSize = 11.sp,
                    modifier = Modifier.padding(top = 4.dp),
                )
                Text(
                    "高德 Key（amapKey/amapSecurity）自 v3.0 起已废弃：地图改用 railmap.html 的" +
                        "OSM/ORM 图源，老配置里的字段会保留写入但不再使用。",
                    color = p.textTertiary, fontSize = 11.sp,
                    modifier = Modifier.padding(top = 6.dp),
                )
                Text(
                    "配属号段表来源 LBJ_Console（GPL-3.0）；参数表来源 trainfanz.com 公开资料。",
                    color = p.textTertiary, fontSize = 11.sp,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }

            Spacer(Modifier.height(14.dp))
            Button(
                onClick = {
                    vm.updateSettings(s)
                    saved = true
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(
                    containerColor = p.accent, contentColor = p.onAccent),
            ) { Text("保存设置（重建链路）", fontSize = 14.sp) }

            if (saved) {
                Spacer(Modifier.height(6.dp))
                Text("已保存：连接类参数已重建链路，地图项已下发地图页",
                    color = p.ok, fontSize = 12.sp)
            }
            Spacer(Modifier.height(Dim.dockSpace))
        }
    }
}

// ------------------------------------------------------------------ 小控件

private fun fmt(v: Double): String =
    if (v == v.toLong().toDouble()) v.toLong().toString()
    else String.format(Locale.US, "%.4f", v).trimEnd('0').trimEnd('.')

@Composable
private fun Field(
    label: String,
    value: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    onChange: (String) -> Unit,
) {
    val p = pal()
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = p.textSecondary, fontSize = 12.sp, modifier = Modifier.width(110.dp))
        LbjTextField(
            value = value,
            onValueChange = onChange,
            modifier = Modifier.weight(1f),
            keyboardType = keyboardType,
        )
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    val p = pal()
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = p.text, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = p.onAccent,
                checkedTrackColor = p.accent,
            ),
        )
    }
}

@Composable
private fun ChipRow(
    options: List<Pair<String, String>>,
    selected: String,
    onPick: (String) -> Unit,
) {
    val p = pal()
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (id, label) ->
            val active = id == selected
            Box(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(50))
                    .background(if (active) p.accent.copy(alpha = 0.16f) else p.surfaceAlt)
                    .border(
                        1.dp,
                        if (active) p.accent.copy(alpha = 0.5f) else p.border,
                        RoundedCornerShape(50),
                    )
                    .clickable { onPick(id) }
                    .padding(vertical = 7.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    color = if (active) p.accent else p.textSecondary,
                    fontSize = 11.sp,
                    fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun SelectRow(
    label: String,
    value: String,
    options: List<Pair<String, String>>,
    onPick: (String) -> Unit,
) {
    val p = pal()
    var open by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = p.textSecondary, fontSize = 12.sp, modifier = Modifier.width(110.dp))
        Box(Modifier.weight(1f)) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(p.surfaceAlt)
                    .border(1.dp, p.border, RoundedCornerShape(8.dp))
                    .clickable { open = true }
                    .padding(horizontal = 10.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    value,
                    color = p.text, fontSize = 13.sp,
                    fontFamily = FontFamily.Default,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                )
                Text("▾", color = p.textTertiary, fontSize = 11.sp)
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { (id, name) ->
                    DropdownMenuItem(
                        text = {
                            Text(
                                name,
                                fontSize = 13.sp,
                                color = if (id == value) p.accent else p.text,
                            )
                        },
                        onClick = {
                            open = false
                            onPick(id)
                        },
                    )
                }
            }
        }
    }
}
