package xyz.mlxkj.crlbj.core

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * USB 直连数据源（RTL-SDR 电视棒）。
 *
 * Android 仅提供 fd（UsbDeviceConnection.getFileDescriptor()），枚举/调谐/读流
 * 全部在 native librtlsdr（rtlsdr_open_fd 补丁）完成。本类负责：设备发现 →
 * USB 权限 → openDevice 拿 fd。需要真机验证（模拟器无 USB host 设备）。
 */
class UsbSource(private val context: Context) : Source {

    companion object {
        private const val ACTION_USB_PERMISSION = "xyz.mlxkj.crlbj.USB_PERMISSION"
        const val RTL_VID = 0x0BDA
        val RTL_PIDS = setOf(0x2832, 0x2838, 0x2831, 0x2839, 0x283A, 0x283B, 0x283C)
    }

    private var connection: android.hardware.usb.UsbDeviceConnection? = null
    private var grantedDevice: UsbDevice? = null

    override var lastError: String? = null
    override val isOpen: Boolean get() = connection != null

    /** 枚举 RTL-SDR 设备（电视棒常见 PID 全收，含 RTL-SDR Blog V4 的 0x2838） */
    fun findDevice(): UsbDevice? {
        val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
        return usb.deviceList.values.firstOrNull {
            it.vendorId == RTL_VID && it.productId in RTL_PIDS
        }
    }

    /** 请求 USB 权限（挂起，用户拒绝/超时抛 IOException）。已授权时立即返回。 */
    suspend fun requestPermission(): UsbDevice {
        val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
        val dev = findDevice() ?: throw IOException("未找到 RTL-SDR 设备（先插电视棒）")
        if (usb.hasPermission(dev)) return dev

        return suspendCancellableCoroutine { cont ->
            val receiver = object : BroadcastReceiver() {
                override fun onReceive(c: Context, i: Intent) {
                    c.unregisterReceiver(this)
                    val granted = i.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                    if (granted) {
                        grantedDevice = dev
                        if (cont.isActive) cont.resume(dev)
                    } else if (cont.isActive) {
                        cont.resumeWithException(IOException("USB 权限被拒绝"))
                    }
                }
            }
            if (android.os.Build.VERSION.SDK_INT >= 33) {
                context.registerReceiver(
                    receiver, IntentFilter(ACTION_USB_PERMISSION),
                    Context.RECEIVER_EXPORTED
                )
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                context.registerReceiver(receiver, IntentFilter(ACTION_USB_PERMISSION))
            }
            val pi = PendingIntent.getBroadcast(
                context, 0,
                Intent(ACTION_USB_PERMISSION).setPackage(context.packageName),
                PendingIntent.FLAG_MUTABLE,
            )
            usb.requestPermission(dev, pi)
        }
    }

    /** 返回 native 使用的 fd（USB 模式 mode=0，native 内 rtlsdr_open_fd 直接管该 fd） */
    override fun open(): Int {
        val dev = grantedDevice ?: findDevice() ?: throw IOException("未找到 RTL-SDR 设备")
        val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
        val conn = usb.openDevice(dev) ?: throw IOException("openDevice 失败（设备被占用？）")
        connection = conn
        return conn.fileDescriptor
    }

    /** USB 模式 native 直读 fd，不走此方法 */
    override fun readBlock(buffer: ByteArray): Int = 0

    override fun close() {
        connection?.close()
        connection = null
        grantedDevice = null
    }
}
