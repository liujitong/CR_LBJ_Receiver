package xyz.mlxkj.crlbj.data

import java.io.OutputStream
import java.io.OutputStreamWriter
import java.nio.charset.StandardCharsets

/**
 * CSV 导出（列与桌面版 HistoryDb.exportToCsv 完全一致，utf-8 BOM 兼容 Excel）。
 */
object CsvExporter {

    private val HEADERS = listOf(
        "时间", "车次", "方向", "速度", "公里标", "机车", "线路", "类别",
        "报文类型", "地址", "功能码", "BCD", "信号强度", "AFC", "FERR", "置信度",
        "经度", "纬度",
    )

    private fun row(r: RecordEntity): List<String> = listOf(
        r.timeStr, r.train, r.direction, r.speed, r.position, r.loco,
        r.route, r.category,
        if (r.isDetailed) "详细" else "短报文",
        r.rawAddr.toString(), r.rawFunc.toString(), r.rawBcd,
        fmt(r.rssi), fmt(r.afcHz), fmt(r.afcErrHz), fmt(r.afcScore),
        r.longitude?.toString() ?: "", r.latitude?.toString() ?: "",
    )

    private fun fmt(v: Double): String = trimNum(v)

    private fun trimNum(v: Double): String {
        val s = "%.6f".format(java.util.Locale.US, v).trimEnd('0').trimEnd('.')
        return s.ifEmpty { "0" }
    }

    fun export(out: OutputStream, records: List<RecordEntity>) {
        OutputStreamWriter(out, StandardCharsets.UTF_8).use { w ->
            w.write(0xFEFF)   // BOM
            w.write(HEADERS.joinToString(",") { csvCell(it) })
            w.write("\r\n")
            for (r in records) {
                w.write(row(r).joinToString(",") { csvCell(it) })
                w.write("\r\n")
            }
        }
    }

    /** CSV 单元格：含逗号/引号/换行时加引号包裹并转义 */
    private fun csvCell(s: String): String =
        if (s.contains(',') || s.contains('"') || s.contains('\n') || s.contains('\r')) {
            "\"" + s.replace("\"", "\"\"") + "\""
        } else s
}
