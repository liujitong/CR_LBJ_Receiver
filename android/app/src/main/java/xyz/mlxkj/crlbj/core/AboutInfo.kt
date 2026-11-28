package xyz.mlxkj.crlbj.core

import android.content.Context
import org.json.JSONObject

/**
 * 关于信息（v4.0）。
 *
 * 数据来自 **shared/about.json** —— 桌面端与安卓端共用同一份文件，
 * 版本号 / 作者 / 开源致谢 / 开源协议只维护一处，避免两端文案不一致。
 * 打包进 APK 后路径为 `assets/about.json`（shared/ 是 assets 根目录）。
 */
data class AboutCredit(
    val name: String = "",
    val author: String = "",
    val url: String = "",
    val license: String = "",
    val usage: String = "",
)

data class AboutInfo(
    val name: String = "CR-LBJ-Receiver",
    val displayName: String = "中国铁路 LBJ 列车预警器解码程序",
    val version: String = "",
    val releaseDate: String = "",
    val author: String = "刘纪彤（BG2GBQ）",
    val email: String = "",
    val repository: String = "",
    val license: String = "GPL-3.0",
    val summary: String = "",
    val disclaimer: String = "",
    val platforms: List<String> = emptyList(),
    val credits: List<AboutCredit> = emptyList(),
    val specialThanks: List<Pair<String, String>> = emptyList(),
) {
    companion object {
        /** 读取内置 about.json；文件缺失/损坏时返回最小可用对象（不影响界面）。 */
        fun load(ctx: Context): AboutInfo = try {
            val text = ctx.assets.open("about.json")
                .bufferedReader(Charsets.UTF_8).use { it.readText() }
            parse(text)
        } catch (_: Exception) {
            AboutInfo()
        }

        fun parse(text: String): AboutInfo {
            val o = JSONObject(text)
            val creditArr = o.optJSONArray("credits")
            val credits = ArrayList<AboutCredit>()
            if (creditArr != null) {
                for (i in 0 until creditArr.length()) {
                    val c = creditArr.optJSONObject(i) ?: continue
                    credits.add(
                        AboutCredit(
                            name = c.optString("name"),
                            author = c.optString("author"),
                            url = c.optString("url"),
                            license = c.optString("license"),
                            usage = c.optString("usage"),
                        )
                    )
                }
            }
            val thanksArr = o.optJSONArray("specialThanks")
            val thanks = ArrayList<Pair<String, String>>()
            if (thanksArr != null) {
                for (i in 0 until thanksArr.length()) {
                    val c = thanksArr.optJSONObject(i) ?: continue
                    thanks.add(c.optString("name") to c.optString("reason"))
                }
            }
            val platArr = o.optJSONArray("platforms")
            val platforms = ArrayList<String>()
            if (platArr != null) {
                for (i in 0 until platArr.length()) platArr.optString(i)?.let { platforms.add(it) }
            }
            return AboutInfo(
                name = o.optString("name", "CR-LBJ-Receiver"),
                displayName = o.optString("displayName", "中国铁路 LBJ 列车预警器解码程序"),
                version = o.optString("version", ""),
                releaseDate = o.optString("releaseDate", ""),
                author = o.optString("author", "刘纪彤（BG2GBQ）"),
                email = o.optString("email", ""),
                repository = o.optString("repository", ""),
                license = o.optString("license", "GPL-3.0"),
                summary = o.optString("summary", ""),
                disclaimer = o.optString("disclaimer", ""),
                platforms = platforms,
                credits = credits,
                specialThanks = thanks,
            )
        }
    }
}