package xyz.mlxkj.crlbj.vm

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.engine.RouteUtils
import xyz.mlxkj.crlbj.engine.ArrivalEstimator
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.engine.DecoderEngine
import xyz.mlxkj.crlbj.engine.EngineState

/**
 * 全局收发枢纽：解码事件流 / StatusFrame / 日志 / 设置。
 * 五页 UI 全部只从这里取数据。
 */
class ReceiverViewModel(app: Application) : AndroidViewModel(app) {

    val engine = DecoderEngine(app)

    private val _settings = MutableStateFlow(ReceiverSettings.load(app))
    val settings: StateFlow<ReceiverSettings> = _settings

    private val _running = MutableStateFlow(false)
    val running: StateFlow<Boolean> = _running

    val state: StateFlow<EngineState> get() = engine.state
    val events: StateFlow<List<DecodeEvent>> get() = engine.events
    val status: StateFlow<xyz.mlxkj.crlbj.engine.StatusFrame?> get() = engine.status
    val logs: StateFlow<List<String>> get() = engine.logs

    init {
        syncBusinessParams(_settings.value)
        // 应用启动即初始化 native 引擎（一键开始的前提）
        viewModelScope.launch(Dispatchers.IO) {
            engine.init(_settings.value)
            engine.log("[初始化] native 引擎已创建")
        }
    }

    /** 把设置中的业务参数同步到引擎（车次规则/去重窗口/ETA） */
    private fun syncBusinessParams(s: ReceiverSettings) {
        engine.trainScheme = s.trainScheme
        engine.dedupeWindow = s.dedupeWindow
        engine.estimator = ArrivalEstimator(
            userKm = RouteUtils.parseKm(s.userKm),
            maxSeconds = s.etaMaxMin * 60.0,
            routeKmMap = RouteUtils.parseRouteKmMap(s.routeKmText),
        )
    }

    /** 更新设置（设置页保存时调用）：落盘 + 热更新业务参数 + 重建引擎链路 */
    fun updateSettings(s: ReceiverSettings) {
        _settings.value = s
        ReceiverSettings.save(getApplication(), s)
        syncBusinessParams(s)
        // 连接类参数需要重建 DSP 链路；运行中先停
        if (_running.value) stop()
        viewModelScope.launch(Dispatchers.IO) {
            engine.release()
            engine.init(s)
        }
    }

    fun toggleStartStop() {
        when (engine.state.value) {
            EngineState.RUNNING -> stop()
            else -> start()
        }
    }

    private var watchdog: Job? = null

    private fun start() {
        _running.value = false
        val s = _settings.value
        viewModelScope.launch(Dispatchers.IO) {
            if (!engine.init(s)) return@launch
            try {
                val src = engine.createSource(s)
                val ok = engine.start(s, src)
                _running.value = ok
                if (ok) startWatchdog()
            } catch (t: Throwable) {
                engine.log("[错误] 数据源打开失败: ${t.message}")
                _running.value = false
            }
        }
    }

    /** 断流监护：pipe EOF / 数据流中断时自动重建数据源并重连 */
    private fun startWatchdog() {
        watchdog?.cancel()
        watchdog = viewModelScope.launch(Dispatchers.IO) {
            while (_running.value) {
                delay(3000)
                val f = engine.status.value
                val broken = f != null && f.errorState == 1
                val srcDead = !engine.isSourceOpen()
                if (broken || srcDead) {
                    engine.log("[监护] 数据流中断（broken=$broken srcDead=$srcDead），自动重连…")
                    engine.stop()
                    val s = _settings.value
                    try {
                        val src = engine.createSource(s)
                        if (engine.start(s, src)) {
                            engine.log("[监护] 重连成功")
                        } else {
                            engine.log("[监护] 重连失败，3s 后重试")
                        }
                    } catch (t: Throwable) {
                        engine.log("[监护] 重连失败: ${t.message}，3s 后重试")
                    }
                }
            }
        }
    }

    private fun stop() {
        watchdog?.cancel()
        watchdog = null
        engine.stop()
        _running.value = false
    }

    override fun onCleared() {
        engine.release()
        super.onCleared()
    }
}
