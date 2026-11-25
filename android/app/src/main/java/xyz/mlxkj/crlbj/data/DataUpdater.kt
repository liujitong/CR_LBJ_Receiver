package xyz.mlxkj.crlbj.data

import android.content.Context
import android.util.Base64
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.net.UnknownHostException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 第三方数据自动更新（机车配属号段表）。
 *
 * 上游：`github.com/undef-i/LBJ_Console` 的 `resources` 分支 `loco_info.csv`
 * （桌面端 `cr_lbj/data/loco_roster.py` 注释里的同一份数据），国内走 gitcode 镜像，
 * 返回文件内容（base64）+ sha，零鉴权。
 *
 * 落地：
 *   · `filesDir/data/loco_roster.csv`       运行时快照（文件头补 3 行 `#` 注释）
 *   · `filesDir/data/data_manifest.json`    版本记录 {sha, fetchedAt, rows, source}
 *   · `filesDir/data/loco_roster.csv.bak`   上一次的旧快照（回滚用）
 *
 * 安全策略（**任何失败都不抛异常**，绝不损坏已有数据）：
 *   1. sha 与 manifest 相同 → 直接跳过（省流量）；
 *   2. 下载后先校验（行数 ≥ 15000、每行 ≥ 4 列、起止号是数字、型号 ≥ 100 种）；
 *      校验不过 → 丢弃，保留旧文件，返回 ok=false + 原因；
 *   3. 通过 → 写 `.tmp` → 旧文件改名 `.bak` → `.tmp` 原子改名成正式文件；
 *   4. 网络/JSON/超时异常 → 捕获后返回 ok=false，调用方静默处理（不阻塞启动）。
 */
object DataUpdater {

    private const val TAG = "DataUpdater"

    /** 上游地址（gitcode 镜像，实测 200） */
    const val REMOTE_URL =
        "https://api.gitcode.com/api/v5/repos/CCCccc233/LBJ_Console/contents/loco_info.csv?ref=resources"

    const val SOURCE_ID = "gitcode:CCCccc233/LBJ_Console@resources"

    const val FILE = "loco_roster.csv"
    const val MANIFEST = "data_manifest.json"
    private const val BAK = "$FILE.bak"
    private const val TMP = "$FILE.tmp"

    /** 校验下限：真实数据 16622 行、约 200 个型号 */
    const val MIN_ROWS = 15_000

    const val MIN_MODELS = 100

    private const val PREF_LAST_CHECK = "dataLastCheck"

    private const val UA = "CR-LBJ-Receiver/3.0 (Android)"

    // ------------------------------------------------------------------ 结果

    data class UpdateResult(
        val ok: Boolean,
        val message: String,
        val rows: Int = 0,
        val updated: Boolean = false,
    )

    /** manifest 里的一条记录 */
    data class Entry(
        val sha: String,
        val fetchedAt: String,
        val rows: Int,
        val source: String,
    )

    // ------------------------------------------------------------------ 路径

    fun dataDir(ctx: Context): File = File(ctx.filesDir, "data").apply { mkdirs() }

    fun targetFile(ctx: Context): File = File(dataDir(ctx), FILE)

    // ---------------------------------------------------------------- 状态

    fun readManifest(ctx: Context): Entry? {
        val f = File(dataDir(ctx), MANIFEST)
        if (!f.isFile) return null
        return try {
            val root = JSONObject(f.readText(Charsets.UTF_8))
            val item = root.optJSONObject(FILE) ?: return null
            Entry(
                sha = item.optString("sha"),
                fetchedAt = item.optString("fetchedAt"),
                rows = item.optInt("rows"),
                source = item.optString("source"),
            )
        } catch (t: Throwable) {
            Log.w(TAG, "manifest 读不出来: ${t.message}")
            null
        }
    }

    /** 距离上次检查是否超过 [days] 天（用于「启动时静默自动检查」） */
    fun shouldAutoCheck(ctx: Context, days: Int = 7): Boolean {
        val last = ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE)
            .getLong(PREF_LAST_CHECK, 0L)
        if (last <= 0L) return true
        return System.currentTimeMillis() - last > days * 24L * 3600_000L
    }

    fun markChecked(ctx: Context) {
        ctx.getSharedPreferences("lbj", Context.MODE_PRIVATE).edit()
            .putLong(PREF_LAST_CHECK, System.currentTimeMillis()).apply()
    }

    // ---------------------------------------------------------------- 校验

    data class Validation(
        val ok: Boolean,
        val rows: Int,
        val models: Int,
        val reason: String = "",
    )

    /**
     * 校验上游 CSV（纯函数，单元测试直接调）。
     *
     * 注意上游**没有表头**，第一行就是数据；`#` 开头视为注释。
     */
    fun validate(csv: String?): Validation {
        if (csv.isNullOrBlank()) return Validation(false, 0, 0, "内容为空")
        var rows = 0
        var badCols = 0
        var badNumber = 0
        val models = HashSet<String>(512)
        csv.lineSequence().forEach { line ->
            val t = line.trim()
            if (t.isEmpty() || t.startsWith("#")) return@forEach
            val cols = t.split(',')
            if (cols.size < 4) {
                badCols++
                return@forEach
            }
            val model = cols[0].trim()
            val a = cols[1].filter { it.isDigit() }
            val b = cols[2].filter { it.isDigit() }
            if (model.isEmpty() || a.isEmpty() || b.isEmpty()) {
                badNumber++
                return@forEach
            }
            models.add(model.uppercase(Locale.US))
            rows++
        }
        return when {
            rows < MIN_ROWS ->
                Validation(false, rows, models.size, "行数不足（$rows < $MIN_ROWS）")
            models.size < MIN_MODELS ->
                Validation(false, rows, models.size, "型号过少（${models.size} < $MIN_MODELS）")
            badCols * 100 > rows ->
                Validation(false, rows, models.size, "列数异常行过多（$badCols）")
            badNumber * 100 > rows ->
                Validation(false, rows, models.size, "起止号异常行过多（$badNumber）")
            else -> Validation(true, rows, models.size)
        }
    }

    /** 给快照补 3 行注释头（`#` 开头，解析时跳过） */
    fun withHeader(body: String, sha: String): String {
        val head = buildString {
            appendLine("# 机车配属号段表 · 运行时自动更新")
            appendLine("# 来源: $SOURCE_ID (sha ${sha.take(12)})")
            appendLine("# 格式: 机车型号,起号,止号,配属单位(路局/机务段),备注,制造厂")
        }
        return head + body
    }

    // ---------------------------------------------------------------- 更新

    /**
     * 检查并（必要时）更新配属表。
     *
     * @param force true = 忽略 sha 比较，强制重新下载
     * @return 永不抛异常；失败时 `ok=false` 且 message 说明原因
     */
    suspend fun check(
        ctx: Context,
        force: Boolean = false,
        timeoutMs: Int = 20_000,
    ): UpdateResult = withContext(Dispatchers.IO) {
        var conn: HttpURLConnection? = null
        try {
            conn = (URL(REMOTE_URL).openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = timeoutMs
                readTimeout = timeoutMs
                setRequestProperty("User-Agent", UA)
                setRequestProperty("Accept", "application/json")
            }
            val code = conn.responseCode
            if (code !in 200..299) {
                return@withContext UpdateResult(false, "上游返回 HTTP $code")
            }
            val body = conn.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
            val root = JSONObject(body)
            val sha = root.optString("sha")
            val contentB64 = root.optString("content")
            if (sha.isEmpty() || contentB64.isEmpty()) {
                return@withContext UpdateResult(false, "上游返回缺少 sha/content 字段")
            }

            val manifest = readManifest(ctx)
            if (!force && manifest?.sha == sha) {
                return@withContext UpdateResult(
                    ok = true,
                    message = "已是最新（sha ${sha.take(8)}，${manifest.rows} 行）",
                    rows = manifest.rows,
                    updated = false,
                )
            }

            val raw = try {
                Base64.decode(contentB64.replace("\n", "").replace("\r", ""), Base64.DEFAULT)
                    .toString(Charsets.UTF_8)
            } catch (t: Throwable) {
                return@withContext UpdateResult(false, "base64 解码失败：${t.message}")
            }

            val v = validate(raw)
            if (!v.ok) {
                return@withContext UpdateResult(
                    false, "校验未通过：${v.reason}（已保留原数据）", v.rows, false)
            }

            val dir = dataDir(ctx)
            val target = File(dir, FILE)
            val tmp = File(dir, TMP)
            val bak = File(dir, BAK)
            tmp.writeText(withHeader(raw, sha), Charsets.UTF_8)
            if (target.isFile) {
                runCatching { bak.delete() }
                if (!target.renameTo(bak)) {
                    tmp.delete()
                    return@withContext UpdateResult(false, "旧文件改名 .bak 失败（已保留原数据）")
                }
            }
            if (!tmp.renameTo(target)) {
                // 改名失败：把 .bak 还原，别把数据弄丢
                if (bak.isFile) bak.renameTo(target)
                tmp.delete()
                return@withContext UpdateResult(false, "新文件落盘失败（已还原原数据）")
            }

            val fetchedAt = isoNow()
            val manifestJson = JSONObject().apply {
                put(FILE, JSONObject().apply {
                    put("sha", sha)
                    put("fetchedAt", fetchedAt)
                    put("rows", v.rows)
                    put("source", SOURCE_ID)
                })
            }
            File(dir, MANIFEST).writeText(manifestJson.toString(2), Charsets.UTF_8)

            Log.i(TAG, "配属表已更新 sha=${sha.take(8)} rows=${v.rows} models=${v.models}")
            UpdateResult(
                ok = true,
                message = "已更新：${v.rows} 行 / ${v.models} 个型号（sha ${sha.take(8)}）",
                rows = v.rows,
                updated = true,
            )
        } catch (e: SocketTimeoutException) {
            UpdateResult(false, "请求超时（${timeoutMs / 1000}s）")
        } catch (e: UnknownHostException) {
            UpdateResult(false, "网络不可达（域名解析失败）")
        } catch (e: IOException) {
            UpdateResult(false, "网络不可达（${e.message ?: e.javaClass.simpleName}）")
        } catch (e: Throwable) {
            Log.w(TAG, "更新失败", e)
            UpdateResult(false, "更新失败：${e.message ?: e.javaClass.simpleName}")
        } finally {
            runCatching { conn?.disconnect() }
        }
    }

    fun isoNow(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).format(Date())
}
