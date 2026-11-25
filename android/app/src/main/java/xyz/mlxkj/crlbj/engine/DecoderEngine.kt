package xyz.mlxkj.crlbj.engine

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.core.RtlTcpSource
import xyz.mlxkj.crlbj.core.Source
import xyz.mlxkj.crlbj.core.UsbSource

/** 引擎运行状态 */
enum class EngineState { IDLE, INITIALIZED, RUNNING, STOPPED, ERROR }

/**
 * 解码引擎 Kotlin 编排层（对应桌面版 LbjCore 的对外面）。
 *
 * init(settings) → nativeInit（DSP 链按参数构建）
 * start(settings, source) → source.open() 拿 fd → nativeStart(mode, fd, …)
 *   mode: 0=USB（native rtlsdr_open_fd 直读），1=pipe（socketpair/pipe 桥）
 * 解码回调（native 线程）→ JSON 解析 → 车次分类 + ETA → 去重 → StateFlow。
 */
class DecoderEngine(private val context: Context) {

    private val _state = MutableStateFlow(EngineState.IDLE)
    val state: StateFlow<EngineState> = _state

    private val _logs = MutableStateFlow<List<String>>(emptyList())
    val logs: StateFlow<List<String>> = _logs

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError

    /** 最近一帧 StatusFrame（轮询器 150ms 更新） */
    private val _status = MutableStateFlow<StatusFrame?>(null)
    val status: StateFlow<StatusFrame?> = _status

    /** 最近解码事件（新事件插到最前，最多保留 100 条） */
    private val _events = MutableStateFlow<List<DecodeEvent>>(emptyList())
    val events: StateFlow<List<DecodeEvent>> = _events

    private var initialized = false
    private var source: Source? = null
    private var poller: StatusFramePoller? = null

    // 业务参数（VM 从设置页同步进来）
    var trainScheme: String = "auto"
    var dedupeWindow: Double = 2.5
    var estimator: ArrivalEstimator = ArrivalEstimator()

    private val dedupe = RecordDeduplicator()

    fun log(msg: String) {
        _logs.value = (_logs.value + msg).takeLast(300)
    }

    private fun postEvent(json: String) {
        try {
            val now = System.currentTimeMillis() / 1000.0
            val base = DecodeEvent.fromNativeJson(json, now)
            val category = TrainClassifier.classify(
                base.train, base.isDetailed, base.speed, trainScheme)
            val eta = estimator.estimateEta(
                base.train, base.direction, base.speed, base.position,
                base.route, goodData = !base.msgTypeError, now = now)
            val withBiz = base.copy(category = category, etaSeconds = eta.seconds,
                etaTime = eta.time, etaDistanceKm = eta.distanceKm, etaStatus = eta.status)
            val kept = dedupe.apply(withBiz) ?: return   // 窗口内重复且非更优 → 丢弃
            _events.value = (listOf(kept) + _events.value).take(100)
        } catch (t: Throwable) {
            log("[事件] 解析失败: ${t.message}")
        }
    }

    /** 创建 native 引擎（DSP 链按设置构建）。重复调用无害。 */
    fun init(settings: ReceiverSettings): Boolean {
        if (initialized) return true
        if (!LbjNative.load()) {
            _lastError.value = "liblbj.so 加载失败"
            _state.value = EngineState.ERROR
            return false
        }
        LbjNative.onLog = { log(it) }
        LbjNative.onDecodeEvent = { postEvent(it) }
        val rc = LbjNative.nativeInit(settings.toParamsJson())
        initialized = rc == 0
        if (!initialized) {
            _lastError.value = "nativeInit 失败 rc=$rc"
            _state.value = EngineState.ERROR
        } else {
            if (_state.value == EngineState.IDLE) _state.value = EngineState.INITIALIZED
        }
        return initialized
    }

    /**
     * 启动接收。source 由调用方按 settings.sourceType 构造（USB 需先取权限），
     * 本方法负责 open fd → nativeStart → 启动 StatusFrame 轮询。
     */
    fun start(settings: ReceiverSettings, src: Source): Boolean {
        if (!initialized && !init(settings)) return false
        if (_state.value == EngineState.RUNNING) return true
        return try {
            LbjNative.nativeStop()   // 防御：引擎可能残留上次会话
            val fd = src.open()
            source = src
            val mode = if (settings.isUsb) 0 else 1
            val rc = LbjNative.nativeStart(
                fd, mode, settings.hwFreqHz, settings.sampleRate,
                (settings.gainDb * 100).toInt(), settings.ppm.toInt())
            if (rc != 0) {
                _lastError.value = "nativeStart 失败 rc=$rc"
                src.close(); source = null
                _state.value = EngineState.ERROR
                return false
            }
            poller?.stop()
            poller = StatusFramePoller { _status.value = it }.also { it.start() }
            _state.value = EngineState.RUNNING
            log("[启动] ${settings.sourceType} ${settings.host}:${settings.port} " +
                "采样率 ${settings.sampleRate / 1000}k 频率 ${settings.freqMhz} MHz")
            true
        } catch (t: Throwable) {
            _lastError.value = "启动失败: ${t.message}"
            _state.value = EngineState.ERROR
            log("[错误] 启动失败: ${t.message}")
            false
        }
    }

    /** 按设置构造数据源（USB 权限流程由调用方协程内先完成） */
    suspend fun createSource(settings: ReceiverSettings): Source =
        if (settings.isUsb) {
            UsbSource(context).also { it.requestPermission() }
        } else {
            RtlTcpSource(
                settings.host, settings.port, settings.hwFreqHz,
                settings.sampleRate, settings.gainDb, settings.ppm)
        }

    /** 当前数据源是否存活（监护用） */
    fun isSourceOpen(): Boolean = source?.isOpen == true

    /** 当前数据源若是 rtl_tcp/OWRX 管道源则返回（IQ 录制用） */
    fun sourceIfTcp(): xyz.mlxkj.crlbj.core.RtlTcpSource? =
        source as? xyz.mlxkj.crlbj.core.RtlTcpSource

    fun stop() {
        if (_state.value != EngineState.RUNNING && source == null) return
        LbjNative.nativeStop()
        poller?.stop(); poller = null
        try { source?.close() } catch (_: Throwable) { }
        source = null
        _state.value = EngineState.STOPPED
        log("[停止] 接收已停止")
    }

    fun release() {
        stop()
        if (initialized) {
            LbjNative.nativeRelease()
            initialized = false
            _state.value = EngineState.IDLE
        }
    }
}
