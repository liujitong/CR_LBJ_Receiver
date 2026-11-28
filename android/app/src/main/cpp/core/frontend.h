// frontend.h — 接收前端流水线，数值路径对齐 decoder.py（scipy 2.x 实际精度）：
// IQ 校正(c64) → DDC(c64×c64 float32) → 半带(lfilter→c128) → 信道 FIR(c128)
// → 整数抽取(c128) → RSSI(complex128 vdot) → FM(c64 截断+atan2f) → AFC(float32 pairwise)
#pragma once
#include "dsp_math.h"
#include "fir_filter.h"
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <cstdio>

namespace lbj {

constexpr double kBasebandRate = 48000.0;
constexpr int    kBaudRate     = 1200;
constexpr double kDefaultDcOffsetHz = 50000.0;
constexpr double kDefaultBwKhz = 35.0;
constexpr double kDefaultAfcMaxHz = 8000.0;
constexpr double kDefaultRssiThresholdDb = -55.0;
constexpr double kDefaultRssiHystDb = 4.0;
constexpr double kDefaultRssiHoldMs = 700.0;
constexpr int    kSpectrumBins = 256;
constexpr int    kNfft = 1024;

// numpy complex64 乘法（float32 分量运算，不经 double 中介）
inline c64 mulC64(c64 a, c64 b) {
    float ar = a.real(), ai = a.imag(), br = b.real(), bi = b.imag();
    return c64{ar * br - ai * bi, ar * bi + ai * br};
}

// R820T 增益表（dB），将期望增益映射到硬件最接近档位
inline double nearestGain(double want) {
    static const double gains[] = {
        0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7, 16.6,
        19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8, 36.4, 37.2,
        38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6 };
    constexpr int n = 29;
    double best = gains[0], bestD = 1e9;
    for (int i = 0; i < n; i++) {
        double d = fabs(gains[i] - want);
        if (d < bestD) { bestD = d; best = gains[i]; }
    }
    return best;
}

// ---- IQ 直流校正与增益平衡（IqCorrector）----
// Python: real/imag→float64 全程计算 → (i+1j·q).astype(complex64) 一次截断
class IqCorrector {
public:
    double dcI = 0.0, dcQ = 0.0, gainRatio = 1.0;
    void process(c64* iq, int n) {
        double mi = 0, mq = 0;
        for (int i = 0; i < n; i++) { mi += iq[i].real(); mq += iq[i].imag(); }
        mi /= n; mq /= n;
        dcI += 0.001 * (mi - dcI);
        dcQ += 0.001 * (mq - dcQ);
        double pi = 0, pq = 0;
        for (int i = 0; i < n; i++) {
            double x = (double)iq[i].real() - dcI, y = (double)iq[i].imag() - dcQ;
            pi += x * x; pq += y * y;
        }
        pi /= n; pq /= n;
        double gr = gainRatio;
        if (pi > 1e-20) {
            gr = gainRatio + 0.0001 * (sqrt(pq / pi) - gainRatio);
            if (gr < 0.9) gr = 0.9;
            if (gr > 1.1) gr = 1.1;
            gainRatio = gr;
            for (int i = 0; i < n; i++) {
                double y = ((double)iq[i].imag() - dcQ) * gr;
                iq[i].imag((float)y);
            }
            for (int i = 0; i < n; i++)
                iq[i].real((float)((double)iq[i].real() - dcI));
        } else {
            for (int i = 0; i < n; i++)
                iq[i] = c64{(float)((double)iq[i].real() - dcI),
                            (float)((double)iq[i].imag() - dcQ)};
        }
    }
};

// ---- DDC / NCO（DigitalDownConverter）----
// Python: ph = phase + inc·arange(n)（double）→ exp(1j·ph).astype(c64) → iq·lo（c64 乘法）
class DigitalDownConverter {
public:
    double sampleRate = 0, offsetHz = 0, phase = 0, increment = 0;
    void init(double sr, double off) { sampleRate = sr; offsetHz = off; update(); }
    void update() { increment = -2.0 * M_PI * offsetHz / sampleRate; }
    void setOffset(double off) { offsetHz = off; update(); }
    void process(c64* iq, int n) {
        if (fabs(offsetHz) < 0.1) return;
        for (int i = 0; i < n; i++) {
            double ph = phase + increment * (double)i;
            c64 lo{(float)cos(ph), (float)sin(ph)};
            iq[i] = mulC64(iq[i], lo);
        }
        double last = phase + increment * (double)n;
        phase = fmod(last, 2.0 * M_PI);
    }
};

// ---- RSSI 门控（RssiGate）----
class RssiGate {
public:
    double onDb, hysteresisDb, offDb, holdMs;
    int confirmBlocks = 1;
    bool enabled = true;
    bool active = false;
    double holdLeftMs = 0.0;
    int onCount = 0;
    bool justActivated = false, justDeactivated = false;
    int state = 0; // 0=OFF 1=ARM 2=ON 3=HOLD 4=BYPASS

    RssiGate(double on = kDefaultRssiThresholdDb, double hyst = kDefaultRssiHystDb,
             double hold = kDefaultRssiHoldMs)
        : onDb(on), hysteresisDb(hyst), offDb(on - hyst), holdMs(hold) {}

    void updateThreshold(double on) { onDb = on; offDb = onDb - hysteresisDb; }
    void reset() {
        active = false; holdLeftMs = 0; onCount = 0;
        justActivated = justDeactivated = false;
        state = enabled ? 0 : 4;
    }
    bool update(double rssiDb, int audioLen, double fsAudio) {
        justActivated = justDeactivated = false;
        if (!enabled) { active = true; holdLeftMs = holdMs; state = 4; return true; }
        double blockMs = 1000.0 * (double)(audioLen > 0 ? audioLen : 0) / fsAudio;
        bool wasActive = active;
        if (!active) {
            if (rssiDb >= onDb) {
                onCount++;
                if (onCount >= confirmBlocks) { active = true; holdLeftMs = holdMs; }
            } else onCount = 0;
        } else if (rssiDb >= offDb) {
            holdLeftMs = holdMs;
            onCount = confirmBlocks;
        } else {
            holdLeftMs -= blockMs;
            if (holdLeftMs <= 0.0) { active = false; holdLeftMs = 0; onCount = 0; }
        }
        justActivated = !wasActive && active;
        justDeactivated = wasActive && !active;
        if (active) state = (rssiDb >= offDb) ? 2 : 3;
        else state = (onCount > 0) ? 1 : 0;
        return active;
    }
};

// ---- AFC 闭环（AfcLoop）----
// Python: yy float32；trimmedMean/pwr/score 为 float32 pairwise 均值；dcNorm double 递推
class AfcLoop {
public:
    double fs, baseDdcHz, maxAfcHz, loopGain, maxStepHz, minAltScore;
    double afcHz = 0.0, dcNorm = 0.0, lastErrHz = 0.0, lastScore = 0.0;
    bool updated = false, enabled = true;

    AfcLoop(double fs_ = 48000, double baseDdc = 0, double maxAfc = 1500.0,
            double gain = 0.45, double maxStep = 350.0, double minScore = 0.25)
        : fs(fs_), baseDdcHz(baseDdc), maxAfcHz(maxAfc), loopGain(gain),
          maxStepHz(maxStep), minAltScore(minScore) {}

    static double trimmedMean(std::vector<float>& xs, double trim) {
        int n = (int)xs.size();
        if (n <= 0) return 0.0;
        std::sort(xs.begin(), xs.end());
        int k = (int)(n * trim);
        const float* p = xs.data();
        if (k > 0 && n > 2 * k) { p += k; n -= 2 * k; }
        return (double)(npPairwiseSumF32(p, n) / (float)n);
    }

    void process(float* y, int n, DigitalDownConverter& ddc, bool updateAllowed) {
        updated = false;
        if (!enabled) return;
        if (n < 160) {
            for (int i = 0; i < n; i++) y[i] = (float)((double)y[i] - dcNorm);
            return;
        }
        if (!updateAllowed) {
            lastScore = 0.0;
            lastErrHz = dcNorm * fs * 0.5;
            for (int i = 0; i < n; i++) y[i] = (float)((double)y[i] - dcNorm);
            return;
        }
        // 有限值过滤（|y|<0.95）
        finite_.clear();
        for (int i = 0; i < n; i++) {
            float v = y[i];
            if (std::isfinite(v) && fabs(v) < 0.95f) finite_.push_back(v);
        }
        if ((int)finite_.size() < 160) {
            for (int i = 0; i < n; i++) y[i] = (float)((double)y[i] - dcNorm);
            return;
        }
        double dcNow = trimmedMean(finite_, 0.1);
        double maxNorm = 2.0 * maxAfcHz / fs;
        if (dcNow > maxNorm) dcNow = maxNorm;
        if (dcNow < -maxNorm) dcNow = -maxNorm;
        // yc = yy - dcNow（float32，标量弱类型转 float32）
        float dcNowF = (float)dcNow;
        // 评分: -1 倍 spb 滞后自相关（float32 pairwise 均值）
        int spb = (int)llround(fs / (double)kBaudRate);
        if (spb < 1) spb = 1;
        double score = 0.0;
        if (n > spb) {
            prodBuf_.resize(n);
            for (int i = 0; i < n; i++) prodBuf_[i] = (y[i] - dcNowF) * (y[i] - dcNowF);
            float pwrF = npPairwiseSumF32(prodBuf_.data(), n) / (float)n;
            double pwr = (double)pwrF + 1e-12;
            for (int i = 0; i + spb < n; i++)
                lagBuf_.push_back((y[i] - dcNowF) * (y[i + spb] - dcNowF));
            float mF = npPairwiseSumF32(lagBuf_.data(), (int)lagBuf_.size()) / (float)lagBuf_.size();
            lagBuf_.clear();
            score = -(double)mF / pwr;
        }
        lastScore = score;
        double alphaDc = (score >= minAltScore) ? 1.0 : 0.01;
        dcNorm += alphaDc * (dcNow - dcNorm);
        if (dcNorm > maxNorm) dcNorm = maxNorm;
        if (dcNorm < -maxNorm) dcNorm = -maxNorm;
        if (score >= minAltScore) {
            double fErrHz = dcNow * fs * 0.5;
            if (fErrHz > maxAfcHz) fErrHz = maxAfcHz;
            if (fErrHz < -maxAfcHz) fErrHz = -maxAfcHz;
            lastErrHz = fErrHz;
            double step = loopGain * fErrHz;
            if (step > maxStepHz) step = maxStepHz;
            if (step < -maxStepHz) step = -maxStepHz;
            double old = afcHz;
            afcHz += step;
            if (afcHz > maxAfcHz) afcHz = maxAfcHz;
            if (afcHz < -maxAfcHz) afcHz = -maxAfcHz;
            if (fabs(afcHz - old) >= 5.0) {
                ddc.setOffset(baseDdcHz + afcHz);
                updated = true;
            }
        } else {
            lastErrHz = dcNorm * fs * 0.5;
        }
        float dcNormF = (float)dcNorm;
        for (int i = 0; i < n; i++) y[i] = y[i] - dcNormF;
    }

private:
    std::vector<float> finite_;
    std::vector<float> prodBuf_;
    std::vector<float> lagBuf_;
};

// ---- 前端链（FrontendChain）----
class FrontendChain {
public:
    double rssiOffsetDb = 0.0;
    double baseDdc = 0.0, inputSr = 0;
    int hbN = 0;
    double midRate = 0, actualOut = 0;
    int firDec = 1;
    std::string chainDesc;

    IqCorrector iqCorrector;
    DigitalDownConverter ddc;
    C128Fir channelFilter;
    C128Fir firDecimator;
    AfcLoop afc;

    static void computeChain(double srIn, double targetOut, double targetMid,
                             int& hbN, double& midRate, int& firDec, double& actualOut) {
        int bestHb = 0; double bestRate = srIn, bestScore = fabs(srIn - targetMid);
        for (int hb = 1; hb < 8; hb++) {
            double rate = floor(srIn / pow(2.0, (double)hb));
            if (rate < targetOut) break;
            double score = fabs(rate - targetMid);
            if (score <= bestScore) { bestHb = hb; bestRate = rate; bestScore = score; }
        }
        firDec = (int)(bestRate / targetOut);
        if (firDec < 1) firDec = 1;
        actualOut = floor(bestRate / (double)firDec);
        hbN = bestHb;
        midRate = bestRate;
    }

    void init(double sampleRate, double dcOffsetHz, double userOffsetHz,
              double bwHz, bool afcEnable, double afcMaxHz, double afcGain,
              double rssiOffset = 0.0) {
        rssiOffsetDb = rssiOffset;
        baseDdc = dcOffsetHz + userOffsetHz;
        inputSr = sampleRate;
        computeChain(sampleRate, kBasebandRate, 240000.0, hbN, midRate, firDec, actualOut);
        ddc.init(sampleRate, baseDdc);
        {
            double cut = bwHz / 2.0;
            if (cut > midRate * 0.45) cut = midRate * 0.45;
            double tw = bwHz * 0.1;
            if (tw < 1000) tw = 1000;
            int nt = (int)(4.0 * midRate / tw);
            if (nt < 31) nt = 31;
            if (nt > 511) nt = 511;
            nt |= 1;
            channelFilter.setTaps(firwinBh(nt, cut, midRate));
        }
        for (int i = 0; i < hbN; i++) {
            halfbands_.emplace_back();
            halfbands_.back().setTaps(firwinLowpass(63, 0.25, 2.0, blackmanharris(63)));
        }
        {
            double cut = actualOut / 2.0 * 0.9;
            double tw = actualOut * 0.1;
            int nt = (int)(4.0 * midRate / tw);
            if (nt < 31) nt = 31;
            if (nt > 255) nt = 255;
            nt |= 1;
            firDecimator.setTaps(firwinBh(nt, cut, midRate));
            decHist_.assign(firDecimator.taps().size() - 1, c128{0.0, 0.0});
        }
        afc = AfcLoop(actualOut, baseDdc, afcMaxHz, afcGain);
        afc.enabled = afcEnable;
        char buf[256];
        snprintf(buf, sizeof(buf), "%.0fk→DDC(%+.0fk+AFC)", sampleRate / 1000.0, baseDdc / 1000.0);
        chainDesc = buf;
        if (hbN > 0) {
            snprintf(buf, sizeof(buf), "→HB×%d→%.0fk", hbN, midRate / 1000.0);
            chainDesc += buf;
        }
        snprintf(buf, sizeof(buf), "→CH(%.1fk)→FIR÷%d→%.0fk→FM→AFC",
                 bwHz / 1000.0, firDec, actualOut / 1000.0);
        chainDesc += buf;
    }

    // 处理一块 IQ，输出基带 PCM（y）与 RSSI。返回 PCM 样本数。
    int process(const c64* iq, int n, float* y, double* rssiDb, RssiGate* gate) {
        // IQ 校正（c64 输出）
        iq64_.assign(iq, iq + n);
        iqCorrector.process(iq64_.data(), n);
        if (getenv("LBJ_DEBUG2") && n > 0) {
            static int dbgN = 0;
            if (dbgN++ < 3) {
                fprintf(stderr, "[dbg2] afterIQ:");
                for (int i = 0; i < 8; i++)
                    fprintf(stderr, " %.9g%+.9gj", iq64_[i].real(), iq64_[i].imag());
                fprintf(stderr, "\n");
            }
        }
        ddc.process(iq64_.data(), n);
        // 半带抽取：第一级输入 c64 → lfilter 输出 c128
        buf128_.resize(n);
        for (int i = 0; i < n; i++)
            buf128_[i] = c128{(double)iq64_[i].real(), (double)iq64_[i].imag()};
        int len = n;
        for (int h = 0; h < hbN; h++) {
            hbOut_.resize(len);
            halfbands_[h].process128(buf128_.data(), len, hbOut_.data());
            len = len / 2;
            for (int i = 0; i < len; i++) buf128_[i] = hbOut_[2 * i];
        }
        // 信道滤波（c128）
        chOut_.resize(len);
        channelFilter.process128(buf128_.data(), len, chOut_.data());
        // 整数抽取（out[::dec] 语义 = ceil(len/dec) 个输出点，卷积含跨块历史，double 累加）
        int decN = (len + firDec - 1) / firDec;
        const std::vector<double>& dTaps = firDecimator.taps();
        const int L = (int)dTaps.size();
        decOut_.resize(decN);
        for (int i = 0; i < decN; i++) {
            int idx = i * firDec;
            c128 s{0.0, 0.0};
            for (int k = 0; k < L; k++) {
                int j = idx - k;
                if (j >= 0) s += dTaps[k] * chOut_[j];
                else s += dTaps[k] * decHist_[(int)decHist_.size() + j];
            }
            decOut_[i] = s;
        }
        // 更新抽取历史（保留 L-1 个 chOut_ 尾部）
        {
            const int keep = (int)decHist_.size();
            if (len >= keep) {
                for (int k = 0; k < keep; k++) decHist_[k] = chOut_[len - keep + k];
            } else {
                int mv = keep - len;
                for (int k = 0; k < mv; k++) decHist_[k] = decHist_[k + len];
                for (int k = 0; k < len; k++) decHist_[mv + k] = chOut_[k];
            }
        }
        if (getenv("LBJ_DEBUG2")) {
            static int dbgN2 = 0;
            if (dbgN2++ < 3) {
                fprintf(stderr, "[dbg2] decOut:");
                for (int i = 0; i < 8; i++)
                    fprintf(stderr, " %.9g%+.9gj", decOut_[i].real(), decOut_[i].imag());
                fprintf(stderr, "\n");
            }
        }
        // RSSI（complex128 vdot / len）
        double pwr = 0;
        for (int i = 0; i < decN; i++) {
            pwr += decOut_[i].real() * decOut_[i].real()
                 + decOut_[i].imag() * decOut_[i].imag();
        }
        double rssi = 10.0 * log10(pwr / (decN > 0 ? decN : 1) + 1e-12) + rssiOffsetDb;
        // FM 鉴频：c128 → c64 截断（对应 buf[1:]=iq 的 astype），float32 差分相位
        c64 prev = fmPrev_;
        for (int i = 0; i < decN; i++) {
            c64 cur{(float)decOut_[i].real(), (float)decOut_[i].imag()};
            c64 d = mulC64(cur, c64{prev.real(), -prev.imag()});
            y[i] = atan2f(d.imag(), d.real()) * (float)(1.0 / M_PI);
            prev = cur;
        }
        fmPrev_ = prev;
        bool rxActive = true;
        if (gate) rxActive = gate->update(rssi, decN, actualOut);
        afc.process(y, decN, ddc, rxActive);
        *rssiDb = rssi;
        return decN;
    }

    void resetAfc() {
        afc.afcHz = 0; afc.dcNorm = 0; afc.lastErrHz = 0; afc.lastScore = 0;
        afc.updated = false;
        ddc.setOffset(baseDdc);
    }

    // 对拍辅助：导出 taps
    std::vector<float> chTapsForDebug() {
        std::vector<float> v;
        for (double t : channelFilter.taps()) v.push_back((float)t);
        return v;
    }
    std::vector<float> decTapsForDebug() {
        std::vector<float> v;
        for (double t : firDecimator.taps()) v.push_back((float)t);
        return v;
    }
    std::vector<float> hbTapsForDebug(int h) {
        std::vector<float> v;
        for (double t : halfbands_[h].taps()) v.push_back((float)t);
        return v;
    }

    bool consumeAfcUpdated() {
        bool u = afc.updated;
        afc.updated = false;
        return u;
    }

private:
    std::vector<c128> decHist_;
    std::vector<c64> iq64_;
    std::vector<c128> buf128_, hbOut_, chOut_, decOut_;
    std::vector<C128Fir> halfbands_;
    c64 fmPrev_{0.f, 0.f};
};

} // namespace lbj
