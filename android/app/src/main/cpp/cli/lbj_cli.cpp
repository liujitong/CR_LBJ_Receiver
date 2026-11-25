/**
 * lbj_cli.cpp — 离线对拍驱动（M2）
 *
 * 用法：lbj_cli <params.json> <iq.u8> [maxBlocks]
 *   params.json：与 nativeInit 相同字段的配置（freqMhz、sampleRate、bwKhz、dcOffsetHz、
 *                gainDb、ppm、blockSize、rssi 门限、afc、baudRate）
 *   iq.u8      ：RTL-SDR uint8 交错 IQ 录制（OWRX/USB 抓取）
 *
 * 输出：stdout 每行一个 JSON（与 native 解码回调完全同构，由 core/result_json 生成）；
 *       日志走 stderr。与 Python offline_decode.py 逐字段比对，差异必须为 0。
 */
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>
#include "core/frontend.h"
#include "core/decoder.h"
#include "core/result_json.h"

using namespace lbj;

// 极简扁平 JSON 取值（与 engine.cpp 同一套协议）
namespace {
const char* findKey(const char* json, const char* key) {
    std::string pat = std::string("\"") + key + "\"";
    const char* p = strstr(json, pat.c_str());
    if (!p) return nullptr;
    p += pat.size();
    while (*p == ' ' || *p == ':') p++;
    return p;
}
double jd(const char* json, const char* key, double def) {
    const char* p = findKey(json, key);
    return p ? strtod(p, nullptr) : def;
}
int ji(const char* json, const char* key, int def) { return (int)jd(json, key, def); }
bool jb(const char* json, const char* key, bool def) {
    const char* p = findKey(json, key);
    if (!p) return def;
    if (strncmp(p, "true", 4) == 0) return true;
    if (strncmp(p, "false", 5) == 0) return false;
    return def;
}

std::string readFile(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return "";
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::string s(n, '\0');
    size_t got = fread(s.data(), 1, n, f);
    (void)got;
    fclose(f);
    return s;
}
} // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <params.json> <iq.u8> [maxBlocks]\n", argv[0]);
        return 2;
    }
    std::string cfg = readFile(argv[1]);
    if (cfg.empty()) {
        fprintf(stderr, "无法读取配置 %s\n", argv[1]);
        return 2;
    }

    int sampleRate = ji(cfg.c_str(), "sampleRate", 240000);
    double dcOffsetHz = jd(cfg.c_str(), "dcOffsetHz", 50000.0);
    double userOffsetHz = jd(cfg.c_str(), "userOffsetHz", 0.0);
    double bwHz = jd(cfg.c_str(), "bwKhz", 35.0) * 1000.0;
    bool afcEnable = jb(cfg.c_str(), "afcEnable", true);
    double afcMaxHz = jd(cfg.c_str(), "afcMaxHz", kDefaultAfcMaxHz);
    double afcGain = jd(cfg.c_str(), "afcGain", 0.45);
    double baudRate = jd(cfg.c_str(), "baudRate", 1200.0);
    int blockSize = ji(cfg.c_str(), "blockSize", 65536);
    double rssiThr = jd(cfg.c_str(), "rssiThresholdDb", kDefaultRssiThresholdDb);
    double rssiHyst = jd(cfg.c_str(), "rssiHystDb", kDefaultRssiHystDb);
    double rssiHold = jd(cfg.c_str(), "rssiHoldMs", kDefaultRssiHoldMs);
    bool keepAfc = jb(cfg.c_str(), "keepAfcAfterPacket", false);

    FrontendChain chain;
    chain.init((double)sampleRate, dcOffsetHz, userOffsetHz, bwHz, afcEnable, afcMaxHz, afcGain);
    RssiGate gate(rssiThr, rssiHyst, rssiHold);
    LbjParser parser;
    parser.initDecoder(chain.actualOut, baudRate);

    fprintf(stderr, "[cli] 链路 %s\n", chain.chainDesc.c_str());
    if (getenv("LBJ_DUMP_TAPS")) {
        auto dumpF = [](const char* name, const std::vector<float>& t) {
            FILE* f = fopen(name, "w");
            for (auto v : t) fprintf(f, "%.9g\n", v);
            fclose(f);
        };
        dumpF("taps_hb0.txt", chain.hbTapsForDebug(0));
        dumpF("taps_ch.txt", chain.chTapsForDebug());
        dumpF("taps_dec.txt", chain.decTapsForDebug());
        fprintf(stderr, "[cli] taps 已导出\n");
    }

    FILE* f = fopen(argv[2], "rb");
    if (!f) {
        fprintf(stderr, "无法打开 IQ 文件 %s\n", argv[2]);
        return 2;
    }

    std::vector<uint8_t> raw((size_t)blockSize * 2);
    std::vector<c64> iq(blockSize);
    std::vector<float> pcm(blockSize / 2 + 64);
    long maxBlocks = argc > 3 ? atol(argv[3]) : -1;
    long nBlocks = 0;
    int totalResults = 0;

    while (!feof(f) && (maxBlocks <= 0 || nBlocks < maxBlocks)) {
        size_t chunk = raw.size();
        size_t got = fread(raw.data(), 1, chunk, f);
        if (got < chunk) {
            if (got < 2) break;
            // 尾块补齐（pad 0x7f = 中值）
            memset(raw.data() + got, 0x7f, chunk - got);
        }
        nBlocks++;
        for (int i = 0; i < blockSize; i++) {
            iq[i] = c64{(float)((raw[2 * i] - 127.5) / 128.0),
                        (float)((raw[2 * i + 1] - 127.5) / 128.0)};
        }
        double rssi = -140;
        int pcmN = chain.process(iq.data(), blockSize, pcm.data(), &rssi, &gate);
        if (getenv("LBJ_DEBUG") && nBlocks <= 3) {
            fprintf(stderr, "[dbg] block %ld pcmN=%d rssi=%.6f y[0..7]=", nBlocks, pcmN, rssi);
            for (int i = 0; i < 8 && i < pcmN; i++) fprintf(stderr, "%.9g ", pcm[i]);
            fprintf(stderr, "\n");
        }
        if (chain.consumeAfcUpdated()) parser.resetDpllSoft();
        if (gate.active) {
            std::vector<LbjResult> results;
            parser.processChunk(pcm.data(), pcmN, results);
            for (auto& r : results) {
                r.rssi = rssi;
                r.afcHz = chain.afc.afcHz;
                r.afcErrHz = chain.afc.lastErrHz;
                r.afcScore = chain.afc.lastScore;
                printf("%s\n", resultToJson(r).c_str());
                totalResults++;
            }
        } else if (gate.justDeactivated) {
            parser.resetReceiverState();
            if (!keepAfc && chain.afc.enabled) chain.resetAfc();
        }
    }
    fclose(f);
    fprintf(stderr, "[cli] 处理 %ld 块，输出 %d 条结果\n", nBlocks, totalResults);
    return 0;
}
