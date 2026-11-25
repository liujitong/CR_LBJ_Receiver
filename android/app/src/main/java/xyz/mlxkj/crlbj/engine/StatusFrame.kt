package xyz.mlxkj.crlbj.engine

import android.util.Log
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * StatusFrame（native 双缓冲共享帧，208 字节 / 52 word，小端）。
 * 布局与 cpp/core/status_frame.h 严格一致：
 *  [0]seq [1]gateState [2]rssi [3]afcHz [4]afcErrHz [5]afcScore
 *  [6]tunerTypeId [7]appliedGainCentiDb [8]actualSampleRate [9]hwFreqHz
 *  [10]blocksPerSec [11]totalBlocks [12]droppedBlocks [13]reconnectCount
 *  [14]decodeCpuPct [15]bufferLevel [16]running [17]linkMode [18]errorState
 *  [20..51]spectrum[32]
 */
data class StatusFrame(
    val seq: Int = 0,
    val gateState: Int = 0,       // 0=OFF 1=ARM 2=ON 3=HOLD 4=BYPASS
    val rssiDb: Float = -140f,
    val afcHz: Float = 0f,
    val afcErrHz: Float = 0f,
    val afcScore: Float = 0f,
    val tunerTypeId: Int = 0,
    val appliedGainCentiDb: Int = 0,
    val actualSampleRate: Int = 0,
    val hwFreqHz: Int = 0,
    val blocksPerSec: Float = 0f,
    val totalBlocks: Int = 0,
    val droppedBlocks: Int = 0,
    val reconnectCount: Int = 0,
    val decodeCpuPct: Float = 0f,
    val bufferLevel: Float = 0f,
    val running: Int = 0,
    val linkMode: Int = 1,        // 0=usb 1=pipe
    val errorState: Int = 0,      // 0=ok 1=streamBroken
    val spectrum: FloatArray = FloatArray(32),
) {
    val signalOn: Boolean get() = gateState >= 2 // ON / HOLD

    companion object {
        const val WORDS = 52
        const val BYTES = WORDS * 4

        fun parse(bb: ByteBuffer): StatusFrame {
            bb.order(ByteOrder.LITTLE_ENDIAN)
            val spec = FloatArray(32)
            for (i in 0 until 32) spec[i] = bb.getFloat((20 + i) * 4)
            return StatusFrame(
                seq = bb.getInt(0),
                gateState = bb.getInt(4),
                rssiDb = bb.getFloat(8),
                afcHz = bb.getFloat(12),
                afcErrHz = bb.getFloat(16),
                afcScore = bb.getFloat(20),
                tunerTypeId = bb.getInt(24),
                appliedGainCentiDb = bb.getInt(28),
                actualSampleRate = bb.getInt(32),
                hwFreqHz = bb.getInt(36),
                blocksPerSec = bb.getFloat(40),
                totalBlocks = bb.getInt(44),
                droppedBlocks = bb.getInt(48),
                reconnectCount = bb.getInt(52),
                decodeCpuPct = bb.getFloat(56),
                bufferLevel = bb.getFloat(60),
                running = bb.getInt(64),
                linkMode = bb.getInt(68),
                errorState = bb.getInt(72),
                spectrum = spec,
            )
        }
    }
}

/**
 * StatusFrame 轮询器：每 150ms 调 nativeReadSpectrum，seq 变化才发布。
 * native 未启动 / 未跑时保持 null（UI 显示待机）。
 */
class StatusFramePoller(private val onFrame: (StatusFrame) -> Unit) {

    private val buffer: ByteBuffer = ByteBuffer.allocateDirect(StatusFrame.BYTES)
    private var lastSeq = -1
    private var job: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch {
            while (isActive) {
                try {
                    val seq = LbjNative.nativeReadSpectrum(buffer)
                    if (seq > 0 && seq != lastSeq) {
                        lastSeq = seq
                        onFrame(StatusFrame.parse(buffer))
                    }
                } catch (t: Throwable) {
                    Log.e("StatusPoller", "poll failed", t)
                }
                delay(150)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
        lastSeq = -1
    }
}
