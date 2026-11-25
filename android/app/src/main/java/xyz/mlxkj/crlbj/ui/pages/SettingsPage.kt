package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.composefluent.component.Text

/** 设置页（M1 起逐组启用）：数据源 / 射频 / 到达估算 / 地图 / 界面。 */
@Composable
fun SettingsPage() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(16.dp)
        ) {
            Text("设置", fontSize = 20.sp)
            Text(
                "数据源（USB / rtl_tcp / OWRX + 设备检测）\n" +
                "射频（频率/采样率/增益/PPM/带宽/偏移）\n" +
                "到达估算 · 地图（Key/中心/日夜/跟随） · 界面（主题/字号）",
                color = Color(0xFF9AA0A6), fontSize = 12.sp,
            )
        }
    }
}
