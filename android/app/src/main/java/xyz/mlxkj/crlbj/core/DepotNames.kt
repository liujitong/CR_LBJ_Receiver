package xyz.mlxkj.crlbj.core

import java.util.Locale

/**
 * 配属单位 / 制造厂名称的全称化（v3.2.8 自桌面 `cr_lbj/data/depot_names.py` 移植）。
 *
 * **双端一致**：表与算法逐条对齐 Python 版（同一份人工核对数据，改表必须双端同步）：
 *  * `shared/data/loco_roster.csv` 的配属单位沿用号段表简称（南局南段/上局沪段…），
 *    这里翻译成「南昌局南昌机务段」式全称；没收录的写法**原样返回**，绝不猜。
 *  * RailGo 的担当局/担当段同样走这里拼全称。
 *
 * 纯数据 + 纯函数，不依赖 Android Framework，可直接跑 JVM 单测。
 */
object DepotNames {

    /** 局简称 → 全称局名（不含「集团」二字，与用户要求的写法一致） */
    private val BUREAUS = mapOf(
        "哈" to "哈尔滨局", "沈" to "沈阳局", "京" to "北京局", "呼" to "呼和浩特局",
        "太" to "太原局", "济" to "济南局", "郑" to "郑州局", "上" to "上海局",
        "武" to "武汉局", "西" to "西安局", "乌" to "乌鲁木齐局", "南" to "南昌局",
        "成" to "成都局", "昆" to "昆明局", "兰" to "兰州局", "宁" to "南宁局",
        "柳" to "柳州局", "广" to "广州局", "齐" to "齐齐哈尔局",
    )

    /** 号段表配属简称 → 全称配属单位（只收录核对过的标准写法） */
    private val DEPOTS = mapOf(
        // 哈尔滨局
        "哈局哈段" to "哈尔滨局哈尔滨机务段",
        "哈局三段" to "哈尔滨局三棵树机务段",
        "哈局齐段" to "哈尔滨局齐齐哈尔机务段",
        // 沈阳局
        "沈局沈段" to "沈阳局沈阳机务段",
        "沈局苏段" to "沈阳局苏家屯机务段",
        "沈局锦段" to "沈阳局锦州机务段",
        "沈局吉段" to "沈阳局吉林机务段",
        "沈局辽段" to "沈阳局通辽机务段",
        "沈局通段" to "沈阳局通辽机务段",
        // 北京局
        "京局京段" to "北京局北京机务段",
        "京局丰段" to "北京局丰台机务段",
        "京局唐段" to "北京局唐山机务段",
        "京局石段" to "北京局石家庄电力机务段",
        "京局怀段" to "北京局怀柔北机务段",
        "京局津段" to "北京局天津机务段",
        "京局邯段" to "北京局邯郸机务段",
        "京局洞段" to "北京局洞庙河机务段",
        // 济南局 / 上海局
        "济局济段" to "济南局济南机务段",
        "济局西段" to "济南局济南西机务段",
        "济局青段" to "济南局青岛机务段",
        "济局徐段" to "济南局徐州机务段",
        "上局沪段" to "上海局上海机务段",
        "上局杭段" to "上海局杭州机务段",
        "上局宁东段" to "上海局南京东机务段",
        "上局合段" to "上海局合肥机务段",
        "上局阜段" to "上海局阜阳机务段",
        "上局徐段" to "上海局徐州机务段",
        "上局宁段" to "上海局南京机务段",
        "上局翔段" to "上海局南翔机务段",
        "上局金段" to "上海局金华机务段",
        "上局芜段" to "上海局芜湖机务段",
        "上局蚌段" to "上海局蚌埠机务段",
        // 南昌局
        "南局南段" to "南昌局南昌机务段",
        "南局向段" to "南昌局向塘机务段",
        "南局塘段" to "南昌局向塘机务段",
        "南局福段" to "南昌局福州机务段",
        "南局鹰段" to "南昌局鹰潭机务段",
        // 郑州局
        "郑局郑段" to "郑州局郑州机务段",
        "郑局洛段" to "郑州局洛阳机务段",
        "郑局乡段" to "郑州局新乡机务段",
        "郑局新段" to "郑州局新乡机务段",
        // 武汉局
        "武局江段" to "武汉局江岸机务段",
        "武局南段" to "武汉局武昌南机务段",
        "武局襄段" to "武汉局襄阳机务段",
        // 广州局（广铁）
        "广铁广段" to "广州局广州机务段",
        "广铁深段" to "广州局深圳机务段",
        "广铁株段" to "广州局株洲机务段",
        "广铁怀段" to "广州局怀化机务段",
        "广铁龙段" to "广州局龙川机务段",
        "广铁三段" to "广州局三水机务段",
        "广铁海段" to "广州局海口机务段",
        "广铁长段" to "广州局长沙机务段",
        "广局广段" to "广州局广州机务段",
        "广局长段" to "广州局长沙机务段",
        "广局海段" to "广州局海口机务段",
        // 南宁局（原柳州局）
        "宁局邕段" to "南宁局南宁机务段",
        "宁局柳段" to "南宁局柳州机务段",
        "柳局柳段" to "柳州局柳州机务段",
        "柳局邕段" to "柳州局南宁机务段",
        // 西安局
        "西局西段" to "西安局西安机务段",
        "西局新段" to "西安局新丰镇机务段",
        "西局安段" to "西安局安康机务段",
        // 成都局
        "成局成段" to "成都局成都机务段",
        "成局重段" to "成都局重庆机务段",
        "成局贵段" to "成都局贵阳机务段",
        "成局西段" to "成都局西昌机务段",
        "成局六段" to "成都局六盘水机务段",
        "成局南段" to "成都局南充机务段",
        // 昆明局
        "昆局昆段" to "昆明局昆明机务段",
        "昆局开段" to "昆明局开远机务段",
        // 兰州局
        "兰局兰段" to "兰州局兰州西机务段",
        "兰局西段" to "兰州局兰州西机务段",
        "兰局嘉段" to "兰州局嘉峪关机务段",
        "兰局迎段" to "兰州局迎水桥机务段",
        "兰局桥段" to "兰州局迎水桥机务段",
        // 太原局
        "太局太段" to "太原局太原机务段",
        "太局原段" to "太原局太原北机务段",
        "太局湖段" to "太原局湖东机务段",
        "太局侯段" to "太原局侯马北机务段",
        "太局候段" to "太原局侯马北机务段",
        // 呼和浩特局
        "呼局包段" to "呼和浩特局包头西机务段",
        "呼局集段" to "呼和浩特局集宁机务段",
        "呼局呼段" to "呼和浩特局呼和浩特机务段",
        // 乌鲁木齐局
        "乌局乌段" to "乌鲁木齐局乌鲁木齐机务段",
        "乌局库段" to "乌鲁木齐局库尔勒机务段",
        "乌局柳段" to "乌鲁木齐局柳园机务段",
        // 青藏公司 / 其他
        "青藏宁段" to "青藏集团公司西宁机务段",
        "青藏格段" to "青藏集团公司格尔木机务段",
        "齐局加段" to "齐齐哈尔局加格达奇机务段",
    )

    /** 制造厂短名 → 公司全称 */
    private val MAKERS = mapOf(
        "中车大连机车" to "中车大连机车车辆有限公司",
        "中车株洲机车" to "中车株洲电力机车有限公司",
        "中车资阳机车" to "中车资阳机车有限公司",
        "中车青岛四方" to "中车青岛四方机车车辆股份有限公司",
        "中车大同机车" to "中车大同电力机车有限公司",
        "中车戚墅堰机车" to "中车戚墅堰机车有限公司",
        "中车唐山机车" to "中车唐山机车车辆有限公司",
        "中车南京浦镇" to "中车南京浦镇车辆有限公司",
        "中车长客股份" to "中车长春轨道客车股份有限公司",
        "中车长春客车" to "中车长春轨道客车股份有限公司",
        "中车广东江门" to "中车广东轨道交通车辆有限公司",
        "中车太原机车" to "中车太原机车车辆有限公司",
        "中车青岛四方客车" to "中车青岛四方机车车辆股份有限公司",
        "北京二七机车厂" to "中车北京二七机车有限公司",
        "大同电力机车" to "中车大同电力机车有限公司",
        "中车四方" to "中车青岛四方机车车辆股份有限公司",
        "中车株洲" to "中车株洲电力机车有限公司",
        "中车大连" to "中车大连机车车辆有限公司",
        "中车大同" to "中车大同电力机车有限公司",
        "中车唐山" to "中车唐山机车车辆有限公司",
        "中车长客" to "中车长春轨道客车股份有限公司",
        "中车兰州" to "中车兰州机车有限公司",
        "中车太原" to "中车太原机车车辆有限公司",
        "中车洛阳" to "中车洛阳机车有限公司",
        "中车戚墅堰" to "中车戚墅堰机车有限公司",
        // 短写（号段表/车型参数里只写两字）
        "大连" to "中车大连机车车辆有限公司",
        "株洲" to "中车株洲电力机车有限公司",
        "大同" to "中车大同电力机车有限公司",
        "戚墅堰" to "中车戚墅堰机车有限公司",
        "四方" to "中车青岛四方机车车辆股份有限公司",
        "唐山" to "中车唐山机车车辆有限公司",
    )

    /** 这些不是配属/制造厂名称，不要硬翻（与桌面 _PLACEHOLDERS 一致） */
    private val PLACEHOLDERS = setOf(
        "", "----", "---", "—", "暂无数据", "未知", "不详",
        "配属未知", "未知配属", "暂无局段", "局段未知",
    )

    /** 括号备注切分：`京局丰段（京铁运输）` → 主名 + 备注（对齐 Python _TAIL_RE） */
    private val TAIL_RE = Regex("^(?<base>[^（(]+)(?<tail>.*)$")
    private val MAKER_SPLIT_RE = Regex("\\s*[/|、]\\s*")

    private fun clean(value: Any?): String =
        (value?.toString() ?: "").trim()

    /** X局 前缀命中（对齐 Python _BUREAU_RE = `^(哈|沈|…)局`） */
    private fun bureauPrefix(s: String): String? =
        BUREAUS.keys.firstOrNull { s.startsWith(it + "局") }

    /**
     * 局简称 → 全称局名；已是全称/未知写法时原样返回。
     * `南局` → `南昌局`、`京局` → `北京局`；`南昌局集团公司` 不动。
     */
    fun fullBureau(text: Any?): String {
        val s = clean(text)
        if (s.isEmpty()) return ""
        val b = bureauPrefix(s) ?: return s
        return BUREAUS[b]!! + s.substring(2)
    }

    /** 号段表配属简称 → 全称配属单位（查不到原样返回，绝不猜）。 */
    fun fullDepot(text: Any?): String {
        val s = clean(text)
        if (s.isEmpty() || s in PLACEHOLDERS) return s
        val m = TAIL_RE.matchEntire(s)
        val base = m?.groups?.get("base")?.value?.trim() ?: s
        val tail = m?.groups?.get("tail")?.value ?: ""
        DEPOTS[base]?.let { return it + tail }
        val b = bureauPrefix(base)
        if (b != null) {
            // 只写了局（如 `哈局`）：补全成 `哈尔滨局`
            val rest = base.substring(2)          // 去掉「X局」两个字
            if (rest.isEmpty()) return BUREAUS[b]!! + tail
            // 形如 `沈局锦州车辆段`：局名是简称、段名本身已是完整地名 → 只换局名。
            // 2 字及以下（`南段`/`沪段`）仍属配属简称，没收录就原样返回，不拼半截。
            if (rest.length > 2 && (rest.endsWith("段") || rest.endsWith("所"))) {
                return BUREAUS[b]!! + rest + tail
            }
        }
        return s
    }

    /** 制造厂短名 → 公司全称；多厂并列逐个翻译，未知写法原样返回。 */
    fun fullMaker(text: Any?): String {
        val s = clean(text)
        if (s.isEmpty() || s in PLACEHOLDERS) return s
        val parts = MAKER_SPLIT_RE.split(s)
        val out = parts.map { it.trim() }.filter { it.isNotEmpty() }
            .map { MAKERS[it] ?: it }
        return if (out.isNotEmpty()) out.joinToString(" / ") else s
    }

    /**
     * 车次担当单位全称：`担当局 + 担当段` 直接拼接（不缩写）。
     * 兼容 `南昌局` + `南昌客运段` → `南昌局南昌客运段`；
     * runner 已自带局名则不重复拼接。
     */
    fun formatDuty(bureau: Any?, runner: Any?): String {
        val b = fullBureau(bureau)
        val r = fullBureau(runner)
        if (b.isEmpty()) return r
        if (r.isEmpty()) return b
        if (r.startsWith(b) || b in r) return r
        return b + r
    }

    /** 始发 → 终到（缺一边时只显示已有的一边）。 */
    fun formatTrainRange(start: Any?, end: Any?): String {
        val a = clean(start)
        val b = clean(end)
        return if (a.isNotEmpty() && b.isNotEmpty()) "$a → $b" else a.ifEmpty { b }
    }

    /**
     * 车次信息行拼接（对齐桌面 info_lookup.train_display 的展示口径：
     * 等级 / 担当 / 配属 / 车型 / 区间）。仅做文案拼装，不做网络查询。
     */
    fun dutyLine(bureau: String?, runner: String?): String {
        val d = formatDuty(bureau, runner)
        return if (d.isEmpty()) "—" else d
    }

    /** 数值文本按设备语言环境（保持与桌面无 Locale 差异，统一 US） */
    fun fmt1(v: Double): String =
        String.format(Locale.US, "%.1f", v).trimEnd('0').trimEnd('.')
}