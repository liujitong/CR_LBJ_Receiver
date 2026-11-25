package xyz.mlxkj.crlbj.data

import android.content.Context
import android.util.Log
import java.io.File

/**
 * 共享数据（与桌面端 `CR_LBJ_Receiver/shared/data/` **逐字同一份**文件）的读取抽象。
 *
 * 两类来源，优先级从高到低：
 *   1. `filesDir/data/` —— 运行时自动更新下载下来的新快照（见 [DataUpdater]）；
 *   2. `assets/data/`   —— 打包进 APK 的内置快照（离线可用）。
 *
 * 之所以抽成接口，是为了让 JVM 单元测试能注入源码目录（`shared/data`）做解析校验，
 * 不必起模拟器。Android 侧用 [AndroidSharedAssets]。
 */
interface SharedAssets {
    /** 读文本；不存在返回 null（不抛异常）。 */
    fun read(name: String): String?

    /** 数据来源说明（设置页展示）：`外部更新` / `内置快照` / `缺失`。 */
    fun origin(name: String): String
}

/** 内置快照 */
const val ORIGIN_BUILTIN = "内置快照"

/** 运行时更新过的快照 */
const val ORIGIN_DOWNLOADED = "外部更新"

const val ORIGIN_MISSING = "缺失"

/**
 * Android 实现：先找 `filesDir/data/<name>`，再退到 `assets/data/<name>`。
 *
 * 注意：assets 里是 `assets/data/...`，因为 build.gradle.kts 把 `shared/` 整个目录
 * 加成了 assets 根目录（`shared/web` → `assets/web`，`shared/data` → `assets/data`）。
 */
class AndroidSharedAssets(private val ctx: Context) : SharedAssets {

    private val updateDir: File get() = File(ctx.filesDir, "data")

    override fun read(name: String): String? {
        val fresh = File(updateDir, name)
        if (fresh.isFile) {
            runCatching { return fresh.readText(Charsets.UTF_8) }
                .onFailure { Log.w(TAG, "读取更新数据失败: ${it.message}") }
        }
        return runCatching {
            ctx.assets.open("data/$name").use { it.readBytes().toString(Charsets.UTF_8) }
        }.onFailure { Log.w(TAG, "读取内置数据失败 $name: ${it.message}") }.getOrNull()
    }

    override fun origin(name: String): String = when {
        File(updateDir, name).isFile -> ORIGIN_DOWNLOADED
        runCatching { ctx.assets.open("data/$name").close() }.isSuccess -> ORIGIN_BUILTIN
        else -> ORIGIN_MISSING
    }

    companion object {
        private const val TAG = "SharedAssets"
    }
}

/** 预设中心点（`places.csv` 的一行） */
data class Place(val name: String, val lat: Double, val lng: Double) {
    override fun toString(): String = name
}

/** `places.csv` 解析：`name,lat,lng`，`#` 开头为注释。 */
fun parsePlaces(csv: String?): List<Place> {
    if (csv.isNullOrBlank()) return emptyList()
    val out = ArrayList<Place>(64)
    csv.lineSequence().forEach { line ->
        val t = line.trim()
        if (t.isEmpty() || t.startsWith("#")) return@forEach
        val cols = t.split(',')
        if (cols.size < 3) return@forEach
        val name = cols[0].trim()
        if (name.isEmpty() || name.equals("name", ignoreCase = true)) return@forEach
        val lat = cols[1].trim().toDoubleOrNull() ?: return@forEach
        val lng = cols[2].trim().toDoubleOrNull() ?: return@forEach
        out.add(Place(name, lat, lng))
    }
    return out
}
