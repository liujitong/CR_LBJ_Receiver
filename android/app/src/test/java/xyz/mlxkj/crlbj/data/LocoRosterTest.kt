package xyz.mlxkj.crlbj.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * 机车配属查询的回归测试（与桌面端 `cr_lbj/data/loco_roster.py` 语义必须一致）。
 *
 * 两类用例：
 *  · 合成小表：验证规则本身（别名、闭区间、第一条命中、不做泛化前缀回退）；
 *  · 真实 shared/data：验证「数据能装进来」且关键样例（HXD1D 0123 → 上局沪段）对得上。
 */
class LocoRosterTest {

    private val TYPES = """
        # 机车代号 → 短型号 / 中文名
        code,shortCode,name
        104,DF4B,东风4
        105,DF4R,东风4客
        207,SS4,韶山4
        240,HXD1D,HXD1D
        241,HXD1,和谐1
    """.trimIndent()

    private val ROSTER = """
        # 机车型号,起号,止号,配属单位,备注,制造厂
        DF4,1001,1100,京局丰段,,中车大连机车
        DF4,1101,1200,上局沪段,,中车大连机车
        SS4,2001,2100,南局南段,,中车株洲机车
        HXD1,3001,3100,广铁广段,,中车株洲机车
        HXD1D,101,200,上局沪段,,中车株洲机车
        HXD1D,150,260,南局南段,重叠号段,中车株洲机车
    """.trimIndent()

    private fun roster(types: String = TYPES, ros: String = ROSTER) = LocoRoster(
        object : SharedAssets {
            override fun read(name: String): String? = when (name) {
                LocoRoster.TYPES_FILE -> types
                LocoRoster.ROSTER_FILE -> ros
                LocoRoster.SPECS_FILE -> """{"models":{"HXD1D":{"name":"和谐1D","axle":"2(Bo-Bo)","power":"7200 kW","speed":"160 km/h","brief":"测试简介"}}}"""
                else -> null
            }

            override fun origin(name: String): String = "测试"
        }
    )

    // ------------------------------------------------------------ 文本解析

    @Test
    fun parseLocoText_variants() {
        assertEquals("HXD1D" to "0123", LocoRoster.parseLocoText("HXD1D-0123"))
        assertEquals("HXD1D" to "0123", LocoRoster.parseLocoText("HXD1D0123"))
        assertEquals("HXD1D" to "0123", LocoRoster.parseLocoText("HXD1D 0123"))
        // 中文型名 → 交给 shortCode 归一
        assertEquals("韶山4" to "0123", LocoRoster.parseLocoText("韶山4-0123"))
        // 完全无号：只给型号文本
        assertEquals("HXD1D" to null, LocoRoster.parseLocoText("HXD1D"))
        assertEquals("" to null, LocoRoster.parseLocoText(""))
        assertEquals("" to null, LocoRoster.parseLocoText("----"))
    }

    @Test
    fun parseNumber_stripsLeadingZerosAndNoise() {
        assertEquals(123, LocoRoster.parseNumber("0123"))
        // 与桌面端 _parse_number 一致：**只留数字**，所以 "HXD1D-0123" 会串成 10123。
        // 这种写法由 parseLocoText 先拆开（见上一条用例），不会走到这里。
        assertEquals(10123, LocoRoster.parseNumber("HXD1D-0123"))
        assertNull(LocoRoster.parseNumber(""))
        assertNull(LocoRoster.parseNumber("----"))
    }

    // ------------------------------------------------------------ 代号归一

    @Test
    fun shortCode_fromCodeAndFromName() {
        val r = roster()
        assertEquals("HXD1D", r.shortCode(code = "240"))
        assertEquals("SS4", r.shortCode(name = "韶山4"))
        assertEquals("SS4", r.shortCode(name = "ss4"))
        // 表里没收录的代号：不能凭空造，返回空串
        assertEquals("", r.shortCode(code = "9999"))
        assertEquals("", r.shortCode(name = "----"))
        assertEquals("韶山4", r.typeName("207"))
        assertEquals("", r.typeName("9999"))
    }

    // ------------------------------------------------------------ 主查询

    @Test
    fun lookup_exactHit_returnsFirstRange() {
        // 180 同时落在 101-200 与 150-260 两个号段里 → 取第一条，另一条进 alternatives
        val res = roster().lookup("HXD1D", "0180")
        assertTrue(res.ok)
        assertTrue(res.exact)
        assertEquals("上局沪段", res.depot)
        assertEquals("101-200", res.range)
        assertEquals("中车株洲机车", res.maker)
        assertEquals(1, res.alternatives.size)
        assertEquals("150-260", res.alternatives[0].text)
        assertEquals("南局南段", res.alternatives[0].depot)
    }

    @Test
    fun lookup_numberUnrecorded_isOkButNotExact() {
        val res = roster().lookup("HXD1D", "999")
        assertTrue("型号存在 → ok=true（界面显示配属未知）", res.ok)
        assertFalse(res.exact)
        assertTrue(res.reason.contains("无该编号"))
    }

    @Test
    fun lookup_modelOnly_isOkButNotExact() {
        val res = roster().lookup("HXD1D", "")
        assertTrue(res.ok)
        assertFalse(res.exact)
        assertTrue(res.reason.contains("缺少机车编号"))
    }

    @Test
    fun lookup_unknownModel_notOkWithSuggestions() {
        // 表里有 SS4，没有 SS：前缀相同 → 给出相近型号提示
        val res = roster().lookup("SS", "1")
        assertFalse(res.ok)
        assertTrue(res.reason.contains("未收录"))
        assertTrue("相近型号应包含 SS4，实际 ${res.suggest}", res.suggest.contains("SS4"))
    }

    @Test
    fun lookup_aliasDf4b_foldsToDf4() {
        val res = roster().lookup("DF4B", "1050")
        assertTrue(res.ok)
        assertTrue(res.exact)
        assertEquals("DF4", res.model)
        assertEquals("DF4B", res.aliasFrom)
        assertEquals("京局丰段", res.depot)
    }

    @Test
    fun lookup_noGenericPrefixFallback_hxd1dNeverBecomesHxd1() {
        // 表里只有 HXD1，没有 HXD1D：必须「未收录」，绝不能退化成 HXD1 的号段
        val onlyHxd1 = roster(ros = "HXD1,3001,3100,广铁广段,,中车株洲机车")
        val res = onlyHxd1.lookup("HXD1D", "3050")
        assertFalse(res.ok)
        assertTrue(res.reason.contains("未收录"))
    }

    @Test
    fun lookup_emptyModel_reportsMissingModel() {
        val res = roster().lookup("", "123")
        assertFalse(res.ok)
        assertTrue(res.reason.contains("缺少机车型号"))
    }

    @Test
    fun lookupLoco_usesCodeFirst() {
        val res = roster().lookupLoco("HXD1D-0123", "240")
        assertTrue(res.ok)
        assertEquals("上局沪段", res.depot)
        assertEquals("HXD1D", res.name)
    }

    // ------------------------------------------------------------ 技术参数

    @Test
    fun specsFor_readsModelsAndFallsBackToPrefix() {
        val r = roster()
        val spec = r.specsFor("HXD1D")
        assertNotNull(spec)
        assertEquals("和谐1D", spec!!.name)
        // 号段表里常见加长写法（HXD3CA）：按前缀退一步
        val ca = roster(ros = "HXD1DCA,1,10,测试段,,测试厂").specsFor("HXD1DCA")
        assertNotNull(ca)
        assertEquals("和谐1D", ca!!.name)
    }

    // ------------------------------------------------------------ 真实数据

    private fun realDir(): File? {
        // 单元测试工作目录 = app/，shared 在仓库根
        val dir = File("../../shared/data")
        return if (File(dir, LocoRoster.ROSTER_FILE).isFile) dir else null
    }

    @Test
    fun realRoster_loadsAndMatchesHxd1d0123() {
        val dir = realDir()
        if (dir == null) {
            println("跳过：找不到 shared/data（工作目录 ${File(".").absolutePath}）")
            return
        }
        val r = LocoRosterHolder.fromDir(dir)
        val st = r.stats()
        assertTrue("号段行数应 ≥ 15000，实际 ${st.rows}", st.rows >= 15000)
        assertTrue("型号数应 ≥ 100，实际 ${st.models}", st.models >= 100)
        // 官方原始表里有极少数行没写配属单位，界面按「原表未标注配属」处理
        assertTrue("空配属行应很少，实际 ${st.emptyDepot}", st.emptyDepot < 20)

        val res = r.lookup("HXD1D", "0123")
        assertTrue(res.ok && res.exact)
        assertEquals("上局沪段", res.depot)
        assertEquals("106-137", res.range)

        // 报文代号 240 → HXD1D；代号 207 → SS4
        assertEquals("HXD1D", r.shortCode(code = "240"))
        assertEquals("SS4", r.shortCode(code = "207"))
        assertNotNull(r.specsFor("HXD1D"))
        assertTrue(r.models().contains("DF4"))
    }
}
