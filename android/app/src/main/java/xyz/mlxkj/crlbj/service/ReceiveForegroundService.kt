package xyz.mlxkj.crlbj.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat
import xyz.mlxkj.crlbj.MainActivity

/**
 * 接收中前台服务（类型 connectedDevice）：仅在接收期间存在，停止接收即销毁。
 * 常驻通知 = "开机就用、用完就关" 的状态锚点；系统低内存时保接收线程优先。
 */
class ReceiveForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                startForeground(NOTIFY_ID, buildNotification())
            }
        }
        return START_STICKY
    }

    private fun buildNotification(): Notification {
        val contentIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("LBJ 预警接收中")
            .setContentText("便携 LBJ 列车预警接收运行中")
            .setContentIntent(contentIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    companion object {
        const val CHANNEL_ID = "receive"
        const val NOTIFY_ID = 1
        const val ACTION_STOP = "xyz.mlxkj.crlbj.STOP"

        fun ensureChannel(ctx: Context) {
            val mgr = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            mgr.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "接收状态", NotificationManager.IMPORTANCE_LOW)
            )
        }
    }
}
