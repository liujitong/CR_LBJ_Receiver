package xyz.mlxkj.crlbj.service

import android.app.Service
import android.content.Intent
import android.os.IBinder

/**
 * 接收中前台服务（类型 connectedDevice）：仅在接收期间存在，停止接收即销毁。
 * M1 接入：通知 + USB 断连自恢复监护。
 */
class ReceiveForegroundService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
}
