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
    val host: String = "nc.example.com",
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
            e.apply()
        }
    }
}
