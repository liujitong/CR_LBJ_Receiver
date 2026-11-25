package xyz.mlxkj.crlbj.data

import org.json.JSONObject
import java.io.File
import java.util.Locale

/**
 * 机车配属查询（安卓端 = 桌面端 `cr_lbj/data/loco_roster.py` 的 1:1 移植）。
 *
 * 数据来自 `shared/data/`（两端同一份文件）：
 *
 *     loco_types.csv    机车代号 → 短型号 / 中文名
 *     loco_roster.csv   机车型号 + 号段 → 配属单位（路局/机务段）、制造厂
 *     loco_specs.json   机车型号 → 技术参数（轴式/功率/构造速度/简介）
 *
 * 三条查询路径：
 *     shortCode(code)             报文里的「机车代号」(如 240) → 短型号
 *     lookup(model, number)       短型号 + 机车号 → 配属局段（号段表命中）
 *     lookupLoco(text, code)      解码结果里的 "HXD1D-0123" + 代号 → 一次拿全
 *
 * 设计约定（与桌面端严格一致，改这里必须同步桌面端）：
 *  - 型号一律用**短型号**（DF4 / SS4 / HXD1D），与 loco_roster.csv 第一列对齐；
 *  - 号段是闭区间，命中即返回第一条，其余放进 `alternatives` 供界面提示歧义；
 *  - 找不到号段 ≠ 型号不存在：`exact=false` 时界面显示「配属未知」而不是「无此机车」；
 *  - 别名只有 DF4B→DF4、DF4R→DF4，**不做泛化前缀回退**（HXD1D 绝不能退成 HXD1）。
 */
class LocoRoster(private val assets: SharedAssets) {

    /** 号段表一行 */
    data class Range(
        val start: Int,
        val end: Int,
        val depot: String,
        val remark: String,
        val maker: String,
    ) {
        val text: String get() = "${start}-$end"
    }

    /** 查询结果（字段对应桌面端 lookup() 的 dict） */
    data class Lookup(
        val ok: Boolean,
        val exact: Boolean,
        val model: String,
        val number: Int?,
        val numberText: String,
        val depot: String = "",
        val maker: String = "",
        val remark: String = "",
        val range: String = "",
        val alternatives: List<Range> = emptyList(),
        val reason: String = "",
        val suggest: List<String> = emptyList(),
        val aliasFrom: String? = null,
        /** 报文代号查到的中文名（如 韶山4） */
        val name: String = "",
    ) {
        /** 一行摘要（列表/日志用） */
        fun summary(): String {
            val head = listOf(model, numberText).filter { it.isNotBlank() }.joinToString(" ")
            if (!ok) return "$head → ${reason.ifEmpty { "未知" }}".trim()
            if (exact) {
                return buildString {
                    append(head)
                    append(" → ")
                    append(depot.ifEmpty { "（原表未标注配属）" })
                    if (range.isNotEmpty()) append("（号段 $range）")
                }
            }
            return "$head → 配属未知（${reason.ifEmpty { "未命中号段" }}）"
        }
    }

    /** 技术参数（loco_specs.json 的 models[型号]） */
    data class Spec(
        val model: String,
        val name: String,
        val type: String,
        val maker: String,
        val axle: String,
        val power: String,
        val speed: String,
        val brief: String,
    ) {
        val empty: Boolean get() = name.isBlank() && brief.isBlank() && axle.isBlank()
    }

    /** 数据概况（设置页展示） */
    data class Stats(
        val rows: Int,
        val models: Int,
        val emptyDepot: Int,
        val origin: String,
        val revision: String,
    )

    // ------------------------------------------------------------------ 装载
    private val types: TypeTable by lazy { parseTypes(assets.read(TYPES_FILE)) }

    private val roster: Map<String, List<Range>> by lazy { parseRoster(assets.read(ROSTER_FILE)) }

    private val specsRoot: JSONObject? by lazy {
        runCatching { JSONObject(assets.read(SPECS_FILE) ?: "{}") }.getOrNull()
    }

    private var cachedStats: Stats? = null

    /** 号段表是否可用（缺文件时界面降级） */
    val available: Boolean get() = roster.isNotEmpty()

    fun stats(): Stats {
        cachedStats?.let { return it }
        var rows = 0
        var emptyDepot = 0
        roster.values.forEach { list ->
            rows += list.size
            emptyDepot += list.count { it.depot.isBlank() }
        }
        val st = Stats(
            rows = rows,
            models = roster.size,
            emptyDepot = emptyDepot,
            origin = assets.origin(ROSTER_FILE),
            revision = specsRoot?.optString("revision").orEmpty(),
        )
        cachedStats = st
        return st
    }

    /** 丢缓存（数据更新后调用） */
    fun invalidate() {
        cachedStats = null
    }

    // -------------------------------------------------------- 代号 → 短型号
    /** 报文代号 → 中文显示名（查不到返回空串） */
    fun typeName(code: String?): String {
        val key = (code ?: "").trim()
        if (key.isEmpty()) return ""
        return types.nameByCode[key].orEmpty()
    }

    /**
     * 把「代号」或「中文名/短型号」统一成短型号（DF4/SS4/HXD1D）。
     *
     * @param code 报文里的机车代号（优先，最可靠）
     * @param name 型号文本（可能是短型号，也可能是「韶山4」这类中文名）
     */
    fun shortCode(code: String? = null, name: String? = null): String {
        val byCode = (code ?: "").trim()
        if (byCode.isNotEmpty()) {
            types.shortByCode[byCode]?.let { if (it.isNotEmpty()) return it.uppercase(Locale.US) }
        }
        val s = (name ?: "").trim()
        if (s.isEmpty() || s in PLACEHOLDERS) return ""
        types.shortByShort[s.uppercase(Locale.US)]?.let { return it.uppercase(Locale.US) }
        types.shortByName[s]?.let { return it.uppercase(Locale.US) }
        return s.uppercase(Locale.US)
    }

    /** 全部已收录型号（排序） */
    fun models(): List<String> = roster.keys.sorted()

    /** 某型号的全部号段（按起号排序） */
    fun rangesOf(model: String): List<Range> =
        roster[model.trim().uppercase(Locale.US)] ?: emptyList()

    /** 号段表没收录该型号时给出「开头相同」的候选（只作提示，不自动采用） */
    fun suggestModels(model: String?, limit: Int = 4): List<String> {
        val key = (model ?: "").trim().uppercase(Locale.US)
        if (key.isEmpty()) return emptyList()
        return roster.keys
            .filter { it != key && (it.startsWith(key) || key.startsWith(it)) }
            .sortedWith(compareBy({ kotlin.math.abs(it.length - key.length) }, { it }))
            .take(limit)
    }

    /** 型号短码 → 中文名 */
    fun modelDisplayName(model: String?): String {
        val m = (model ?: "").trim().uppercase(Locale.US)
        if (m.isEmpty()) return ""
        return types.nameByShort[m] ?: m
    }

    // ------------------------------------------------------------ 主查询
    fun lookup(model: String?, number: String?): Lookup {
        var m = shortCode(name = model)
        val n = parseNumber(number)
        if (m.isEmpty()) {
            return Lookup(false, false, "", n, number?.toString().orEmpty(),
                reason = "缺少机车型号")
        }
        val asked = m
        var aliasFrom: String? = null
        if (m !in roster && m in MODEL_ALIASES) {
            aliasFrom = asked
            m = MODEL_ALIASES.getValue(m)
        }
        val ranges = roster[m]
        if (ranges.isNullOrEmpty()) {
            return Lookup(false, false, m, n, number?.toString().orEmpty(),
                reason = "配属号段表未收录该型号",
                suggest = suggestModels(asked), aliasFrom = aliasFrom,
                name = modelDisplayName(asked))
        }
        // 与桌面端一致：型号在表里就算 ok（界面显示「配属未知」而不是「无此机车」），
        // exact 才代表号段命中。差别很关键——新造车号没收录不代表型号不存在。
        if (n == null) {
            return Lookup(true, false, m, null, number?.toString().orEmpty(),
                reason = "缺少机车编号（只有车型信息）",
                aliasFrom = aliasFrom, name = modelDisplayName(m))
        }
        val hits = ranges.filter { n >= it.start && n <= it.end }
        if (hits.isEmpty()) {
            return Lookup(true, false, m, n, number.toString(),
                reason = "号段表内无该编号（可能新造/未收录）",
                aliasFrom = aliasFrom, name = modelDisplayName(m))
        }
        val first = hits.first()
        return Lookup(
            ok = true, exact = true, model = m, number = n, numberText = number.toString(),
            depot = first.depot, maker = first.maker, remark = first.remark,
            range = first.text, alternatives = hits.drop(1),
            aliasFrom = aliasFrom, name = modelDisplayName(m),
        )
    }

    /** 解码结果 → 配属。`locoCode` 是报文里的机车代号（如 "240"），最可靠。 */
    fun lookupLoco(locoText: String?, locoCode: String?): Lookup {
        val (modelFromText, num) = parseLocoText(locoText)
        var model = if ((locoCode ?: "").trim() in PLACEHOLDERS) "" else shortCode(code = locoCode)
        if (model.isEmpty()) model = shortCode(name = modelFromText)
        val res = lookup(model, num)
        return res.copy(name = typeName(locoCode).ifEmpty { res.name })
    }

    // ------------------------------------------------------------ 技术参数
    fun specsFor(model: String?): Spec? {
        val models = specsRoot?.optJSONObject("models") ?: return null
        val key = shortCode(name = model)
        if (key.isEmpty()) return null
        val direct = models.optJSONObject(key) ?: models.keys()
            .asSequence()
            .sortedByDescending { it.length }
            .firstOrNull { key.startsWith(it) }
            ?.let { models.optJSONObject(it) }
            ?: return null
        return Spec(
            model = key,
            name = direct.optString("name"),
            type = direct.optString("type"),
            maker = direct.optString("maker"),
            axle = direct.optString("axle"),
            power = direct.optString("power"),
            speed = direct.optString("speed"),
            brief = direct.optString("brief"),
        )
    }

    /** 参数表元信息（关于/设置页展示） */
    fun specsMeta(): Pair<String, String> =
        (specsRoot?.optString("revision").orEmpty()) to (specsRoot?.optString("source").orEmpty())

    companion object {
        const val ROSTER_FILE = "loco_roster.csv"
        const val TYPES_FILE = "loco_types.csv"
        const val SPECS_FILE = "loco_specs.json"
        const val PLACES_FILE = "places.csv"

        /** 报文里的「未知型号」占位符，查询时当作没给 */
        private val PLACEHOLDERS = setOf("", "----", "---", "未知型号", "None", "none")

        /**
         * 号段表把「东风4B」并入 DF4 统计（DF4 有 2000+ 行，DF4B/DF4R 都在其号段内）。
         * 只放**确定合并**的别名，不做泛化前缀回退——HXD1D 绝不能退成 HXD1。
         */
        private val MODEL_ALIASES = mapOf("DF4B" to "DF4", "DF4R" to "DF4")

        private val LOCO_RE = Regex(
            "^(?<model>[A-Za-z][A-Za-z0-9\\-]*?)\\s*[-_ ]?\\s*(?<num>\\d{1,6})$")
        private val LOOSE_RE = Regex("^(?<model>.*?)[-_]?(?<num>\\d{1,6})$")

        /** 去掉非数字后转 int（"0123" → 123，"HXD1D-0123" 的号部分） */
        fun parseNumber(raw: String?): Int? {
            val digits = (raw ?: "").filter { it.isDigit() }
            return digits.toIntOrNull()
        }

        /**
         * 把 "HXD1D-0123" / "HXD1D0123" / "韶山4-0123" 拆成 (型号, 号)。
         * 型号可能是中文名（韶山4），交给 [shortCode] 再归一。
         */
        fun parseLocoText(text: String?): Pair<String, String?> {
            val s = (text ?: "").trim().replace(" ", "")
            if (s.isEmpty() || s in PLACEHOLDERS) return "" to null
            LOCO_RE.matchEntire(s)?.let { m ->
                return m.groups["model"]!!.value to m.groups["num"]!!.value
            }
            LOOSE_RE.matchEntire(s)?.let { m ->
                return m.groups["model"]!!.value to m.groups["num"]!!.value
            }
            return s to null
        }

        /**
         * 代号/名称索引表。分开四个 map，避免「代号 240」与「中文名 韶山4」共用一个
         * 前缀键空间（扁平字符串 map 曾把 `name:<code>` 与 `name:<中文名>` 混在一起）。
         */
        data class TypeTable(
            /** 报文代号 → 短型号（"240" → "SS4"） */
            val shortByCode: Map<String, String> = emptyMap(),
            /** 报文代号 → 中文名（"240" → "韶山4"） */
            val nameByCode: Map<String, String> = emptyMap(),
            /** 短型号大写 → 短型号（"SS4" → "SS4"，用于统一大小写） */
            val shortByShort: Map<String, String> = emptyMap(),
            /** 中文名 → 短型号（"韶山4" → "SS4"） */
            val shortByName: Map<String, String> = emptyMap(),
            /** 短型号大写 → 中文名（"SS4" → "韶山4"） */
            val nameByShort: Map<String, String> = emptyMap(),
        )

        /** loco_types.csv → [TypeTable] */
        fun parseTypes(csv: String?): TypeTable {
            if (csv.isNullOrBlank()) return TypeTable()
            val shortByCode = HashMap<String, String>(256)
            val nameByCode = HashMap<String, String>(256)
            val shortByShort = HashMap<String, String>(256)
            val shortByName = HashMap<String, String>(256)
            val nameByShort = HashMap<String, String>(256)
            csv.lineSequence().forEach { line ->
                val t = line.trim()
                if (t.isEmpty() || t.startsWith("#")) return@forEach
                val cols = t.split(',')
                if (cols.size < 3) return@forEach
                val code = cols[0].trim()
                if (code.isEmpty() || code == "code") return@forEach
                val short = cols[1].trim()
                val name = cols[2].trim()
                if (short.isEmpty()) return@forEach
                val key = short.uppercase(Locale.US)
                shortByCode[code] = short
                if (name.isNotEmpty()) nameByCode[code] = name
                shortByShort.putIfAbsent(key, short)
                if (name.isNotEmpty()) shortByName.putIfAbsent(name, short)
                nameByShort.putIfAbsent(key, name)
            }
            return TypeTable(shortByCode, nameByCode, shortByShort, shortByName, nameByShort)
        }

        /** loco_roster.csv → 型号 → 号段列表（按起号排序） */
        fun parseRoster(csv: String?): Map<String, List<Range>> {
            if (csv.isNullOrBlank()) return emptyMap()
            val idx = HashMap<String, MutableList<Range>>(512)
            csv.lineSequence().forEach { line ->
                val t = line.trim()
                if (t.isEmpty() || t.startsWith("#")) return@forEach
                val cols = t.split(',')
                if (cols.size < 4) return@forEach
                val model = cols[0].trim().uppercase(Locale.US)
                val a = parseNumber(cols[1])
                val b = parseNumber(cols[2])
                if (model.isEmpty() || a == null || b == null) return@forEach
                val depot = cols[3].trim()
                val remark = cols.getOrNull(4)?.trim().orEmpty()
                val maker = cols.getOrNull(5)?.trim().orEmpty()
                idx.getOrPut(model) { ArrayList() }
                    .add(Range(minOf(a, b), maxOf(a, b), depot, remark, maker))
            }
            return idx.mapValues { (_, v) -> v.sortedBy { it.start } }
        }
    }
}

/** 便捷：从 Context 构造（应用内单例见 [LocoRosterHolder]） */
object LocoRosterHolder {
    @Volatile private var instance: LocoRoster? = null

    fun get(assets: SharedAssets): LocoRoster =
        instance ?: synchronized(this) {
            instance ?: LocoRoster(assets).also { instance = it }
        }

    /** 数据更新后重建索引 */
    fun refresh(assets: SharedAssets): LocoRoster = synchronized(this) {
        instance?.invalidate()
        val fresh = LocoRoster(assets)
        instance = fresh
        fresh
    }

    /** 单元测试用：替换实现 */
    fun setForTest(roster: LocoRoster?) {
        synchronized(this) { instance = roster }
    }

    fun current(): LocoRoster? = instance

    /** 从本地目录装载（单元测试/离线校验用） */
    fun fromDir(dir: File): LocoRoster = LocoRoster(object : SharedAssets {
        override fun read(name: String): String? =
            File(dir, name).takeIf { it.isFile }?.readText(Charsets.UTF_8)

        override fun origin(name: String): String =
            if (File(dir, name).isFile) "本地目录" else ORIGIN_MISSING
    })
}
