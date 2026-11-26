package xyz.mlxkj.crlbj.core

import android.os.ParcelFileDescriptor
import java.io.FileOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket

/**
 * rtl_tcp 协议数据源（rtl_tcp / OWRX 转发共用，协议与桌面版 RtlTcpSource 一致）。
 *
 * 握手：连接 → 读 12 字节头 → 下发 5 字节命令（频率−DC偏移、采样率、手动增益、PPM、AGC 关）。
 * 与 native 的衔接：Kotlin 泵线程把 socket 原始字节写进本地管道，native 引擎
 * 读管道 fd（mode=1），保持 JNI 契约 6 个方法不变。
 */
class RtlTcpSource(
    private val host: String,
    private val port: Int,
    private val hwFreqHz: Long,
    private val sampleRate: Int,
    private val gainDb: Double,
    private val ppm: Double,
) : Source {

    private var socket: Socket? = null
    private var input: java.io.InputStream? = null
    private var pump: Thread? = null
    private var pipeRead: ParcelFileDescriptor? = null
    private var pipeWrite: ParcelFileDescriptor? = null

    override var lastError: String? = null
    override val isOpen: Boolean
        get() = socket?.isConnected == true && pump?.isAlive == true

    /** 连接 + 握手 + 建管道；返回交给 native 的管道读端 fd（native dup 后自行管理） */
    override fun open(): Int {
        val sock = Socket()
        sock.tcpNoDelay = true
        sock.connect(InetSocketAddress(host, port), 10_000)
        sock.soTimeout = 0

        val ins = sock.getInputStream()
        val hdr = ByteArray(12)
        var got = 0
        while (got < 12) {
            val r = ins.read(hdr, got, 12 - got)
            if (r < 0) { sock.close(); throw IOException("握手阶段连接断开") }
            got += r
        }

        fun cmd(id: Int, param: Long) {
            val b = ByteArray(5)
            b[0] = id.toByte()
            b[1] = ((param ushr 24) and 0xFF).toByte()
            b[2] = ((param ushr 16) and 0xFF).toByte()
            b[3] = ((param ushr 8) and 0xFF).toByte()
            b[4] = (param and 0xFF).toByte()
            sock.getOutputStream().apply { write(b); flush() }
        }
        // 与桌面版 _readerTask 同序：频率 → 采样率 → 手动增益 → PPM → AGC 关
        cmd(1, hwFreqHz)            // CMD_SET_FREQ（频率已扣 DC 偏移）
        cmd(2, sampleRate.toLong()) // CMD_SET_SAMPLERATE
        cmd(3, 1)                   // CMD_SET_GAINMODE = manual
        cmd(4, (gainDb * 10).toLong()) // CMD_SET_GAIN (1/10 dB)
        cmd(5, ppm.toLong())        // CMD_SET_FREQCORR
        cmd(8, 0)                   // CMD_SET_AGC off

        socket = sock
        input = ins

        // 管道桥：泵线程 socket → pipe，native 读 pipe fd
        val pair = ParcelFileDescriptor.createPipe()
        pipeRead = pair[0]
        pipeWrite = pair[1]
        val out = FileOutputStream(pipeWrite!!.fileDescriptor)
        pump = Thread {
            val buf = ByteArray(32768)
            try {
                while (!Thread.currentThread().isInterrupted && socket?.isConnected == true) {
                    val n = ins.read(buf)
                    if (n < 0) { lastError = "上游断开（EOF）"; break }
                    out.write(buf, 0, n) // 管道满时阻塞，形成背压
                    out.flush()
                }
            } catch (_: IOException) {
                // socket 关闭 / 管道关闭：正常退出路径
            } finally {
                try { out.close() } catch (_: IOException) { }
                lastError = lastError ?: "数据通路关闭"
            }
        }.apply { name = "rtl-tcp-pump"; start() }
        return pipeRead!!.fd
    }

    /** 原始字节直读（USB 兜底用；pipe 模式下引擎直读 fd，不走此方法） */
    override fun readBlock(buffer: ByteArray): Int =
        input?.read(buffer) ?: -1

    override fun close() {
        pump?.interrupt()
        pump = null
        try { socket?.close() } catch (_: IOException) { }
        socket = null
        input = null
        pipeRead?.let { try { it.close() } catch (_: IOException) { } }
        pipeRead = null
        pipeWrite?.let { try { it.close() } catch (_: IOException) { } }
        pipeWrite = null
    }
}
