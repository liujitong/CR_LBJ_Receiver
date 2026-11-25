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

/** 地图页（M3 接入高德 SDK；M0 占位）。 */
@Composable
fun MapPage() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("地图（M3 接入）", fontSize = 20.sp)
            Text(
                "高德原生地图 + 列车标记 + 轨迹\n无网时退化为经纬度/公里标/距离文字卡",
                color = Color(0xFF9AA0A6), fontSize = 12.sp, modifier = Modifier.padding(8.dp)
            )
        }
    }
}
