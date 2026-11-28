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
 * StatusFrame（native 双缓冲共享帧，1104 字节 / 276 word，小端）。
 * 布局与 cpp/core/status_frame.h 严格一致：
 *  [0]seq [1]gateState [2]rssi [3]afcHz [4]afcErrHz [5]afcScore
 *  [6]tunerTypeId [7]appliedGainCentiDb [8]actualSampleRate [9]hwFreqHz
 *  [10]blocksPerSec [11]totalBlocks [12]droppedBlocks [13]reconnectCount
 *  [14]decodeCpuPct [15]bufferLevel [16]running [17]linkMode [18]errorState
 *  [19]interference(低16=上行, 高16=下行；v3.2.9 解析不出车次的干扰帧数)
 *  [20..275]spectrum[256]  (v4.0: 32->256 bin)
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
    /** v3.2.9：word[19] 打包的干扰计数（低16=上行帧数，高16=下行帧数；
     *  口径 = 解析不出车次、被判为干扰且**不入库**的帧） */
    val interferenceRaw: Int = 0,
    val spectrum: FloatArray = FloatArray(32),
) {
    val signalOn: Boolean get() = gateState >= 2 // ON / HOLD

    /** 上行干扰帧数（解析不出车次、不入库） */
    val interferenceUp: Int get() = interferenceRaw and 0xFFFF

    /** 下行干扰帧数（解析不出车次、不入库） */
    val interferenceDown: Int get() = (interferenceRaw ushr 16) and 0xFFFF

    companion object {
        const val WORDS = 276          // 20 头 + 256 频谱 bin（v4.0）
        const val SPECTRUM_BINS = 256
        const val BYTES = WORDS * 4

        fun parse(bb: ByteBuffer): StatusFrame {
            bb.order(ByteOrder.LITTLE_ENDIAN)
            val spec = FloatArray(SPECTRUM_BINS)
            for (i in 0 until SPECTRUM_BINS) spec[i] = bb.getFloat((20 + i) * 4)
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
                interferenceRaw = bb.getInt(76),
                spectrum = spec,
            )
        }
    }
}

/**
 * StatusFrame 轮询器：每 [POLL_MS] 调 nativeReadSpectrum，seq 变化才发布。
 * native 未启动 / 未跑时保持 null（UI 显示待机）。
 *
 * 间隔从 150ms 降到 70ms（v3.2.6）：native 的频谱在每个 DSP 块更新
 * （blockSize 65536 @ 960k ≈ 68ms 一块），150ms 轮询会丢掉一半帧，
 * 瀑布看起来发"横条纹"。70ms ≈ 1 块 1 帧，帧率 ~14 fps。
 * 状态页指标刷新因此也变快，但只是文本刷新，无副作用。
 */
class StatusFramePoller(private val onFrame: (StatusFrame) -> Unit) {

    companion object {
        /** 轮询间隔：略小于一个 DSP 块（≈68ms），避免同一帧被读两次/漏帧 */
        const val POLL_MS = 40L     // v4.0: 70->40ms（约 25fps，瀑布更连贯）
    }

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
                delay(POLL_MS)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
        lastSeq = -1
    }
}
