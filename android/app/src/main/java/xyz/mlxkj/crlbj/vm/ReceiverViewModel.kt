package xyz.mlxkj.crlbj.vm

import android.app.Application
import android.content.Intent
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.engine.RouteUtils
import xyz.mlxkj.crlbj.data.CsvExporter
import xyz.mlxkj.crlbj.data.LbjDatabase
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.engine.ArrivalEstimator
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.engine.DecoderEngine
import xyz.mlxkj.crlbj.engine.EngineState
import xyz.mlxkj.crlbj.service.ReceiveForegroundService

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

    /** 历史库（Room）：最近记录 + 条数，uid upsert */
    private val db = LbjDatabase.get(app)
    val records: StateFlow<List<RecordEntity>> =
        db.recordDao().recent(500)
            .stateIn(viewModelScope, SharingStarted.Lazily, emptyList())
    val recordCount: StateFlow<Int> =
        db.recordDao().count()
            .stateIn(viewModelScope, SharingStarted.Lazily, 0)

    private val _csvMsg = MutableStateFlow<String?>(null)
    val csvMsg: StateFlow<String?> = _csvMsg

    init {
        syncBusinessParams(_settings.value)
        // 解码事件 → uid 去重入库（窗口内被更优记录替换时同 uid 更新）
        viewModelScope.launch(Dispatchers.IO) {
            engine.events.collect { list ->
                list.firstOrNull()?.let { ev ->
                    runCatching { db.recordDao().upsert(RecordEntity.fromEvent(ev)) }
                }
            }
        }
        // 应用启动即初始化 native 引擎（一键开始的前提）
        viewModelScope.launch(Dispatchers.IO) {
            engine.init(_settings.value)
            engine.log("[初始化] native 引擎已创建")
        }
        // 前台服务随接收状态启停
        viewModelScope.launch {
            _running.collect { running ->
                val ctx = getApplication<Application>()
                ReceiveForegroundService.ensureChannel(ctx)
                if (running) {
                    ctx.startForegroundService(Intent(ctx, ReceiveForegroundService::class.java))
                } else {
                    ctx.startService(
                        Intent(ctx, ReceiveForegroundService::class.java)
                            .setAction(ReceiveForegroundService.ACTION_STOP))
                }
            }
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

    /** 导出历史为 CSV（SAF 目标 Uri，由页面 CreateDocument 启动器提供） */
    fun exportCsv(uri: Uri) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val all = db.recordDao().all()
                getApplication<Application>().contentResolver.openOutputStream(uri)?.use { out ->
                    CsvExporter.export(out, all)
                }
                _csvMsg.value = "已导出 ${all.size} 条记录"
            } catch (t: Throwable) {
                _csvMsg.value = "导出失败: ${t.message}"
            }
        }
    }

    fun clearHistory() {
        viewModelScope.launch(Dispatchers.IO) { db.recordDao().clear() }
    }

    /** IQ 录制状态（null = 未录制；DecodePage/设置页用 SAF CreateDocument 提供 Uri） */
    private val _recording = MutableStateFlow(false)
    val recording: StateFlow<Boolean> = _recording

    /** 开始/停止 IQ 原始录制（仅网络源可用；USB 模式 native 直读 fd 不支持） */
    fun toggleIqRecord(uri: Uri?) {
        viewModelScope.launch(Dispatchers.IO) {
            val src = engine.sourceIfTcp()
            if (src == null) {
                engine.log("[录制] 当前为 USB 模式或未在接收，暂不支持 IQ 录制")
                return@launch
            }
            val cur = src.recordOut
            if (cur != null) {
                src.recordOut = null
                try { cur.close() } catch (_: Throwable) { }
                _recording.value = false
                engine.log("[录制] IQ 录制已停止")
            } else if (uri != null) {
                try {
                    val out = getApplication<Application>().contentResolver.openOutputStream(uri)
                    src.recordOut = out
                    _recording.value = true
                    engine.log("[录制] IQ 录制开始（uint8 交错 IQ，采样率 ${_settings.value.sampleRate}）")
                } catch (t: Throwable) {
                    engine.log("[录制] 打开录制文件失败: ${t.message}")
                }
            }
        }
    }

    override fun onCleared() {
        engine.release()
        super.onCleared()
    }
}
