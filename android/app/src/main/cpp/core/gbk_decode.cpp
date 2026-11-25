// gbk_decode.cpp — LbjParser::gbkToUtf8 实现（GBK 双字节 → UTF-8，errors='ignore' 语义）
#include "decoder.h"
#include "gbk_table.h"

namespace lbj {

std::string LbjParser::gbkToUtf8(const unsigned char* bytes, int n) {
    std::string out;
    out.reserve(n);
    int i = 0;
    while (i < n) {
        unsigned char b = bytes[i];
        if (b < 0x80) { out += (char)b; i++; continue; }
        if (i + 1 >= n) break;
        int hi = b, lo = bytes[i + 1];
        if (hi < 0x81 || hi > 0xFE || lo < 0x40 || lo > 0xFE || lo == 0x7F) {
            i++; continue; // 非法序列忽略（errors='ignore'）
        }
        // 表生成时 lo 跳过了 0x7F（190 列），此处同步折算列索引
        int col = lo - 0x40;
        if (lo > 0x7F) col--;
        uint16_t cp = kGbkTable[hi - 0x81][col];
        if (cp == 0) { i++; continue; }
        if (cp < 0x80) {
            out += (char)cp;
        } else if (cp < 0x800) {
            out += (char)(0xC0 | (cp >> 6));
            out += (char)(0x80 | (cp & 0x3F));
        } else {
            out += (char)(0xE0 | (cp >> 12));
            out += (char)(0x80 | ((cp >> 6) & 0x3F));
            out += (char)(0x80 | (cp & 0x3F));
        }
        i += 2;
    }
    return out;
}

} // namespace lbj
