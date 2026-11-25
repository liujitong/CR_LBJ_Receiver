package xyz.mlxkj.crlbj.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import xyz.mlxkj.crlbj.engine.DecoderEngine
import xyz.mlxkj.crlbj.engine.EngineState

/**
 * 全局收发枢纽：解码事件流 / RSSI 与频谱帧 / 链路统计 / 日志。
 * 五页 UI 全部只从这里取数据（M0：状态与日志）。
 */
class ReceiverViewModel : ViewModel() {

    val engine = DecoderEngine()

    private val _running = MutableStateFlow(false)
    val running: StateFlow<Boolean> = _running

    /** 日志流（透传引擎日志，五页共用） */
    val logs: StateFlow<List<String>> get() = engine.logs

    init {
        // 应用启动即初始化 native 引擎（一键开始的前提）
        viewModelScope.launch {
            engine.init()
            engine.log("[初始化] native 引擎已创建")
        }
    }

    fun toggleStartStop() {
        when (engine.state.value) {
            EngineState.RUNNING -> {
                engine.stop()
                _running.value = false
            }
            else -> {
                _running.value = engine.start()
            }
        }
    }
}
