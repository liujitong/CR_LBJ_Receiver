// result_json.cpp — LbjResult → JSON 序列化（engine / lbj_cli 共用）
#include "result_json.h"
#include <cstdio>

namespace lbj {

namespace {
void jsonAppendEscaped(std::string& out, const std::string& s) {
    for (char c : s) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if ((unsigned char)c < 0x20) {
                char buf[8];
                snprintf(buf, sizeof(buf), "\\u%04X", c);
                out += buf;
            } else out += c;
        }
    }
}
} // namespace

std::string resultToJson(const LbjResult& r) {
    std::string j = "{";
    auto num = [&](const char* k, long long v) {   // 整数字段（bool/addr/func）
        char buf[64];
        snprintf(buf, sizeof(buf), "%lld", v);
        j += std::string("\"") + k + "\":" + buf + ",";
    };
    auto dbl = [&](const char* k, double v, const char* fmt) { // 浮点字段
        char buf[64];
        snprintf(buf, sizeof(buf), fmt, v);
        j += std::string("\"") + k + "\":" + buf + ",";
    };
    auto str = [&](const char* k, const std::string& v) {
        j += std::string("\"") + k + "\":\"";
        jsonAppendEscaped(j, v);
        j += "\",";
    };
    j += "\"timestamp\":" + std::to_string(r.timestamp) + ",";
    str("train", r.train);
    str("baseTrain", r.baseTrain);
    str("prefix", r.prefix);
    str("direction", r.direction);
    str("speed", r.speed);
    str("position", r.position);
    str("loco", r.loco);
    str("locoCode", r.locoCode);
    str("route", r.route);
    num("isDetailed", r.isDetailed ? 1 : 0);
    num("routeValid", r.routeValid ? 1 : 0);
    if (r.hasCoord) {
        dbl("latitude", r.latitude, "%.6f");
        dbl("longitude", r.longitude, "%.6f");
    } else {
        j += "\"latitude\":null,\"longitude\":null,";
    }
    num("msgTypeError", r.msgTypeError ? 1 : 0);
    num("hasInterference", r.hasInterference ? 1 : 0);
    str("rawBcd", r.rawBcd);
    num("rawAddr", r.rawAddr);
    num("rawFunc", r.rawFunc);
    j += "\"rawCodewords\":[";
    for (size_t i = 0; i < r.rawCodewords.size(); i++) {
        j += std::to_string(r.rawCodewords[i]);
        if (i + 1 < r.rawCodewords.size()) j += ",";
    }
    j += "],";
    num("rawIsShort", r.rawIsShort ? 1 : 0);
    num("rawIsMerged", r.rawIsMerged ? 1 : 0);
    num("rawIsStandalone", r.rawIsStandalone ? 1 : 0);
    dbl("rssi", r.rssi, "%.1f");
    dbl("afcHz", r.afcHz, "%.1f");
    dbl("afcErrHz", r.afcErrHz, "%.1f");
    dbl("afcScore", r.afcScore, "%.3f");
    if (j.back() == ',') j.pop_back();
    j += "}";
    return j;
}

} // namespace lbj
