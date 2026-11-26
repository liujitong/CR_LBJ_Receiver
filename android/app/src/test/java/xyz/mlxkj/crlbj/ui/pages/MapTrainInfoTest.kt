package xyz.mlxkj.crlbj.ui.pages

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import xyz.mlxkj.crlbj.data.LocoRoster
import xyz.mlxkj.crlbj.data.TrainInfoClient

/**
 * v3.2：车次/机车信息 → 地图 payload info 字段的映射。
 *
 * 契约与 `shared/web/railmap.html` 的 `infoRows()` 一致：
 * grade 等级 · bureau 担当局 · section 担当段 · owner 配属段 · model 车型
 * · from/to 始发终到 · locoDepot 机车配属 · locoMaker 制造厂 · locoModel 型号
 */
class MapTrainInfoTest {

    private fun loco(
        ok: Boolean = true,
        model: String = "HXD3C",
        depot: String = "",
        maker: String = "",
        exact: Boolean = true,
        reason: String = "",
    ) = LocoRoster.Lookup(
        ok = ok,
        exact = exact,
        model = model,
        number = 891,
        numberText = "0891",
        depot = depot,
        maker = maker,
        reason = reason,
    )

    @Test
    fun mapsTrainInfoFields() {
        val ti = TrainInfoClient.TrainInfo(
            ok = true,
            train = "K1234",
            category = "快速旅客列车",
            bureau = "南昌局",
            runner = "南昌客运段",
            carOwner = "南昌车辆段",
            car = "25G",
            start = "南昌",
            end = "北京西",
        )
        val out = trainInfoMap(ti, null)
        assertEquals("快速旅客列车", out["grade"])
        assertEquals("南昌局", out["bureau"])
        assertEquals("南昌客运段", out["section"])
        assertEquals("南昌车辆段", out["owner"])
        assertEquals("25G", out["model"])
        assertEquals("南昌", out["from"])
        assertEquals("北京西", out["to"])
    }

    @Test
    fun mapsLocoInfoFields() {
        val out = trainInfoMap(null, loco(depot = "南昌局南昌机务段", maker = "中车大连机车"))
        assertEquals("南昌局南昌机务段", out["locoDepot"])
        assertEquals("中车大连机车", out["locoMaker"])
        assertEquals("HXD3C", out["locoModel"])
    }

    @Test
    fun mergedWhenBothPresent() {
        val ti = TrainInfoClient.TrainInfo(
            ok = true, train = "G1", category = "动车组", bureau = "北京局",
        )
        val out = trainInfoMap(ti, loco(model = "CR400BF", depot = "北京局北京机务段"))
        assertEquals("动车组", out["grade"])
        assertEquals("北京局", out["bureau"])
        assertEquals("CR400BF", out["locoModel"])
        assertEquals("北京局北京机务段", out["locoDepot"])
    }

    @Test
    fun failedQueriesYieldEmptyInfo() {
        val badTrain = TrainInfoClient.TrainInfo(ok = false, error = "未查询到车次")
        val badLoco = loco(ok = false, depot = "不该出现", reason = "号段未命中")
        assertTrue(trainInfoMap(badTrain, badLoco).isEmpty())
        assertTrue(trainInfoMap(null, null).isEmpty())
    }

    @Test
    fun blankFieldsAreDropped() {
        val ti = TrainInfoClient.TrainInfo(ok = true, train = "Z1", category = "  ")
        val out = trainInfoMap(ti, null)
        assertTrue("空字符串不应写进 info", out.isEmpty())
    }
}