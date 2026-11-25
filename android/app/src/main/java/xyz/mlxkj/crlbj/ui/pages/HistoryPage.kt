package xyz.mlxkj.crlbj.ui.pages

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Button
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.ui.theme.CrRed
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale

/**
 * 历史页：解码记录列表（Room，uid 去重后的最终记录）+ CSV 导出 + 清空。
 */
@Composable
fun HistoryPage(vm: ReceiverViewModel) {
    val records by vm.records.collectAsStateWithLifecycle()
    val count by vm.recordCount.collectAsStateWithLifecycle()
    val csvMsg by vm.csvMsg.collectAsStateWithLifecycle()

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri -> uri?.let { vm.exportCsv(it) } }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("历史记录", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(8.dp))
            Text("共 $count 条", color = Color(0xFF9AA0A6), fontSize = 13.sp)
            Spacer(Modifier.weight(1f))
            Button(onClick = { exportLauncher.launch("lbj_history.csv") }) { Text("导出 CSV") }
            Spacer(Modifier.width(8.dp))
            Button(onClick = { vm.clearHistory() }) { Text("清空") }
        }
        csvMsg?.let {
            Spacer(Modifier.height(4.dp))
            Text(it, color = Color(0xFF8BE28B), fontSize = 12.sp)
        }
        Spacer(Modifier.height(8.dp))

        if (records.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("暂无记录（开始接收后自动入库）", color = Color(0xFF9AA0A6))
            }
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                items(records, key = { it.uid }) { r ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(r.train.ifEmpty { "----" }, fontSize = 18.sp,
                                fontWeight = FontWeight.Bold, color = Color(0xFFE8EAED))
                            Spacer(Modifier.width(8.dp))
                            Text(r.direction, fontSize = 12.sp, color = CrRed)
                            Spacer(Modifier.weight(1f))
                            Text(r.timeStr, fontSize = 11.sp, color = Color(0xFF666E78))
                        }
                        Text(
                            "${r.category}  ${r.speed} km/h  ${r.position}  " +
                                "线路 ${r.route.ifEmpty { "----" }}" +
                                (r.latitude?.let {
                                    "  %.5f,%.5f".format(Locale.US, it, r.longitude ?: 0.0)
                                } ?: ""),
                            fontSize = 11.sp, color = Color(0xFF9AA0A6),
                        )
                        Text(
                            "RSSI %.1f dB  ETA %s %s".format(
                                Locale.US, r.rssi, r.etaTime, r.etaStatus),
                            fontSize = 10.sp, color = Color(0xFF666E78),
                        )
                        Spacer(Modifier.height(2.dp))
                        Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0xFF222833)))
                    }
                }
            }
        }
    }
}
