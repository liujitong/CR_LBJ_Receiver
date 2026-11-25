package xyz.mlxkj.crlbj.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 车次查询解析的回归测试（字段语义与桌面端 `cr_lbj/data/train_info.py` 对齐）。
 *
 * 用真实接口返回结构的 JSON 字面量，纯离线跑——网络相关的部分由模拟器实测覆盖。
 */
class TrainInfoClientTest {

    // RailGo `/api/train/query?train=G7` 的真实结构（截了几站）
    private val RAILGO = """
        {
          "number": "G7",
          "numberKind": "G",
          "numberFull": ["G7"],
          "type": "高速动车组",
          "bureauName": "北京局集团公司",
          "runner": "北京客运段",
          "carOwner": "北京动车段",
          "car": "CR400AF",
          "rundays": ["2026-11-24", "2026-11-25", "2026-11-26"],
          "diagramType": "始发",
          "timetable": [
            {"station": "北京南", "stationTelecode": "VNP", "arrive": "07:00", "depart": "07:00",
             "stopTime": 0, "distance": 0, "speed": 0, "day": 0},
            {"station": "济南西", "stationTelecode": "JGK", "arrive": "08:22", "depart": "08:25",
             "stopTime": 3, "distance": 406, "speed": 300, "day": 0},
            {"station": "上海虹桥", "stationTelecode": "AOH", "arrive": "11:29", "depart": "11:29",
             "stopTime": 0, "distance": 1318, "speed": 0, "day": 0}
          ],
          "diagram": [
            {"number": "G7", "from": ["北京南", "07:00"], "to": ["上海虹桥", "11:29"]}
          ]
        }
    """.trimIndent()

    @Test
    fun normalizeAndValidateTrainCode() {
        assertEquals("G7", TrainInfoClient.normalizeTrain(" g 7 "))
        assertEquals("G7", TrainInfoClient.normalizeTrain("ｇ7"))
        assertTrue(TrainInfoClient.isTrainCode("G7"))
        assertTrue(TrainInfoClient.isTrainCode("K1234"))
        assertTrue(TrainInfoClient.isTrainCode("1461"))
        assertFalse(TrainInfoClient.isTrainCode(""))
        assertFalse(TrainInfoClient.isTrainCode("G7G"))
        assertFalse(TrainInfoClient.isTrainCode("G123456"))
    }

    @Test
    fun parseRailGo_fullFields() {
        val r = TrainInfoClient.parseRailGo(JSONObject(RAILGO), "G7")
        assertTrue(r.ok)
        assertEquals("railgo", r.source)
        assertEquals("G7", r.train)
        assertEquals("高速动车组", r.category)
        assertEquals("北京局集团公司", r.bureau)
        assertEquals("北京客运段", r.runner)
        assertEquals("北京动车段", r.carOwner)
        assertEquals("CR400AF", r.car)
        assertEquals(3, r.rundaysCount)
        assertEquals("始发", r.diagramType)

        assertEquals(3, r.stops.size)
        assertEquals("北京南", r.start)
        assertEquals("上海虹桥", r.end)
        assertEquals("07:00", r.startTime)
        assertEquals("11:29", r.endTime)
        assertEquals(1318.0, r.distance!!, 0.001)

        val jinan = r.stops[1]
        assertEquals(2, jinan.no)
        assertEquals("济南西", jinan.station)
        assertEquals("08:22", jinan.arrive)
        assertEquals("08:25", jinan.depart)
        assertEquals(3, jinan.stopMin)
        assertEquals(406.0, jinan.distance!!, 0.001)

        assertEquals(1, r.diagram.size)
        assertEquals("北京南", r.diagram[0].fromStation)
        assertEquals("上海虹桥", r.diagram[0].toStation)
        assertTrue(r.summary().contains("北京南→上海虹桥"))
    }

    @Test
    fun parseRailGo_missingNumber_isError() {
        val r = TrainInfoClient.parseRailGo(JSONObject("{}"), "G404")
        assertFalse(r.ok)
        assertTrue(r.error.contains("未查询到车次"))
        assertTrue(r.summary().contains("查询失败"))
    }

    @Test
    fun parseRailGo_nullTimetable_isSafe() {
        val json = """{"number":"K1","type":"快速"}"""
        val r = TrainInfoClient.parseRailGo(JSONObject(json), "K1")
        assertTrue(r.ok)
        assertTrue(r.stops.isEmpty())
        assertEquals("", r.start)
        assertNull(r.distance)
    }

    @Test
    fun parse12306Search_requiresStatusAndRows() {
        val ok = JSONObject(
            """{"status":true,"data":[{"train_no":"240000G7","station_train_code":"G7"}]}""")
        assertEquals("240000G7" to "G7", TrainInfoClient.parse12306Search(ok, "G7", "20261126"))
        val bad = JSONObject("""{"status":false,"data":[]}""")
        assertNull(TrainInfoClient.parse12306Search(bad, "G7", "20261126"))
    }

    @Test
    fun parse12306Detail_mapsFieldsAndStops() {
        val json = """
            {"status":true,"data":{"data":[
              {"station_no":"01","station_name":"北京南","arrive_time":"----","start_time":"07:00",
               "arrive_day_diff":"0","train_class_name":"高速动车组"},
              {"station_no":"02","station_name":"济南西","arrive_time":"08:22","start_time":"08:25",
               "arrive_day_diff":"0"},
              {"station_no":"03","station_name":"上海虹桥","arrive_time":"11:29","start_time":"----",
               "arrive_day_diff":"0"}
            ]}}
        """.trimIndent()
        val r = TrainInfoClient.parse12306Detail(JSONObject(json), "G7", "20261126")
        assertTrue(r.ok)
        assertEquals("12306", r.source)
        assertEquals("20261126", r.queryDate)
        assertEquals("高速动车组", r.category)
        assertEquals(3, r.stops.size)
        assertEquals("北京南", r.start)
        assertEquals("07:00", r.startTime)
        assertEquals("上海虹桥", r.end)
        assertEquals("11:29", r.endTime)
        // 停站分由到发时刻自行推算
        assertEquals(3, r.stops[1].stopMin)
        assertEquals(0, r.stops[0].stopMin)
        // 12306 没有担当/配属字段
        assertEquals("", r.carOwner)
        assertNull(r.distance)
    }

    @Test
    fun parse12306Detail_emptyIsError() {
        val r = TrainInfoClient.parse12306Detail(
            JSONObject("""{"status":true,"data":{"data":[]}}"""), "G7", "20261126")
        assertFalse(r.ok)
        assertTrue(r.error.contains("时刻表为空"))
    }

    @Test
    fun stopMinutes_handlesOvernightAndInvalid() {
        assertEquals(3, TrainInfoClient.stopMinutes("08:22", "08:25"))
        assertEquals(0, TrainInfoClient.stopMinutes("25:00", "26:00")) // 非法时刻
        assertEquals(0, TrainInfoClient.stopMinutes("----", "07:00"))
        assertEquals(0, TrainInfoClient.stopMinutes("23:50", "00:10")) // 跨零点不当成 20 分
    }

    @Test
    fun query_rejectsBadTrainCodeWithoutNetwork() {
        val r = TrainInfoClient.query("随便打的字")
        assertFalse(r.ok)
        assertTrue(r.error.contains("格式不对") || r.error.contains("未查询到"))
        assertNotNull(r.stops)
    }
}
