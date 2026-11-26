package xyz.mlxkj.crlbj.ui.pages

import androidx.compose.foundation.Canvas
import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.graphics.FilterQuality
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.TrainInfoClient
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.engine.StatusFrame
import xyz.mlxkj.crlbj.engine.StatusFramePoller
import xyz.mlxkj.crlbj.ui.components.Chip
import xyz.mlxkj.crlbj.ui.components.Divider
import xyz.mlxkj.crlbj.ui.components.EmptyState
import xyz.mlxkj.crlbj.ui.components.InfoRow
import xyz.mlxkj.crlbj.ui.components.PageHeader
import xyz.mlxkj.crlbj.ui.components.SectionCard
import xyz.mlxkj.crlbj.ui.components.StatusCapsule
import xyz.mlxkj.crlbj.ui.components.Tone
import xyz.mlxkj.crlbj.ui.theme.Dim
import xyz.mlxkj.crlbj.ui.theme.pal
import xyz.mlxkj.crlbj.vm.ReceiverViewModel
import java.util.Locale
import kotlin.math.ln
import kotlinx.coroutines.withContext
import androidx.compose.runtime.produceState

/**
 * 解码页：一键开始 + 信号强度（真实 RSSI 历史 + 门限线）+ 当前解码大卡 + 最近列表。
 *
 * v3.0 视觉：状态胶囊 / 分组卡片 / 方向方块 / 等宽数字；点卡片看详情（底部弹层）。
 * 新解码自动后台查询车次/配属并内联展示；点「车次」「机车」跳设置页查询分组并预填。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DecodePage(
    vm: ReceiverViewModel,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val running by vm.running.collectAsStateWithLifecycle()
    val logs by vm.logs.collectAsStateWithLifecycle()
    val status by vm.status.collectAsStateWithLifecycle()
    val events by vm.events.collectAsStateWithLifecycle()
    val settings by vm.settings.collectAsStateWithLifecycle()
    val trainInfos by vm.trainInfos.collectAsStateWithLifecycle()
    val locoInfos by vm.locoInfos.collectAsStateWithLifecycle()
    val p = pal()

    // 信号历史环形缓冲（轮询帧驱动，最多 240 点 ≈ 36s）
    // 用不可变快照驱动重组：ArrayDeque 本身不是 snapshot 状态，改它不会触发重绘。
    val rssi = remember { ArrayDeque<Float>(240) }
    var rssiSnapshot by remember { mutableStateOf(FloatArray(0)) }
    // 频谱瀑布数据：每帧 32 个 bin 存一行（最多 80 行 ≈ 12s），弹层关掉时只留内存不渲染
    val spectrumRows = remember { ArrayDeque<FloatArray>(240) }
    var spectrumSnapshot by remember { mutableStateOf<List<FloatArray>>(emptyList()) }
    LaunchedEffect(Unit) {
        var lastSeq = -1
        while (true) {
            val f = vm.status.value
            if (f != null && f.seq != lastSeq) {
                lastSeq = f.seq
                rssi.addLast(f.rssiDb)
                while (rssi.size > 240) rssi.removeFirst()
                rssiSnapshot = rssi.toFloatArray()
                if (f.spectrum.isNotEmpty()) {
                    spectrumRows.addLast(f.spectrum.copyOf())
                    while (spectrumRows.size > 240) spectrumRows.removeFirst()
                    spectrumSnapshot = spectrumRows.toList()
                }
            }
            kotlinx.coroutines.delay(150)
        }
    }
    /** 信号瀑布弹层开关：关掉后不占位（页面里不再有常驻图形） */
    var signalSheet by remember { mutableStateOf(false) }

    var detail by remember { mutableStateOf<DecodeEvent?>(null) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val latest = events.firstOrNull()

    Column(Modifier.fillMaxSize().padding(horizontal = Dim.pagePad)) {
        PageHeader(
            title = "解码",
            subtitle = latest?.let { it.category } ?: "等待第一条报文",
            trailing = {
                StatusCapsule(
                    sourceLabel = sourceLabelOf(settings.sourceType),
                    running = running,
                    lastEventTs = latest?.timestamp,
                    onToggle = { vm.toggleStartStop() },
                    // v3.2.1：点胶囊打开「信号瀑布」小弹层（替代原先常驻的频谱图）
                    onOpen = { signalSheet = true },
                )
            },
        )

        // ---- 一键开始 / 停止 ----
        Button(
            onClick = { vm.toggleStartStop() },
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(50),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (running) p.surfaceAlt else p.accent,
                contentColor = if (running) p.text else p.onAccent,
            ),
        ) {
            Text(
                if (running) "■  停止接收" else "▶  一键开始",
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }

        Spacer(Modifier.height(Dim.gap))

        // ---- 信号摘要条（v3.2.1：不再常驻画图；点它或点顶部胶囊看「信号瀑布」）----
        SignalStrip(
            status = status,
            onClick = { signalSheet = true },
        )

        Spacer(Modifier.height(Dim.gap))

        // ---- 当前解码 ----
        Box(Modifier.weight(1f)) {
            if (latest == null) {
                EmptyState(
                    title = if (running) "等待信号…" else "未开始接收",
                    hint = if (running)
                        "收到报文后这里显示 车次 / 方向 / 速度 / 公里标 / 线路 / 机车"
                    else
                        "点上方「一键开始」，或用状态胶囊切换数据源",
                )
            } else {
                CurrentCard(
                    ev = latest,
                    trainInfo = trainInfos[TrainInfoClient.normalizeTrain(latest.train)],
                    locoInfo = locoInfos[ReceiverViewModel.locoKey(latest.loco, latest.locoCode)],
                    onDetail = { detail = latest },
                    onQueryTrain = onQueryTrain,
                    onQueryLoco = onQueryLoco,
                )
            }
        }

        // ---- 最近解码 ----
        SectionCard(title = "最近解码", modifier = Modifier.padding(top = Dim.gap)) {
            if (events.size <= 1) {
                Text(
                    logs.takeLast(3).joinToString("\n").ifEmpty { "—" },
                    color = p.textTertiary,
                    fontSize = 11.sp,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                )
            } else {
                LazyColumn(Modifier.fillMaxWidth().height(150.dp)) {
                    items(events.drop(1).take(30), key = { it.uid + it.timestamp }) { ev ->
                        RecentRow(
                            ev = ev,
                            onClick = { detail = ev },
                            onQueryLoco = onQueryLoco,
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(Dim.dockSpace))
    }

    detail?.let { ev ->
        ModalBottomSheet(
            onDismissRequest = { detail = null },
            sheetState = sheetState,
            containerColor = p.surface,
        ) {
            DecodeDetailSheet(
                ev = ev,
                onQueryTrain = { onQueryTrain(it); detail = null },
                onQueryLoco = { m, n -> onQueryLoco(m, n); detail = null },
            )
        }
    }

    // ---- 信号瀑布小弹层（尺寸小、不挡主要内容；关掉即恢复原布局）----
    if (signalSheet) {
        SignalWaterfallSheet(
            rssi = rssiSnapshot,
            spectrum = spectrumSnapshot,
            status = status,
            running = running,
            thresholdDb = settings.rssiThresholdDb,
            sourceLabel = sourceLabelOf(settings.sourceType),
            onToggle = { vm.toggleStartStop() },
            onDismiss = { signalSheet = false },
        )
    }
}

/**
 * 信号摘要条：一行显示 RSSI + 门控 + 入口提示（替代 v3.0 的常驻频谱画布）。
 * 点整条或点顶部状态胶囊都会打开 [SignalWaterfallSheet]。
 */
@Composable
private fun SignalStrip(
    status: StatusFrame?,
    onClick: () -> Unit,
) {
    val p = pal()
    val f = status
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(p.surfaceAlt.copy(alpha = 0.55f))
            .border(1.dp, p.border, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("信号", color = p.textTertiary, fontSize = 11.sp)
        Spacer(Modifier.width(8.dp))
        Text(
            f?.let { "%.1f dB".format(Locale.US, it.rssiDb) } ?: "— dB",
            color = p.textSecondary, fontSize = 14.sp,
            fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.width(8.dp))
        f?.let {
            val tone = when {
                it.gateState >= 2 -> Tone.Ok
                it.gateState == 1 -> Tone.Warn
                else -> Tone.Neutral
            }
            Chip(gateLabel(it.gateState), tone)
        }
        Spacer(Modifier.weight(1f))
        Text(
            "瀑布 ›", color = p.accent, fontSize = 11.sp, fontWeight = FontWeight.Medium,
        )
    }
}

/**
 * 信号瀑布弹层（ModalBottomSheet，高度约 320dp，只挡下半屏）：
 *  · 优先画窄带频谱瀑布（32 bin × 最近若干帧，颜色越亮能量越强）；
 *  · 频谱还没起伏（或驱动没给频谱）时退回 RSSI 历史色条 + 门限虚线；
 *  · 底部保留「开始/停止接收」，不削弱原胶囊的快捷操作。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SignalWaterfallSheet(
    rssi: FloatArray,
    spectrum: List<FloatArray>,
    status: StatusFrame?,
    running: Boolean,
    thresholdDb: Double,
    sourceLabel: String,
    onToggle: () -> Unit,
    onDismiss: () -> Unit,
) {
    val p = pal()
    val gateDb = thresholdDb.toFloat()
    // 频谱是否真的有起伏：全平坦（驱动没填/无信号）就用 RSSI 色条
    val spectrumRange = remember(spectrum) {
        if (spectrum.size < 2) 0f
        else {
            val mn = spectrum.minOf { row -> row.min() }
            val mx = spectrum.maxOf { row -> row.max() }
            mx - mn
        }
    }
    val useSpectrum = spectrumRange > 2f

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = p.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = Dim.pagePad)
                .padding(bottom = 20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("信号瀑布", color = p.text, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.width(8.dp))
                status?.let {
                    val tone = when {
                        it.gateState >= 2 -> Tone.Ok
                        it.gateState == 1 -> Tone.Warn
                        else -> Tone.Neutral
                    }
                    Chip(gateLabel(it.gateState), tone)
                }
                Spacer(Modifier.weight(1f))
                Text(
                    status?.let { "%.1f dB".format(Locale.US, it.rssiDb) } ?: "— dB",
                    color = p.textSecondary, fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold,
                )
            }
            Spacer(Modifier.height(2.dp))
            Text(
                "$sourceLabel · 每 ${StatusFramePoller.POLL_MS} ms 刷新 · " +
                    if (useSpectrum) "频谱 ${spectrum.firstOrNull()?.size ?: 0} bin × ${spectrum.size} 帧"
                    else "RSSI ${rssi.size} 点（约 ${(rssi.size * 150 / 1000)} s）",
                color = p.textTertiary, fontSize = 11.sp,
            )
            Spacer(Modifier.height(8.dp))

            Box(
                Modifier
                    .fillMaxWidth()
                    .height(if (useSpectrum) 200.dp else 140.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(p.bg)
                    .border(1.dp, p.border, RoundedCornerShape(8.dp)),
            ) {
                if (useSpectrum) {
                    // v3.2.6：频谱只有 32 bin，逐 bin 画矩形就是马赛克。
                    // 这里做横向+纵向双线性插值 + 对数压缩生成位图，再用
                    // FilterQuality.Medium 平滑拉伸到全宽 → 连续瀑布。
                    // **位图必须后台生成**：12 万像素 × 每秒 6~14 次在主线程做，
                    // 实测主线程每秒掉一百多帧；放到 Dispatchers.Default 后，
                    // 上一帧没算完会被 produceState 自动取消，不堆积。
                    val waterfall by produceState<androidx.compose.ui.graphics.ImageBitmap?>(
                        initialValue = null,
                        spectrum, p.bg, p.spectrum, p.warn, p.accent,
                    ) {
                        val rows = spectrum.takeLast(240)
                        if (rows.size < 2) return@produceState
                        value = withContext(kotlinx.coroutines.Dispatchers.Default) {
                            buildWaterfallBitmap(rows, p.bg, p.spectrum, p.warn, p.accent)
                        }
                    }
                    waterfall?.let { img ->
                        Image(
                            bitmap = img,
                            contentDescription = "信号瀑布",
                            modifier = Modifier.fillMaxSize().padding(3.dp),
                            contentScale = ContentScale.FillBounds,
                            filterQuality = FilterQuality.Medium,
                        )
                    }
                } else {
                    Canvas(Modifier.fillMaxSize().padding(4.dp)) {
                        // RSSI 色条：低于门限用蓝灰，高门限用 CR 红/绿
                        val n = rssi.size
                        fun dbToY(db: Float): Float =
                            size.height * (1f - ((db + 140f) / 90f).coerceIn(0f, 1f))
                        // 门限虚线
                        var x = 0f
                        while (x < size.width) {
                            drawLine(
                                p.warn.copy(alpha = 0.65f),
                                Offset(x, dbToY(gateDb)),
                                Offset((x + 8f).coerceAtMost(size.width), dbToY(gateDb)),
                                1.2f,
                            )
                            x += 14f
                        }
                        if (n == 0) {
                            drawLine(
                                p.textTertiary.copy(alpha = 0.5f),
                                Offset(0f, dbToY(-140f)),
                                Offset(size.width, dbToY(-140f)),
                                2f,
                            )
                        } else {
                            val step = if (n > 1) size.width / (n - 1) else size.width
                            rssi.forEachIndexed { i, db ->
                                val barX = size.width - (n - 1 - i) * step
                                val on = db >= gateDb
                                drawLine(
                                    if (on) p.accent else p.spectrum.copy(alpha = 0.55f),
                                    Offset(barX, dbToY(db)),
                                    Offset(barX, size.height),
                                    if (n > 1) 2f else 4f,
                                )
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                if (useSpectrum) "颜色越亮能量越强；红色 = 当前信号最强 bin（门限 ${"%.0f".format(Locale.US, gateDb)} dB 仅对 RSSI 判定）"
                else "红/绿 = 超过门限 ${"%.0f".format(Locale.US, gateDb)} dB，蓝色 = 低于门限；虚线为门限",
                color = p.textTertiary, fontSize = 10.sp,
            )
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onToggle,
                    modifier = Modifier.weight(1f).height(42.dp),
                    shape = RoundedCornerShape(50),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (running) p.surfaceAlt else p.accent,
                        contentColor = if (running) p.text else p.onAccent,
                    ),
                ) {
                    Text(
                        if (running) "■  停止接收" else "▶  开始接收",
                        fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                }
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.height(42.dp),
                    shape = RoundedCornerShape(50),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = p.surfaceAlt, contentColor = p.text),
                ) { Text("关闭", fontSize = 13.sp) }
            }
        }
    }
}

/** 门控状态文案（解码页信号条 / 瀑布弹层共用） */
private fun gateLabel(gate: Int): String = when (gate) {
    0 -> "门控关闭"; 1 -> "待命"; 2 -> "有信号"; 3 -> "保持"; 4 -> "旁路"; else -> "未知"
}

/** 热力色阶：低=底色，中=蓝（频谱），高=黄，最高=CR 红 */
private fun heatColor(
    t: Float,
    low: androidx.compose.ui.graphics.Color,
    mid: androidx.compose.ui.graphics.Color,
    high: androidx.compose.ui.graphics.Color,
    top: androidx.compose.ui.graphics.Color,
): androidx.compose.ui.graphics.Color = when {
    t < 0.35f -> lerp(low, mid, t / 0.35f)
    t < 0.7f -> lerp(mid, high, (t - 0.35f) / 0.35f)
    else -> lerp(high, top, (t - 0.7f) / 0.3f)
}

/**
 * 频谱帧序列 → 平滑瀑布位图（v3.2.6）。
 *
 * 为什么看着"马赛克"：窄带频谱只有 **32 bin**，纵向又只有一帧一行；
 * 直接铺满屏就是 30px 见方的色块 + 横向条纹。
 *
 * 这一版做四件事（全部在 CPU 上、结果缓存成位图）：
 *  1. **横向三点平滑** `[0.25, 0.5, 0.25]`：抹掉 bin 之间的台阶；
 *  2. **双线性插值**：横向每 bin 插 [WATERFALL_INTERP_X] 列、纵向每帧插
 *     [WATERFALL_INTERP_Y] 行（帧与帧之间也按小数权重混合）——纵向条纹消失；
 *  3. **对数动态范围压缩**（`ln(1+k·t)/ln(1+k)`）：弱信号层次更丰富，
 *     不像线性拉伸那样要么全黑要么全亮；
 *  4. **256 级颜色查找表**：每像素只算一次插值 + 查表，14 fps 重建也不卡。
 *
 * 返回 `ImageBitmap` 供 `Image(..., filterQuality = Medium)` 直接绘制。
 */
private const val WATERFALL_INTERP_X = 8
private const val WATERFALL_INTERP_Y = 2
private const val WATERFALL_DRC = 4.0f   // 对数压缩强度：越大弱信号越明显

private fun buildWaterfallBitmap(
    rows: List<FloatArray>,
    low: androidx.compose.ui.graphics.Color,
    mid: androidx.compose.ui.graphics.Color,
    high: androidx.compose.ui.graphics.Color,
    top: androidx.compose.ui.graphics.Color,
): androidx.compose.ui.graphics.ImageBitmap {
    val bins = rows.firstOrNull()?.size ?: 0
    if (bins == 0 || rows.isEmpty()) {
        val bmp = Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888)
        return bmp.asImageBitmap()
    }
    val h = rows.size

    // 1) 横向三点平滑（先平滑再插值，边界不会出锯齿）
    val hs = Array(h) { y ->
        val r = rows[y]
        FloatArray(bins).also { out ->
            for (x in 0 until bins) {
                val a = r[if (x > 0) x - 1 else 0]
                val b = r[x]
                val c = r[if (x < bins - 1) x + 1 else bins - 1]
                out[x] = 0.25f * a + 0.5f * b + 0.25f * c
            }
        }
    }

    // 2) 能量范围（整块瀑布统一，避免逐帧跳色）
    var mn = Float.MAX_VALUE
    var mx = -Float.MAX_VALUE
    for (row in hs) for (v in row) {
        if (v < mn) mn = v
        if (v > mx) mx = v
    }
    val span = (mx - mn).coerceAtLeast(0.001f)

    // 3) 颜色查找表（256 级），避免每像素都算 lerp
    val lut = IntArray(256) { i ->
        heatColor(i / 255f, low, mid, high, top).toArgb()
    }
    val lnMax = ln(1f + WATERFALL_DRC)

    // 4) 双线性插值输出
    val w = (bins - 1).coerceAtLeast(1) * WATERFALL_INTERP_X + 1
    val H = h * WATERFALL_INTERP_Y
    val pixels = IntArray(w * H)
    for (py in 0 until H) {
        val fy = py.toFloat() / WATERFALL_INTERP_Y
        val y0 = fy.toInt().coerceIn(0, h - 1)
        val y1 = (y0 + 1).coerceAtMost(h - 1)
        val ty = (fy - y0).coerceIn(0f, 1f)
        val r0 = hs[y0]
        val r1 = hs[y1]
        val base = py * w
        for (px in 0 until w) {
            val fx = px.toFloat() / WATERFALL_INTERP_X
            val x0 = fx.toInt().coerceIn(0, bins - 1)
            val x1 = (x0 + 1).coerceAtMost(bins - 1)
            val tx = (fx - x0).coerceIn(0f, 1f)
            // 双线性：横向 + 纵向同时插值
            val v = (r0[x0] * (1f - tx) + r0[x1] * tx) * (1f - ty) +
                    (r1[x0] * (1f - tx) + r1[x1] * tx) * ty
            val raw = ((v - mn) / span).coerceIn(0f, 1f)
            // 对数动态范围压缩：弱信号层次更丰富
            val t = ln(1f + WATERFALL_DRC * raw) / lnMax
            pixels[base + px] = lut[(t * 255f).toInt().coerceIn(0, 255)]
        }
    }
    val bmp = Bitmap.createBitmap(w, H, Bitmap.Config.ARGB_8888)
    bmp.setPixels(pixels, 0, w, 0, 0, w, H)
    return bmp.asImageBitmap()
}

/** 当前解码大卡：车次大号 + 方向方块 + 速度/公里标/线路/机车/时间 + 自动查询的车次/配属信息 */
@Composable
private fun CurrentCard(
    ev: DecodeEvent,
    trainInfo: TrainInfoClient.TrainInfo?,
    locoInfo: LocoRoster.Lookup?,
    onDetail: () -> Unit,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(Dim.cardCorner))
            .background(p.surface)
            .border(1.dp, p.border, RoundedCornerShape(Dim.cardCorner))
            .clickable(onClick = onDetail)
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                ev.train.ifEmpty { "----" },
                color = p.text,
                fontSize = 38.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.5).sp,
                modifier = Modifier.clickable { if (ev.train.isNotBlank()) onQueryTrain(ev.train) },
            )
            Spacer(Modifier.width(10.dp))
            DirectionBadge(ev.direction)
            Spacer(Modifier.weight(1f))
            if (ev.hasInterference) Chip("干扰", Tone.Warn)
            Chip(
                if (ev.latitude != null) "含坐标" else "无坐标",
                if (ev.latitude != null) Tone.Ok else Tone.Neutral,
            )
        }
        Spacer(Modifier.height(6.dp))
        Text(ev.category, color = p.textSecondary, fontSize = 13.sp)

        Spacer(Modifier.height(12.dp))
        Row {
            BigMetric("速度", ev.speed.ifEmpty { "---" }, "km/h", Modifier.weight(1f))
            BigMetric("公里标", ev.position.ifEmpty { "---.-" }, "km", Modifier.weight(1f))
            BigMetric(
                label = "剩距/到达",
                value = ev.etaDistanceKm?.let { "%.1f".format(Locale.US, it) } ?: ev.etaTime,
                unit = if (ev.etaDistanceKm != null) "km" else "",
                modifier = Modifier.weight(1f),
            )
        }

        Spacer(Modifier.height(12.dp))
        Divider()
        Spacer(Modifier.height(8.dp))

        InfoRow("线路", ev.route.ifEmpty { "未知" })
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
            Text("机车", color = p.textSecondary, fontSize = 13.sp, modifier = Modifier.width(84.dp))
            Text(
                ev.loco.ifEmpty { "----" },
                color = p.accent,
                fontSize = 13.sp,
                modifier = Modifier.clickable {
                    if (ev.loco.isNotBlank()) {
                        val (m, n) = xyz.mlxkj.crlbj.data.LocoRoster.parseLocoText(ev.loco)
                        onQueryLoco(m, n ?: "")
                    }
                },
            )
        }
        // ---- 自动查询内联结果（收到新解码后台查好即显示；失败静默不显示） ----
        trainInfo?.let { ti ->
            // v3.2：等级 · 担当局 · 担当段/客运段 · 配属段/车辆段 · 车型 · 始发→终到
            val bits = listOf(ti.category, ti.bureau, ti.runner, ti.carOwner, ti.car)
                .filter { it.isNotBlank() }
            if (bits.isNotEmpty()) InfoRow("车次", bits.joinToString(" · "))
            if (ti.start.isNotBlank() || ti.end.isNotBlank()) {
                InfoRow("区间", "${ti.start.ifBlank { "?" }} → ${ti.end.ifBlank { "?" }}")
            }
        }
        locoInfo?.let { li ->
            if (li.ok) {
                val bits = listOf(
                    li.model,
                    li.depot.ifEmpty { "配属未知" },
                    li.maker,
                ).filter { it.isNotBlank() }
                if (bits.isNotEmpty()) InfoRow("配属", bits.joinToString(" · "))
            }
        }
        ev.latitude?.let {
            InfoRow(
                "坐标",
                "%.5f, %.5f".format(Locale.US, it, ev.longitude ?: 0.0),
                mono = true,
            )
        }
        InfoRow("ETA", "${ev.etaTime}  ${ev.etaStatus}")
        InfoRow("收到时间", ev.timeStr, mono = true)
    }
}

/** 最近解码列表的一行 */
@Composable
private fun RecentRow(
    ev: DecodeEvent,
    onClick: () -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            ev.train.ifEmpty { "----" },
            color = p.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.width(72.dp),
        )
        DirectionBadge(ev.direction, small = true)
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "%s km/h · K%s".format(
                    Locale.US, ev.speed.ifEmpty { "---" }, ev.position.ifEmpty { "---.-" }),
                color = p.textSecondary, fontSize = 12.sp, fontFamily = FontFamily.Monospace,
            )
            Text(
                listOfNotNull(
                    ev.route.takeIf { it.isNotBlank() }?.let { "线路 $it" },
                    ev.loco.takeIf { it.isNotBlank() }?.let { "机车 $it" },
                ).joinToString(" · ").ifEmpty { ev.category },
                color = p.textTertiary, fontSize = 11.sp, maxLines = 1,
            )
        }
        Text(ev.timeStr, color = p.textTertiary, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
    }
}

/** 方向方块（上/下行用带底色的方标签，比小字更醒目） */
@Composable
fun DirectionBadge(direction: String, small: Boolean = false) {
    val p = pal()
    val color = p.dirColor(direction)
    Box(
        Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(color.copy(alpha = 0.16f))
            .padding(horizontal = if (small) 4.dp else 6.dp, vertical = if (small) 1.dp else 2.dp)
    ) {
        Text(
            direction.ifEmpty { "未知" },
            color = color,
            fontSize = if (small) 10.sp else 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

/** 大号指标（速度/公里标/距到达） */
@Composable
private fun BigMetric(label: String, value: String, unit: String, modifier: Modifier = Modifier) {
    val p = pal()
    Column(modifier) {
        Text(label, color = p.textTertiary, fontSize = 11.sp)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                value,
                color = p.text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace,
            )
            if (unit.isNotEmpty()) {
                Spacer(Modifier.width(2.dp))
                Text(unit, color = p.textTertiary, fontSize = 10.sp,
                    modifier = Modifier.padding(bottom = 3.dp))
            }
        }
    }
}

/** 兼容重载：把 (label to value) 直接当指标用（距到达没有单位） */
@Composable
private fun BigMetric(pair: Pair<String, String>, unit: String, modifier: Modifier) {
    BigMetric(pair.first, pair.second, unit, modifier)
}/** 解码记录详情（底部弹层，不做整页跳转） */
@Composable
private fun DecodeDetailSheet(
    ev: DecodeEvent,
    onQueryTrain: (String) -> Unit,
    onQueryLoco: (String, String) -> Unit,
) {
    val p = pal()
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Dim.pagePad)
            .padding(bottom = 28.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ev.train.ifEmpty { "----" }, color = p.text, fontSize = 26.sp,
                fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(10.dp))
            DirectionBadge(ev.direction)
            Spacer(Modifier.weight(1f))
            Text(ev.timeStr, color = p.textTertiary, fontSize = 12.sp,
                fontFamily = FontFamily.Monospace)
        }
        Spacer(Modifier.height(10.dp))
        SectionCard("基本") {
            InfoRow("类别", ev.category)
            InfoRow("速度", "${ev.speed} km/h", mono = true)
            InfoRow("公里标", ev.position, mono = true)
            InfoRow("线路", ev.route.ifEmpty { "未知" })
            InfoRow("机车", ev.loco.ifEmpty { "----" }, mono = true)
            InfoRow("机车代号", ev.locoCode.ifEmpty { "----" }, mono = true)
            InfoRow("报文类型", if (ev.isDetailed) "详细长报文" else "基础短报文")
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("到达估算") {
            InfoRow("预计到达", ev.etaTime, mono = true)
            InfoRow("剩余里程", ev.etaDistanceKm?.let { "%.1f km".format(Locale.US, it) } ?: "—",
                mono = true)
            InfoRow("状态", ev.etaStatus)
            InfoRow("剩余秒数", ev.etaSeconds?.let { "%.0f s".format(Locale.US, it) } ?: "—",
                mono = true)
        }
        Spacer(Modifier.height(Dim.gap))
        SectionCard("链路") {
            InfoRow("RSSI", "%.1f dB".format(Locale.US, ev.rssi), mono = true)
            InfoRow("AFC", "%.0f Hz（评分 %.2f）".format(Locale.US, ev.afcHz, ev.afcScore), mono = true)
            ev.latitude?.let {
                InfoRow("坐标", "%.5f, %.5f".format(Locale.US, it, ev.longitude ?: 0.0), mono = true)
            }
            InfoRow("BCH 错", if (ev.msgTypeError) "有" else "无")
            InfoRow("原始 BCD", ev.rawBcd.ifEmpty { "—" }, mono = true)
            InfoRow("地址", "0x%X".format(ev.rawAddr), mono = true)
            InfoRow("合并/独立", listOfNotNull(
                "合并".takeIf { ev.rawIsMerged },
                "独立".takeIf { ev.rawIsStandalone },
                "短报文".takeIf { ev.rawIsShort },
            ).joinToString(" / ").ifEmpty { "—" })
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(Dim.gap)) {
            Button(
                onClick = { if (ev.train.isNotBlank()) onQueryTrain(ev.train) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(containerColor = p.accent),
            ) { Text("查这趟车", fontSize = 13.sp) }
            Button(
                onClick = {
                    if (ev.loco.isNotBlank()) {
                        val (m, n) = xyz.mlxkj.crlbj.data.LocoRoster.parseLocoText(ev.loco)
                        onQueryLoco(m, n ?: "")
                    }
                },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(
                    containerColor = p.surfaceAlt, contentColor = p.text),
            ) { Text("查这台机车", fontSize = 13.sp) }
        }
    }
}

/** 数据源显示名（与地图页同一套文案） */
internal fun sourceLabelOf(type: String): String = when (type) {
    "usb" -> "USB 直连"
    "rtl_tcp" -> "rtl_tcp"
    "owrx" -> "OWRX"
    else -> type
}
