package xyz.mlxkj.crlbj.ui.pages

import android.Manifest
import android.content.Context
import android.location.LocationManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.github.composefluent.component.Button
import io.github.composefluent.component.Text
import xyz.mlxkj.crlbj.core.Gcj02
import xyz.mlxkj.crlbj.ui.theme.CrRed
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 地图页：高德 Web(JS API) 内嵌 WebView（Key 用户在设置页配置）。
 *  - 有 Key + 有网：列车标记（GCJ-02）+ 轨迹线 + 自动跟随
 *  - 无 Key / 无网：降级文本卡（最新坐标 + 与本机 GPS 的距离）
 */
@Composable
fun MapPage(vm: ReceiverViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val events by vm.events.collectAsStateWithLifecycle()
    val latest = events.firstOrNull()

    var useMap by remember { mutableStateOf(settings.amapKey.isNotBlank()) }
    var gps by remember { mutableStateOf(doubleArrayOf(0.0, 0.0)) } // WGS-84
    var gpsValid by remember { mutableStateOf(false) }

    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (grants.values.any { it }) {
            val ctx = vm.getApplication<android.app.Application>()
            readLastGps(ctx)?.let { gps = it; gpsValid = true }
        }
    }

    LaunchedEffect(Unit) {
        val ctx = vm.getApplication<android.app.Application>()
        readLastGps(ctx)?.let { gps = it; gpsValid = true }
    }

    // 最新坐标变化 → 推给 JS
    var jsBridge: WebView? = remember { null }
    LaunchedEffect(latest?.latitude, latest?.longitude, settings.mapFollow) {
        val web = jsBridge ?: return@LaunchedEffect
        val lat = latest?.latitude ?: return@LaunchedEffect
        val lng = latest?.longitude ?: return@LaunchedEffect
        val c = Gcj02.fromWgs(lat, lng)
        web.evaluateJavascript(
            "window.updateTrain(${c[0]}, ${c[1]}, '${latest!!.train}', ${settings.mapFollow})",
            null,
        )
    }

    Column(Modifier.fillMaxSize().padding(12.dp)) {
        Row {
            Text("地图", fontSize = 20.sp)
            Spacer(Modifier.weight(1f))
            if (settings.amapKey.isNotBlank()) {
                Button(onClick = { useMap = !useMap }) {
                    Text(if (useMap) "文字卡" else "地图")
                }
            }
        }

        Box(Modifier.fillMaxSize().padding(top = 8.dp).background(Color(0xFF10131A))) {
            if (useMap && settings.amapKey.isNotBlank()) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx ->
                        WebView(ctx).apply {
                            this.settings.setJavaScriptEnabled(true)
                            this.settings.setDomStorageEnabled(true)
                            webViewClient = WebViewClient()
                            addJavascriptInterface(Bridge(), "lbj")
                            val security = settings.amapSecurity
                            val secJs = if (security.isNotBlank())
                                "window._AMapSecurityConfig={securityJsCode:'$security'};"
                            else ""
                            loadDataWithBaseURL(
                                "https://lbs.amap.com",
                                """
                                <html><head><meta charset="utf-8"/>
                                <meta name="viewport" content="width=device-width,initial-scale=1"/>
                                <style>body{margin:0}#m{width:100%;height:100vh}</style>
                                <script>$secJs</script>
                                <script src="https://webapi.amap.com/maps?v=2.0&key=${settings.amapKey}"></script>
                                </head><body><div id="m"></div>
                                <script>
                                  var map = new AMap.Map('m', {
                                    zoom: ${settings.mapZoom},
                                    mapStyle: '${if (settings.mapNight) "amap://styles/dark" else "amap://styles/normal"}',
                                    center: [114.305469, 30.592835],
                                    viewMode: '2D'
                                  });
                                  var marker = null, trail = [], line = null;
                                  window.updateTrain = function(lat, lng, name, follow) {
                                    var pos = [lng, lat];
                                    if (!marker) {
                                      marker = new AMap.Marker({position: pos, title: name});
                                      map.add(marker);
                                    } else { marker.setPosition(pos); marker.setTitle(name); }
                                    trail.push(pos); if (trail.length > 200) trail.shift();
                                    if (line) map.remove(line);
                                    if (trail.length > 1) {
                                      line = new AMap.Polyline({path: trail, strokeColor: '#DA291C', strokeWeight: 3});
                                      map.add(line);
                                    }
                                    if (follow) map.setCenter(pos);
                                  };
                                </script></body></html>
                                """.trimIndent(),
                                "text/html", "utf-8", null,
                            )
                            jsBridge = this
                        }
                    },
                )
            } else {
                // ---- 降级文本卡：坐标 + 公里标 + 与本机 GPS 距离 ----
                Column(Modifier.align(Alignment.Center).padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    if (latest?.latitude != null) {
                        Text(latest!!.train.ifEmpty { "----" }, fontSize = 30.sp,
                            color = Color(0xFFE8EAED))
                        Text("WGS-84 %.5f, %.5f".format(
                            Locale.US, latest!!.latitude!!, latest!!.longitude ?: 0.0),
                            fontSize = 15.sp, color = Color(0xFF9AA0A6))
                        Text("公里标 ${latest!!.position}  ${latest!!.direction}",
                            fontSize = 14.sp, color = Color(0xFF9AA0A6))
                        if (gpsValid) {
                            val d = haversineKm(
                                gps[0], gps[1], latest!!.latitude!!, latest!!.longitude ?: 0.0)
                            Text("距本机约 %.1f km（GPS）".format(Locale.US, d),
                                fontSize = 16.sp, color = CrRed)
                        } else {
                            Button(onClick = {
                                permLauncher.launch(arrayOf(
                                    Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION))
                            }) { Text("授权定位以计算距离") }
                        }
                    } else {
                        Text("暂无列车坐标", fontSize = 20.sp, color = Color(0xFF9AA0A6))
                    }
                    if (settings.amapKey.isBlank()) {
                        Text("未配置高德 Key（设置页 → 地图），已降级为文字卡",
                            fontSize = 12.sp, color = Color(0xFF666E78),
                            modifier = Modifier.padding(top = 12.dp))
                    }
                }
            }
        }
    }
}

/** JS 桥（预留：页面 ↔ 原生交互） */
private class Bridge {
    @JavascriptInterface
    fun ping(): String = "ok"
}

/** 读系统最后一次已知定位（不主动开启 GPS，零功耗） */
private fun readLastGps(ctx: Context): DoubleArray? = try {
    val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER,
        LocationManager.PASSIVE_PROVIDER)
        .firstNotNullOfOrNull { p ->
            try { lm.getLastKnownLocation(p) } catch (_: SecurityException) { null }
        }
        ?.let { doubleArrayOf(it.latitude, it.longitude) }
} catch (_: Exception) { null }

/** 球面距离（km） */
private fun haversineKm(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
    val r = 6371.0
    val dLat = Math.toRadians(lat2 - lat1)
    val dLng = Math.toRadians(lng2 - lng1)
    val a = sin(dLat / 2) * sin(dLat / 2) +
        cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) *
        sin(dLng / 2) * sin(dLng / 2)
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))
}
