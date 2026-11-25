package xyz.mlxkj.crlbj.engine

import android.util.Log

/**
 * JNI 契约（严格保持 6 个 native 方法）：
 *
 *  init          —— 创建 native 引擎（DSP 链按参数构建），返回 0 成功 / 负数错误码
 *  start         —— 启动读线程 + DSP 线程。sourceFd: USB 模式=UsbDeviceConnection fd，
 *                   网络模式=本地 socketpair 读端；mode: 0=USB, 1=pipe
 *  stop          —— 停线程、释放设备（引擎保留，可再次 start）
 *  release       —— 销毁引擎
 *  readSpectrum  —— UI 定时轮询：拷出最近一帧 StatusFrame（共享 ByteBuffer 双缓冲+seq），返回当前 seq
 *  setParams     —— 热更新：RSSI 门限/迟滞/保持、AFC 开关、增益、用户偏移等（JSON）
 *
 * 回调（native → Kotlin）只有 2 个：onDecodeEvent(json) 解码帧（每秒几次）、onLog(msg)。
 */
object LbjNative {

    private const val LIB = "lbj"

    /** 解码帧事件回调（JSON 字段与桌面版 DecodeResult.toDict() 同名） */
    @Volatile
    var onDecodeEvent: ((String) -> Unit)? = null

    /** 日志回调 */
    @Volatile
    var onLog: ((String) -> Unit)? = null

    fun load(): Boolean = try {
        System.loadLibrary(LIB)
        true
    } catch (t: Throwable) {
        Log.e("LbjNative", "load lib$LIB failed", t)
        false
    }

    external fun nativeInit(paramsJson: String): Int
    external fun nativeStart(sourceFd: Int, mode: Int, freqHz: Long, sampleRate: Int,
                             gainCentiDb: Int, ppm: Int): Int
    external fun nativeStop()
    external fun nativeRelease()
    external fun nativeReadSpectrum(buffer: java.nio.ByteBuffer): Int
    external fun nativeSetParams(paramsJson: String)

    // ---- 供 native 回调（M1/M2 起 JNI 反向调用入口） ----
    @Suppress("unused")
    private fun onDecodeEventFromNative(json: String) {
        onDecodeEvent?.invoke(json)
    }

    @Suppress("unused")
    private fun onLogFromNative(msg: String) {
        onLog?.invoke(msg)
    }
}
