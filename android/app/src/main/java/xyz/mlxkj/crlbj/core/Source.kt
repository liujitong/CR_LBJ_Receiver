package xyz.mlxkj.crlbj.core

/**
 * 数据源统一接口（对应桌面版 RtlSdrDirectSource / RtlTcpSource / OwrxSource 的公共面）。
 *
 * 语义与桌面版一致：
 *  - open：建立数据通路（USB 拿 fd / 网络连 Socket），失败抛异常并给出可读原因
 *  - readBlock：阻塞读一块 IQ（uint8 交错 I/Q），返回原始字节
 *  - close：停止并释放
 *
 * Android 端与 native 的衔接：
 *  - USB 模式：open 后通过 UsbDeviceConnection.getFileDescriptor() 把 fd 交给 JNI
 *  - 网络模式（rtl_tcp / OWRX）：纯 Kotlin Socket 读原始字节，经本地 socketpair fd 交给 JNI
 */
interface Source {
    /** 是否已成功打开且在读数 */
    val isOpen: Boolean

    /** 最近一次错误描述（用于状态页与重连提示） */
    var lastError: String?

    /** 打开数据源。返回交给 native 的文件描述符（-1 表示由实现自行处理）。 */
    fun open(): Int

    /** 读一块 IQ 原始字节（uint8 交错）。返回实际读取字节数，0 表示流结束。 */
    fun readBlock(buffer: ByteArray): Int

    /** 关闭数据源 */
    fun close()
}
