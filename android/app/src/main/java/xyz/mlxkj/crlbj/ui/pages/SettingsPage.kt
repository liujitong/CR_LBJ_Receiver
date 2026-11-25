package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.background
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Button
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.vm.ReceiverViewModel

/**
 * 设置页（M2c 最小可编辑版）：数据源 / 射频 / RSSI 门控 / AFC / 业务。
 * 字段名与桌面版 lbj_config.json 同名；保存即落盘并重建 DSP 链路。
 */
@Composable
fun SettingsPage(vm: ReceiverViewModel) {
    val current by vm.settings.collectAsStateWithLifecycle()
    // 本地草稿：进入页面时快照，保存时统一提交
    var s by remember(current) { mutableStateOf(current) }
    var saved by remember { mutableStateOf(false) }

    @Composable
    fun field(label: String, value: String, onChange: (String) -> Unit) =
        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(label, color = Color(0xFF9AA0A6), fontSize = 13.sp,
                modifier = Modifier.width(150.dp))
            androidx.compose.foundation.text.BasicTextField(
                value = value,
                onValueChange = onChange,
                singleLine = true,
                textStyle = androidx.compose.ui.text.TextStyle(
                    color = Color(0xFFE8EAED), fontSize = 13.sp),
                modifier = Modifier.weight(1f).background(Color(0xFF1A2028))
                    .padding(horizontal = 8.dp, vertical = 6.dp),
            )
        }

    Column(Modifier.fillMaxSize().padding(12.dp).verticalScroll(rememberScrollState())) {
        Text("设置", fontSize = 20.sp)
        Spacer(Modifier.height(8.dp))

        group("数据源") {
            field("类型 (usb/owrx/rtl_tcp)", s.sourceType) { s = s.copy(sourceType = it.trim()) }
            if (!s.isUsb) {
                field("主机", s.host) { s = s.copy(host = it.trim()) }
                field("端口", s.port.toString()) { s = s.copy(port = it.toIntOrNull() ?: s.port) }
            }
            field("采样率 Hz", s.sampleRate.toString()) { s = s.copy(sampleRate = it.toIntOrNull() ?: s.sampleRate) }
        }
        group("射频") {
            field("频率 MHz", s.freqMhz.toString()) { s = s.copy(freqMhz = it.toDoubleOrNull() ?: s.freqMhz) }
            field("增益 dB", s.gainDb.toString()) { s = s.copy(gainDb = it.toDoubleOrNull() ?: s.gainDb) }
            field("PPM", s.ppm.toString()) { s = s.copy(ppm = it.toDoubleOrNull() ?: s.ppm) }
            field("带宽 kHz", s.bwKhz.toString()) { s = s.copy(bwKhz = it.toDoubleOrNull() ?: s.bwKhz) }
            field("DC 偏移 Hz", s.dcOffsetHz.toString()) { s = s.copy(dcOffsetHz = it.toDoubleOrNull() ?: s.dcOffsetHz) }
        }
        group("RSSI 门控") {
            field("开启门限 dB", s.rssiThresholdDb.toString()) { s = s.copy(rssiThresholdDb = it.toDoubleOrNull() ?: s.rssiThresholdDb) }
            field("释放迟滞 dB", s.rssiHystDb.toString()) { s = s.copy(rssiHystDb = it.toDoubleOrNull() ?: s.rssiHystDb) }
            field("保持 ms", s.rssiHoldMs.toString()) { s = s.copy(rssiHoldMs = it.toDoubleOrNull() ?: s.rssiHoldMs) }
        }
        group("AFC") {
            field("启用 (true/false)", s.afcEnable.toString()) {
                s = s.copy(afcEnable = it.trim().equals("true", true))
            }
            field("最大修正 Hz", s.afcMaxHz.toString()) { s = s.copy(afcMaxHz = it.toDoubleOrNull() ?: s.afcMaxHz) }
            field("环路增益", s.afcGain.toString()) { s = s.copy(afcGain = it.toDoubleOrNull() ?: s.afcGain) }
        }
        group("解码业务") {
            field("车次规则 (auto/2026/legacy)", s.trainScheme) { s = s.copy(trainScheme = it.trim()) }
            field("去重窗口 秒", s.dedupeWindow.toString()) { s = s.copy(dedupeWindow = it.toDoubleOrNull() ?: s.dedupeWindow) }
            field("ETA 上限 分钟", s.etaMaxMin.toString()) { s = s.copy(etaMaxMin = it.toDoubleOrNull() ?: s.etaMaxMin) }
            field("本站公里标 km", s.userKm) { s = s.copy(userKm = it.trim()) }
            field("线路公里标", s.routeKmText) { s = s.copy(routeKmText = it) }
        }
        group("地图") {
            field("高德 Key", s.amapKey) { s = s.copy(amapKey = it.trim()) }
            field("安全密钥", s.amapSecurity) { s = s.copy(amapSecurity = it.trim()) }
            field("缩放级别", s.mapZoom.toString()) { s = s.copy(mapZoom = it.toIntOrNull() ?: s.mapZoom) }
            field("跟随 (true/false)", s.mapFollow.toString()) {
                s = s.copy(mapFollow = it.trim().equals("true", true))
            }
            field("夜间模式 (true/false)", s.mapNight.toString()) {
                s = s.copy(mapNight = it.trim().equals("true", true))
            }
        }

        Spacer(Modifier.height(10.dp))
        Row {
            Button(onClick = {
                vm.updateSettings(s)
                saved = true
            }, modifier = Modifier.weight(1f)) {
                Text("保存（重建链路）")
            }
        }
        if (saved) {
            Spacer(Modifier.height(6.dp))
            Text("已保存并重建引擎链路（下一次启动生效）",
                color = Color(0xFF8BE28B), fontSize = 12.sp)
        }
    }
}

@Composable
private fun group(title: String, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxWidth().background(Color(0xFF10131A)).padding(10.dp)) {
        Column {
            Text(title, fontSize = 15.sp, color = Color(0xFFE8EAED))
            Spacer(Modifier.height(4.dp))
            content()
        }
    }
    Spacer(Modifier.height(8.dp))
}
