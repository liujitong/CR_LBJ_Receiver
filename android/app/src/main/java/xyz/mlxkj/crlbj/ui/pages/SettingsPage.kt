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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Sensors
import androidx.compose.material.icons.filled.SettingsInputAntenna
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.ui.components.Divider
import xyz.mlxkj.crlbj.ui.components.LbjTextField
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/** 底图候选（id/名称/顺序与 railmap.html 的 BASE_SOURCES 逐字一致） */
private val MAP_BASES = listOf(
    "amap" to "高德 街道（免 Key）",
    "amap_img" to "高德 卫星（免 Key）",
    "baidu" to "百度 街道（免 Key）",
    "baidu_sat" to "百度 卫星（免 Key）",
    "osm" to "OSM 标准",
    "tdt_vec" to "天地图 矢量（CGCS2000）",
    "tdt_img" to "天地图 影像（CGCS2000）",
)

/** 铁路图层候选（ORM = OpenRailwayMap） */
private val MAP_RAILS = listOf(
    "off" to "不显示",
    "orm_standard" to "ORM 标准（线路+信号）",
    "orm_maxspeed" to "ORM 限速",
    "orm_signals" to "ORM 信号",
    "orm_electrified" to "ORM 电气化",
    "orm_gauge" to "ORM 轨距",
    "rail_local" to "本地铁路线（GeoJSON）",
)

/** 菜单式设置：每项进入独立子页（顶部返回） */
private data class MenuGroup(val id: String, val title: String, val icon: ImageVector)

private val MENU = listOf(
    MenuGroup("source", "数据源", Icons.Filled.SettingsInputAntenna),
    MenuGroup("rf", "射频", Icons.Filled.Tune),
    MenuGroup("gate", "门控·AFC", Icons.Filled.Sensors),
    MenuGroup("decode", "解码", Icons.Filled.GraphicEq),
    MenuGroup("map", "地图", Icons.Filled.Map),
    MenuGroup("query", "查询·数据", Icons.Filled.Search),
    MenuGroup("about", "关于", Icons.Filled.Info),
)

/**
 * 设置页（菜单式 + 自动保存）：
 *  · 首页是链接列表（图标 + 标题 + 副标题 + 箭头），点击进入子页，顶部返回；
 *  · **没有保存按钮**：开关/单选/滑块即时保存并下发；文本输入失焦/回车/离开页面
 *    自动保存（失焦后 400ms 防抖）；
 *  · 连接类参数变更走 vm.updateSettings（重建 DSP 链路），地图/界面类走
 *    updateViewSettings（即时下发 WebView 不断流），业务类走 updateBusinessSettings；
 *  · 草稿提升到子页之外，返回/切换不丢未提交内容；保存失败给轻提示。
 */
@Composable
fun SettingsPage(vm: ReceiverViewModel) {
    val current by vm.settings.collectAsStateWithLifecycle()
    val places by vm.places.collectAsStateWithLifecycle()
    val dataInfo by vm.dataInfo.collectAsStateWithLifecycle()
    val update by vm.dataUpdate.collectAsStateWithLifecycle()
    val pending by vm.pendingQuery.collectAsStateWithLifecycle()
    val p = pal()

    // 草稿在子页之外提升：设置变化（含本页自动保存）时重新快照
    var s by remember(current) { mutableStateOf(current) }
    var sub by rememberSaveable { mutableStateOf<String?>(null) }
    var usbPrompt by remember { mutableStateOf(false) }
    var saveErr by remember { mutableStateOf<String?>(null) }

    // 自动保存：按变更字段路由到对应保存语义
    fun commit(next: ReceiverSettings) {
        val cur = vm.settings.value
        if (next == cur) return
        runCatching {
            when {
                connChanged(cur, next) -> vm.updateSettings(next)
                viewChanged(cur, next) -> vm.updateViewSettings(next)
                else -> vm.updateBusinessSettings(next)
            }
        }.onFailure { saveErr = "保存失败：${it.message}" }
    }

    // 解码页「查这趟车 / 查这台机车」→ 查询·数据子页（QuerySection 消费预填）
    LaunchedEffect(pending) { if (pending != null) sub = "query" }
    LaunchedEffect(saveErr) {
        if (saveErr != null) {
            kotlinx.coroutines.delay(3500)
            saveErr = null
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        if (sub == null) {
            PageHeader(title = "设置", subtitle = "v3.2.1 · 更改自动保存")
            saveErr?.let {
                Text(it, color = p.err, fontSize = 12.sp,
                    modifier = Modifier.padding(bottom = 4.dp))
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                SectionCard {
                    MENU.forEachIndexed { i, g ->
                        if (i > 0) Divider()
                        MenuRow(g, menuSubtitle(g.id, s)) { sub = g.id }
                    }
                }
                Spacer(Modifier.height(Dim.dockSpace))
            }
        } else {
            val title = MENU.firstOrNull { it.id == sub }?.title ?: "设置"
            Row(
                Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "返回",
                    tint = p.text,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .clickable { sub = null }
                        .padding(6.dp)
                        .size(24.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(title, color = p.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            }
            saveErr?.let {
                Text(it, color = p.err, fontSize = 12.sp,
                    modifier = Modifier.padding(bottom = 4.dp))
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                when (sub) {
                    // -------------------------------------------------- 数据源
                    "source" -> SectionCard("数据源") {
                        ChipRow(
                            options = listOf("usb" to "本机 USB", "rtl_tcp" to "rtl_tcp", "owrx" to "OWRX"),
                            selected = s.sourceType,
                            onPick = { id ->
                                if (id == "usb" && s.sourceType != "usb") usbPrompt = true
                                commit(s.copy(sourceType = id))
                            },
                        )
                        Spacer(Modifier.height(8.dp))
                        if (s.isUsb) {
                            Text(
                                "USB 直连：手机 OTG 接 RTL-SDR 电视棒，设备查找与权限由系统弹窗确认。",
                                color = p.textTertiary, fontSize = 11.sp,
                            )
                            Spacer(Modifier.height(6.dp))
                        } else {
                            Field("主机", s.host) { commit(s.copy(host = it.trim())) }
                            Field("端口", s.port.toString(), KeyboardType.Number) {
                                commit(s.copy(port = it.toIntOrNull() ?: s.port))
                            }
                        }
                        Field("采样率 Hz", s.sampleRate.toString(), KeyboardType.Number) {
                            commit(s.copy(sampleRate = it.toIntOrNull() ?: s.sampleRate))
                        }
                    }

                    // ---------------------------------------------------- 射频
                    "rf" -> SectionCard("射频") {
                        Field("频率 MHz", fmt(s.freqMhz), KeyboardType.Decimal) {
                            commit(s.copy(freqMhz = it.toDoubleOrNull() ?: s.freqMhz))
                        }
                        Field("增益 dB", fmt(s.gainDb), KeyboardType.Decimal) {
                            commit(s.copy(gainDb = it.toDoubleOrNull() ?: s.gainDb))
                        }
                        Field("PPM 校正", fmt(s.ppm), KeyboardType.Decimal) {
                            commit(s.copy(ppm = it.toDoubleOrNull() ?: s.ppm))
                        }
                        Field("信道带宽 kHz", fmt(s.bwKhz), KeyboardType.Decimal) {
                            commit(s.copy(bwKhz = it.toDoubleOrNull() ?: s.bwKhz))
                        }
                        Field("DC 偏移 Hz", fmt(s.dcOffsetHz), KeyboardType.Decimal) {
                            commit(s.copy(dcOffsetHz = it.toDoubleOrNull() ?: s.dcOffsetHz))
                        }
                        Text(
                            "USB 直连建议 DC 偏移 50000 Hz（让目标频点落在 DDC 之后），OWRX 保持 0。",
                            color = p.textTertiary, fontSize = 11.sp,
                        )
                    }

                    // ----------------------------------------------- 门控与 AFC
                    "gate" -> SectionCard("RSSI 门控与 AFC") {
                        Field("开启门限 dB", fmt(s.rssiThresholdDb), KeyboardType.Decimal) {
                            commit(s.copy(rssiThresholdDb = it.toDoubleOrNull() ?: s.rssiThresholdDb))
                        }
                        Field("释放迟滞 dB", fmt(s.rssiHystDb), KeyboardType.Decimal) {
                            commit(s.copy(rssiHystDb = it.toDoubleOrNull() ?: s.rssiHystDb))
                        }
                        Field("保持时长 ms", fmt(s.rssiHoldMs), KeyboardType.Decimal) {
                            commit(s.copy(rssiHoldMs = it.toDoubleOrNull() ?: s.rssiHoldMs))
                        }
                        SwitchRow("AFC 自动频率补偿", s.afcEnable) { commit(s.copy(afcEnable = it)) }
                        Field("AFC 最大修正 Hz", fmt(s.afcMaxHz), KeyboardType.Decimal) {
                            commit(s.copy(afcMaxHz = it.toDoubleOrNull() ?: s.afcMaxHz))
                        }
                        Field("AFC 环路增益", fmt(s.afcGain), KeyboardType.Decimal) {
                            commit(s.copy(afcGain = it.toDoubleOrNull() ?: s.afcGain))
                        }
                        SwitchRow("报文后保持 AFC", s.keepAfcAfterPacket) {
                            commit(s.copy(keepAfcAfterPacket = it))
                        }
                    }

                    // ------------------------------------------------- 解码业务
                    "decode" -> SectionCard("解码业务") {
                        Field("去重窗口 秒", fmt(s.dedupeWindow), KeyboardType.Decimal) {
                            commit(s.copy(dedupeWindow = it.toDoubleOrNull() ?: s.dedupeWindow))
                        }
                        Field("ETA 上限 分钟", fmt(s.etaMaxMin), KeyboardType.Decimal) {
                            commit(s.copy(etaMaxMin = it.toDoubleOrNull() ?: s.etaMaxMin))
                        }
                        Field("本站公里标 km", s.userKm, KeyboardType.Decimal) {
                            commit(s.copy(userKm = it.trim()))
                        }
                        Field("线路公里标", s.routeKmText) { commit(s.copy(routeKmText = it)) }
                        Text(
                            "线路公里标格式：线路=km，多条用逗号分隔，例如 京九线=1420,沪昆线=730",
                            color = p.textTertiary, fontSize = 11.sp,
                        )
                    }

                    // ----------------------------------------------------- 地图
                    "map" -> SectionCard("地图") {
                        SelectRow(
                            label = "底图",
                            value = MAP_BASES.firstOrNull { it.first == s.mapBase }?.second ?: s.mapBase,
                            options = MAP_BASES,
                        ) { commit(s.copy(mapBase = it)) }
                        SelectRow(
                            label = "铁路图层",
                            value = MAP_RAILS.firstOrNull { it.first == s.mapRail }?.second ?: s.mapRail,
                            options = MAP_RAILS,
                        ) { commit(s.copy(mapRail = it)) }
                        var opacity by remember(s.mapRailOpacity) {
                            mutableStateOf(s.mapRailOpacity.toFloat())
                        }
                        Text(
                            "铁路不透明度 %.0f%%".format(Locale.US, opacity * 100),
                            color = p.textSecondary, fontSize = 12.sp,
                            modifier = Modifier.padding(top = 6.dp),
                        )
                        Slider(
                            value = opacity,
                            onValueChange = { opacity = it },
                            onValueChangeFinished = {
                                commit(s.copy(mapRailOpacity = opacity.toDouble()))
                            },
                            valueRange = 0.2f..1f,
                        )
                        SwitchRow("夜间底图", s.mapNight) { commit(s.copy(mapNight = it)) }
                        SwitchRow("自动跟随最新列车", s.mapFollow) { commit(s.copy(mapFollow = it)) }
                        Field("缩放级别", s.mapZoom.toString(), KeyboardType.Number) {
                            commit(s.copy(mapZoom = it.toIntOrNull() ?: s.mapZoom))
                        }
                        Field("天地图 tk", s.mapTdtKey) { commit(s.copy(mapTdtKey = it.trim())) }
                        Text(
                            "天地图底图需要「浏览器端」tk（tianditu.gov.cn 免费申请）；留空时选中该底图只会提示不加载。",
                            color = p.textTertiary, fontSize = 11.sp,
                        )
                        Spacer(Modifier.height(6.dp))
                        Field("天地图 Referer 域名", s.tdtReferer) { commit(s.copy(tdtReferer = it.trim())) }
                        Text(
                            "申请浏览器端 tk 时登记的白名单域名（如 example.com）。填写后安卓代拉天地图瓦片" +
                                "并附加 Referer: https://<域名>/；留空不附加。",
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
                                    commit(s.copy(mapCenterName = pl.name, mapCenterLat = pl.lat,
                                        mapCenterLng = pl.lng))
                                }
                            }
                        }
                        Field("中心纬度", fmt(s.mapCenterLat), KeyboardType.Decimal) {
                            commit(s.copy(mapCenterLat = it.toDoubleOrNull() ?: s.mapCenterLat))
                        }
                        Field("中心经度", fmt(s.mapCenterLng), KeyboardType.Decimal) {
                            commit(s.copy(mapCenterLng = it.toDoubleOrNull() ?: s.mapCenterLng))
                        }
                        Spacer(Modifier.height(10.dp))
                        Divider()
                        Spacer(Modifier.height(8.dp))
                        // 离线瓦片缓存（cacheDir/tile_cache，300MB LRU）
                        val cacheStats by vm.tileCacheStats.collectAsStateWithLifecycle()
                        LaunchedEffect(Unit) { vm.refreshTileCacheStats() }
                        Text(
                            "地图瓦片缓存：%d 张 / %.1f MB（上限 300 MB）".format(
                                Locale.US, cacheStats.first, cacheStats.second / 1048576.0),
                            color = p.textSecondary, fontSize = 12.sp,
                        )
                        Spacer(Modifier.height(6.dp))
                        Button(
                            onClick = { vm.clearTileCache() },
                            shape = RoundedCornerShape(50),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = p.surfaceAlt, contentColor = p.text),
                        ) { Text("清除地图缓存", fontSize = 13.sp) }
                    }

                    // ----------------------------------------------- 查询与数据
                    "query" -> {
                        SectionCard("查询") {
                            ChipRow(
                                options = listOf(
                                    "auto" to "自动（RailGo→12306）",
                                    "railgo" to "仅 RailGo",
                                    "12306" to "仅 12306",
                                ),
                                selected = s.trainQuerySource,
                                onPick = { commit(s.copy(trainQuerySource = it)) },
                            )
                        }
                        Spacer(Modifier.height(Dim.gap))
                        // 原「查询」页的手动查询 UI 并入此处（不再占 Dock 页签）
                        QuerySection(vm)
                        Spacer(Modifier.height(Dim.gap))
                        SectionCard("第三方数据") {
                            SwitchRow("自动检查配属表更新（7 天一次）", s.dataAutoUpdate) {
                                commit(s.copy(dataAutoUpdate = it))
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
                    }

                    // ----------------------------------------------------- 关于
                    else -> SectionCard("关于") {
                        Text("CR 列车预警器 · Android v3.2.1", color = p.text, fontSize = 13.sp)
                        Text(
                            "桌面版与安卓版 v3.2.1 同版本号；地图页与桌面端共用 " +
                                "shared/web/railmap.html，数据共用 shared/data/*。",
                            color = p.textTertiary, fontSize = 11.sp,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                        Text(
                            "配属号段表来源 LBJ_Console（GPL-3.0）；参数表来源 trainfanz.com 公开资料。",
                            color = p.textTertiary, fontSize = 11.sp,
                            modifier = Modifier.padding(top = 6.dp),
                        )
                        Text(
                            "开源致谢",
                            color = p.text, fontSize = 12.sp,
                            modifier = Modifier.padding(top = 10.dp),
                        )
                        Text(
                            "· LBJ_Console（github.com/undef-i/LBJ_Console，作者 undef-i，GPL-3.0）：" +
                                "机车配属号段表、机车类型代号表取自该项目 resources 分支；" +
                                "界面骨架与地图图源方案亦参考其实现，特此致谢。\n" +
                                "· OpenStreetMap 贡献者（ODbL）、OpenRailwayMap（CC-BY-SA）、" +
                                "Leaflet（BSD-2-Clause）：地图与铁路图层。\n" +
                                "· RailGo / 中国铁路 12306：车次时刻表查询。\n" +
                                "· 天地图、高德地图、百度地图：底图瓦片服务。",
                            color = p.textTertiary, fontSize = 11.sp,
                            modifier = Modifier.padding(top = 4.dp),
                        )
                    }
                }
                Spacer(Modifier.height(Dim.dockSpace))
            }
        }
    }

    // ---- 切到本机 USB：推荐参数弹窗（确认覆盖并自动保存，取消保持不变） ----
    if (usbPrompt) {
        AlertDialog(
            onDismissRequest = { usbPrompt = false },
            containerColor = p.surface,
            title = { Text("USB 推荐参数", color = p.text, fontSize = 17.sp) },
            text = {
                Text(
                    "本机 USB 直连推荐：\n" +
                        "· 采样率 240 kS/s\n" +
                        "· 增益 19.7 dB\n" +
                        "· DC 偏移 50 kHz\n\n" +
                        "是否采用推荐值？（采用后立即自动保存）",
                    color = p.textSecondary, fontSize = 13.sp,
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    val d = ReceiverSettings.USB_DEFAULTS
                    commit(s.copy(
                        sampleRate = d.sampleRate,
                        gainDb = d.gainDb,
                        dcOffsetHz = d.dcOffsetHz,
                    ))
                    usbPrompt = false
                }) { Text("采用推荐值", color = p.accent) }
            },
            dismissButton = {
                TextButton(onClick = { usbPrompt = false }) {
                    Text("保持当前", color = p.textSecondary)
                }
            },
        )
    }
}

// ------------------------------------------------------------------ 变更路由

/** 连接类字段：变更需要重建 DSP 链路（vm.updateSettings） */
private fun connChanged(a: ReceiverSettings, b: ReceiverSettings): Boolean =
    a.sourceType != b.sourceType || a.host != b.host || a.port != b.port ||
    a.sampleRate != b.sampleRate || a.freqMhz != b.freqMhz || a.gainDb != b.gainDb ||
    a.ppm != b.ppm || a.dcOffsetHz != b.dcOffsetHz || a.bwKhz != b.bwKhz ||
    a.blockSize != b.blockSize || a.rssiThresholdDb != b.rssiThresholdDb ||
    a.rssiHystDb != b.rssiHystDb || a.rssiHoldMs != b.rssiHoldMs ||
    a.afcEnable != b.afcEnable || a.afcMaxHz != b.afcMaxHz ||
    a.afcGain != b.afcGain || a.keepAfcAfterPacket != b.keepAfcAfterPacket

/** 地图/界面类字段：即时下发 WebView，不重建链路（vm.updateViewSettings） */
private fun viewChanged(a: ReceiverSettings, b: ReceiverSettings): Boolean =
    a.mapZoom != b.mapZoom || a.mapFollow != b.mapFollow || a.mapNight != b.mapNight ||
    a.mapBase != b.mapBase || a.mapRail != b.mapRail || a.mapRailOpacity != b.mapRailOpacity ||
    a.mapTdtKey != b.mapTdtKey || a.tdtReferer != b.tdtReferer ||
    a.mapCenterName != b.mapCenterName || a.mapCenterLat != b.mapCenterLat ||
    a.mapCenterLng != b.mapCenterLng

// ------------------------------------------------------------------ 菜单行

private fun menuSubtitle(id: String, s: ReceiverSettings): String = when (id) {
    "source" -> (if (s.isUsb) "本机 USB" else "${s.sourceType} · ${s.host}:${s.port}") +
        " · ${s.sampleRate / 1000} kS/s"
    "rf" -> "${fmt(s.freqMhz)} MHz · 增益 ${fmt(s.gainDb)} dB"
    "gate" -> "门限 ${fmt(s.rssiThresholdDb)} dB · AFC ${if (s.afcEnable) "开" else "关"}"
    "decode" -> "去重 ${fmt(s.dedupeWindow)} s · ETA ≤ ${fmt(s.etaMaxMin)} min"
    "map" -> (MAP_BASES.firstOrNull { it.first == s.mapBase }?.second ?: s.mapBase) +
        " · " + (MAP_RAILS.firstOrNull { it.first == s.mapRail }?.second ?: s.mapRail)
    "query" -> (when (s.trainQuerySource) {
        "railgo" -> "仅 RailGo"; "12306" -> "仅 12306"; else -> "RailGo→12306"
    }) + " · 配属表自动更新" + if (s.dataAutoUpdate) "开" else "关"
    else -> "v3.2.1 · 桌面版与安卓版同版本号"
}

@Composable
private fun MenuRow(g: MenuGroup, subtitle: String, onClick: () -> Unit) {
    val p = pal()
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(g.icon, contentDescription = null, tint = p.accent, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(g.title, color = p.text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
            Text(subtitle, color = p.textTertiary, fontSize = 11.sp, maxLines = 1)
        }
        Text("›", color = p.textTertiary, fontSize = 20.sp)
    }
}

// ------------------------------------------------------------------ 小控件

private fun fmt(v: Double): String =
    if (v == v.toLong().toDouble()) v.toLong().toString()
    else String.format(Locale.US, "%.4f", v).trimEnd('0').trimEnd('.')

/**
 * 文本输入行：编辑期间只改本地状态；**失焦后 400ms 防抖 / 回车 / 离开页面**自动提交。
 */
@Composable
private fun Field(
    label: String,
    value: String,
    keyboardType: KeyboardType = KeyboardType.Text,
    onCommit: (String) -> Unit,
) {
    val p = pal()
    val latestCommit by rememberUpdatedState(onCommit)
    val latestValue by rememberUpdatedState(value)
    var text by remember(value) { mutableStateOf(value) }
    var focused by remember { mutableStateOf(false) }

    // 失焦后 400ms 防抖提交（聚焦输入期间不打断）
    LaunchedEffect(text, focused) {
        if (!focused && text != latestValue) {
            kotlinx.coroutines.delay(400)
            latestCommit(text)
        }
    }
    // 离开页面（子页切换/返回）时提交未保存内容
    DisposableEffect(Unit) {
        onDispose { if (text != latestValue) latestCommit(text) }
    }

    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = p.textSecondary, fontSize = 12.sp, modifier = Modifier.width(110.dp))
        LbjTextField(
            value = text,
            onValueChange = { text = it },
            modifier = Modifier
                .weight(1f)
                .onFocusChanged { focused = it.isFocused },
            keyboardType = keyboardType,
            onDone = { latestCommit(text) },
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
