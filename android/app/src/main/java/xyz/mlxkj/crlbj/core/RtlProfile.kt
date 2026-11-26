package xyz.mlxkj.crlbj.core

/**
 * RTL-SDR 型号识别与推荐射频配置（v3.2.7）。
 *
 * 与桌面端 `desktop/cr_lbj/core/usb_direct.py` 的 `TUNER_NAMES` /
 * `recommendProfile()` **规则对齐**（用户要求"安卓参考 PC 端的推荐方法"）：
 *
 *  1. **采样率 960 kS/s**：本项目 DSP 链路要 240 kS/s，半带 ×2 之前需要 960 kS/s；
 *     再高只会白烧 USB 带宽。
 *  2. **AGC 关闭 + 手动增益**：LBJ 是突发窄带信号，AGC 会把噪声一起抬起来。
 *     增益按 tuner 型号给（R820T 19.7 dB 实测最稳、R828D 15.7 起调）；
 *  3. **DC 偏移 50 kHz**（仅本地硬件）：避开零频直流与 1/f 噪声，DDC 后再落回目标频点；
 *     OWRX 是服务器端已做 DDC，DC 偏移应为 0。
 */
object RtlProfile {

    /** librtlsdr 的 `enum rtlsdr_tuner` 顺序 */
    private val TUNER_NAMES = mapOf(
        0 to "Unknown",
        1 to "E4000",
        2 to "FC0012",
        3 to "FC0013",
        4 to "FC2580",
        5 to "R820T",
        6 to "R828D",
    )

    fun tunerName(id: Int): String = TUNER_NAMES[id] ?: "未知($id)"

    /** 一套推荐参数 + 型号 + 人话说明（弹窗里直接展示 note）。 */
    data class Recommendation(
        val sampleRate: Int,
        val gainDb: Double,
        val dcOffsetHz: Double,
        val tuner: String,
        val note: String,
    )

    /** 按 tuner 型号给推荐（规则与 PC 端 `recommendProfile` 一致）。 */
    fun recommend(tunerTypeId: Int): Recommendation {
        val tuner = tunerName(tunerTypeId)
        val gain: Double
        val note: String
        when (tuner) {
            "R828D" -> {
                gain = 15.7
                note = "R828D（多为 RTL-SDR Blog V4）：从 15.7 dB 起调，若欠载再上调；" +
                    "osmocom 版库可能把型号报错，建议用 rtl-sdr-blog 版 librtlsdr"
            }
            "R820T", "R820T2" -> {
                gain = 19.7
                note = "R820T/R820T2：LBJ 实测 19.7 dB 手动增益最稳，务必关 AGC"
            }
            "E4000" -> {
                gain = 19.7
                note = "E4000：增益表与 R820T 不同，按设备实际增益表就近取；" +
                    "821 MHz 已接近其上限，灵敏度偏低"
            }
            "FC0012", "FC0013" -> {
                gain = 19.7
                note = "$tuner：廉价 tuner，增益档位粗，按设备增益表就近取"
            }
            else -> {
                gain = 15.7
                note = "未识别 tuner，用保守参数；可点「检测设备」重新读取型号"
            }
        }
        return Recommendation(960000, gain, 50000.0, tuner, note)
    }

    /**
     * 按数据源类型给推荐：
     *  * USB：尽量用探测到的 tuner 型号（type id ≥ 0），否则保守值；
     *  * RTL-TCP：与 USB 共用同一块 RTL 硬件 → 同一套射频参数；
     *  * OWRX：采样率由服务器端决定，DC 偏移设 0。
     */
    fun recommendFor(type: String, tunerTypeId: Int = -1): Recommendation = when (type) {
        "usb" -> if (tunerTypeId >= 0) {
            recommend(tunerTypeId)
        } else {
            Recommendation(960000, 19.7, 50000.0, "未检测",
                "还没读到 tuner 型号：可点「检测设备」识别，或先点一键开始接收")
        }
        "rtl_tcp" -> recommend(5).copy(
            tuner = "RTL-TCP（共用本机 RTL 硬件）",
            note = "RTL-TCP：同一块 RTL 硬件经网络转发，与 USB 直连共用射频参数" +
                "（960 kS/s · 手动增益 · DC 50 kHz）",
        )
        else -> Recommendation(960000, 15.7, 0.0, "OWRX 服务器",
            "OWRX：采样率由服务器端决定（一般 960 kS/s 或更高），增益单位与本地不同，" +
                "DC 偏移设 0（服务器端已完成 DDC）")
    }

    /** 数据源类型的界面显示名（内部 id 保持 usb / rtl_tcp / owrx 不变）。 */
    fun typeLabel(type: String): String = when (type) {
        "usb" -> "USB 直连"
        "rtl_tcp" -> "RTL-TCP"
        else -> "OWRX"
    }
}