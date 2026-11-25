package xyz.mlxkj.crlbj.engine

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** 引擎运行状态 */
enum class EngineState { IDLE, RUNNING, STOPPED, ERROR }

/**
 * 解码引擎 Kotlin 编排层（对应桌面版 LbjCore 的对外面）。
 * M0：仅打通 init 生命周期，验证 JNI 链路（"native init ok"）。
 * M1：接 USB/pipe fd；M2：解码事件流；M3：完整业务。
 */
class DecoderEngine {

    private val _state = MutableStateFlow(EngineState.IDLE)
    val state: StateFlow<EngineState> = _state

    private val _logs = MutableStateFlow<List<String>>(emptyList())
    val logs: StateFlow<List<String>> = _logs

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError

    private var initialized = false

    fun log(msg: String) {
        _logs.value = (_logs.value + msg).takeLast(200)
    }

    /** 创建 native 引擎。默认参数沿用桌面版已验证值（手机端采样率 240k）。 */
    fun init(): Boolean {
        if (initialized) return true
        if (!LbjNative.load()) {
            _lastError.value = "liblbj.so 加载失败"
            _state.value = EngineState.ERROR
            return false
        }
        LbjNative.onLog = { log(it) }
        LbjNative.onDecodeEvent = { log("decode: $it") }
        val params = """
            {"freqMhz": 821.2375, "sampleRate": 240000, "bwKhz": 35.0,
             "dcOffsetHz": 50000.0, "gainDb": 19.7, "ppm": 1,
             "basebandRate": 48000, "baudRate": 1200}
        """.trimIndent()
        val rc = LbjNative.nativeInit(params)
        initialized = rc == 0
        if (!initialized) {
            _lastError.value = "nativeInit 失败 rc=$rc"
            _state.value = EngineState.ERROR
        }
        return initialized
    }

    /** 一键开始（M0 占位：fd 来源在 M1 接入） */
    fun start(): Boolean {
        if (!initialized && !init()) return false
        // M0：尚未接数据源，不真正启动；M1 在此传 fd
        log("[启动] M0 骨架：数据源尚未接入（M1 实现）")
        _state.value = EngineState.RUNNING
        return true
    }

    fun stop() {
        if (!initialized) return
        LbjNative.nativeStop()
        _state.value = EngineState.STOPPED
        log("[停止] 接收已停止")
    }
}
