package com.ahmemory.app.llm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import com.ahmemory.app.AhApplication
import com.ahmemory.app.MainActivity
import com.ahmemory.app.R
import com.ahmemory.app.data.LiveAhRepository

class ModelPrepareService : Service() {
    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startInForeground("подготовка модели…")
        acquireLocks()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground(AndroidNpuEngine.status.label.ifBlank { "подготовка модели…" })
        if (worker?.isAlive == true) return START_STICKY
        val variant = intent?.getStringExtra(EXTRA_VARIANT)
        val downloadOnly = intent?.getBooleanExtra(EXTRA_DOWNLOAD_ONLY, false) == true
        worker = Thread({
            val repo = (application as AhApplication).repository
            try {
                if (repo is LiveAhRepository) {
                    repo.runPrepare(variant, downloadOnly)
                } else if (!variant.isNullOrBlank()) {
                    if (downloadOnly) repo.beginDownload(variant) else repo.setModelVariant(variant)
                } else {
                    repo.start()
                }
            } catch (error: Throwable) {
                Log.e(AhApplication.TAG, "model prepare failed", error)
            } finally {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }, "ah-model-prepare").also { it.start() }
        Thread({
            while (worker?.isAlive == true) {
                val status = AndroidNpuEngine.status
                updateNotification(status.label.ifBlank { "подготовка модели…" })
                try {
                    Thread.sleep(500)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }, "ah-model-notify").start()
        return START_STICKY
    }

    override fun onDestroy() {
        releaseLocks()
        super.onDestroy()
    }

    private fun acquireLocks() {
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AHMemory:model").apply {
            setReferenceCounted(false)
            acquire(4 * 60 * 60 * 1000L)
        }
        val wifi = applicationContext.getSystemService(WIFI_SERVICE) as WifiManager
        wifiLock = runCatching {
            @Suppress("DEPRECATION")
            wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "AHMemory:model").apply {
                setReferenceCounted(false)
                acquire()
            }
        }.getOrNull()
    }

    private fun releaseLocks() {
        runCatching { if (wakeLock?.isHeld == true) wakeLock?.release() }
        runCatching { if (wifiLock?.isHeld == true) wifiLock?.release() }
        wakeLock = null
        wifiLock = null
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < 26) return
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(CHANNEL_ID, "Загрузка модели", NotificationManager.IMPORTANCE_LOW)
        channel.setShowBadge(false)
        manager.createNotificationChannel(channel)
    }

    private fun startInForeground(text: String) {
        val notification = notification(text)
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle(getString(R.string.app_name))
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        .setSmallIcon(android.R.drawable.stat_sys_download)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setContentIntent(
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            ),
        )
        .build()

    companion object {
        private const val CHANNEL_ID = "ah_model"
        private const val NOTIFICATION_ID = 41
        const val EXTRA_VARIANT = "variant"
        const val EXTRA_DOWNLOAD_ONLY = "download_only"

        fun start(context: Context, variantId: String? = null, downloadOnly: Boolean = false) {
            val intent = Intent(context, ModelPrepareService::class.java)
            if (!variantId.isNullOrBlank()) intent.putExtra(EXTRA_VARIANT, variantId)
            intent.putExtra(EXTRA_DOWNLOAD_ONLY, downloadOnly)
            if (Build.VERSION.SDK_INT >= 26) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
