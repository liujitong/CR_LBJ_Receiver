// decoder.h — DPLL 比特恢复 + BCH(31,21) + POCSAG 帧同步 + LBJ 报文解析
// 1:1 移植 decoder.py：dpllBitRecovery / calcSyndrome / buildSyndromeLut /
// bchDecodeFast / processBitStreaming / extractBcd / decodeLbj / LbjDecoder
#pragma once
#include "dsp_math.h"
#include "frontend.h"
#include <vector>
#include <map>
#include <string>
#include <sstream>
#include <ctime>

namespace lbj {

// ---- BCH(31,21) ----
inline int calcSyndrome(uint32_t d31) {
    // LFSR 模拟 g(x)=x^10+x^9+x^8+x^6+x^5+x^3+1，反馈 873 (0x369)
    int syn = 0;
    for (int i = 0; i < 31; i++) {
        int bit = (d31 >> (30 - i)) & 1;
        if (syn & (1 << 9)) syn = ((syn << 1) ^ bit ^ 873) & 0x3FF;
        else                syn = ((syn << 1) ^ bit) & 0x3FF;
    }
    return syn;
}

class BchDecoder {
public:
    // {伴随式: 错误比特位} 反查表（首见优先，同 Python buildSyndromeLut）
    BchDecoder() {
        lut_.assign(1024, -1);
        for (int i = 0; i < 31; i++) {
            int syn = calcSyndrome(1u << i);
            if (lut_[syn] < 0) lut_[syn] = i;
        }
    }
    // 返回 (correctedCw, isValid)
    bool decodeFast(uint32_t cwVal, uint32_t& corrected) const {
        uint32_t data31 = (cwVal >> 1) & 0x7FFFFFFFu;
        int syn = calcSyndrome(data31);
        if (syn == 0) { corrected = cwVal; return true; }
        int fp = (syn >= 0 && syn < 1024) ? lut_[syn] : -1;
        if (fp >= 0) {
            corrected = ((data31 ^ (1u << fp)) << 1) | (cwVal & 1);
            return true;
        }
        corrected = cwVal;
        return false;
    }
private:
    std::vector<int> lut_;
};

// ---- DPLL 比特恢复（dpllBitRecovery）----
struct DpllState {
    double ncoPhase = 0.0, ncoStep = 0.0, pllIntegrator = 0.0;
    double peakMax = 0.0, peakMin = 0.0;
    int lastHardBit = 0, lastBitClk = 0;
    void resetSoft() {
        ncoPhase = 0; pllIntegrator = 0; peakMax = 0; peakMin = 0;
        lastHardBit = 0; lastBitClk = 0;
    }
};

inline void dpllBitRecovery(const double* bb, int n, DpllState& st, std::vector<int>& bits) {
    bits.clear();
    double _ph = st.ncoPhase, _int = st.pllIntegrator, _mx = st.peakMax, _mn = st.peakMin;
    int _lh = st.lastHardBit, _lc = st.lastBitClk;
    double step = st.ncoStep;
    const double hyst = 0.03;
    double MD = st.ncoStep * 0.02;
    for (int i = 0; i < n; i++) {
        double v = bb[i];
        double ha = fmax(1e-6, (_mx - _mn) * 0.5);
        if (v > _mx) _mx = v; else _mx -= ha * 0.0005;
        if (v < _mn) _mn = v; else _mn += ha * 0.0005;
        double mid = (_mx + _mn) * 0.5;
        double amp = fmax(1e-6, _mx - _mn);
        double h = fmax(0.006, fmin(hyst, 0.15 * amp));
        int hb;
        if (v > mid + h) hb = 1;
        else if (v < mid - h) hb = 0;
        else hb = _lh;
        if (hb != _lh) {
            double err = _ph;
            if (err > 0.5) err -= 1.0;
            _int += 0.005 * err;
            if (_int > MD) _int = MD;
            else if (_int < -MD) _int = -MD;
            _ph -= 0.1 * err + _int;
        }
        _lh = hb;
        _ph += step;
        if (_ph > 0.5) {
            if (_lc == 0) bits.push_back(1 - hb); // LBJ 反逻辑
            _lc = 1;
        } else {
            _lc = 0;
        }
        if (_ph >= 1.0) _ph -= 1.0;
    }
    st.ncoPhase = _ph; st.pllIntegrator = _int; st.peakMax = _mx; st.peakMin = _mn;
    st.lastHardBit = _lh; st.lastBitClk = _lc;
}

// ---- 解码结果 ----
struct LbjResult {
    double timestamp = 0;
    std::string train = "----", baseTrain = "----", prefix;
    std::string direction = "未知", speed = "---", position = "---.-";
    std::string loco = "----", locoCode = "---", route = "----";
    bool isDetailed = false, routeValid = false;
    double latitude = 0, longitude = 0;
    bool hasCoord = false;
    bool msgTypeError = false, hasInterference = false;
    std::string rawBcd;
    int rawAddr = 0, rawFunc = 0;
    std::vector<uint32_t> rawCodewords;
    bool rawIsShort = false, rawIsMerged = false, rawIsStandalone = false;
    double rssi = -140.0, afcHz = 0, afcErrHz = 0, afcScore = 0;
};

// ---- LBJ 报文解析（LbjDecoder 会话逻辑）----
class LbjParser {
public:
    BchDecoder bch;
    // 帧同步常量
    static constexpr uint32_t kSyncStd = 2094142936u;
    static constexpr uint32_t kSyncInv = 2200824359u;
    static constexpr uint32_t kIdleWord = 2055848343u;

    struct Session {
        std::string baseTrain, prefix;
        std::string direction = "未知", speed = "---", position = "---.-";
        std::string loco = "----", locoCode = "---", route = "----";
        bool routeValid = false;
        double latitude = 0, longitude = 0;
        bool hasCoord = false;
        bool isDetailed = false;
        double timestamp = 0;
    };

    // 机车代号 → 名称（decoder.py LOCO_TABLE 全表）
    static const char* locoName(int code) {
        switch (code) {
        case 1: return "解放"; case 3: return "前进"; case 5: return "建设";
        case 6: return "KD7"; case 55: return "蓝箭控车"; case 81: return "东风21";
        case 101: return "东风"; case 102: return "东风2"; case 103: return "东风3";
        case 104: return "东风4"; case 105: return "东风4客"; case 106: return "东风4C";
        case 107: return "东风5"; case 108: return "东风5宽"; case 109: return "东风6";
        case 110: return "东风7"; case 111: return "东风8"; case 112: return "东风9";
        case 113: return "东风10"; case 114: return "东方红1"; case 115: return "东方红2";
        case 116: return "东方红3"; case 117: return "东方红5"; case 118: return "北京";
        case 119: return "北京宽"; case 120: return "ND2"; case 121: return "ND3";
        case 122: return "ND4"; case 123: return "ND5"; case 124: return "NY5";
        case 125: return "NY6"; case 126: return "NY7"; case 127: return "轻油";
        case 128: return "东方红21"; case 129: return "东风7B"; case 130: return "东风5S";
        case 131: return "东风7C"; case 132: return "东风7S"; case 133: return "工矿1";
        case 134: return "工矿1F"; case 135: return "东风4E"; case 136: return "东风7D";
        case 137: return "工矿1A"; case 138: return "东风11"; case 139: return "天安";
        case 140: return "东风10F"; case 141: return "东风4D"; case 142: return "东风8B";
        case 143: return "东风12"; case 144: return "东风7E"; case 145: return "NYJ1";
        case 146: return "NZJ1"; case 147: return "NZJ2"; case 148: return "东风4DJ";
        case 149: return "新曙光"; case 150: return "神州"; case 151: return "NJ2";
        case 152: return "东风7G"; case 153: return "NDJ3"; case 157: return "FXN3D";
        case 158: return "东风11G"; case 160: return "HXN3"; case 161: return "HXN5";
        case 162: return "HXN3B"; case 163: return "HXN5B"; case 167: return "FXN3B";
        case 170: return "FXN5C"; case 171: return "FXN3-J"; case 201: return "8G";
        case 202: return "8K"; case 203: return "6G"; case 204: return "6K";
        case 205: return "韶山1"; case 206: return "韶山3"; case 207: return "韶山4";
        case 208: return "韶山5"; case 209: return "韶山6"; case 210: return "韶山3B";
        case 211: return "韶山7"; case 212: return "韶山8"; case 213: return "韶山7B";
        case 214: return "韶山7C"; case 215: return "韶山6B"; case 216: return "韶山9";
        case 217: return "韶山7D"; case 218: return "DJ熊猫"; case 219: return "DJ1";
        case 220: return "DJ2"; case 221: return "DJF"; case 222: return "蓝箭动车";
        case 223: return "先锋号"; case 224: return "韶山7E"; case 225: return "韶山4G";
        case 226: return "韶山3C"; case 228: return "天梭"; case 229: return "DJ4和谐";
        case 230: return "KTT"; case 231: return "HXD1"; case 232: return "HXD2";
        case 233: return "HXD3"; case 234: return "HXD1B"; case 235: return "HXD2B";
        case 236: return "HXD3B"; case 237: return "HXD1C"; case 238: return "HXD2C";
        case 239: return "HXD3C"; case 240: return "HXD1D"; case 241: return "HXD2D";
        case 242: return "HXD3D"; case 243: return "FXD1B"; case 244: return "FXD2B";
        case 245: return "FXD1"; case 246: return "FXD3"; case 247: return "FXD1-J";
        case 248: return "FXD3-J"; case 249: return "KZ25TA"; case 251: return "KZ25TB";
        case 252: return "HXD1D-J"; case 254: return "FXD1H"; case 299: return "雪域神州";
        case 300: return "CRH1"; case 301: return "CRH2"; case 302: return "CRH3";
        case 304: return "CRH5"; case 305: return "CRH380A"; case 306: return "CRH380B";
        case 307: return "CRH380C"; case 308: return "CRH380D"; case 309: return "CRH6A";
        case 310: return "CR400AF"; case 311: return "CR400BF"; case 312: return "CR300AF";
        case 313: return "CR300BF"; case 314: return "CRH2E"; case 315: return "CRH6F";
        case 329: return "CJ1"; case 330: return "CJ2"; case 331: return "CJ3";
        case 332: return "CJ4"; case 333: return "CJ5"; case 334: return "CJ6";
        default: return nullptr;
        }
    }

    // ---- 状态机变量（对应 LbjDecoder.__init__）----
    RealFir smooth;
    DpllState dpll;
    int state = 0;            // 0=搜同步 1=收码字
    uint32_t shiftReg = 0;
    int cwBitCount = 0, polarity = 1;
    int wordCount = 0, framePos = 0;
    bool inMessage = false;
    int currentAddr = 0, currentFunc = 0;
    bool currentMsgHasError = false;
    std::vector<uint32_t> currentCodewords;
    int huntTimeout = 0;
    std::map<std::string, Session> sessions;
    std::string lastTrain;
    double lastWarnTime = 0;
    std::string trainScheme = "auto";
    std::vector<std::string> pendingWarnings; // 干扰告警（方向, 文本）

    void initDecoder(double fs, double baudRate) {
        // 高斯 FIR（截止 1200Hz，('gaussian',7.0) 窗），归一化
        // Python: bSmooth = firwin(31,1200,fs,('gaussian',7.0))/sum —— float64 全程
        auto w = gaussianWindow(31, 7.0);
        auto taps = firwinLowpassD(31, 1200.0, fs, w);
        double sum = 0;
        for (auto t : taps) sum += t;
        if (sum != 0) for (auto& t : taps) t = t / sum;
        smoothTaps_ = taps;
        smooth.setTaps(taps);
        dpll.resetSoft();
        dpll.ncoStep = baudRate / fs;
        state = 0; shiftReg = 0; cwBitCount = 0; polarity = 1;
        wordCount = framePos = 0; inMessage = false; huntTimeout = 0;
        currentCodewords.clear(); currentMsgHasError = false;
    }

    void resetDpllSoft() { dpll.resetSoft(); }
    void resetReceiverState() {
        resetDpllSoft();
        smooth.setTaps(smoothTaps_); // 重置滤波器历史（zi=0）
        state = 0; shiftReg = 0; cwBitCount = 0;
        wordCount = framePos = 0; inMessage = false; huntTimeout = 0;
    }

    // PCM 块 → 高斯平滑 → DPLL → 逐比特帧同步；产生的解码结果写入 results
    void processChunk(const float* pcm, int n, std::vector<LbjResult>& results) {
        smoothBuf_.resize(n);
        smooth.process(pcm, n, smoothBuf_.data());
        std::vector<int> bits;
        dpllBitRecovery(smoothBuf_.data(), n, dpll, bits);
        for (int bit : bits) processBitStreaming(bit, results);
    }

private:
    std::vector<double> smoothTaps_;
    std::vector<double> smoothBuf_;

    static char bcdChar(int rev) {
        static const char* tbl = "0123456789*U -)(";
        return tbl[rev & 0xF];
    }

    std::string extractBcd(const std::vector<uint32_t>& cws) const {
        std::string s;
        s.reserve(cws.size() * 5);
        for (uint32_t cw : cws) {
            uint32_t data20 = (cw >> 11) & 0xFFFFFu;
            for (int n = 0; n < 5; n++) {
                int val = (int)((data20 >> (16 - n * 4)) & 0xF);
                int rev = (int)(((val & 1) << 3) | ((val & 2) << 1) | ((val & 4) >> 1) | ((val & 8) >> 3));
                s += bcdChar(rev);
            }
        }
        return s;
    }

    void processBitStreaming(int bit, std::vector<LbjResult>& results) {
        shiftReg = ((shiftReg << 1) | (uint32_t)(bit & 1)) & 0xFFFFFFFFu;
        if (state == 0) {
            if (popcount32(shiftReg ^ kSyncStd) <= 2) {
                polarity = 1; state = 1;
                wordCount = framePos = cwBitCount = huntTimeout = 0;
            } else if (popcount32(shiftReg ^ kSyncInv) <= 2) {
                polarity = -1; state = 1;
                wordCount = framePos = cwBitCount = huntTimeout = 0;
            }
            if (inMessage) {
                huntTimeout++;
                if (huntTimeout > 64) triggerParse(results);
            }
        } else {
            cwBitCount++;
            if (cwBitCount == 32) {
                cwBitCount = 0;
                uint32_t raw = (polarity == 1) ? shiftReg : (~shiftReg) & 0xFFFFFFFFu;
                uint32_t corrected = 0;
                bool isBchValid = bch.decodeFast(raw, corrected);
                framePos++;
                wordCount++;
                if (popcount32(corrected ^ kSyncStd) <= 2) {
                    wordCount = framePos = 0;
                } else if (popcount32(corrected ^ kIdleWord) <= 2) {
                    if (inMessage) triggerParse(results);
                } else if ((corrected >> 31) == 0) {
                    // 控制字：报文起始
                    if (inMessage) triggerParse(results);
                    currentFunc = (int)((corrected >> 11) & 3);
                    currentAddr = (int)(((corrected >> 13) & 0x3FFFF) * 8 + (size_t)(framePos - 1) / 2);
                    currentCodewords.clear();
                    inMessage = true;
                    currentMsgHasError = !isBchValid;
                } else {
                    // 数据字
                    if (inMessage) {
                        currentCodewords.push_back(corrected);
                        if (!isBchValid) currentMsgHasError = true;
                    }
                }
                if (wordCount >= 16) state = 0;
            }
        }
    }

    void triggerParse(std::vector<LbjResult>& results) {
        inMessage = false;
        if (currentCodewords.empty()) return;
        bool hasError = currentMsgHasError;
        bool validForEta = !hasError;
        std::string bcd = extractBcd(currentCodewords);
        if (hasError) {
            double now = nowSeconds();
            if (now - lastWarnTime >= 1.0) {
                lastWarnTime = now;
                const char* d = currentFunc == 1 ? "下行" : currentFunc == 3 ? "上行" : "未知";
                char buf[128];
                snprintf(buf, sizeof(buf), "⚠ 探测到%s信号 干扰严重", d);
                pendingWarnings.push_back(std::string(d) + "|" + buf);
            }
        }
        decodeLbj(bcd, validForEta, hasError, results);
        currentCodewords.clear();
        currentMsgHasError = false;
    }

    static double nowSeconds() {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        return (double)ts.tv_sec + ts.tv_nsec / 1e9;
    }

    // 度分坐标（DDD + MM.MMMM）
    static bool parseDmCoordinate(const std::string& degText, const std::string& minText,
                                  bool isLatitude, double& out) {
        char* e = nullptr;
        long deg = strtol(degText.c_str(), &e, 10);
        if (e == degText.c_str() || *e != '\0') return false;
        long minRaw = strtol(minText.c_str(), &e, 10);
        if (e == minText.c_str() || *e != '\0') return false;
        double minute = minRaw / 10000.0;
        if (minute >= 60.0) return false;
        double value = deg + minute / 60.0;
        if (isLatitude) { if (!(value > 0.0 && value <= 60.0)) return false; }
        else { if (!(value >= 70.0 && value <= 140.0)) return false; }
        out = round(value * 1e6) / 1e6;
        return true;
    }

    static bool isAlnumBcd(const std::string& s) {
        if (s.empty()) return false;
        for (char c : s) {
            if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')))
                return false;
        }
        return true;
    }

    // 线路名合法性（isValidRouteName）：≤24，仅中文/字母/数字/横线/空格
    static bool isValidRouteName(const std::string& r) {
        if (r.empty() || r.size() > 24 * 3) return false;
        // 长度按字符计（UTF-8 中文 3 字节算 1 字符）
        int charCount = 0;
        for (size_t i = 0; i < r.size();) {
            unsigned char c = r[i];
            int len = 1;
            if (c >= 0xF0) len = 4; else if (c >= 0xE0) len = 3; else if (c >= 0xC0) len = 2;
            charCount++;
            // 允许：ASCII 字母数字横线空格；其余须为 CJK（0x4E00-0x9FA5）
            if (len == 1) {
                char a = r[i];
                if (!((a >= 'A' && a <= 'Z') || (a >= 'a' && a <= 'z') ||
                      (a >= '0' && a <= '9') || a == '-' || a == ' '))
                    return false;
            } else if (len == 3) {
                unsigned int cp = ((r[i] & 0x0F) << 12) | ((r[i+1] & 0x3F) << 6) | (r[i+2] & 0x3F);
                if (!(cp >= 0x4E00 && cp <= 0x9FA5)) return false;
            } else {
                return false;
            }
            i += len;
        }
        if (charCount > 24) return false;
        // 至少含一个中文/字母/数字
        bool hasValid = false;
        for (size_t i = 0; i < r.size();) {
            unsigned char c = r[i];
            if (c < 0x80) {
                char a = r[i];
                if ((a >= 'A' && a <= 'Z') || (a >= 'a' && a <= 'z') || (a >= '0' && a <= '9'))
                    hasValid = true;
                i++;
            } else if (c >= 0xE0 && c < 0xF0) {
                hasValid = true;
                i += 3;
            } else {
                i += (c >= 0xF0) ? 4 : (c >= 0xC0 ? 2 : 1);
            }
        }
        return hasValid;
    }

    // GBK 双字节 → UTF-8（嵌入表，见 gbk_table.h）
    static std::string gbkToUtf8(const unsigned char* bytes, int n);

public:
    // decodeLbj：报文类型判定 + 会话合并 + 字段解析（与 Python 逐行对应）
    void decodeLbj(const std::string& bcd, bool validForEta, bool hasInterference,
                   std::vector<LbjResult>& results) {
        int addr = currentAddr, func = currentFunc;
        double ct = nowSeconds();
        std::string baseTrain;

        // 过滤无效地址
        if (addr == 1234008) return;
        if (addr == 1233999 || addr == 1234000) {
            if (func == 0 && bcd.size() == 5 &&
                (bcd[0] == '-' || bcd[0] == '*') && bcd[4] != '-')
                return;
        }
        bool isShort = (addr == 1233999 || addr == 1234000) && (int)bcd.size() >= 15;
        bool isMerged = (addr == 1233999 || addr == 1234000 || addr == 1234002) && (int)bcd.size() >= 65;
        bool isStandalone = (addr == 1234001 || addr == 1234002) && (int)bcd.size() < 65;

        auto isDigitOrSpace = [](char c) {
            return (c >= '0' && c <= '9') || c == ' ' || c == 'U' || c == '*';
        };

        // === 短报文 ===
        if (isShort) {
            std::string raw = bcd.substr(0, 6);
            // strip（去空格）
            while (!raw.empty() && raw.back() == ' ') raw.pop_back();
            size_t p = raw.find_first_not_of(' ');
            if (p != std::string::npos) raw = raw.substr(p);
            if (isAlnumBcd(raw)) baseTrain = raw; else baseTrain = "----";
            lastTrain = baseTrain;
            std::string direction = (func == 1) ? "下行" : (func == 3) ? "上行"
                                      : ("未知(" + std::to_string(func) + ")");
            std::string rs = bcd.substr(6, 3);
            for (auto& c : rs) if (c == ' ' || c == 'U' || c == '*') c = '0';
            bool digits = !rs.empty();
            for (char c : rs) if (c < '0' || c > '9') digits = false;
            std::string speed = "---";
            if (digits) {
                long v = strtol(rs.c_str(), nullptr, 10);
                if (v >= 0 && v <= 400) speed = std::to_string(v); // Python: str(int(rs))
            }
            std::string pr = bcd.substr(10, 5);
            std::string position = "---.-";
            if (pr.find('*') == std::string::npos && pr.find('-') == std::string::npos &&
                pr.find('U') == std::string::npos) {
                std::string ps = pr;
                for (auto& c : ps) if (c == ' ') c = '0';
                bool d2 = ps.size() == 5;
                for (char c : ps) if (c < '0' || c > '9') d2 = false;
                if (d2) position = ps.substr(0, 4) + "." + ps.substr(4, 1);
            }
            auto it = sessions.find(baseTrain);
            if (it == sessions.end()) {
                Session s;
                s.baseTrain = baseTrain; s.prefix = ""; s.direction = direction;
                s.speed = speed; s.position = position;
                s.loco = "----"; s.locoCode = "---"; s.route = "----";
                s.routeValid = false; s.isDetailed = false;
                s.timestamp = ct;
                sessions[baseTrain] = s;
            } else {
                Session& s = it->second;
                if (direction != "未知" && direction.rfind("未知", 0) != 0) s.direction = direction;
                if (speed != "---") s.speed = speed;
                if (position != "---.-") s.position = position;
                s.timestamp = ct;
            }
        }

        // === 合并/独立长报文 ===
        if (isMerged || isStandalone) {
            std::string tid = isMerged ? baseTrain : lastTrain;
            if (tid.empty() && isStandalone && !sessions.empty()) {
                // 最近 10 秒内的会话
                std::string best; double bestTs = -1;
                for (auto& kv : sessions) {
                    if (kv.second.timestamp > bestTs) { bestTs = kv.second.timestamp; best = kv.first; }
                }
                if (!best.empty() && ct - bestTs < 10) tid = best;
            }
            if (!tid.empty() && sessions.count(tid)) {
                if (isStandalone && ct - sessions[tid].timestamp > 8.0) {
                    // 独立报文间隔过久
                } else {
                    std::string buf = bcd.size() > 50 ? bcd.substr(bcd.size() - 50) : bcd;
                    // 机车代号与编号
                    std::string lm = "----", lk = "---";
                    std::string lr = buf.size() >= 12 ? buf.substr(4, 8) : "";
                    if (lr.size() >= 3) {
                        std::string cp = lr.substr(0, 3);
                        bool cpDig = true;
                        for (char c : cp) if (c < '0' || c > '9') cpDig = false;
                        if (cpDig) {
                            lk = cp;
                            int ti = atoi(cp.c_str());
                            const char* ln = locoName(ti);
                            std::string name = ln ? ln : "未知型号";
                            std::string np = lr.substr(3);
                            while (!np.empty() && np.back() == ' ') np.pop_back();
                            size_t q = np.find_first_not_of(' ');
                            if (q != std::string::npos) np = np.substr(q);
                            bool npDig = !np.empty();
                            for (char c : np) if (c < '0' || c > '9') npDig = false;
                            if (!npDig) np = "----";
                            lm = name + "-" + np;
                        }
                    }
                    // 线路名：ih[14:30] 8 字节 GBK
                    std::string ru = "----";
                    // ih = ''.join(bcdToHexChar(c) for c in buf)：每 BCD 字符→1 个 hex 字符
                    std::string ih;
                    ih.reserve(buf.size());
                    for (char c : buf) {
                        switch (c) {
                        case '*': ih += 'A'; break; case 'U': ih += 'B'; break;
                        case ' ': ih += 'C'; break; case '-': ih += 'D'; break;
                        case ')': ih += 'E'; break; case '(': ih += 'F'; break;
                        default:
                            if (c >= '0' && c <= '9') ih += c;
                            else ih += '0'; // 理论不出现的字符
                            break;
                        }
                    }
                    // 机车号解析（buf[4:12]，上面已做）
                    // 车次前缀：ih[0:4] 两字节 ASCII
                    std::string lc;
                    if (ih.size() >= 4) {
                        auto okChar = [](int v) { return (v >= 48 && v <= 57) || (v >= 65 && v <= 90); };
                        int c1 = hexNibbles(ih, 0), c2 = hexNibbles(ih, 2);
                        if (okChar(c1)) lc += (char)c1;
                        if (okChar(c2)) lc += (char)c2;
                        // lc.replace(' ','').strip()
                        lc.erase(std::remove(lc.begin(), lc.end(), ' '), lc.end());
                    }
                    // 线路名 ih[14:30] → 8 字节 GBK → UTF-8
                    if (ih.size() >= 30) {
                        unsigned char rb[8];
                        bool ok = true;
                        for (int i = 0; i < 8; i++) {
                            int hi = hexVal(ih[14 + i * 2]);
                            int lo = hexVal(ih[15 + i * 2]);
                            if (hi < 0 || lo < 0) { ok = false; break; }
                            rb[i] = (unsigned char)((hi << 4) | lo);
                        }
                        if (ok) {
                            std::string dec = gbkToUtf8(rb, 8);
                            // 去 \x00 与首尾空白
                            dec.erase(std::remove(dec.begin(), dec.end(), '\0'), dec.end());
                            size_t a = dec.find_first_not_of(" \t\r\n");
                            size_t b = dec.find_last_not_of(" \t\r\n");
                            if (a != std::string::npos) dec = dec.substr(a, b - a + 1);
                            else dec.clear();
                            if (!dec.empty()) {
                                // 仅允许中文/字母/数字/横线/空格
                                bool valid = true;
                                for (size_t i = 0; i < dec.size();) {
                                    unsigned char c = dec[i];
                                    if (c < 0x80) {
                                        char ch = dec[i];
                                        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
                                              (ch >= '0' && ch <= '9') || ch == '-' || ch == ' '))
                                            valid = false;
                                        i++;
                                    } else if (c >= 0xE0 && c < 0xF0) {
                                        unsigned int cp = ((dec[i] & 0x0F) << 12) |
                                                          ((dec[i+1] & 0x3F) << 6) | (dec[i+2] & 0x3F);
                                        if (!(cp >= 0x4E00 && cp <= 0x9FA5)) valid = false;
                                        i += 3;
                                    } else { valid = false; i += (c >= 0xF0) ? 4 : (c >= 0xC0 ? 2 : 1); }
                                }
                                if (valid) ru = dec;
                            }
                        }
                    }
                    // 经纬度
                    double lat = 0, lon = 0;
                    bool hasLL = false;
                    if (ih.size() >= 47) {
                        double lo, la;
                        bool okL = parseDmCoordinate(ih.substr(30, 3), ih.substr(33, 6), false, lo);
                        bool okA = parseDmCoordinate(ih.substr(39, 2), ih.substr(41, 6), true, la);
                        if (okL && okA) { lon = lo; lat = la; hasLL = true; }
                    }
                    // 写回会话
                    Session& s = sessions[tid];
                    if (!lc.empty()) s.prefix = lc;
                    if (lm != "----") { s.loco = lm; s.locoCode = lk; }
                    if (validForEta && ru != "----" && isValidRouteName(ru)) {
                        s.route = ru;
                        s.routeValid = true;
                    }
                    if (hasLL) { s.latitude = lat; s.longitude = lon; s.hasCoord = true; }
                    s.isDetailed = true;
                    s.timestamp = ct;
                }
            }
        }

        // === 汇总会话 ===
        std::string aid = isShort ? baseTrain : lastTrain;
        if (!aid.empty() && sessions.count(aid)) {
            Session& s = sessions[aid];
            LbjResult r;
            r.timestamp = ct;
            r.train = s.prefix + s.baseTrain;
            // replace(' ','').strip()
            r.train.erase(std::remove(r.train.begin(), r.train.end(), ' '), r.train.end());
            r.baseTrain = s.baseTrain;
            r.prefix = s.prefix;
            r.direction = s.direction;
            r.speed = s.speed;
            r.position = s.position;
            r.loco = s.loco;
            r.locoCode = s.locoCode;
            r.route = s.route;
            r.isDetailed = s.isDetailed;
            r.routeValid = s.routeValid;
            r.hasCoord = s.hasCoord;
            r.latitude = s.latitude;
            r.longitude = s.longitude;
            r.msgTypeError = currentMsgHasError;   // 与 Python 相同（triggerParse 时已清为 false 前）
            r.hasInterference = hasInterference;
            r.rawBcd = bcd;
            r.rawAddr = addr;
            r.rawFunc = func;
            r.rawCodewords = currentCodewords;
            r.rawIsShort = isShort;
            r.rawIsMerged = isMerged;
            r.rawIsStandalone = isStandalone;
            results.push_back(r);
        }

        // 清理 30 秒未更新的过期会话
        std::vector<std::string> expired;
        for (auto& kv : sessions)
            if (ct - kv.second.timestamp > 30) expired.push_back(kv.first);
        for (auto& k : expired) {
            sessions.erase(k);
            if (lastTrain == k) lastTrain.clear();
        }
    }

private:
    static int hexVal(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        return -1;
    }
    static int hexNibbles(const std::string& ih, size_t pos) {
        int hi = hexVal(ih[pos]);
        int lo = hexVal(ih[pos + 1]);
        if (hi < 0 || lo < 0) return -1;
        return (hi << 4) | lo;
    }
};

} // namespace lbj
