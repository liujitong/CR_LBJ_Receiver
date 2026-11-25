package xyz.mlxkj.crlbj.data

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.net.UnknownHostException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 车次查询（安卓端 = 桌面端 `cr_lbj/data/train_info.py` 的移植，字段语义逐字一致）。
 *
 * 两条数据源：
 *
 *   RailGo `https://data.railgo.zenglingkun.cn/api/train/query?train=G7`
 *          · 零鉴权、CORS *、有列车等级 / 担当局 / 客运段 / 配属段 / 车型 / 时刻表 /
 *            开行日 / 交路——「车次查询」要的字段它基本都有；
 *          · 个人托管服务，可能随时不可用，所以只做**首选**，失败自动退回 12306。
 *   12306  `search.12306.cn` 查 train_no → `kyfw.12306.cn` 查时刻表
 *          · 官方稳定，但没有担当/配属信息。
 *
 * 约定：任何失败都不抛异常，返回 `ok=false` + `error` 文案，界面据此提示。
 * 解析函数（[parseRailGo] / [parse12306Search] / [parse12306Detail]）是纯函数，
 * 可被 JVM 单元测试直接调用（不需要网络、不需要模拟器）。
 */
object TrainInfoClient {

    const val RAILGO_URL = "https://data.railgo.zenglingkun.cn/api/train/query"
    const val SEARCH_12306_URL = "https://search.12306.cn/search/v1/train/search"
    const val DETAIL_12306_URL = "https://kyfw.12306.cn/otn/queryTrainInfo/query"

    private const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"

    private val TRAIN_RE = Regex("^[A-Za-z]{0,2}\\d{1,5}$")

    // ------------------------------------------------------------------ 模型

    /** 时刻表一站 */
    data class Stop(
        val no: Int,
        val station: String,
        val telecode: String = "",
        val arrive: String = "",
        val depart: String = "",
        /** 停站分钟数 */
        val stopMin: Int = 0,
        /** 第几天（跨日） */
        val day: Int = 0,
        /** 累计里程（km，12306 无此字段时为 null） */
        val distance: Double? = null,
        val speed: Double = 0.0,
    )

    /** 交路一段（同一趟车换车次时给出） */
    data class DiagramSegment(
        val number: String,
        val fromStation: String,
        val fromTime: String,
        val toStation: String,
        val toTime: String,
    )

    /** 查询结果 */
    data class TrainInfo(
        val ok: Boolean = false,
        val source: String = "",
        val error: String = "",
        val train: String = "",
        val numberFull: List<String> = emptyList(),
        val category: String = "",
        val bureau: String = "",
        val runner: String = "",
        val carOwner: String = "",
        val car: String = "",
        val rundays: List<String> = emptyList(),
        val diagramType: String = "",
        val diagram: List<DiagramSegment> = emptyList(),
        val stops: List<Stop> = emptyList(),
        val start: String = "",
        val end: String = "",
        val startTime: String = "",
        val endTime: String = "",
        val distance: Double? = null,
        val queryDate: String = "",
        /** auto 模式退回时记录上一次失败的来源说明 */
        val fallbackFrom: String = "",
    ) {
        val rundaysCount: Int get() = rundays.size

        /** 一行摘要（状态胶囊/日志用） */
        fun summary(): String {
            if (!ok) return "车次 $train 查询失败：$error"
            val bits = ArrayList<String>(4)
            if (train.isNotEmpty()) bits.add(train)
            if (category.isNotEmpty()) bits.add(category)
            if (start.isNotEmpty() && end.isNotEmpty()) bits.add("$start→$end")
            if (carOwner.isNotEmpty()) bits.add("配属 $carOwner") else if (bureau.isNotEmpty()) bits.add("担当 $bureau")
            return bits.joinToString(" · ")
        }
    }

    // ------------------------------------------------------------------ 工具

    /**
     * 车次号规整：去空格、全角转半角、字母大写。`g 7` → `G7`，`Ｇ7` → `G7`。
     *
     * 全角转半角是安卓端在桌面端规则之上的补充：中文输入法常打出全角字母，
     * 直接查会报「格式不对」，用户完全不知道为什么。
     */
    fun normalizeTrain(text: String?): String {
        val raw = (text ?: "").trim().replace(" ", "").replace("\u3000", "")
        val sb = StringBuilder(raw.length)
        for (ch in raw) {
            val c = ch.code
            // 全角 ！～（U+FF01–U+FF5E）→ 半角，全角空格已在上面处理
            if (c in 0xFF01..0xFF5E) sb.append((c - 0xFEE0).toChar()) else sb.append(ch)
        }
        return sb.toString().uppercase(Locale.US)
    }

    fun isTrainCode(text: String?): Boolean = TRAIN_RE.matches(normalizeTrain(text))

    private fun str(o: JSONObject?, key: String): String {
        if (o == null) return ""
        val v = o.opt(key) ?: return ""
        if (v == JSONObject.NULL) return ""
        val s = v.toString().trim()
        return if (s == "null") "" else s
    }

    private fun num(o: JSONObject?, key: String): Double? {
        if (o == null) return null
        val v = o.opt(key) ?: return null
        if (v == JSONObject.NULL) return null
        return when (v) {
            is Number -> v.toDouble()
            is String -> v.trim().toDoubleOrNull()
            else -> null
        }
    }

    private fun strList(o: JSONObject?, key: String): List<String> {
        val arr = o?.optJSONArray(key) ?: return emptyList()
        val out = ArrayList<String>(arr.length())
        for (i in 0 until arr.length()) {
            val v = arr.opt(i)
            if (v != null && v != JSONObject.NULL) out.add(v.toString())
        }
        return out
    }

    private fun strAt(arr: JSONArray?, index: Int): String {
        val v = arr?.opt(index) ?: return ""
        return if (v == JSONObject.NULL) "" else v.toString()
    }

    private fun friendly(e: Throwable): String = when (e) {
        is HttpStatusException -> "服务返回 HTTP ${e.code}"
        is SocketTimeoutException -> "请求超时"
        is UnknownHostException -> "网络不可达（域名解析失败）"
        is JSONException -> "返回内容不是合法 JSON"
        is IOException -> "网络不可达（${e.message ?: e.javaClass.simpleName}）"
        else -> "请求失败：${e.message ?: e.javaClass.simpleName}"
    }

    class HttpStatusException(val code: Int) : IOException("HTTP $code")

    private fun httpGetJson(
        url: String,
        timeoutMs: Int,
        headers: Map<String, String> = emptyMap(),
    ): JSONObject {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = timeoutMs
            readTimeout = timeoutMs
            setRequestProperty("User-Agent", UA)
            setRequestProperty("Accept", "application/json, text/plain, */*")
            headers.forEach { (k, v) -> setRequestProperty(k, v) }
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) throw HttpStatusException(code)
            val text = conn.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
            return JSONObject(text)
        } finally {
            runCatching { conn.disconnect() }
        }
    }

    fun todayCompact(): String =
        SimpleDateFormat("yyyyMMdd", Locale.US).format(Date())

    // ------------------------------------------------------------- RailGo

    fun queryRailGo(train: String, timeoutMs: Int = 12000): TrainInfo {
        val t = normalizeTrain(train)
        if (!isTrainCode(t)) return TrainInfo(train = t, error = "车次号格式不对：${train.ifEmpty { "空" }}")
        return try {
            val d = httpGetJson("$RAILGO_URL?train=$t", timeoutMs)
            parseRailGo(d, t)
        } catch (e: Throwable) {
            TrainInfo(source = "railgo", train = t, error = friendly(e))
        }
    }

    /** 纯函数：RailGo JSON → TrainInfo（缺字段安全） */
    fun parseRailGo(d: JSONObject?, requested: String): TrainInfo {
        if (d == null || str(d, "number").isEmpty()) {
            return TrainInfo(source = "railgo", train = requested,
                error = "未查询到车次 $requested")
        }
        val stops = ArrayList<Stop>()
        val tt = d.optJSONArray("timetable")
        if (tt != null) {
            for (i in 0 until tt.length()) {
                val s = tt.optJSONObject(i) ?: continue
                stops.add(
                    Stop(
                        no = i + 1,
                        station = str(s, "station"),
                        telecode = str(s, "stationTelecode"),
                        arrive = str(s, "arrive"),
                        depart = str(s, "depart"),
                        stopMin = num(s, "stopTime")?.toInt() ?: 0,
                        day = num(s, "day")?.toInt() ?: 0,
                        distance = num(s, "distance"),
                        speed = num(s, "speed") ?: 0.0,
                    )
                )
            }
        }
        val diagram = ArrayList<DiagramSegment>()
        val dg = d.optJSONArray("diagram")
        if (dg != null) {
            for (i in 0 until dg.length()) {
                val seg = dg.optJSONObject(i) ?: continue
                diagram.add(
                    DiagramSegment(
                        number = str(seg, "number"),
                        fromStation = strAt(seg.optJSONArray("from"), 0),
                        fromTime = strAt(seg.optJSONArray("from"), 1),
                        toStation = strAt(seg.optJSONArray("to"), 0),
                        toTime = strAt(seg.optJSONArray("to"), 1),
                    )
                )
            }
        }
        val first = stops.firstOrNull()
        val last = stops.lastOrNull()
        return TrainInfo(
            ok = true,
            source = "railgo",
            train = str(d, "number").ifEmpty { requested },
            numberFull = strList(d, "numberFull"),
            category = str(d, "type"),
            bureau = str(d, "bureauName"),
            runner = str(d, "runner"),
            carOwner = str(d, "carOwner"),
            car = str(d, "car"),
            rundays = strList(d, "rundays"),
            diagramType = str(d, "diagramType"),
            diagram = diagram,
            stops = stops,
            start = first?.station.orEmpty(),
            startTime = first?.let { it.depart.ifEmpty { it.arrive } }.orEmpty(),
            end = last?.station.orEmpty(),
            endTime = last?.let { it.arrive.ifEmpty { it.depart } }.orEmpty(),
            distance = last?.distance,
        )
    }

    // -------------------------------------------------------------- 12306

    fun query12306(train: String, dateCompact: String? = null, timeoutMs: Int = 12000): TrainInfo {
        val t = normalizeTrain(train)
        if (!isTrainCode(t)) return TrainInfo(train = t, error = "车次号格式不对：${train.ifEmpty { "空" }}")
        val ds = dateCompact ?: todayCompact()
        return try {
            val search = httpGetJson("$SEARCH_12306_URL?keyword=$t&date=$ds", timeoutMs)
            val found = parse12306Search(search, t, ds)
                ?: return TrainInfo(source = "12306", train = t, queryDate = ds,
                    error = "12306 未查询到车次 $t（$ds）")
            val (trainNo, trainCode) = found
            val detailDate = "${ds.substring(0, 4)}-${ds.substring(4, 6)}-${ds.substring(6, 8)}"
            val detail = httpGetJson(
                "$DETAIL_12306_URL?leftTicketDTO.train_no=$trainNo" +
                    "&leftTicketDTO.train_date=$detailDate&rand_code=",
                timeoutMs,
                mapOf("Referer" to "https://kyfw.12306.cn/otn/leftTicket/init"),
            )
            parse12306Detail(detail, trainCode, ds)
        } catch (e: Throwable) {
            TrainInfo(source = "12306", train = t, queryDate = ds, error = friendly(e))
        }
    }

    /** 纯函数：搜索结果 → (train_no, station_train_code)；查不到返回 null */
    fun parse12306Search(root: JSONObject?, requested: String, ds: String): Pair<String, String>? {
        if (root == null || !root.optBoolean("status", false)) return null
        val rows = root.optJSONArray("data") ?: return null
        if (rows.length() == 0) return null
        val first = rows.optJSONObject(0) ?: return null
        val trainNo = str(first, "train_no")
        if (trainNo.isEmpty()) return null
        return trainNo to str(first, "station_train_code").ifEmpty { requested }
    }

    /** 纯函数：时刻表 JSON → TrainInfo（12306 没有担当/配属字段） */
    fun parse12306Detail(root: JSONObject?, trainCode: String, ds: String): TrainInfo {
        if (root == null || !root.optBoolean("status", false)) {
            return TrainInfo(source = "12306", train = trainCode, queryDate = ds,
                error = "12306 时刻表为空（$trainCode）")
        }
        val inner = root.optJSONObject("data")
        val data = inner?.optJSONArray("data")
        if (data == null || data.length() == 0) {
            return TrainInfo(source = "12306", train = trainCode, queryDate = ds,
                error = "12306 时刻表为空（$trainCode）")
        }
        val stops = ArrayList<Stop>(data.length())
        for (i in 0 until data.length()) {
            val s = data.optJSONObject(i) ?: continue
            val arrive = str(s, "arrive_time").ifEmpty { "----" }
            val depart = str(s, "start_time").ifEmpty { "----" }
            stops.add(
                Stop(
                    no = num(s, "station_no")?.toInt() ?: (i + 1),
                    station = str(s, "station_name"),
                    arrive = arrive,
                    depart = depart,
                    stopMin = stopMinutes(arrive, depart),
                    day = num(s, "arrive_day_diff")?.toInt() ?: 0,
                )
            )
        }
        val first = stops.firstOrNull()
        val last = stops.lastOrNull()
        val category = data.optJSONObject(0)?.let { str(it, "train_class_name") }.orEmpty()
        return TrainInfo(
            ok = true, source = "12306", train = trainCode,
            queryDate = ds, numberFull = listOf(trainCode), category = category,
            stops = stops,
            start = first?.station.orEmpty(), startTime = first?.depart.orEmpty(),
            end = last?.station.orEmpty(), endTime = last?.arrive.orEmpty(),
        )
    }

    /** 停站分钟数（12306 只给时刻，自己减） */
    fun stopMinutes(arrive: String?, depart: String?): Int {
        fun parse(x: String?): Int? {
            val m = Regex("^(\\d{1,2}):(\\d{2})$").find((x ?: "").trim()) ?: return null
            val h = m.groupValues[1].toInt()
            val min = m.groupValues[2].toInt()
            // 拒收 25:00 这类非法时刻，避免算出荒唐的停站时间
            if (h !in 0..23 || min !in 0..59) return null
            return h * 60 + min
        }
        val a = parse(arrive) ?: return 0
        val b = parse(depart) ?: return 0
        val d = b - a
        return if (d in 0 until 24 * 60) d else 0
    }

    // -------------------------------------------------------------- 总入口

    /**
     * @param prefer `auto`（先 RailGo 再 12306）/ `railgo` / `12306`
     */
    fun query(
        train: String,
        prefer: String = "auto",
        timeoutMs: Int = 12000,
        dateCompact: String? = null,
    ): TrainInfo {
        val t = normalizeTrain(train)
        val order = when (prefer) {
            "railgo" -> listOf("railgo")
            "12306" -> listOf("12306")
            else -> listOf("railgo", "12306")
        }
        var firstErr = ""
        for (src in order) {
            val res = if (src == "railgo") queryRailGo(t, timeoutMs)
            else query12306(t, dateCompact, timeoutMs)
            if (res.ok) return if (firstErr.isEmpty()) res else res.copy(fallbackFrom = firstErr)
            if (firstErr.isEmpty()) firstErr = res.error
        }
        return TrainInfo(train = t, error = firstErr.ifEmpty { "未查询到车次" })
    }
}
