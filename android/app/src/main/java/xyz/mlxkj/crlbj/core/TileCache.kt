package xyz.mlxkj.crlbj.core

import android.content.Context
import com.jakewharton.disklrucache.DiskLruCache
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * 地图瓦片离线缓存宿主（v3.1，与 shared/web/railmap.html 的 LBJHost 契约配套）。
 *
 *  · DiskLruCache：cacheDir/tile_cache，上限 300MB，LRU 自动淘汰；
 *  · 拦截瓦片主机（天地图/百度/高德/OSM/ORM）：命中直接返回，未命中原生代拉落盘；
 *  · 代拉统一浏览器 UA；天地图按 tdtReferer 附加 Referer，百度固定
 *    `Referer: https://map.baidu.com/`（无 Referer 会 403，实测）；
 *  · 非 2xx / 超时 / 异常一律返回 null，由调用方走 WebView 原路。
 */
class TileCache private constructor(private val cache: DiskLruCache) {

    /** 缓存命中 → 原始字节（DiskLruCache 自动维护 LRU 访问序） */
    fun get(url: String): ByteArray? = runCatching {
        cache.get(key(url))?.use { snap -> snap.getInputStream(0).readBytes() }
    }.getOrNull()

    /** 代拉成功后落盘（失败静默，不影响本次显示） */
    fun put(url: String, bytes: ByteArray) {
        runCatching {
            val ed = cache.edit(key(url)) ?: return
            try {
                ed.newOutputStream(0).use { it.write(bytes) }
                ed.commit()
            } catch (t: Throwable) {
                runCatching { ed.abort() }
            }
        }
    }

    /** (张数, 字节数)。张数按 journal 数据文件计，字节数取 DiskLruCache.size() */
    fun stats(): Pair<Long, Long> {
        val bytes = runCatching { cache.size() }.getOrDefault(0L)
        val count = runCatching {
            cache.directory.listFiles()?.count { it.name.endsWith(".0") }?.toLong() ?: 0L
        }.getOrDefault(0L)
        return count to bytes
    }

    /** 清空缓存：DiskLruCache 2.0.2 无 evictAll，用 delete() 全删并重建实例 */
    fun clear() {
        runCatching { cache.delete() }
        synchronized(TileCache) { instance = null }
    }

    data class Fetched(val bytes: ByteArray, val mime: String)

    companion object {
        private const val MAX_BYTES = 300L * 1024 * 1024

        @Volatile private var instance: TileCache? = null

        fun get(ctx: Context): TileCache = instance ?: synchronized(this) {
            instance ?: TileCache(
                DiskLruCache.open(File(ctx.applicationContext.cacheDir, "tile_cache"), 1, 1, MAX_BYTES)
            ).also { instance = it }
        }

        /** DiskLruCache 键要求 [a-z0-9_-]{1,120} → URL 的 SHA-256 hex */
        fun key(url: String): String =
            MessageDigest.getInstance("SHA-256").digest(url.toByteArray())
                .joinToString("") { "%02x".format(it) }

        /**
         * 瓦片请求的 User-Agent。
         *
         * **合规要求（v3.2.2 整改）**：OpenStreetMap 官方瓦片与 OpenRailwayMap 的
         * 使用政策都要求客户端提供**可识别的 UA**（含应用名 / 版本 / 联系方式），
         * 伪装成浏览器会被判定为违规并返回 `418 Access blocked`。所以这两家用
         * [UA_APP]；高德 / 百度 / 天地图对 UA 无此要求，沿用浏览器 UA 更稳。
         */
        const val UA_APP = "CR-LBJ-Receiver/3.2.2 " +
            "(+https://github.com/liujitong/CR_LBJ_Receiver; LBJ train-alert receiver)"

        const val UA_BROWSER = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"

        /** OSM / ORM：须用可识别 UA，且**禁止批量预取/下载**（其使用政策明文规定） */
        fun isPolicyStrictHost(host: String): Boolean =
            host == "tile.openstreetmap.org" || host.endsWith(".openrailwaymap.org")

        fun userAgentFor(host: String): String =
            if (isPolicyStrictHost(host)) UA_APP else UA_BROWSER

        /** 瓦片主机白名单（代拉 + 缓存） */
        fun isTileHost(host: String): Boolean =
            host.endsWith("tianditu.gov.cn") ||
            host.endsWith(".bdimg.com") ||
            host.endsWith(".autonavi.com") ||
            host == "tile.openstreetmap.org" ||
            host.endsWith(".openrailwaymap.org")

        /** 按主机附加 Referer；null = 不附加 */
        fun refererFor(host: String, tdtReferer: String): String? = when {
            host.endsWith("tianditu.gov.cn") ->
                tdtReferer.ifEmpty { null }?.let { "https://$it/" }
            host.endsWith(".bdimg.com") -> "https://map.baidu.com/"
            // ORM 不允许伪造 Referer（其政策要求真实来源），带合规 UA 即可正常取图
            else -> null
        }

        /**
         * 原生代拉：按主机选合规 UA + 按主机 Referer，10s 连接 / 20s 读取超时。
         * 非 2xx / 异常返回 null（调用方走 WebView 原路）。
         */
        fun fetch(url: String, tdtReferer: String): Fetched? = runCatching {
            val u = URL(url)
            val host = u.host ?: ""
            val conn = u.openConnection() as HttpURLConnection
            conn.connectTimeout = 10_000
            conn.readTimeout = 20_000
            conn.instanceFollowRedirects = true
            conn.setRequestProperty("User-Agent", userAgentFor(host))
            refererFor(host, tdtReferer)?.let { conn.setRequestProperty("Referer", it) }
            val code = conn.responseCode
            if (code !in 200..299) {
                conn.disconnect()
                return@runCatching null
            }
            val bytes = conn.inputStream.use { it.readBytes() }
            val mime = conn.contentType?.substringBefore(';')?.trim()?.ifEmpty { null }
                ?: sniffMime(bytes)
            conn.disconnect()
            Fetched(bytes, mime)
        }.getOrNull()

        /** Content-Type 缺失时按魔数嗅探（瓦片均为 png/jpeg/webp/gif） */
        fun sniffMime(b: ByteArray): String = when {
            b.size >= 8 && b[0] == 0x89.toByte() && b[1] == 0x50.toByte() -> "image/png"
            b.size >= 2 && b[0] == 0xFF.toByte() && b[1] == 0xD8.toByte() -> "image/jpeg"
            b.size >= 12 && b[0] == 0x52.toByte() && b[8] == 0x57.toByte() -> "image/webp"
            b.size >= 4 && b[0] == 0x47.toByte() && b[1] == 0x49.toByte() -> "image/gif"
            else -> "application/octet-stream"
        }
    }
}
