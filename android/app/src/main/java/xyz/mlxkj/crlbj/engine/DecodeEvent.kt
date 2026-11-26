package xyz.mlxkj.crlbj.engine

import org.json.JSONObject
import java.util.Locale
import java.text.SimpleDateFormat
import java.util.Date
import java.time.LocalDate
import java.time.ZoneId

/**
 * 解码事件业务层（M2）：native JSON → 业务加工 → UI/存储。
 *
 * 组成（全部 1:1 移植桌面版 cr_lbj/core/decoder.py 规则）：
 *  - DecodeEvent：解码结果模型（native 解码层字段 + 业务层字段）
 *  - TrainClassifier：车次分类（纯自动日期驱动：2027-01-01 起全量新版，之前过渡期兼容）
 *  - RecordDeduplicator：同车次 2.5s 窗口去重（质量分替换、uid 沿用）
 *  - ArrivalEstimator：ETA 到达估算（本站公里标 + 线路映射）
 */

/** 解码事件。decode 层字段与 native result_json 输出同名；业务层字段在此加工。 */
data class DecodeEvent(
    // ---- native 解码层（result_json 同名） ----
    val train: String = "",
    val baseTrain: String = "",
    val prefix: String = "",
    val direction: String = "",
    val speed: String = "",
    val position: String = "",
    val loco: String = "",
    val locoCode: String = "",
    val route: String = "",
    val isDetailed: Boolean = false,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val routeValid: Boolean = false,
    val msgTypeError: Boolean = false,
    val hasInterference: Boolean = false,
    val rawBcd: String = "",
    val rawAddr: Long = 0,
    val rawFunc: Int = 0,
    val rawIsShort: Boolean = false,
    val rawIsMerged: Boolean = false,
    val rawIsStandalone: Boolean = false,
    /** BCH(31,21) 纠错后的码字（与桌面 rawCodewords 同名；v3.2.8 起进详情） */
    val rawCodewords: List<Int> = emptyList(),
    val rssi: Double = -140.0,
    val afcHz: Double = 0.0,
    val afcErrHz: Double = 0.0,
    val afcScore: Double = 0.0,
    // ---- 业务层 ----
    val timestamp: Double = 0.0,
    val timeStr: String = "",
    val category: String = "等待信号...",
    val uid: String = "",
    val etaSeconds: Double? = null,
    val etaTime: String = "--:--:--",
    val etaDistanceKm: Double? = null,
    val etaStatus: String = "等待信号",
) {
    companion object {
        private val tsFmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA)

        /** 从 native result_json 输出解析解码层字段 */
        fun fromNativeJson(json: String, nowSec: Double): DecodeEvent {
            val o = JSONObject(json)
            return DecodeEvent(
                train = o.optString("train", ""),
                baseTrain = o.optString("baseTrain", ""),
                prefix = o.optString("prefix", ""),
                direction = o.optString("direction", ""),
                speed = o.optString("speed", ""),
                position = o.optString("position", ""),
                loco = o.optString("loco", ""),
                locoCode = o.optString("locoCode", ""),
                route = o.optString("route", ""),
                isDetailed = o.optBoolean("isDetailed", false),
                latitude = if (o.isNull("latitude")) null else o.optDouble("latitude"),
                longitude = if (o.isNull("longitude")) null else o.optDouble("longitude"),
                routeValid = o.optBoolean("routeValid", false),
                msgTypeError = o.optBoolean("msgTypeError", false),
                hasInterference = o.optBoolean("hasInterference", false),
                rawBcd = o.optString("rawBcd", ""),
                rawAddr = o.optLong("rawAddr", 0),
                rawFunc = o.optInt("rawFunc", 0),
                rawIsShort = o.optBoolean("rawIsShort", false),
                rawIsMerged = o.optBoolean("rawIsMerged", false),
                rawIsStandalone = o.optBoolean("rawIsStandalone", false),
                rawCodewords = o.optJSONArray("rawCodewords")
                    ?.let { a -> (0 until a.length()).map { a.getInt(it) } }
                    ?: emptyList(),
                rssi = o.optDouble("rssi", -140.0),
                afcHz = o.optDouble("afcHz", 0.0),
                afcErrHz = o.optDouble("afcErrHz", 0.0),
                afcScore = o.optDouble("afcScore", 0.0),
                timestamp = nowSec,
                timeStr = tsFmt.format(Date(nowSec.toLong() * 1000)),
            )
        }
    }
}

// ===========================================================================
// 车次分类（移植 classifyTrainCategory / _category2026 / _categoryLegacy /
// _categoryNumeric / _speedValue，规则与桌面版逐条一致；纯自动、无手动方案）
// ===========================================================================
object TrainClassifier {

    /**
     * 新车次编排方案全量启用时刻（对应桌面 TRAIN_NEW_SCHEME_DATE = datetime(2027,1,1)）：
     * 设备本地时区 2027-01-01 00:00 的 epoch 毫秒，类加载时求值一次。
     * 与桌面「本地午夜」语义在任何时区严格一致（修正旧版 UTC 午夜常量近似）。
     */
    private val TRAIN_NEW_SCHEME_BEFORE: Long =
        LocalDate.of(2027, 1, 1).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()

    private val numeric2026 = arrayOf(
        intArrayOf(10001, 19998, 0), intArrayOf(20001, 29998, 1), intArrayOf(30001, 39998, 2),
        intArrayOf(40001, 44998, 3), intArrayOf(45001, 49998, 4), intArrayOf(50001, 50998, 5),
        intArrayOf(51001, 51998, 6), intArrayOf(52001, 52998, 7), intArrayOf(53001, 54998, 8),
        intArrayOf(55001, 55998, 9), intArrayOf(56001, 56998, 10), intArrayOf(57001, 57998, 11),
        intArrayOf(58101, 58998, 12), intArrayOf(60001, 69998, 13), intArrayOf(70001, 70998, 14),
        intArrayOf(71001, 77998, 15), intArrayOf(80001, 81748, 16), intArrayOf(81751, 81998, 17),
        intArrayOf(82001, 84998, 18), intArrayOf(85001, 85998, 19), intArrayOf(86001, 86998, 20),
        intArrayOf(87001, 87998, 21), intArrayOf(88001, 88998, 22), intArrayOf(90001, 91998, 23),
        intArrayOf(93001, 94998, 24),
    )
    // 数值段类别名（索引对应上表第三列）
    private val numericNames = arrayOf(
        "技术直达货运列车", "直通货运列车", "区段货运列车", "摘挂列车", "小运转列车",
        "客车单机", "货车单机", "小运转单机", "补机", "试运行列车",
        "轨道车、小型工程车", "路用列车", "救援列车", "工厂自备车", "超限货运列车",
        "重载货物列车", "直达货运/五定班列", "快运货运列车", "煤炭直达列车", "石油直达列车",
        "始发直达列车", "空车直达列车", "汽运专列", "军用列车(满载)", "军用列车(空车)",
    )

    /** 把速度字段转成数值；无效返回 null（移植 _speedValue） */
    private fun speedValue(speed: String?): Double? {
        if (speed == null) return null
        val v = speed.replace("km/h", "").trim().toDoubleOrNull() ?: return null
        return if (v in 0.0..500.0) v else null
    }

    /** 按 2026 版《列车车次编排规定》分类（移植 _category2026） */
    private fun category2026(prefix: String, numText: String): String? {
        val n = if (numText.isNotEmpty()) numText.toIntOrNull() ?: -1 else -1
        return when (prefix) {
            "X" -> "新时速动车组 (350km/h+)"
            "G" -> "高速动车组 (350km/h)"
            "T" -> "特快动车组 (300km/h)"
            "K" -> "快速动车组 (200~250km/h)"
            "D" -> "动力集中动车组 (≤200km/h)"
            "C" -> "城际动车组 (≤200km/h)"
            "S" -> "市郊(域)列车 (≤160km/h)"
            "Z" -> "快速旅客列车 (160km/h)"
            "N" -> "快速旅客列车 (140km/h)"
            "V" -> when {
                n in 6001..6998 -> "普通旅客快车 (120km/h)"
                n in 7001..7998 -> "普通旅客慢车 (120km/h)"
                else -> "快速旅客列车 (120km/h)"
            }
            "Y" -> if (n <= 998) "普速旅游专线列车" else "普速旅游专列"
            "B" -> when {
                n in 1..198 -> "特快城际班列 (160km/h)"
                n in 201..998 -> "快速多式联运班列 (120km/h)"
                n in 1001..1998 -> "快速城际班列 (120km/h)"
                n in 2001..2998 -> "快速中欧班列 (120km/h)"
                n in 3001..3998 -> "快速中亚班列 (120km/h)"
                n in 4001..5998 -> "普快多式联运班列 (90km/h)"
                n in 6001..7998 -> "普快城际班列 (90km/h)"
                n in 8001..8998 -> "普快中欧班列 (90km/h)"
                n in 9001..9998 -> "普快中亚班列 (90km/h)"
                else -> "货运班列"
            }
            "DH" -> if (n <= 998) "动车组快运 (250km/h+)" else "动车组快运 (≤250km/h)"
            "DJ" -> "动车组检测/确认列车"
            else -> null
        }
    }

    /** 按 2014 版旧规则分类（移植 _categoryLegacy；仅过渡期 T/K/X 内部复用） */
    private fun categoryLegacy(prefix: String): String = when (prefix) {
        "K" -> "快速旅客列车"; "Z" -> "直达特快列车"; "T" -> "特快旅客列车"
        "G" -> "高速动车组"; "D" -> "动车组列车"; "C" -> "城际动车组"
        "X" -> "行包货物列车"; "Y" -> "旅游旅客列车"
        else -> ""
    }

    /** 纯数字车次（货物/路用/回送等）分类，按新版区段表（移植 _categoryNumeric） */
    private fun categoryNumeric(numText: String, tn: String, isDetailed: Boolean): String {
        // 00 开头 → 回送列车（新旧规则一致）
        if (tn.startsWith("00")) {
            val d = tn.filter { it.isDigit() }
            if (d.isNotEmpty()) {
                val n = d.toIntOrNull() ?: -1
                if (n in 1..100) return "动车组有火回送"
                if (n in 101..198) return "动车组无火跨局回送"
                if (n in 201..298) return "动车组无火管内回送"
                if (n in 301..398) return "跨局回送客车"
                if (n in 401..498) return "管内回送客车"
            }
        }
        val d = (if (numText.isNotEmpty()) numText else tn).filter { it.isDigit() }
        if (d.isEmpty()) return "未知类别"
        val n = d.toIntOrNull() ?: return "未知类别"
        for (r in numeric2026) {
            if (n >= r[0] && n <= r[1]) return numericNames[r[2]]
        }
        if (n in 1..9998 && !tn.startsWith("00")) {
            return if (isDetailed) "普通旅客列车" else "等待详细报文确认..."
        }
        return "未知类别"
    }

    /**
     * 车次分类（移植 classifyTrainCategory；纯自动、纯日期驱动，无手动方案）。
     * nowMs >= TRAIN_NEW_SCHEME_BEFORE：所有车次（高铁+普速）一律新版，不看速度；
     * nowMs <  TRAIN_NEW_SCHEME_BEFORE：过渡期——稳定前缀已新版，T/K/X 按速度判定，
     * 速度缺失/无效一律旧版兜底。nowMs 可注入便于测试拨钟，默认当前时间。
     */
    fun classify(trainNo: String, isDetailed: Boolean, speed: String? = null,
                 nowMs: Long = System.currentTimeMillis()): String {
        if (trainNo.isEmpty() || trainNo == "等待信号..." || trainNo == "----") return "等待信号..."
        val tn = trainNo.replace(" ", "").trim().uppercase(Locale.US)
        // ^([A-Z]+)(\d*)：字母前缀 + 数字
        val m = Regex("^([A-Z]+)(\\d*)").find(tn)
        val prefix = m?.groupValues?.get(1) ?: ""
        val numText = m?.groupValues?.get(2) ?: ""
        // ---------- 2027-01-01 起：全量新版（高铁+普速，不看速度） ----------
        if (nowMs >= TRAIN_NEW_SCHEME_BEFORE) {
            return category2026(prefix, numText)
                ?: categoryNumeric(numText, tn, isDetailed)
        }
        // ---------- 过渡期（2027-01-01 前） ----------
        // Z/N/V/B/DH/DJ/Y 以及 G/D/C/S 含义稳定，直接按新版
        if (prefix in setOf("Z", "N", "V", "B", "DH", "DJ", "Y", "G", "D", "C", "S")) {
            category2026(prefix, numText)?.let { return it }
        }
        // T/K/X 新旧含义冲突：用速度判定（新 T=300、K=200~250、X=350+）
        if (prefix in setOf("T", "K", "X")) {
            val spd = speedValue(speed)
            if (spd != null) {
                return if (spd >= 200.0) {
                    category2026(prefix, numText) ?: "未知类别"
                } else {
                    categoryLegacy(prefix).ifEmpty { "未知类别" }
                }
            }
            // 速度缺失/无效：过渡期内一律按旧版兜底（此分支 nowMs < 阈值恒成立）
            return categoryLegacy(prefix).ifEmpty { "未知类别" }
        }
        return categoryNumeric(numText, tn, isDetailed)
    }
}

// ===========================================================================
// 线路名清洗 / 校验 / 公里标解析（移植 sanitizeRouteName / isValidRouteName /
// parseKmValue / parseRouteKmMap）
// ===========================================================================
object RouteUtils {
    private val invalidChars = Regex("[*U()<>\\[\\]{}\\\\/|;:,.，。！？?！@#$%^&_=+`~]")
    private val validChars = Regex("^[\\u4e00-\\u9fa5A-Za-z0-9\\-\\s]+$")
    private val hasContent = Regex("[\\u4e00-\\u9fa5A-Za-z0-9]")

    /** 清洗线路名：去除控制字符与空白；无效返回空串 */
    fun sanitize(route: String?): String {
        if (route == null) return ""
        val r = route.replace("\u0000", "").trim()
        if (r.isEmpty() || r in setOf("----", "---", "未知", "等待信号...")) return ""
        return r
    }

    /** 校验线路名：长度 ≤24，仅含中文/字母/数字/横线/空格 */
    fun isValid(route: String?): Boolean {
        val r = sanitize(route)
        if (r.isEmpty() || r.length > 24) return false
        if (invalidChars.containsMatchIn(r)) return false
        if (!hasContent.containsMatchIn(r)) return false
        return validChars.matches(r)
    }

    /** 从字符串/数字解析公里标 (km)，无效返回 null（round 到 0.1） */
    fun parseKm(v: String?): Double? {
        if (v == null) return null
        val s = v.uppercase(Locale.US).replace("KM", "").trim()
        if (s.isEmpty() || s in setOf("---", "---.-", "----")) return null
        val km = s.toDoubleOrNull() ?: return null
        if (km < 0 || km > 9999.9) return null
        return kotlin.math.round(km * 10.0) / 10.0
    }

    /** 解析 "线路名=公里标" 逗号分隔列表为字典 */
    fun parseRouteKmMap(items: String?): Map<String, Double> {
        val result = LinkedHashMap<String, Double>()
        if (items.isNullOrBlank()) return result
        for (part in items.split(",")) {
            val p = part.trim()
            if (p.isEmpty() || '=' !in p) continue
            val (name, val_) = p.split("=", limit = 2)
            val route = sanitize(name)
            val km = parseKm(val_)
            if (route.isNotEmpty() && km != null) result[route] = km
        }
        return result
    }
}

// ===========================================================================
// ETA 到达估算器（移植 ArrivalEstimator）
// ===========================================================================
class ArrivalEstimator(
    userKm: Double? = null,
    maxSeconds: Double = 6.0 * 3600.0,
    routeKmMap: Map<String, Double> = emptyMap(),
) {
    var defaultKm: Double? = userKm
        private set
    private var downIncreases = true   // 约定下行公里标递增
    private val maxSeconds: Double = maxSeconds
    private val routeKmMap = LinkedHashMap<String, Double>()

    init {
        routeKmMap.forEach { (r, km) -> addRouteKm(r, km) }
    }

    fun getRouteKm(route: String): Double? {
        val r = RouteUtils.sanitize(route)
        return routeKmMap[r] ?: defaultKm
    }

    fun addRouteKm(route: String, km: Double?): Boolean {
        val r = RouteUtils.sanitize(route)
        val kmVal = RouteUtils.parseKm(km?.toString())
        if (r.isEmpty() || kmVal == null) return false
        routeKmMap[r] = kmVal
        return true
    }

    fun removeRouteKm(route: String) {
        routeKmMap.remove(RouteUtils.sanitize(route))
    }

    fun setUserKm(userKm: Double?) {
        defaultKm = userKm
    }

    /** ETA 数据四元组 */
    data class Eta(
        val seconds: Double? = null,
        val time: String = "--:--:--",
        val distanceKm: Double? = null,
        val status: String = "等待信号",
    )

    /** 估算列车到达时间（移植 estimateEta，状态文案逐条一致） */
    fun estimateEta(
        train: String, direction: String, speed: String?,
        position: String?, route: String, goodData: Boolean = true,
        now: Double = System.currentTimeMillis() / 1000.0,
    ): Eta {
        if (!goodData) return Eta(status = "错包忽略")
        val rt = RouteUtils.sanitize(route)
        if (rt.isEmpty()) return Eta(status = "线路未知")
        if (!RouteUtils.isValid(rt)) return Eta(status = "线路名无效")
        val userKmV = getRouteKm(rt)
        if (userKmV == null) return Eta(status = "未设置线路位置")
        if (train.isEmpty() || train == "----") return Eta(status = "等待车次")
        if (direction != "上行" && direction != "下行") return Eta(status = "方向未知")
        val spd = RouteUtils.parseKm(speed)
        if (spd == null || spd <= 0.0) return Eta(status = "速度无效")
        val trainKm = RouteUtils.parseKm(position)
        if (trainKm == null) return Eta(status = "公里标无效")
        // 距离计算
        val dist0 = if (downIncreases) {
            if (direction == "下行") userKmV - trainKm else trainKm - userKmV
        } else {
            if (direction == "下行") trainKm - userKmV else userKmV - trainKm
        }
        if (dist0 < -0.02) return Eta(status = "远离/已过")
        val dist = maxOf(0.0, dist0)
        val etaSec = dist / spd * 3600.0
        if (etaSec > maxSeconds) return Eta(distanceKm = dist, status = "ETA过大")
        val etaTime = SimpleDateFormat("HH:mm:ss", Locale.CHINA)
            .format(Date(((now + etaSec) * 1000).toLong()))
        return Eta(
            seconds = etaSec, time = etaTime, distanceKm = dist,
            status = if (etaSec <= 10.0) "即将到达" else "接近",
        )
    }
}

// ===========================================================================
// 同车次短窗口重复解码合并（移植 RecordDeduplicator）
// ===========================================================================
class RecordDeduplicator(
    window: Double = 2.5,
    private val maxSlots: Int = 256,
) {
    private val window: Double = window
    private val slots = LinkedHashMap<String, Slot>()
    var dropped = 0      // 被合并丢弃的重复记录数
        private set
    var upgraded = 0     // 窗口内被更优记录替换的次数
        private set

    private class Slot(val uid: String, var ts: Double, var score: Double)

    /** 去重键：baseTrain|direction；无效车次返回空串 */
    fun keyOf(d: DecodeEvent): String {
        val base = (d.baseTrain.ifEmpty { d.train }).trim()
        if (base.isEmpty() || base == "----" || base == "未知") return ""
        return "$base|${d.direction}"
    }

    /** 记录质量分，越大越好（移植 quality()） */
    fun quality(d: DecodeEvent): Double {
        var score = 0.0
        if (d.isDetailed) score += 100.0
        if (d.latitude != null && d.longitude != null) score += 40.0
        if (!d.msgTypeError) score += 20.0
        if (d.routeValid) score += 10.0
        if (d.loco.isNotEmpty() && d.loco != "----") score += 15.0
        if (d.route.isNotEmpty() && d.route != "----") score += 10.0
        if (d.speed != "---" && d.speed.isNotEmpty()) score += 5.0
        if (d.position != "---.-" && d.position.isNotEmpty()) score += 5.0
        // RSSI 只作为同分时的微弱权重 (0~1)
        score += (d.rssi + 140.0).coerceIn(0.0, 60.0) / 60.0
        return score
    }

    /** 返回要放行的记录（可能沿用窗口内 uid），null 表示丢弃 */
    fun apply(d: DecodeEvent): DecodeEvent? {
        val key = keyOf(d)
        if (key.isEmpty()) return d
        val now = if (d.timestamp > 0) d.timestamp else System.currentTimeMillis() / 1000.0
        if (window <= 0) {   // 关闭去重：仍分配 uid，便于 DB 唯一标识
            return d.copy(uid = "%s-%.3f".format(Locale.US, key.replace("|", "-"), now))
        }
        var slot = slots[key]
        if (slot != null && now - slot.ts > window) slot = null
        if (slot == null) {
            val uid = "%s-%.3f".format(Locale.US, key.replace("|", "-"), now)
            slots[key] = Slot(uid, now, quality(d))
            prune(now)
            return d.copy(uid = uid)
        }
        val score = quality(d)
        // 只有明显更优才替换（避免 RSSI 抖动导致反复刷新）
        if (score > slot.score + 3.0) {
            slot.score = score
            upgraded++
            return d.copy(uid = slot.uid)
        }
        dropped++
        return null
    }

    private fun prune(now: Double) {
        if (slots.size <= maxSlots) return
        val expire = now - window * 4
        slots.entries.removeAll { it.value.ts < expire }
    }

    fun reset() = slots.clear()
}
