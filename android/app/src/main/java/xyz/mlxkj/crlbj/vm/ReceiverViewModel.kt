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
import kotlinx.coroutines.withContext
import xyz.mlxkj.crlbj.core.ReceiverSettings
import xyz.mlxkj.crlbj.data.AndroidSharedAssets
import xyz.mlxkj.crlbj.data.CsvExporter
import xyz.mlxkj.crlbj.data.DataUpdater
import xyz.mlxkj.crlbj.data.LbjDatabase
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.LocoRosterHolder
import xyz.mlxkj.crlbj.data.Place
import xyz.mlxkj.crlbj.data.RecordEntity
import xyz.mlxkj.crlbj.data.SharedAssets
import xyz.mlxkj.crlbj.data.parsePlaces
import xyz.mlxkj.crlbj.engine.ArrivalEstimator
import xyz.mlxkj.crlbj.engine.DecodeEvent
import xyz.mlxkj.crlbj.engine.DecoderEngine
import xyz.mlxkj.crlbj.engine.EngineState
import xyz.mlxkj.crlbj.engine.RouteUtils
import xyz.mlxkj.crlbj.service.ReceiveForegroundService

/**
 * 全局收发枢纽：解码事件流 / StatusFrame / 日志 / 设置 / 查询数据 / 第三方数据更新。
 * 六个页面全部只从这里取数据（页面之间不互相持有状态）。
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

    // ------------------------------------------------------------ 共享数据
    /** shared/data（assets）+ filesDir/data（运行时更新）的统一读取入口 */
    val sharedAssets: SharedAssets = AndroidSharedAssets(app)

    /** 机车配属/参数查询（懒加载，几 MB 的 CSV 解析都在 IO 线程发生） */
    val roster: LocoRoster get() = LocoRosterHolder.get(sharedAssets)

    /** 预设城市（地图默认中心下拉） */
    private val _places = MutableStateFlow<List<Place>>(emptyList())
    val places: StateFlow<List<Place>> = _places

    /** 数据概况（设置页展示：来源 / 行数 / 更新日期） */
    private val _dataInfo = MutableStateFlow("")
    val dataInfo: StateFlow<String> = _dataInfo

    private val _dataUpdate = MutableStateFlow(DataUpdateState())
    val dataUpdate: StateFlow<DataUpdateState> = _dataUpdate

    // ------------------------------------------------------------ 跨页跳转
    /** 查询页待消费的预填请求（解码卡「机车 / 车次」→ 查询页） */
    private val _pendingQuery = MutableStateFlow<PendingQuery?>(null)
    val pendingQuery: StateFlow<PendingQuery?> = _pendingQuery

    data class PendingQuery(val kind: Kind, val text: String, val number: String = "") {
        enum class Kind { LOCO, TRAIN }
    }

    data class DataUpdateState(
        val running: Boolean = false,
        val message: String = "",
        val ok: Boolean = true,
        val rows: Int = 0,
        val updated: Boolean = false,
        val fetchedAt: String = "",
    )

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
        // 预设城市 + 数据概况（都很小，IO 线程读）
        viewModelScope.launch(Dispatchers.IO) {
            _places.value = parsePlaces(sharedAssets.read(LocoRoster.PLACES_FILE))
            refreshDataInfo()
        }
        // 第三方数据静默自动检查：距上次 > 7 天且开关打开才跑，失败完全静默
        viewModelScope.launch {
            val s = _settings.value
            if (!s.dataAutoUpdate) return@launch
            if (!DataUpdater.shouldAutoCheck(getApplication())) return@launch
            delay(2500)   // 让首屏先出来，别和 native 初始化抢 IO
            val r = DataUpdater.check(getApplication(), force = false)
            DataUpdater.markChecked(getApplication())
            applyUpdateResult(r, silent = true)
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

    /**
     * 只更新地图/界面类设置（地图页的跟随开关、图层回调等高频路径）：
     * 不重建 DSP 链路，避免「切个底图就断流」。
     */
    fun updateViewSettings(s: ReceiverSettings) {
        if (s == _settings.value) return
        _settings.value = s
        ReceiverSettings.save(getApplication(), s)
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

    /** 历史页多选删除 */
    fun deleteRecords(uids: Collection<String>) {
        if (uids.isEmpty()) return
        viewModelScope.launch(Dispatchers.IO) {
            runCatching { db.recordDao().deleteByUids(uids.toList()) }
                .onFailure { _csvMsg.value = "删除失败：${it.message}" }
                .onSuccess { _csvMsg.value = "已删除 ${uids.size} 条记录" }
        }
    }

    // ------------------------------------------------------------ 查询跳转
    fun requestLocoQuery(model: String, number: String) {
        _pendingQuery.value = PendingQuery(PendingQuery.Kind.LOCO, model, number)
    }

    fun requestTrainQuery(train: String) {
        _pendingQuery.value = PendingQuery(PendingQuery.Kind.TRAIN, train)
    }

    /** 查询页取走请求后清空，避免旋转屏幕重复预填 */
    fun consumePendingQuery(): PendingQuery? {
        val p = _pendingQuery.value
        if (p != null) _pendingQuery.value = null
        return p
    }

    // -------------------------------------------------------- 第三方数据更新
    fun refreshDataInfo() {
        viewModelScope.launch(Dispatchers.IO) {
            _dataInfo.value = buildDataInfo()
        }
    }

    private fun buildDataInfo(): String {
        val st = roster.stats()
        val entry = DataUpdater.readManifest(getApplication())
        val rows = if (entry != null && entry.rows > 0) entry.rows else st.rows
        val when_ = entry?.fetchedAt?.take(19)?.replace('T', ' ') ?: "内置快照"
        return "${st.origin} · $rows 行 · ${st.models} 个型号 · $when_"
    }

    private fun applyUpdateResult(r: DataUpdater.UpdateResult, silent: Boolean) {
        if (!silent || r.ok) {
            _dataUpdate.value = DataUpdateState(
                running = false,
                message = r.message,
                ok = r.ok,
                rows = r.rows,
                updated = r.updated,
                fetchedAt = DataUpdater.readManifest(getApplication())?.fetchedAt.orEmpty(),
            )
        }
        if (r.updated) {
            // 索引重建 + 概况刷新（下次查询就走新表）
            LocoRosterHolder.refresh(sharedAssets)
            refreshDataInfo()
            engine.log("[数据] 配属表已更新：${r.message}")
        } else if (!silent) {
            engine.log("[数据] 检查更新：${r.message}")
        }
    }

    /** 「立即检查更新」（设置页按钮） */
    fun checkDataUpdate(force: Boolean = true) {
        if (_dataUpdate.value.running) return
        _dataUpdate.value = _dataUpdate.value.copy(running = true, message = "正在检查…")
        viewModelScope.launch {
            val r = DataUpdater.check(getApplication(), force = force)
            DataUpdater.markChecked(getApplication())
            applyUpdateResult(r, silent = false)
        }
    }

    /** 查询页需要的最新配属索引（数据更新后自动换新实例） */
    fun currentRoster(): LocoRoster = LocoRosterHolder.current() ?: roster

    // ------------------------------------------------------------ IQ 录制
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
                    val out = withContext(Dispatchers.IO) {
                        getApplication<Application>().contentResolver.openOutputStream(uri)
                    }
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
