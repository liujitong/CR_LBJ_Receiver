package xyz.mlxkj.crlbj.core

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject

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
    /** 默认中心：预设城市名（仅显示用，来自 shared/data/places.csv） */
    val mapCenterName: String = "南昌",
    val mapCenterLat: Double = 28.68,
    val mapCenterLng: Double = 115.86,
    // 查询
    /** 车次数据源：auto / railgo / 12306 */
    val trainQuerySource: String = "auto",
    /** 第三方数据（机车配属号段表）自动更新 */
    val dataAutoUpdate: Boolean = true,
) {
    val isUsb: Boolean get() = sourceType == "usb"

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

        /** USB 直连推荐参数（桌面版 rtl_usb 档位） */
        val USB_DEFAULTS = ReceiverSettings(
            sourceType = "usb", sampleRate = 240000, gainDb = 19.7,
            dcOffsetHz = 50000.0,
        )
        val OWRX_DEFAULTS = ReceiverSettings()

        fun load(ctx: Context): ReceiverSettings {
            val sp: SharedPreferences = ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE)
            val d = OWRX_DEFAULTS
            return ReceiverSettings(
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
                mapCenterName = sp.getString("mapCenterName", d.mapCenterName) ?: d.mapCenterName,
                mapCenterLat = Double.fromBits(
                    sp.getLong("mapCenterLat", d.mapCenterLat.toRawBits())),
                mapCenterLng = Double.fromBits(
                    sp.getLong("mapCenterLng", d.mapCenterLng.toRawBits())),
                trainQuerySource = sp.getString("trainQuerySource", d.trainQuerySource)
                    ?: d.trainQuerySource,
                dataAutoUpdate = sp.getBoolean("dataAutoUpdate", d.dataAutoUpdate),
            )
        }

        fun save(ctx: Context, s: ReceiverSettings) {
            val e = ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE).edit()
            e.putString("sourceType", s.sourceType)
            e.putString("host", s.host)
            e.putInt("port", s.port)
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
            e.putString("mapCenterName", s.mapCenterName)
            e.putLong("mapCenterLat", s.mapCenterLat.toRawBits())
            e.putLong("mapCenterLng", s.mapCenterLng.toRawBits())
            e.putString("trainQuerySource", s.trainQuerySource)
            e.putBoolean("dataAutoUpdate", s.dataAutoUpdate)
            e.apply()
        }
    }
}
