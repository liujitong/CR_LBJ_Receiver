// engine.cpp — LbjEngine 实现：USB(librtlsdr fd 直连) / pipe 两种数据源 + DSP 循环
#include "engine.h"
#include "result_json.h"
#include "thirdparty/librtlsdr/include/rtl-sdr.h"
#include <unistd.h>
#include <poll.h>
#include <cstring>
#include <cstdio>
#include <cmath>
#include <chrono>

namespace lbj {

LbjEngine* LbjEngine::instance_ = nullptr;
LbjEngine& LbjEngine::instance() {
    if (!instance_) instance_ = new LbjEngine();
    return *instance_;
}

// ---- 极简扁平 JSON 取值（键值均为简单类型，双方协议固定）----
namespace {

const char* findKey(const char* json, const char* key) {
    std::string pat = std::string("\"") + key + "\"";
    const char* p = strstr(json, pat.c_str());
    if (!p) return nullptr;
    p += pat.size();
    while (*p == ' ' || *p == ':') p++;
    return p;
}

double jsonDouble(const char* json, const char* key, double def) {
    const char* p = findKey(json, key);
    if (!p) return def;
    return strtod(p, nullptr);
}

int jsonInt(const char* json, const char* key, int def) {
    return (int)jsonDouble(json, key, def);
}

bool jsonBool(const char* json, const char* key, bool def) {
    const char* p = findKey(json, key);
    if (!p) return def;
    if (strncmp(p, "true", 4) == 0) return true;
    if (strncmp(p, "false", 5) == 0) return false;
    return def;
}

double nowSeconds() {
    using namespace std::chrono;
    return duration_cast<duration<double>>(system_clock::now().time_since_epoch()).count();
}

} // namespace

void LbjEngine::log(const std::string& msg) {
    if (logFn) {
        std::string m = msg;
        logFn(m.c_str());
    }
}

int LbjEngine::init(const char* paramsJson) {
    freqMhz_ = jsonDouble(paramsJson, "freqMhz", 821.2375);
    sampleRate_ = jsonInt(paramsJson, "sampleRate", 240000);
    bwKhz_ = jsonDouble(paramsJson, "bwKhz", 35.0);
    dcOffsetHz_ = jsonDouble(paramsJson, "dcOffsetHz", 50000.0);
    userOffsetHz_ = jsonDouble(paramsJson, "userOffsetHz", 0.0);
    gainDb_ = jsonDouble(paramsJson, "gainDb", 19.7);
    ppm_ = jsonDouble(paramsJson, "ppm", 1.0);
    blockSize_ = jsonInt(paramsJson, "blockSize", 65536);
    rssiThresholdDb_ = jsonDouble(paramsJson, "rssiThresholdDb", kDefaultRssiThresholdDb);
    rssiHystDb_ = jsonDouble(paramsJson, "rssiHystDb", kDefaultRssiHystDb);
    rssiHoldMs_ = jsonDouble(paramsJson, "rssiHoldMs", kDefaultRssiHoldMs);
    afcEnable_ = jsonBool(paramsJson, "afcEnable", true);
    afcMaxHz_ = jsonDouble(paramsJson, "afcMaxHz", kDefaultAfcMaxHz);
    afcGain_ = jsonDouble(paramsJson, "afcGain", 0.45);
    keepAfcAfterPacket_ = jsonBool(paramsJson, "keepAfcAfterPacket", false);
    baudRate_ = jsonDouble(paramsJson, "baudRate", 1200.0);

    inited_ = true;
    char buf[160];
    snprintf(buf, sizeof(buf), "[链路] %.0fk→DDC(%+.0fk+AFC)", (double)sampleRate_ / 1000.0,
             dcOffsetHz_ / 1000.0);
    log(buf);
    return 0;
}

int LbjEngine::start(int mode, int fd, long long freqHz, int sampleRate,
                     int gainCentiDb, int ppm) {
    if (!inited_) return -1;
    stop();

    mode_ = mode;
    gainDb_ = gainCentiDb / 100.0;
    ppm_ = ppm;
    sampleRate_ = sampleRate;
    hwFreqHz_ = (int)(freqHz - dcOffsetHz_); // USB 模式的硬件调谐频率

    // 重建 DSP 链与解码器
    chain_ = FrontendChain();
    chain_.init((double)sampleRate_, dcOffsetHz_, userOffsetHz_,
                bwKhz_ * 1000.0, afcEnable_, afcMaxHz_, afcGain_);
    gate_ = RssiGate(rssiThresholdDb_, rssiHystDb_, rssiHoldMs_);
    parser_ = LbjParser();
    parser_.initDecoder(chain_.actualOut, baudRate_);
    spectrum_ = SpectrumAnalyzer();

    fifo_.init((size_t)fifoBlocks_ * blockSize_ * 2);
    iqBuf_.resize(blockSize_);
    pcmBuf_.resize(blockSize_ / 2 + 64);
    rawBuf_.resize((size_t)blockSize_ * 2);

    totalBlocks_ = 0; droppedBlocks_ = 0; reconnectCount_ = 0;
    streamBroken_ = false;
    running_ = true;

    if (mode == 0) {
        // ---- USB 直连：rtlsdr_open_fd + configure ----
        rtlsdr_dev_t* dev = nullptr;
        int rc = rtlsdr_open_fd(&dev, fd);
        if (rc != 0) {
            char buf[96];
            snprintf(buf, sizeof(buf), "[USB] rtlsdr_open_fd 失败 rc=%d", rc);
            log(buf);
            running_ = false;
            return rc;
        }
        rtlsdr_set_sample_rate(dev, (uint32_t)sampleRate_);
        actualSampleRate_ = (int)rtlsdr_get_sample_rate(dev);
        rtlsdr_set_center_freq(dev, (uint32_t)hwFreqHz_);
        if (ppm_ != 0) rtlsdr_set_freq_correction(dev, (int)ppm_);
        tunerTypeId_ = (int)rtlsdr_get_tuner_type(dev);
        // 手动增益 + 关 AGC（与桌面版 _configure 一致）
        rtlsdr_set_tuner_gain_mode(dev, 1);
        int gains[64];
        int ng = rtlsdr_get_tuner_gains(dev, gains);
        double want = gainDb_;
        if (ng > 0) {
            double best = gains[0] / 10.0, bestD = 1e9;
            for (int i = 0; i < ng; i++) {
                double g = gains[i] / 10.0;
                double d = fabs(g - gainDb_);
                if (d < bestD) { bestD = d; best = g; }
            }
            want = best;
        }
        appliedGainCentiDb_ = (int)llround(want * 100);
        rtlsdr_set_tuner_gain(dev, (int)llround(want * 10));
        rtlsdr_set_agc_mode(dev, 0);
        rtlsdr_reset_buffer(dev);
        rtlsdrDev_ = dev;
        {
            char buf[192];
            snprintf(buf, sizeof(buf),
                     "[USB] tuner#%d 采样率 %dk 增益 %.1f dB 调谐 %.4f MHz（fd 直连）",
                     tunerTypeId_, actualSampleRate_ / 1000, want,
                     hwFreqHz_ / 1e6);
            log(buf);
        }
        readerThread_ = std::thread(&LbjEngine::usbLoop, this);
    } else {
        // ---- pipe：dup fd，读线程直读 ----
        pipeFd_ = dup(fd);
        fdOwned_ = true;
        readerThread_ = std::thread(&LbjEngine::pipeLoop, this);
        log("[pipe] 数据通路已建立");
    }
    dspThread_ = std::thread(&LbjEngine::dspLoop, this);

    {
        char buf[160];
        snprintf(buf, sizeof(buf), "[启动] 采样率 %dk 频率 %.4f MHz（mode=%s）",
                 sampleRate_ / 1000, freqHz / 1e6, mode == 0 ? "usb" : "pipe");
        log(buf);
        log(std::string("[链路] ") + chain_.chainDesc);
    }
    return 0;
}

void LbjEngine::usbLoop() {
    // rtlsdr_read_async 阻塞收流；断流后退出线程（重开需 Java 传新 fd）
    rtlsdr_dev_t* dev = (rtlsdr_dev_t*)rtlsdrDev_;
    rtlsdr_reset_buffer(dev);
    int rc = rtlsdr_read_async(dev,
                               [](unsigned char* buf, uint32_t len, void* ctx) {
                                   auto* self = static_cast<LbjEngine*>(ctx);
                                   if (!self->running_ || !len) return;
                                   if (!self->fifo_.write(buf, len)) self->droppedBlocks_++;
                               },
                               this, 15, (uint32_t)(blockSize_ * 2));
    if (running_) {
        // 非主动停止：数据流中断
        streamBroken_ = true;
        reconnectCount_++;
        log("[USB] 数据流中断（返回 " + std::to_string(rc) + "），等待上层重开设备");
    }
}

void LbjEngine::pipeLoop() {
    size_t chunk = (size_t)blockSize_ * 2;
    while (running_) {
        size_t got = 0;
        while (got < chunk && running_) {
            // poll 避免永久阻塞（stop 时 close 不一定能唤醒 read）
            struct pollfd pfd;
            pfd.fd = pipeFd_;
            pfd.events = POLLIN;
            int pr = poll(&pfd, 1, 200);
            if (!running_) return;
            if (pr <= 0) continue; // 超时重试
            ssize_t r = read(pipeFd_, rawBuf_.data() + got, chunk - got);
            if (r <= 0) {
                if (running_) {
                    streamBroken_ = true;
                    reconnectCount_++;
                    log(r == 0 ? "[pipe] 上游断开（EOF）" : "[pipe] 读取错误，等待上层重建通路");
                }
                return;
            }
            got += (size_t)r;
        }
        if (!running_) return;
        if (!fifo_.write(rawBuf_.data(), chunk)) droppedBlocks_++;
    }
}

void LbjEngine::dspLoop() {
    size_t chunk = (size_t)blockSize_ * 2;
    size_t consecutiveStarve = 0;
    double cpuAccumMs = 0;
    int cpuBlocks = 0;
    double lastStatTime = nowSeconds();
    double blocksInWindow = 0;

    while (running_) {
        // 取一块（fifo 不足时短暂等待）
        size_t got = fifo_.read(rawBuf_.data(), chunk);
        if (got < chunk) {
            if (++consecutiveStarve > 40) {
                // ~200ms 没有数据：发布一次状态帧
                status_.setInt(1, gate_.state);
                status_.setFloat(2, (float)-140.0);
                status_.setInt(16, running_ ? 1 : 0);
                status_.setInt(18, streamBroken_ ? 1 : 0);
                status_.publish();
                consecutiveStarve = 0;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }
        consecutiveStarve = 0;
        auto t0 = std::chrono::steady_clock::now();

        // uint8 → float 复数（与桌面版一致：(x-127.5)/128）
        for (int i = 0; i < blockSize_; i++) {
            iqBuf_[i] = c64{(float)((rawBuf_[2 * i] - 127.5) / 128.0),
                            (float)((rawBuf_[2 * i + 1] - 127.5) / 128.0)};
        }
        spectrum_.update(rawBuf_.data(), (int)chunk);

        double rssi = -140;
        int pcmN = chain_.process(iqBuf_.data(), blockSize_, pcmBuf_.data(), &rssi, &gate_);

        if (chain_.consumeAfcUpdated()) {
            parser_.resetDpllSoft();
        }

        if (gate_.active) {
            std::vector<LbjResult> results;
            parser_.processChunk(pcmBuf_.data(), pcmN, results);
            for (auto& r : results) {
                // 信号质量回填（与桌面版 LbjCore._onDecode 一致）
                r.rssi = rssi;
                r.afcHz = chain_.afc.afcHz;
                r.afcErrHz = chain_.afc.lastErrHz;
                r.afcScore = chain_.afc.lastScore;
                emitResult(r);
            }
        } else if (gate_.justDeactivated) {
            parser_.resetReceiverState();
            if (!keepAfcAfterPacket_ && chain_.afc.enabled) {
                chain_.resetAfc();
            }
        }

        auto t1 = std::chrono::steady_clock::now();
        cpuAccumMs += std::chrono::duration<double, std::milli>(t1 - t0).count();
        cpuBlocks++;
        blocksInWindow++;
        totalBlocks_++;

        // 每块发布状态帧（DSP 块约 0.27s @240k/65536）
        double elapsed = nowSeconds() - lastStatTime;
        if (elapsed >= 1.0 || blocksInWindow >= 4) {
            double blockDurMs = 1000.0 * blockSize_ / sampleRate_;
            decodeCpuPct_ = cpuBlocks > 0 ? cpuAccumMs / cpuBlocks / blockDurMs * 100.0 : 0;
            cpuAccumMs = 0; cpuBlocks = 0;
            status_.setInt(1, gate_.state);
            status_.setFloat(2, (float)rssi);
            status_.setFloat(3, (float)chain_.afc.afcHz);
            status_.setFloat(4, (float)chain_.afc.lastErrHz);
            status_.setFloat(5, (float)chain_.afc.lastScore);
            status_.setInt(6, tunerTypeId_);
            status_.setInt(7, appliedGainCentiDb_);
            status_.setInt(8, actualSampleRate_ ? actualSampleRate_ : sampleRate_);
            status_.setInt(9, hwFreqHz_);
            status_.setFloat(10, (float)(blocksInWindow / elapsed));
            status_.setInt(11, totalBlocks_);
            status_.setInt(12, droppedBlocks_);
            status_.setInt(13, reconnectCount_);
            status_.setFloat(14, (float)decodeCpuPct_);
            status_.setFloat(15, (float)((double)fifo_.used() / fifo_.capacity()));
            status_.setInt(16, running_ ? 1 : 0);
            status_.setInt(17, mode_);
            status_.setInt(18, streamBroken_ ? 1 : 0);
            status_.setFloats(20, spectrum_.smoothed, kSpectrumBins);
            status_.publish();
            lastStatTime = nowSeconds();
            blocksInWindow = 0;
        }
    }
}

void LbjEngine::emitResult(const LbjResult& r) {
    if (!decodeFn) return;
    std::string out = resultToJson(r);
    decodeFn(out.c_str());
}

void LbjEngine::stop() {
    if (!running_ && !readerThread_.joinable() && !dspThread_.joinable()) return;
    running_ = false;
    if (rtlsdrDev_) {
        {
            std::lock_guard<std::mutex> lk(devMutex_);
            rtlsdr_cancel_async((rtlsdr_dev_t*)rtlsdrDev_);
        }
    }
    if (pipeFd_ >= 0) {
        // 关闭读端让阻塞的 read() 返回
        ::close(pipeFd_);
        pipeFd_ = -1;
    }
    if (readerThread_.joinable()) readerThread_.join();
    if (dspThread_.joinable()) dspThread_.join();
    if (rtlsdrDev_) {
        rtlsdr_close((rtlsdr_dev_t*)rtlsdrDev_);
        rtlsdrDev_ = nullptr;
    }
    log("[停止] native 引擎已停止");
}

void LbjEngine::release() {
    stop();
    inited_ = false;
}

int LbjEngine::readSpectrum(int32_t* dst) {
    return status_.copyLatest(dst);
}

void LbjEngine::setParams(const char* paramsJson) {
    // 热更新：RSSI 门限/迟滞/保持、AFC 开关、keepAfc
    rssiThresholdDb_ = jsonDouble(paramsJson, "rssiThresholdDb", rssiThresholdDb_);
    rssiHystDb_ = jsonDouble(paramsJson, "rssiHystDb", rssiHystDb_);
    rssiHoldMs_ = jsonDouble(paramsJson, "rssiHoldMs", rssiHoldMs_);
    afcEnable_ = jsonBool(paramsJson, "afcEnable", afcEnable_);
    keepAfcAfterPacket_ = jsonBool(paramsJson, "keepAfcAfterPacket", keepAfcAfterPacket_);
    gate_.updateThreshold(rssiThresholdDb_);
    gate_.hysteresisDb = rssiHystDb_;
    gate_.offDb = rssiThresholdDb_ - rssiHystDb_;
    gate_.holdMs = rssiHoldMs_;
    chain_.afc.enabled = afcEnable_;
}


// ===========================================================================
// v3.2.7：设备型号探测（供 App「检测设备并推荐」用）
//   打开 Java 传来的 fd → 读 tuner 型号与可用增益表 → 立刻关闭。
//   设备正在接收时会因被占用而失败，调用方应提示先停止接收。
// ===========================================================================
std::string LbjEngine::probeTuner(int fd) {
    static const char* kNames[] = {"Unknown", "E4000", "FC0012", "FC0013",
                                   "FC2580", "R820T", "R828D"};
    if (fd < 0) return "{\"ok\":false,\"error\":\"invalid fd\"}";
    rtlsdr_dev_t* dev = nullptr;
    int r = rtlsdr_open_fd(&dev, fd);
    if (r < 0 || dev == nullptr) {
        return "{\"ok\":false,\"error\":\"rtlsdr_open_fd rc=" +
               std::to_string(r) + "\"}";
    }
    int tunerType = (int)rtlsdr_get_tuner_type(dev);
    const char* name =
        (tunerType >= 0 && tunerType <= 6) ? kNames[tunerType] : "Unknown";
    std::string gains = "[";
    int n = rtlsdr_get_tuner_gains(dev, nullptr);
    if (n > 0) {
        std::vector<int> g(n);
        int m = rtlsdr_get_tuner_gains(dev, g.data());
        for (int i = 0; i < m; i++) {
            if (i) gains += ",";
            gains += std::to_string(g[i]);
        }
    }
    gains += "]";
    rtlsdr_close(dev);
    std::string json = "{\"ok\":true,\"tunerType\":" + std::to_string(tunerType) +
                       ",\"tuner\":\"" + name + "\",\"gains\":" + gains + "}";
    // static 方法不能直调非静态 log：走单例（探测只在未运行时发生，安全）`n    instance().log("[检测] " + json);
    return json;
}

} // namespace lbj
