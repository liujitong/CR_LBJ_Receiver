package xyz.mlxkj.crlbj.ui.pages

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.Color as AndroidColor
import android.location.LocationManager
import android.util.Log
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.withPermit
import org.json.JSONArray
import org.json.JSONObject
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.core.TileCache
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.ui.components.FloatPill
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.StatusCapsule
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 地图页（v3.0 重写）。
 *
 * 图源为桌面/安卓共用的 `shared/web/railmap.html`（底图可切换 + 铁路图层）：
 *
 *  · 页面内 `window.LBJ` 是唯一接口：`applyConfig` 一次性下发底图/铁路/夜间/中心，
 *    `update` 批量推列车（**WGS-84 原值**，不做任何坐标转换）；
 *  · 页面通过 `window.LBJHost.onLayers(json)` 回报图层变化（用户在地图里改底图时），
 *    这里落盘到设置，保证「设置页 ↔ 地图内操作」双向一致（同一份 ReceiverSettings）；
 *  · 右上角「跟随」胶囊与页面 `LBJ.locked()` 联动：用户一拖地图就自动取消跟随；
 *  · 「转到自己位置」：复用定位权限流程，取系统最后已知位置后调 `LBJ.centerLatLng`；
 *  · 有坐标才推；没坐标时显示半透明空态卡，不遮成大白块。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapPage(vm: ReceiverViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val events by vm.events.collectAsStateWithLifecycle()
    val running by vm.running.collectAsStateWithLifecycle()
    // v3.2：车次/机车查询结果（解码页自动查询的同一份缓存），带进地图标记与弹窗
    val trainInfos by vm.trainInfos.collectAsStateWithLifecycle()
    val locoInfos by vm.locoInfos.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    val p = pal()
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var cacheAreaJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    /** 原生侧缓存进度（done,total）；页面 #panel 被隐藏，进度改由本页浮层显示 */
    var cacheProgress by remember { mutableStateOf<Pair<Int, Int>?>(null) }

    // 带坐标的最新一条（按车次去重，最多 24 列，地图上不挤）
    // 车次/配属信息一并带进 payload（异步查询回来后自动重推，标记与弹窗即时更新）
    val trains = remember(events, trainInfos, locoInfos) {
        collectTrains(events, trainInfos, locoInfos)
    }
    val newest = trains.firstOrNull()

    var web by remember { mutableStateOf<WebView?>(null) }
    var ready by remember { mutableStateOf(false) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var layers by remember { mutableStateOf<List<LayerOption>>(emptyList()) }
    var sheet by remember { mutableStateOf(false) }
    var gps by remember { mutableStateOf<DoubleArray?>(null) }
    /** 「转到自己位置」的临时提示（无权限/无定位），4s 自动消失 */
    var locMsg by remember { mutableStateOf<String?>(null) }
    /** 已发起定位权限申请、等待回调后居中 */
    var pendingCenter by remember { mutableStateOf(false) }
    /** 底图瓦片连续失败（多半是网络到不了该图源）→ 底部横幅提示换底图 */
    var tileFail by remember { mutableStateOf(false) }
    /**
     * 页面底图是否已与 `settings.mapBase` 一致（= applyConfig 已真正生效）。
     * 页面是 file:// 直接加载的，启动瞬间按自身默认底图（高德）渲染并可能回报
     * onLayers；若直接落盘就会把用户在设置里选的底图冲掉（v3.2.1 修的就是这个）。
     * 所以只有确认一致后才接受页面回报。
     */
    val pageSynced = remember { mutableStateOf(false) }

    // 居中到本机位置（WGS-84）。centerLatLng 契约：居中 + 停止自动跟随 + 页面 toast；
    // 接口未就绪时静默跳过（返回 no-api），原生侧仍把 mapFollow 落盘为 false。
    val centerToGps: (DoubleArray) -> Unit = { g ->
        web?.evaluateJavascript(
            "(function(){if(window.LBJ&&window.LBJ.centerLatLng){window.LBJ.centerLatLng(" +
                "${g[0]},${g[1]});return 'ok'}return 'no-api'})()",
        ) { r -> Log.i(TAG, "centerLatLng: $r") }
        vm.updateViewSettings(vm.settings.value.copy(mapFollow = false))
    }

    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val granted = grants.values.any { it }
        if (granted) gps = readLastGps(ctx)
        if (pendingCenter) {
            pendingCenter = false
            val g = if (granted) gps else null
            when {
                !granted -> locMsg = "未授予定位权限，无法转到自己位置"
                g != null -> centerToGps(g)
                else -> locMsg = "暂无可用定位：请开启系统定位（GPS）后重试"
            }
        }
    }
    LaunchedEffect(Unit) { gps = readLastGps(ctx) }
    LaunchedEffect(cacheProgress) {
        val cp = cacheProgress
        if (cp != null && cp.first >= cp.second) {
            kotlinx.coroutines.delay(3000)
            cacheProgress = null
        }
    }
    LaunchedEffect(locMsg) {
        if (locMsg != null) {
            kotlinx.coroutines.delay(4000)
            locMsg = null
        }
    }

    // ---- 就绪探测：不依赖 onPageFinished（模拟器上偶发不回调），并且**持续**探测。
    //      WebView 因任何原因重载时，ready 会先回落再置真，配置随之自动重下，
    //      这样「弹层交互导致网页重载」这类意外也能自愈。----
    LaunchedEffect(web) {
        val w = web ?: return@LaunchedEffect
        var lastLogged = false
        while (true) {
            w.evaluateJavascript("!!(window.LBJ && window.LBJ.ready)") { r ->
                val isReady = r == "true" || r == "\"true\""
                if (isReady != ready) {
                    ready = isReady
                    if (!isReady) Log.i(TAG, "页面重载中（ready 回落）")
                }
                if (isReady && !lastLogged) {
                    lastLogged = true
                    Log.i(TAG, "页面就绪")
                }
                if (!isReady) lastLogged = false
            }
            kotlinx.coroutines.delay(500)
        }
    }

    // ---- 页面就绪：重置同步态 + 注入移动端 CSS + 取图层清单（配置由下一个 effect 统一下发）----
    LaunchedEffect(ready) {
        if (!ready) {
            // 页面重载/离开：之前的「已同步」不再成立，回报一律先不落盘
            pageSynced.value = false
            return@LaunchedEffect
        }
        val w = web ?: return@LaunchedEffect
        // 页面自带的图层/提示层在手机屏上不合适，统一收进本页的胶囊与面板：
        //  · #panel：右上角图层选择面板（手机屏太小，且会压到状态栏）
        //  · #hint ：瓦片全灭时的整屏提示（文案指向已隐藏的 panel，改由本页横幅提示）
        w.evaluateJavascript(
            "(function(){var css='#panel{display:none!important}#hint{display:none!important}" +
                ".leaflet-top.leaflet-left{top:64px!important}';" +
                "var s=document.createElement('style');s.id='lbj-android-css';" +
                "s.appendChild(document.createTextNode(css));document.head.appendChild(s);" +
                "return 'css-ok';})()",
        ) { r -> Log.i(TAG, "注入移动端 CSS: $r") }
        w.evaluateJavascript("JSON.stringify(window.LBJ.layers())") { json ->
            layers = parseLayers(json)
        }
        Log.i(TAG, "页面就绪，等待下发配置 base=${settings.mapBase} rail=${settings.mapRail}")
    }

    // ---- 首次进入 / 设置页改了地图项 → 全量下发配置（幂等，不会触发回环）----
    // 依赖里带 ready：页面重载后（ready 由 false→true）会重新下发，保证「杀进程重启后
    // 再进地图仍是用户选的底图」。
    LaunchedEffect(
        ready, settings.mapBase, settings.mapRail, settings.mapRailOpacity,
        settings.mapNight, settings.mapTdtKey, settings.mapZoom,
        settings.mapCenterLat, settings.mapCenterLng, settings.mapFollow,
    ) {
        if (!ready) return@LaunchedEffect
        val w = web ?: return@LaunchedEffect
        // 配置刚改，页面还没切过去：先暂停接受图层回报，等 status 确认 base 后再放开
        pageSynced.value = false
        w.evaluateJavascript(applyConfigJs(settings), null)
        Log.i(TAG, "已下发地图配置 base=${settings.mapBase} rail=${settings.mapRail}")
    }

    // ---- 列车坐标变化 → 推给页面（WGS-84 原值，不做任何坐标转换）----
    LaunchedEffect(ready, trains, settings.mapFollow, settings.mapNight) {
        if (!ready) return@LaunchedEffect
        val w = web ?: return@LaunchedEffect
        w.evaluateJavascript(updateJs(trains, settings), null)
    }

    // ---- 状态轮询：跟随锁定 + 瓦片失败（1.5s 一次足够）----
    LaunchedEffect(ready) {
        if (!ready) return@LaunchedEffect
        var polls = 0
        while (true) {
            val w = web ?: break
            w.evaluateJavascript("window.LBJ?JSON.stringify(window.LBJ.status()):'null'") { raw ->
                val st = parseStatus(raw)
                polls++
                if (polls == 1) {
                    Log.i(TAG, "status=" + (st?.let {
                        "base=${it.base} rail=${it.rail} tiles=${it.tilesTotal}/${it.tilesFailed}"
                    } ?: raw?.take(120)))
                }
                if (st != null) {
                    // 页面状态与设置一致（底图 + 实际生效铁路图层）→ applyConfig 已真正生效，
                    // 此后才接受页面图层回报。rail 也要比：偏移坐标系底图下页面会主动关铁路
                    // （effective=off），只看 base 会在「用户把铁路选成不显示」时误判为已同步。
                    val s = vm.settings.value
                    val wantRail = if (st.coord != "wgs") "off" else s.mapRail
                    val synced = st.base == s.mapBase && st.rail == wantRail
                    if (synced && !pageSynced.value) {
                        pageSynced.value = true
                        Log.i(TAG, "页面配置已生效: base=${st.base} rail=${st.rail}（接受图层回报）")
                    } else if (!synced && pageSynced.value) {
                        pageSynced.value = false
                        Log.i(TAG, "页面状态与设置不一致: page base=${st.base} rail=${st.rail} " +
                            "want base=${s.mapBase} rail=$wantRail（暂停接受回报）")
                    }
                    if (st.locked && vm.settings.value.mapFollow) {
                        vm.updateViewSettings(vm.settings.value.copy(mapFollow = false))
                    }
                    // 底图瓦片「真的不可达」才提示换图源。注意：
                    //  · 页面 status() 的 tilesTotal/tilesFailed **只统计底图**，
                    //    铁路图层（ORM 需 Referer）失败不再污染判定；
                    //  · tilesTotal 只统计成功的 tileload，网络全断时 total=0、
                    //    failed 仍在涨，所以不能要求 total>0；
                    //  · 有成功瓦片时要求失败率 ≥95% 才算不可达，避免偶尔几张失败误判。
                    val failed = st.tilesFailed >= 6 &&
                        (st.tilesTotal == 0 || st.tilesFailed >= st.tilesTotal * 19)
                    if (failed != tileFail) {
                        Log.i(TAG, "底图不可达状态变化: $failed (total=${st.tilesTotal} failed=${st.tilesFailed})")
                    }
                    tileFail = failed
                }
            }
            kotlinx.coroutines.delay(1500)
        }
    }

    Box(Modifier.fillMaxSize().background(p.bg)) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = {
                Log.i(TAG, "创建 WebView（factory）")
                buildWebView(ctx) { w ->
                    web = w
                    ready = false
                }.also { w ->
                    w.addJavascriptInterface(
                        HostBridge(
                            onLayersJson = { json ->
                                w.post {
                                    // v3.2.1 关键门禁：页面还没按用户配置切过去时，
                                    // 它回报的是自身默认底图（高德），落盘会冲掉用户设置。
                                    if (pageSynced.value) {
                                        persistLayers(vm, json)
                                    } else {
                                        Log.i(TAG, "忽略配置生效前的图层回报: $json")
                                    }
                                }
                            },
                            onCacheArea = { json ->
                                cacheAreaJob?.cancel()
                                cacheAreaJob = scope.launch(kotlinx.coroutines.Dispatchers.IO) {
                                    runCacheArea(ctx, w, json, vm) { d, t ->
                                        w.post { cacheProgress = d to t }
                                    }
                                }
                            },
                            onCacheStats = {
                                scope.launch(kotlinx.coroutines.Dispatchers.IO) {
                                    pushCacheStats(ctx, w)
                                }
                            },
                        ),
                        "LBJHost",
                    )
                    val client = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView,
                            request: WebResourceRequest,
                        ): Boolean {
                            val url = request.url
                            val s = url.toString()
                            if (s.startsWith("file://")) return false
                            runCatching {
                                ctx.startActivity(Intent(Intent.ACTION_VIEW, url))
                            }
                            return true
                        }

                        override fun onPageFinished(view: WebView, url: String) {
                            ready = true
                            loadError = null
                            Log.i(TAG, "railmap.html 加载完成: $url")
                        }

                        /**
                         * 瓦片原生代拉 + 离线缓存（v3.1）：
                         * 天地图/百度/高德/OSM/ORM 主机先查 DiskLruCache，命中直接返回；
                         * 未命中用 HttpURLConnection 代拉（浏览器 UA；天地图按 tdtReferer
                         * 附加 Referer，百度固定 map.baidu.com），成功落盘并返回；
                         * 非 2xx/失败返回 null 走 WebView 原路。本回调在后台线程。
                         */
                        override fun shouldInterceptRequest(
                            view: WebView,
                            request: WebResourceRequest,
                        ): android.webkit.WebResourceResponse? {
                            val url = request.url
                            if (url.scheme != "http" && url.scheme != "https") return null
                            val host = url.host ?: return null
                            if (!TileCache.isTileHost(host)) return null
                            val u = url.toString()
                            val cache = TileCache.get(ctx)
                            cache.get(u)?.let { bytes ->
                                return android.webkit.WebResourceResponse(
                                    TileCache.sniffMime(bytes), null,
                                    java.io.ByteArrayInputStream(bytes),
                                )
                            }
                            val f = TileCache.fetch(u, vm.settings.value.tdtReferer) ?: return null
                            cache.put(u, f.bytes)
                            return android.webkit.WebResourceResponse(
                                f.mime, null, java.io.ByteArrayInputStream(f.bytes),
                            )
                        }

                        override fun onReceivedError(
                            view: WebView,
                            request: WebResourceRequest,
                            error: android.webkit.WebResourceError,
                        ) {
                            if (request.isForMainFrame) {
                                loadError = error.description?.toString() ?: "未知错误"
                                Log.w(TAG, "地图页加载失败: $loadError")
                            }
                        }
                    }
                    w.webViewClient = client
                    w.webChromeClient = object : WebChromeClient() {
                        override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                            Log.i(TAG, "console: ${m.message()} @${m.lineNumber()}")
                            return true
                        }
                    }
                    w.setBackgroundColor(p.bg.toArgbInt())
                    w.loadUrl(MAP_URL)
                }
            },
            update = { /* 页面内容由 evaluateJavascript 驱动，无需重建 View */ },
        )

        // ---- 浮层统一避让状态栏/刘海/挖孔：WebView 仍全屏铺满，只有浮层缩进来 ----
        Box(
            Modifier
                .fillMaxSize()
                .windowInsetsPadding(
                    WindowInsets.safeDrawing.only(
                        WindowInsetsSides.Top + WindowInsetsSides.Horizontal)
                )
        ) {
        // ---- 左上角状态胶囊（地图页无重顶栏，胶囊浮在图上）----
        Box(
            Modifier
                .align(Alignment.TopStart)
                .padding(top = 14.dp, start = 12.dp)
        ) {
            StatusCapsule(
                sourceLabel = sourceLabel(settings),
                running = running,
                lastEventTs = events.firstOrNull()?.timestamp,
                onToggle = { vm.toggleStartStop() },
            )
        }

        // ---- 右上角浮动胶囊 ----
        Column(
            Modifier
                .align(Alignment.TopEnd)
                .padding(top = 76.dp, end = 12.dp),
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FloatPill(
                text = if (settings.mapFollow) "跟随中" else "跟随",
                active = settings.mapFollow,
                onClick = {
                    val next = !settings.mapFollow
                    vm.updateViewSettings(settings.copy(mapFollow = next))
                    web?.evaluateJavascript("window.LBJ&&window.LBJ.setFollow($next)", null)
                },
            )
            FloatPill(
                text = "图层",
                active = false,
                onClick = { sheet = true },
            )
            FloatPill(
                text = "回中心",
                active = false,
                onClick = {
                    web?.evaluateJavascript(
                        "window.LBJ&&window.LBJ.centerTo('${settings.mapCenterName}')", null)
                    vm.updateViewSettings(settings.copy(mapFollow = false))
                },
            )
            FloatPill(
                text = "转到自己位置",
                active = false,
                onClick = {
                    val g = gps ?: readLastGps(ctx).also { gps = it }
                    when {
                        g != null -> centerToGps(g)
                        hasLocPermission(ctx) ->
                            locMsg = "暂无可用定位：请开启系统定位（GPS）后重试"
                        else -> {
                            pendingCenter = true
                            permLauncher.launch(
                                arrayOf(
                                    Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION,
                                )
                            )
                        }
                    }
                },
            )
            FloatPill(
                text = "缓存本区域",
                active = cacheProgress != null,
                onClick = {
                    // 页面「缓存本区域」按钮在被隐藏的 #panel 里，用 JS 代点触发同一逻辑
                    web?.evaluateJavascript(
                        "(function(){var b=document.getElementById('btnCache');" +
                            "if(b){b.click();return 'ok'}return 'no-btn'})()",
                    ) { r -> Log.i(TAG, "cacheArea: $r") }
                },
            )
        }

        // ---- 空态 / 载入失败（半透明卡片，居中；v3.2.1 统一弱化：12sp/11sp + 三级灰）----
        if (trains.isEmpty() || loadError != null) {
            Column(
                Modifier
                    .align(Alignment.Center)
                    .padding(horizontal = 32.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(p.surface.copy(alpha = 0.90f))
                    .border(1.dp, p.border, RoundedCornerShape(14.dp))
                    .padding(horizontal = 18.dp, vertical = 13.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                if (loadError != null) {
                    Text("地图页加载失败", color = p.err, fontSize = 12.sp,
                        fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text(loadError!!, color = p.textTertiary, fontSize = 11.sp)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "重试",
                        color = p.accent,
                        fontSize = 12.sp,
                        modifier = Modifier.clickable {
                            loadError = null
                            web?.loadUrl(MAP_URL)
                        },
                    )
                } else {
                    Text("暂无列车坐标", color = p.textTertiary, fontSize = 12.sp,
                        fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        if (running) "已开始接收，等待含经纬度的长报文"
                        else "点状态胶囊「开始接收」，或到解码页一键开始",
                        color = p.textTertiary, fontSize = 11.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
            }
        }

        // ---- 底部浮层：瓦片失败横幅 + 最近一列车信息（同一竖列，互不遮挡）----
        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .padding(start = 12.dp, end = 12.dp, bottom = Dim.dockSpace + 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            cacheProgress?.let { (d, t) ->
                Text(
                    if (d >= t) "瓦片缓存完成：$t 张" else "缓存瓦片 $d/$t…",
                    color = if (d >= t) p.ok else p.accent, fontSize = 11.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(p.surface.copy(alpha = 0.94f))
                        .border(1.dp, p.border, RoundedCornerShape(10.dp))
                        .padding(horizontal = 12.dp, vertical = 9.dp),
                )
            }
            locMsg?.let { msg ->
                Text(
                    msg,
                    color = p.warn, fontSize = 11.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(10.dp))
                        .background(p.surface.copy(alpha = 0.94f))
                        .border(1.dp, p.warn.copy(alpha = 0.5f), RoundedCornerShape(10.dp))
                        .padding(horizontal = 12.dp, vertical = 9.dp),
                )
            }
            if (tileFail) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(p.surface.copy(alpha = 0.94f))
                        .border(1.dp, p.warn.copy(alpha = 0.5f), RoundedCornerShape(10.dp))
                        .clickable { sheet = true }
                        .padding(horizontal = 12.dp, vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "底图瓦片加载失败：当前网络可能访问不到该图源",
                        color = p.warn, fontSize = 11.sp, modifier = Modifier.weight(1f),
                    )
                    Text("换底图 ›", color = p.accent, fontSize = 12.sp,
                        fontWeight = FontWeight.Medium)
                }
            }
            newest?.let { t ->
                Row(
                    Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .background(p.surface.copy(alpha = 0.94f))
                        .border(1.dp, p.border, RoundedCornerShape(12.dp))
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        t.train.ifEmpty { "----" },
                        color = p.text, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(t.direction, color = p.dirColor(t.direction), fontSize = 12.sp)
                    Spacer(Modifier.width(10.dp))
                    Text(
                        "%s km/h  K%s".format(Locale.US, t.speed.ifEmpty { "---" },
                            t.position.ifEmpty { "---.-" }),
                        color = p.textSecondary, fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                    Spacer(Modifier.width(10.dp))
                    val g = gps
                    if (g != null) {
                        val dkm = haversineKm(g[0], g[1], t.lat, t.lon)
                        Text(
                            "距本机 %.1f km".format(Locale.US, dkm),
                            color = p.accent, fontSize = 12.sp,
                        )
                    } else {
                        Text(
                            "定位算距离",
                            color = p.textTertiary, fontSize = 12.sp,
                            modifier = Modifier.clickable {
                                permLauncher.launch(
                                    arrayOf(
                                        Manifest.permission.ACCESS_FINE_LOCATION,
                                        Manifest.permission.ACCESS_COARSE_LOCATION,
                                    )
                                )
                            },
                        )
                    }
                }
            }
        }
        } // 浮层避让容器（WebView 铺满，不参与 insets）
    }

    // 图层/夜间面板必须**无条件调用**：如果直接写 `if (sheet) ModalBottomSheet(…)`，
    // 兄弟节点数量变化会让 Compose 把上面的 AndroidView 当成新节点重建，
    // WebView 就会整页重载（轨迹一起丢）。这里把 if 收进独立 composable。
    MapLayerSheetHost(
        show = sheet,
        onDismiss = { sheet = false },
        settings = settings,
        layers = layers,
        onApply = { s ->
            vm.updateViewSettings(s)
            web?.evaluateJavascript(applyConfigJs(s), null)
        },
    )

    // 页面销毁时释放 WebView（否则 WebView 线程与 JS 定时器会一直存活）
    DisposableEffect(Unit) {
        Log.i(TAG, "MapPage 进入组合")
        onDispose {
            Log.i(TAG, "MapPage 离开组合 → 销毁 WebView")
            runCatching {
                web?.let {
                    it.removeJavascriptInterface("LBJHost")
                    it.stopLoading()
                    (it.parent as? ViewGroup)?.removeView(it)
                    it.destroy()
                }
            }
            web = null
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MapLayerSheetHost(
    show: Boolean,
    onDismiss: () -> Unit,
    settings: ReceiverSettings,
    layers: List<LayerOption>,
    onApply: (ReceiverSettings) -> Unit,
) {
    if (!show) return
    val p = pal()
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = p.surface,
    ) {
        LayerSheet(settings = settings, layers = layers, onApply = onApply)
    }
}

// ----------------------------------------------------------------- 图层选项

data class LayerOption(val id: String, val name: String, val coord: String, val kind: String)

/** `LBJ.status()` 里本页关心的字段 */
private data class MapStatus(
    val locked: Boolean,
    val tilesTotal: Int,
    val tilesFailed: Int,
    val coord: String,
    val base: String,
    val rail: String,
)

/**
 * 解析 `evaluateJavascript("JSON.stringify(LBJ.status())")` 的返回值。
 *
 * 注意 WebView 的返回值是**再包一层 JSON 字符串**（形如 `"{\"base\":...}"`），
 * 所以先当 JSON 值解，取出字符串再解一次。
 */
private fun parseStatus(raw: String?): MapStatus? {
    if (raw.isNullOrBlank() || raw == "null" || raw == "\"null\"") return null
    return runCatching {
        val inner = if (raw.startsWith("\"")) JSONObject("{\"v\":$raw}").getString("v") else raw
        val o = JSONObject(inner)
        MapStatus(
            locked = o.optBoolean("locked"),
            tilesTotal = o.optInt("tilesTotal"),
            tilesFailed = o.optInt("tilesFailed"),
            coord = o.optString("coord"),
            base = o.optString("base"),
            rail = o.optString("rail"),
        )
    }.getOrNull()
}

/** 页面未就绪时的兜底清单（id/名称与 railmap.html 的 BASE_SOURCES / RAIL_SOURCES 逐字一致） */
private val FALLBACK_LAYERS = listOf(
    LayerOption("amap", "高德 街道（免 Key）", "gcj", "base"),
    LayerOption("amap_img", "高德 卫星（免 Key）", "gcj", "base"),
    LayerOption("baidu", "百度 街道（免 Key）", "bd", "base"),
    LayerOption("baidu_sat", "百度 卫星（免 Key）", "bd", "base"),
    LayerOption("osm", "OSM 标准", "wgs", "base"),
    LayerOption("tdt_vec", "天地图 矢量（CGCS2000）", "wgs", "base"),
    LayerOption("tdt_img", "天地图 影像（CGCS2000）", "wgs", "base"),
    LayerOption("off", "不显示", "wgs", "rail"),
    LayerOption("orm_standard", "ORM 标准（线路+信号）", "wgs", "rail"),
    LayerOption("orm_maxspeed", "ORM 限速", "wgs", "rail"),
    LayerOption("orm_signals", "ORM 信号", "wgs", "rail"),
    LayerOption("orm_electrified", "ORM 电气化", "wgs", "rail"),
    LayerOption("orm_gauge", "ORM 轨距", "wgs", "rail"),
    LayerOption("rail_local", "本地铁路线（GeoJSON）", "wgs", "rail"),
)

private fun parseLayers(json: String?): List<LayerOption> {
    if (json.isNullOrBlank() || json == "null") return FALLBACK_LAYERS
    return try {
        // evaluateJavascript 返回的是「JSON 字符串的 JSON 字面量」：先还原一次
        val arr = JSONArray(JSONObject("{\"v\":$json}").getString("v"))
        val out = ArrayList<LayerOption>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            out.add(
                LayerOption(
                    id = o.optString("id"),
                    name = o.optString("name"),
                    coord = o.optString("coord"),
                    kind = o.optString("kind"),
                )
            )
        }
        out.ifEmpty { FALLBACK_LAYERS }
    } catch (t: Throwable) {
        FALLBACK_LAYERS
    }
}

// ----------------------------------------------------------------- 图层面板

@Composable
private fun LayerSheet(
    settings: ReceiverSettings,
    layers: List<LayerOption>,
    onApply: (ReceiverSettings) -> Unit,
) {
    val p = pal()
    var base by remember(settings.mapBase) { mutableStateOf(settings.mapBase) }
    var rail by remember(settings.mapRail) { mutableStateOf(settings.mapRail) }
    var opacity by remember(settings.mapRailOpacity) {
        mutableStateOf(settings.mapRailOpacity.toFloat())
    }
    var night by remember(settings.mapNight) { mutableStateOf(settings.mapNight) }

    val bases = layers.filter { it.kind == "base" }.ifEmpty { FALLBACK_LAYERS.filter { it.kind == "base" } }
    val rails = layers.filter { it.kind == "rail" }.ifEmpty { FALLBACK_LAYERS.filter { it.kind == "rail" } }

    Column(
        Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp)
            .padding(bottom = 28.dp),
    ) {
        Text("地图图层", color = p.text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(4.dp))
        Text(
            "铁路图源 OpenRailwayMap（WGS-84）；高德/百度底图下页面自动纠偏标记并隐藏铁路图层，" +
                "天地图/OSM 与铁路零偏移叠加。",
            color = p.textTertiary, fontSize = 11.sp,
        )
        Spacer(Modifier.height(12.dp))

        SectionCard("底图") {
            bases.forEach { item ->
                OptionRow(
                    title = item.name,
                    selected = item.id == base,
                    onClick = {
                        base = item.id
                        onApply(settings.copy(mapBase = item.id))
                    },
                )
            }
        }
        Spacer(Modifier.height(Dim.gap))

        SectionCard("铁路图层") {
            rails.forEach { item ->
                OptionRow(
                    title = item.name,
                    selected = item.id == rail,
                    onClick = {
                        rail = item.id
                        onApply(settings.copy(mapRail = item.id))
                    },
                )
            }
            Spacer(Modifier.height(6.dp))
            Text("不透明度 %.0f%%".format(Locale.US, opacity * 100), color = p.textSecondary,
                fontSize = 12.sp)
            Slider(
                value = opacity,
                onValueChange = { opacity = it },
                onValueChangeFinished = { onApply(settings.copy(mapRailOpacity = opacity.toDouble())) },
                valueRange = 0.2f..1f,
            )
        }
        Spacer(Modifier.height(Dim.gap))

        SectionCard("显示") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("夜间底图", color = p.text, fontSize = 14.sp)
                    Text("深色主题下给瓦片加反相，标记与轨迹不受影响",
                        color = p.textTertiary, fontSize = 11.sp)
                }
                Switch(checked = night, onCheckedChange = {
                    night = it
                    onApply(settings.copy(mapNight = it))
                })
            }
        }
    }
}

@Composable
private fun OptionRow(title: String, selected: Boolean, onClick: () -> Unit) {
    val p = pal()
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 9.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, color = if (selected) p.accent else p.text, fontSize = 14.sp,
            modifier = Modifier.weight(1f))
        if (selected) {
            Text("✓", color = p.accent, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        }
    }
}

// ----------------------------------------------------------------- WebView 构建

private const val TAG = "RailMap"
private const val MAP_URL = "file:///android_asset/web/railmap.html"

@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
private fun buildWebView(ctx: Context, onCreated: (WebView) -> Unit): WebView =
    WebView(ctx).apply {
        layoutParams = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.allowContentAccess = false
        settings.cacheMode = android.webkit.WebSettings.LOAD_DEFAULT
        @Suppress("DEPRECATION")
        settings.allowFileAccessFromFileURLs = true
        isVerticalScrollBarEnabled = false
        isHorizontalScrollBarEnabled = false
        setBackgroundColor(AndroidColor.TRANSPARENT)
        onCreated(this)
    }

/** JS 桥：页面回报图层变化 / 请求缓存瓦片 / 查询缓存统计（JS 线程回调，调用方切线程） */
private class HostBridge(
    private val onLayersJson: (String) -> Unit,
    private val onCacheArea: (String) -> Unit,
    private val onCacheStats: () -> Unit,
) {
    @JavascriptInterface
    fun onLayers(json: String) = onLayersJson(json)

    /** 页面「缓存当前视野」：urlsJson 为瓦片 URL 的 JSON 数组 */
    @JavascriptInterface
    fun cacheArea(urlsJson: String) = onCacheArea(urlsJson)

    /** 页面查询缓存占用：宿主经 LBJ.cacheStats(json) 回传 {count,bytes} */
    @JavascriptInterface
    fun cacheStats() = onCacheStats()

    @JavascriptInterface
    fun ping(): String = "ok"
}

/**
 * 缓存一批瓦片：限并发 4 下载落盘（已缓存的跳过），
 * 进度经 `LBJ.onCacheProgress(done,total)` 回传（每 8 张或完成时，避免刷屏）。
 */
private suspend fun runCacheArea(
    ctx: Context,
    w: WebView,
    urlsJson: String,
    vm: ReceiverViewModel,
    onProgress: (Int, Int) -> Unit,
) {
    val arr = runCatching { JSONArray(urlsJson) }.getOrNull() ?: return
    val total = arr.length()
    if (total == 0) return
    val cache = TileCache.get(ctx)
    val referer = vm.settings.value.tdtReferer
    val sem = kotlinx.coroutines.sync.Semaphore(4)
    val done = java.util.concurrent.atomic.AtomicInteger(0)
    kotlinx.coroutines.coroutineScope {
        for (i in 0 until total) {
            val u = arr.optString(i)
            launch(kotlinx.coroutines.Dispatchers.IO) {
                if (u.isNotEmpty()) {
                    sem.withPermit {
                        if (cache.get(u) == null) {
                            TileCache.fetch(u, referer)?.let { cache.put(u, it.bytes) }
                        }
                    }
                }
                val d = done.incrementAndGet()
                if (d % 8 == 0 || d == total) {
                    onProgress(d, total)
                    w.post {
                        w.evaluateJavascript(
                            "window.LBJ&&window.LBJ.onCacheProgress($d,$total)", null)
                    }
                }
            }
        }
    }
    pushCacheStats(ctx, w)
}

/** 缓存统计回传页面：LBJ.cacheStats({count,bytes}) */
private fun pushCacheStats(ctx: Context, w: WebView) {
    val (count, bytes) = TileCache.get(ctx).stats()
    w.post {
        w.evaluateJavascript(
            "window.LBJ&&window.LBJ.cacheStats({\"count\":$count,\"bytes\":$bytes})", null)
    }
}

/** 数据源显示名（胶囊文案） */
private fun sourceLabel(s: ReceiverSettings): String = when (s.sourceType) {
    "usb" -> "USB 直连"
    "rtl_tcp" -> "rtl_tcp"
    "owrx" -> "OWRX"
    else -> s.sourceType
}

/** 底图坐标系（来自页面图源清单）：偏移坐标系（gcj/bd）下页面会自动关闭 WGS-84 铁路图层 */
private fun coordOfBase(baseId: String): String =
    FALLBACK_LAYERS.firstOrNull { it.kind == "base" && it.id == baseId }?.coord ?: "wgs"

/**
 * 把页面回报的图层变化落盘（底图/铁路/透明度/夜间），不重建 DSP 链路。
 *
 * v3.2.1 防回退两道门：
 *  ① 调用方（HostBridge）已用 pageSynced 过滤「配置生效前」的默认值回声；
 *  ② 这里再做语义保护：偏移坐标系底图（高德/百度）下页面会**自动关闭** WGS-84
 *     铁路图层并回报 rail=off，那不是用户的选择，不能写进设置（否则换回 OSM/
 *     天地图后铁路图层永远恢复不了）。只有用户确实选 off 时才接受 off。
 */
private fun persistLayers(vm: ReceiverViewModel, json: String) {
    try {
        val o = JSONObject(json)
        val s = vm.settings.value
        val reportedBase = o.optString("base", s.mapBase).ifEmpty { s.mapBase }
        val reportedRail = o.optString("rail", s.mapRail).ifEmpty { s.mapRail }
        val railAutoOff = reportedRail == "off" && s.mapRail != "off" &&
            coordOfBase(reportedBase) != "wgs"
        val next = s.copy(
            mapBase = reportedBase,
            mapRail = if (railAutoOff) s.mapRail else reportedRail,
            mapRailOpacity = if (o.has("railOpacity")) o.optDouble("railOpacity", s.mapRailOpacity)
            else s.mapRailOpacity,
            mapNight = if (o.has("night")) o.optBoolean("night", s.mapNight) else s.mapNight,
        )
        if (next != s) {
            Log.i(TAG, "图层回报落盘: base=${next.mapBase} rail=${next.mapRail} " +
                "（page base=$reportedBase rail=$reportedRail）")
            vm.updateViewSettings(next)
        }
    } catch (t: Throwable) {
        Log.w(TAG, "图层回报解析失败: ${t.message}")
    }
}

// ----------------------------------------------------------------- JS 生成

/** 与应用内设置的 `toParamsJson` 不同：这里只下发地图页关心的字段 */
private fun applyConfigJs(s: ReceiverSettings): String {
    val cfg = JSONObject().apply {
        put("base", s.mapBase)
        put("rail", s.mapRail)
        put("railOpacity", s.mapRailOpacity)
        put("night", s.mapNight)
        put("follow", s.mapFollow)
        put("zoom", s.mapZoom)
        put("tdtKey", s.mapTdtKey)
        put("center", JSONObject().apply {
            put("lat", s.mapCenterLat)
            put("lng", s.mapCenterLng)
        })
    }
    return "window.LBJ&&window.LBJ.applyConfig($cfg)"
}

private fun updateJs(trains: List<TrainPoint>, s: ReceiverSettings): String {
    val arr = JSONArray()
    trains.forEach { t ->
        arr.put(JSONObject().apply {
            put("id", t.id)
            put("train", t.train)
            put("lat", t.lat)
            put("lon", t.lon)
            put("speed", t.speed)
            put("km", t.position)
            put("position", t.position)
            put("route", t.route)
            put("loco", t.loco)
            put("direction", t.direction)
            put("category", t.category)
            put("time", t.time)
            put("ts", t.ts)
            // v3.2：车次等级/担当局/担当段/配属段/车型 + 机车配属/制造厂
            val info = JSONObject()
            t.info.forEach { (k, v) -> if (v.isNotBlank()) info.put(k, v) }
            if (info.length() > 0) put("info", info)
        })
    }
    val payload = JSONObject().apply {
        put("trains", arr)
        put("follow", s.mapFollow)
        put("night", s.mapNight)
        put("showTrail", true)
    }
    return "window.LBJ&&window.LBJ.update($payload)"
}

// ----------------------------------------------------------------- 数据整形

/** 地图像素：一列车一个点（同一车次只留最新一条） */
data class TrainPoint(
    val id: String,
    val train: String,
    val lat: Double,
    val lon: Double,
    val speed: String,
    val position: String,
    val route: String,
    val loco: String,
    val direction: String,
    val category: String,
    val time: String,
    val ts: Double,
    /** 车次/机车查询信息（grade/bureau/section/owner/model/locoDepot/locoMaker…） */
    val info: Map<String, String> = emptyMap(),
)

/**
 * 车次/机车信息 → 页面 info 字段（与 shared/web/railmap.html 的 `infoRows` 契约一致）。
 *
 * 车次：TrainInfoClient.TrainInfo（category=等级、bureau=担当局、runner=担当段、
 * carOwner=配属段、car=车型）；机车：LocoRoster.Lookup（depot=配属单位、maker=制造厂）。
 * 查询失败/未命中时返回空 map，页面只少几行信息，不影响标记。
 */
internal fun trainInfoMap(
    trainInfo: TrainInfoClient.TrainInfo?,
    locoInfo: LocoRoster.Lookup?,
): Map<String, String> {
    val out = LinkedHashMap<String, String>()
    trainInfo?.let { ti ->
        if (!ti.ok) return@let
        fun pick(src: String, dst: String) {
            if (src.isNotBlank()) out[dst] = src.trim()
        }
        pick(ti.category, "grade")
        pick(ti.bureau, "bureau")
        pick(ti.runner, "section")
        pick(ti.carOwner, "owner")
        pick(ti.car, "model")
        pick(ti.start, "from")
        pick(ti.end, "to")
    }
    locoInfo?.let { li ->
        if (!li.ok) return@let
        if (li.depot.isNotBlank()) out["locoDepot"] = li.depot.trim()
        if (li.maker.isNotBlank()) out["locoMaker"] = li.maker.trim()
        if (li.model.isNotBlank()) out["locoModel"] = li.model.trim()
    }
    return out
}

private fun collectTrains(
    events: List<DecodeEvent>,
    trainInfos: Map<String, TrainInfoClient.TrainInfo> = emptyMap(),
    locoInfos: Map<String, LocoRoster.Lookup> = emptyMap(),
): List<TrainPoint> {
    val seen = HashSet<String>()
    val out = ArrayList<TrainPoint>(24)
    for (e in events) {
        val lat = e.latitude ?: continue
        val lon = e.longitude ?: continue
        // 地图 id 与页面一致：优先 baseTrain（同车次换端不新增标记）
        val id = e.baseTrain.ifEmpty { e.train }.ifEmpty { e.uid }
        if (id.isEmpty() || !seen.add(id)) continue
        val ti = trainInfos[TrainInfoClient.normalizeTrain(e.train)]
        val li = locoInfos[ReceiverViewModel.locoKey(e.loco, e.locoCode)]
        out.add(
            TrainPoint(
                id = id,
                train = e.train,
                lat = lat,
                lon = lon,
                speed = e.speed,
                position = e.position,
                route = e.route,
                loco = e.loco,
                direction = e.direction,
                category = e.category,
                time = e.timeStr,
                ts = e.timestamp,
                info = trainInfoMap(ti, li),
            )
        )
        if (out.size >= 24) break
    }
    return out
}

// ----------------------------------------------------------------- 定位工具

/** 是否已有任一档定位权限 */
private fun hasLocPermission(ctx: Context): Boolean =
    androidx.core.content.ContextCompat.checkSelfPermission(
        ctx, Manifest.permission.ACCESS_FINE_LOCATION,
    ) == android.content.pm.PackageManager.PERMISSION_GRANTED ||
    androidx.core.content.ContextCompat.checkSelfPermission(
        ctx, Manifest.permission.ACCESS_COARSE_LOCATION,
    ) == android.content.pm.PackageManager.PERMISSION_GRANTED

/** 读系统最后一次已知定位（不主动开启 GPS，零功耗） */
private fun readLastGps(ctx: Context): DoubleArray? = try {
    val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    listOf(
        LocationManager.GPS_PROVIDER,
        LocationManager.NETWORK_PROVIDER,
        LocationManager.PASSIVE_PROVIDER,
    ).firstNotNullOfOrNull { provider ->
        try { lm.getLastKnownLocation(provider) } catch (_: SecurityException) { null }
    }?.let { doubleArrayOf(it.latitude, it.longitude) }
} catch (_: Exception) {
    null
}

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

/** Compose Color → Android int（WebView 背景，避免加载瞬间白闪） */
private fun Color.toArgbInt(): Int = AndroidColor.argb(
    (alpha * 255).toInt(), (red * 255).toInt(), (green * 255).toInt(), (blue * 255).toInt())
