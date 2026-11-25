package xyz.mlxkj.crlbj.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 第三方数据自动更新的纯逻辑测试：校验规则、注释头、数据装载。
 *
 * 网络部分（gitcode 拉取 / sha 比对 / 原子替换）在模拟器上实测，
 * 这里只保证「坏数据一定被拒」——这是不把用户的号段表弄坏的最后一道门。
 */
class DataUpdaterTest {

    private fun csv(rows: Int, models: Int = 200, depot: String = "上局沪段"): String =
        buildString {
            appendLine("# 注释行应被跳过")
            for (i in 0 until rows) {
                val m = "MX${i % models}"
                appendLine("$m,${i + 1},${i + 1},$depot,,中车测试")
            }
        }

    @Test
    fun validate_realisticDataPasses() {
        val v = DataUpdater.validate(csv(16_000))
        assertTrue(v.reason, v.ok)
        assertEquals(16_000, v.rows)
        assertEquals(200, v.models)
    }

    @Test
    fun validate_tooFewRowsRejected() {
        val v = DataUpdater.validate(csv(1_000))
        assertFalse(v.ok)
        assertTrue(v.reason.contains("行数不足"))
    }

    @Test
    fun validate_tooFewModelsRejected() {
        // 行数够但型号只有 3 个 → 典型的「拿错文件」特征
        val v = DataUpdater.validate(csv(16_000, models = 3))
        assertFalse(v.ok)
        assertTrue(v.reason.contains("型号过少"))
    }

    @Test
    fun validate_garbageRejected() {
        assertFalse(DataUpdater.validate("").ok)
        assertFalse(DataUpdater.validate(null).ok)
        assertFalse(DataUpdater.validate("<html>403 Forbidden</html>").ok)
    }

    @Test
    fun validate_badNumberColumnsRejected() {
        val body = buildString {
            for (i in 0 until 16_000) appendLine("MX,abc,def,某段,,某厂")
        }
        val v = DataUpdater.validate(body)
        assertFalse(v.ok)
        assertTrue(v.reason.contains("起止号异常") || v.reason.contains("行数不足"))
    }

    @Test
    fun withHeader_prependsExactlyThreeCommentLines() {
        val out = DataUpdater.withHeader("DF4,1,2,某段,,某厂\n", "0123456789abcdef")
        val lines = out.lines()
        assertEquals(3, lines.count { it.startsWith("#") })
        assertTrue(lines[0].startsWith("# 机车配属号段表"))
        assertTrue(lines[1].contains(DataUpdater.SOURCE_ID))
        assertTrue(lines[1].contains("0123456789ab"))
        assertTrue(lines[2].contains("机车型号,起号,止号"))
        // 注释头不能破坏可解析性
        val v = DataUpdater.validate(out.repeat(1) + csv(16_000))
        assertTrue(v.ok)
    }

    @Test
    fun headerDoesNotBreakRosterParsing() {
        val body = ROSTER_BODY
        val withHead = DataUpdater.withHeader(body, "deadbeefcafe")
        val parsed = LocoRoster.parseRoster(withHead)
        assertTrue(parsed.isNotEmpty())
        val hit = parsed["HXD1D"]?.firstOrNull { 123 in it.start..it.end }
        assertNotNull(hit)
        assertEquals("上局沪段", hit!!.depot)
    }

    @Test
    fun isoNowLooksLikeIso8601WithOffset() {
        val s = DataUpdater.isoNow()
        // 2026-11-26T02:45:03+08:00
        assertTrue("实际 $s", Regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}[+-]\\d{2}:\\d{2}$")
            .matches(s))
    }

    @Test
    fun remoteUrlPointsAtResourcesBranch() {
        assertTrue(DataUpdater.REMOTE_URL.startsWith("https://api.gitcode.com/"))
        assertTrue(DataUpdater.REMOTE_URL.contains("loco_info.csv"))
        assertTrue(DataUpdater.REMOTE_URL.contains("ref=resources"))
    }

    @Test
    fun parsePlaces_skipsCommentsAndHeader() {
        val places = parsePlaces(
            """
            # 注释
            name,lat,lng
            北京,39.90,116.41
            南昌,28.68,115.86
            坏行,abc,1
            缺列,1
            """.trimIndent()
        )
        assertEquals(2, places.size)
        assertEquals("北京", places[0].name)
        assertEquals(28.68, places[1].lat, 1e-9)
    }

    private companion object {
        val ROSTER_BODY = """
            HXD1D,1,1,武局南段,,中车株洲机车
            HXD1D,106,137,上局沪段,,中车株洲机车
            SS4,2001,2100,南局南段,,中车株洲机车
        """.trimIndent()
    }
}
