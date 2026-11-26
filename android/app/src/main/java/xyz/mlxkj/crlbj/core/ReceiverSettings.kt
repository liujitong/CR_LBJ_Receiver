package xyz.mlxkj.crlbj.core

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/**
 * 一条可切换的「数据源」配置（v3.2.5 多数据源）。
 *
 * 用户可以在设置里保存多套数据源（USB 棒 / 局域网 rtl_tcp / OWRX……），
 * 点一下即可切换——切换等价于把这一套参数展开到 [ReceiverSettings] 顶层字段，
 * 引擎与 DSP 链路只认顶层字段，所以切换后会自动重建链路。
 */
data class SourceProfile(
    val name: String = "数据源",
    /** usb | rtl_tcp | owrx */
    val type: String = "usb",
    val host: String = "127.0.0.1",
    val port: Int = 1234,
    val sampleRate: Int = 240000,
    val gainDb: Double = 19.7,
    val ppm: Double = 1.0,
    val dcOffsetHz: Double = 50000.0,
) {
    /** 界面显示名：USB 直连 / RTL-TCP / OWRX（统一由 RtlProfile 给出，v3.2.7） */
    val typeLabel: String
        get() = RtlProfile.typeLabel(type)

    /** 列表里的一行副标题：USB 不显示主机端口 */
    val detail: String
        get() = if (type == "usb") {
            "%s · %d kS/s".format(typeLabel, sampleRate / 1000)
        } else {
            "%s · %s:%d".format(typeLabel, host, port)
        }

    fun toJson(): JSONObject = JSONObject().apply {
        put("name", name); put("type", type); put("host", host); put("port", port)
        put("sampleRate", sampleRate); put("gainDb", gainDb)
        put("ppm", ppm); put("dcOffsetHz", dcOffsetHz)
    }

    companion object {
        fun fromJson(o: JSONObject): SourceProfile = SourceProfile(
            name = o.optString("name", "数据源"),
            type = o.optString("type", "usb"),
            host = o.optString("host", "127.0.0.1"),
            port = o.optInt("port", 1234),
            sampleRate = o.optInt("sampleRate", 240000),
            gainDb = o.optDouble("gainDb", 19.7),
            ppm = o.optDouble("ppm", 1.0),
            dcOffsetHz = o.optDouble("dcOffsetHz", 50000.0),
        )
    }
}

/**
 * 接收设置（字段名与桌面版 lbj_config.json 同名，M3 设置页逐组接入编辑）。
 *
 * 默认值取桌面版 dist/lbj_config.json 的 OWRX 配置（模拟器/无 USB 棒可测）；
 * USB 模式默认 240 kS/s、dcOffset 50k、增益 19.7 dB（与桌面版射频参数一致）。
 */
data class ReceiverSettings(
    // 数据源：usb | rtl_tcp | owrx
    val sourceType: String = "owrx",
    val host: String = "127.0.0.1",
    val port: Int = 5678,
    // 射频
    val freqMhz: Double = 821.2375,
    val sampleRate: Int = 960000,
    val gainDb: Double = 15.7,
    val ppm: Double = 1.0,
    val dcOffsetHz: Double = 0.0,
    val bwKhz: Double = 35.0,
    val blockSize: Int = 65536,
    // RSSI 门控
    val rssiThresholdDb: Double = -55.0,
    val rssiHystDb: Double = 3.0,
    val rssiHoldMs: Double = 700.0,
    // AFC
    val afcEnable: Boolean = true,
    val afcMaxHz: Double = 8000.0,
    val afcGain: Double = 0.45,
    val keepAfcAfterPacket: Boolean = false,
    // 业务层
    val dedupeWindow: Double = 2.5,        // 同车次重复报文合并窗口(秒)
    val etaMaxMin: Double = 360.0,         // ETA 最大估算分钟数 (6h)
    val userKm: String = "",               // 本站公里标 (km)，空=未设置
    val routeKmText: String = "",          // 线路公里标: "线路=km,线路=km"
    // 地图（v3.0 起用 shared/web/railmap.html：OpenRailwayMap 铁路图层 + 可选底图）
    val mapZoom: Int = 11,
    val mapFollow: Boolean = true,          // 自动跟随最新列车
    val mapNight: Boolean = true,           // 深色底图
    /** 底图 id，与 railmap.html 的 BASE_SOURCES 对齐（amap/amap_img/baidu/baidu_sat/osm/tdt_vec/tdt_img） */
    val mapBase: String = "amap",
    /** 铁路图层 id：off / orm_standard / orm_maxspeed / orm_signals / orm_electrified / orm_gauge */
    val mapRail: String = "orm_standard",
    /** 铁路图层不透明度 0.2~1.0 */
    val mapRailOpacity: Double = 0.85,
    /** 天地图 tk（「浏览器端」类型）；空 = 天地图底图只提示不加载 */
    val mapTdtKey: String = "",
    /** 天地图 Referer 白名单域名（申请浏览器端 tk 时登记）；空 = 代拉瓦片时不附加 Referer */
    val tdtReferer: String = "",
    /** 默认中心：v3.2.8 起**只保留经纬度**（与桌面一致）。
     *  旧版 mapCenterName 字段已废弃删除；设置页选城市只是把 places.csv 的经纬度回填。 */
    val mapCenterLat: Double = 28.68,
    val mapCenterLng: Double = 115.86,
    // 查询
    /** 车次数据源：auto / railgo / 12306 */
    val trainQuerySource: String = "auto",
    /** 第三方数据（机车配属号段表）自动更新 */
    val dataAutoUpdate: Boolean = true,
    // ---- 多数据源（v3.2.5）：可保存多套配置，点一下切换 ----
    /** 已保存的数据源列表（至少一条） */
    val sources: List<SourceProfile> = DEFAULT_SOURCES,
    /** 当前使用第几条（0-based）；顶层 sourceType/host/... 是其展开值 */
    val activeSource: Int = 0,
) {
    val isUsb: Boolean get() = sourceType == "usb"

    /** 当前生效的数据源配置（越界时回退 0） */
    val currentSource: SourceProfile?
        get() = sources.getOrNull(activeSource)

    /**
     * 把顶层字段写回 [sources] 的当前项（编辑字段后保持列表与实际一致）。
     * 列表为空时原样返回。
     */
    fun withActiveSnapshot(): ReceiverSettings {
        if (sources.isEmpty()) return this
        val idx = activeSource.coerceIn(0, sources.size - 1)
        val updated = sources[idx].copy(
            type = sourceType, host = host, port = port, sampleRate = sampleRate,
            gainDb = gainDb, ppm = ppm, dcOffsetHz = dcOffsetHz,
        )
        return copy(
            sources = sources.toMutableList().also { it[idx] = updated },
            activeSource = idx,
        )
    }

    /** 切换到第 [index] 条数据源：把它的参数展开到顶层字段。 */
    fun selectSource(index: Int): ReceiverSettings {
        val prof = sources.getOrNull(index) ?: return this
        return copy(
            activeSource = index, sourceType = prof.type,
            host = prof.host, port = prof.port, sampleRate = prof.sampleRate,
            gainDb = prof.gainDb, ppm = prof.ppm, dcOffsetHz = prof.dcOffsetHz,
        )
    }

    /** 用当前顶层配置新建一条数据源并激活（原名可自定义）。 */
    fun addSourceFromCurrent(name: String = ""): ReceiverSettings {
        val base = withActiveSnapshot()
        val idx = base.sources.size
        val prof = SourceProfile(
            name = name.ifBlank { "数据源 ${idx + 1}" },
            type = sourceType, host = host, port = port, sampleRate = sampleRate,
            gainDb = gainDb, ppm = ppm, dcOffsetHz = dcOffsetHz,
        )
        return base.copy(sources = base.sources + prof, activeSource = idx)
    }

    /** 删除第 [index] 条（至少保留一条）；删的是当前项就切到第一条。 */
    fun removeSource(index: Int): ReceiverSettings {
        if (sources.size <= 1 || index !in sources.indices) return this
        val snapped = withActiveSnapshot()
        val list = snapped.sources.toMutableList().also { it.removeAt(index) }
        val nextActive = when {
            snapped.activeSource == index -> 0
            snapped.activeSource > index -> snapped.activeSource - 1
            else -> snapped.activeSource
        }
        return snapped.copy(sources = list).selectSource(nextActive)
    }

    /** 重命名第 [index] 条数据源。 */
    fun renameSource(index: Int, name: String): ReceiverSettings {
        val n = name.trim()
        if (n.isEmpty() || index !in sources.indices) return this
        val list = sources.toMutableList()
        list[index] = list[index].copy(name = n)
        return copy(sources = list)
    }

    /** 硬件实际调谐频率 = 目标 − DC 偏移（USB 模式扣 50k 让 DDC 落在目标频点） */
    val hwFreqHz: Long get() = (freqMhz * 1e6).toLong() - dcOffsetHz.toLong()

    /** nativeInit / nativeSetParams 参数 JSON（与桌面版 lbj_config 同名字段） */
    fun toParamsJson(): String = JSONObject().apply {
        put("freqMhz", freqMhz)
        put("sampleRate", sampleRate)
        put("bwKhz", bwKhz)
        put("dcOffsetHz", dcOffsetHz)
        put("userOffsetHz", 0.0)
        put("gainDb", gainDb)
        put("ppm", ppm)
        put("blockSize", blockSize)
        put("rssiThresholdDb", rssiThresholdDb)
        put("rssiHystDb", rssiHystDb)
        put("rssiHoldMs", rssiHoldMs)
        put("afcEnable", afcEnable)
        put("afcMaxHz", afcMaxHz)
        put("afcGain", afcGain)
        put("keepAfcAfterPacket", keepAfcAfterPacket)
        put("baudRate", 1200.0)
    }.toString()
    companion object {
        /** 现行底图 id 全集（与 railmap.html BASE_SOURCES 一致）；旧配置里的废弃 id 读取时回退默认 */
        val KNOWN_BASES = setOf("amap", "amap_img", "baidu", "baidu_sat", "osm", "tdt_vec", "tdt_img")

        /** 默认多数据源：USB 直连 / 本地 RTL-TCP / OWRX，可在设置里增删切换 */
        val DEFAULT_SOURCES = listOf(
            SourceProfile("本机 USB 直连", "usb", sampleRate = 240000,
                gainDb = 19.7, ppm = 1.0, dcOffsetHz = 50000.0),
            SourceProfile("本地 RTL-TCP", "rtl_tcp", host = "127.0.0.1", port = 1234,
                sampleRate = 960000, gainDb = 15.7, ppm = 1.0, dcOffsetHz = 50000.0),
            SourceProfile("OWRX 服务器", "owrx", host = "127.0.0.1", port = 8073,
                sampleRate = 960000, gainDb = 15.7, ppm = 1.0, dcOffsetHz = 0.0),
        )

        /** USB 直连推荐参数（桌面版 rtl_usb 档位） */
        val USB_DEFAULTS = ReceiverSettings(
            sourceType = "usb", sampleRate = 240000, gainDb = 19.7,
            dcOffsetHz = 50000.0,
        )
        val OWRX_DEFAULTS = ReceiverSettings()

        fun load(ctx: Context): ReceiverSettings {
            val sp: SharedPreferences = ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE)
            val d = OWRX_DEFAULTS
            // v3.2.5：没有 sources 键 = 从旧版本升级上来，稍后用当前配置生成第一条
            val hasSources = sp.contains("sources")
            val loadedSources = parseSources(sp.getString("sources", null), d)
            val loaded = ReceiverSettings(
                sourceType = sp.getString("sourceType", d.sourceType) ?: d.sourceType,
                host = sp.getString("host", d.host) ?: d.host,
                port = sp.getInt("port", d.port),
                freqMhz = Double.fromBits(sp.getLong("freqMhz", d.freqMhz.toRawBits())),
                sampleRate = sp.getInt("sampleRate", d.sampleRate),
                gainDb = Double.fromBits(sp.getLong("gainDb", d.gainDb.toRawBits())),
                ppm = Double.fromBits(sp.getLong("ppm", d.ppm.toRawBits())),
                dcOffsetHz = Double.fromBits(sp.getLong("dcOffsetHz", d.dcOffsetHz.toRawBits())),
                bwKhz = Double.fromBits(sp.getLong("bwKhz", d.bwKhz.toRawBits())),
                blockSize = sp.getInt("blockSize", d.blockSize),
                rssiThresholdDb = Double.fromBits(sp.getLong("rssiThresholdDb", d.rssiThresholdDb.toRawBits())),
                rssiHystDb = Double.fromBits(sp.getLong("rssiHystDb", d.rssiHystDb.toRawBits())),
                rssiHoldMs = Double.fromBits(sp.getLong("rssiHoldMs", d.rssiHoldMs.toRawBits())),
                afcEnable = sp.getBoolean("afcEnable", d.afcEnable),
                afcMaxHz = Double.fromBits(sp.getLong("afcMaxHz", d.afcMaxHz.toRawBits())),
                afcGain = Double.fromBits(sp.getLong("afcGain", d.afcGain.toRawBits())),
                keepAfcAfterPacket = sp.getBoolean("keepAfcAfterPacket", d.keepAfcAfterPacket),
                dedupeWindow = Double.fromBits(sp.getLong("dedupeWindow", d.dedupeWindow.toRawBits())),
                etaMaxMin = Double.fromBits(sp.getLong("etaMaxMin", d.etaMaxMin.toRawBits())),
                userKm = sp.getString("userKm", d.userKm) ?: d.userKm,
                routeKmText = sp.getString("routeKmText", d.routeKmText) ?: d.routeKmText,
                mapZoom = sp.getInt("mapZoom", d.mapZoom),
                mapFollow = sp.getBoolean("mapFollow", d.mapFollow),
                mapNight = sp.getBoolean("mapNight", d.mapNight),
                mapBase = (sp.getString("mapBase", d.mapBase) ?: d.mapBase)
                    .let { if (it in KNOWN_BASES) it else d.mapBase },
                mapRail = sp.getString("mapRail", d.mapRail) ?: d.mapRail,
                mapRailOpacity = Double.fromBits(
                    sp.getLong("mapRailOpacity", d.mapRailOpacity.toRawBits())),
                mapTdtKey = sp.getString("mapTdtKey", d.mapTdtKey) ?: d.mapTdtKey,
                tdtReferer = sp.getString("tdtReferer", d.tdtReferer) ?: d.tdtReferer,
                mapCenterLat = Double.fromBits(
                    sp.getLong("mapCenterLat", d.mapCenterLat.toRawBits())),
                mapCenterLng = Double.fromBits(
                    sp.getLong("mapCenterLng", d.mapCenterLng.toRawBits())),
                trainQuerySource = sp.getString("trainQuerySource", d.trainQuerySource)
                    ?: d.trainQuerySource,
                dataAutoUpdate = sp.getBoolean("dataAutoUpdate", d.dataAutoUpdate),
                sources = loadedSources,
                activeSource = sp.getInt("activeSource", 0)
                    .coerceIn(0, maxOf(0, loadedSources.size - 1)),
            )
            // USB 数据源不使用 host/port：把旧版本残留的网络服务器地址归一化回默认值，
            // 避免旧地址继续出现在启动日志/设置页里（也顺带做隐私清理）。
            val normalized = if (loaded.isUsb && loaded.host != d.host) {
                loaded.copy(host = d.host, port = d.port)
            } else {
                loaded
            }
            // 旧配置升级：没有多数据源列表时，用当前配置生成第一条（激活项），
            // 另附两种其它类型的参考项，用户可再增删。避免出现「列表说 USB 240k、
            // 下面字段却是 960k」的错位。
            return if (hasSources) normalized else normalized.copy(
                sources = legacySources(normalized), activeSource = 0)
        }

        /** 旧版配置升级成多数据源列表：当前配置放第一条，其余类型给默认参考项。 */
        private fun legacySources(s: ReceiverSettings): List<SourceProfile> {
            val nm = when (s.sourceType) {
                "usb" -> "本机 USB 直连"
                "owrx" -> "OWRX 服务器"
                else -> "本地 RTL-TCP"
            }
            val cur = SourceProfile(
                name = nm, type = s.sourceType, host = s.host, port = s.port,
                sampleRate = s.sampleRate, gainDb = s.gainDb,
                ppm = s.ppm, dcOffsetHz = s.dcOffsetHz)
            return listOf(cur) + DEFAULT_SOURCES.filter { it.type != s.sourceType }
        }

        /** 解析数据源列表 JSON；缺失/损坏/为空时回退默认三档。 */
        fun parseSources(json: String?, d: ReceiverSettings = OWRX_DEFAULTS): List<SourceProfile> {
            if (json.isNullOrBlank()) return d.sources
            return runCatching {
                val arr = JSONArray(json)
                val out = ArrayList<SourceProfile>(arr.length())
                for (i in 0 until arr.length()) {
                    out.add(SourceProfile.fromJson(arr.getJSONObject(i)))
                }
                out.ifEmpty { d.sources }
            }.getOrDefault(d.sources)
        }

        fun save(ctx: Context, s: ReceiverSettings) {
            val e = ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE).edit()
            e.putString("sourceType", s.sourceType)
            e.putString("host", s.host)
            e.putInt("port", s.port)
            // 多数据源列表（v3.2.5）：JSON 数组落盘；写之前先把顶层字段回写当前项
            val snapped = s.withActiveSnapshot()
            val arr = JSONArray()
            snapped.sources.forEach { arr.put(it.toJson()) }
            e.putString("sources", arr.toString())
            e.putInt("activeSource", snapped.activeSource)
            e.putLong("freqMhz", s.freqMhz.toRawBits())
            e.putInt("sampleRate", s.sampleRate)
            e.putLong("gainDb", s.gainDb.toRawBits())
            e.putLong("ppm", s.ppm.toRawBits())
            e.putLong("dcOffsetHz", s.dcOffsetHz.toRawBits())
            e.putLong("bwKhz", s.bwKhz.toRawBits())
            e.putInt("blockSize", s.blockSize)
            e.putLong("rssiThresholdDb", s.rssiThresholdDb.toRawBits())
            e.putLong("rssiHystDb", s.rssiHystDb.toRawBits())
            e.putLong("rssiHoldMs", s.rssiHoldMs.toRawBits())
            e.putBoolean("afcEnable", s.afcEnable)
            e.putLong("afcMaxHz", s.afcMaxHz.toRawBits())
            e.putLong("afcGain", s.afcGain.toRawBits())
            e.putBoolean("keepAfcAfterPacket", s.keepAfcAfterPacket)
            e.putLong("dedupeWindow", s.dedupeWindow.toRawBits())
            e.putLong("etaMaxMin", s.etaMaxMin.toRawBits())
            e.putString("userKm", s.userKm)
            e.putString("routeKmText", s.routeKmText)
            e.putInt("mapZoom", s.mapZoom)
            e.putBoolean("mapFollow", s.mapFollow)
            e.putBoolean("mapNight", s.mapNight)
            e.putString("mapBase", s.mapBase)
            e.putString("mapRail", s.mapRail)
            e.putLong("mapRailOpacity", s.mapRailOpacity.toRawBits())
            e.putString("mapTdtKey", s.mapTdtKey)
            e.putString("tdtReferer", s.tdtReferer)
            e.putLong("mapCenterLat", s.mapCenterLat.toRawBits())
            e.putLong("mapCenterLng", s.mapCenterLng.toRawBits())
            e.putString("trainQuerySource", s.trainQuerySource)
            e.putBoolean("dataAutoUpdate", s.dataAutoUpdate)
            e.apply()
        }
    }
}
