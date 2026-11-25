// engine.h — LbjEngine：native 引擎编排（对应桌面版 LbjCore 的 native 侧）
#pragma once
#include "fifo.h"
#include "frontend.h"
#include "decoder.h"
#include "spectrum.h"
#include "status_frame.h"
#include <atomic>
#include <thread>
#include <functional>
#include <string>
#include <vector>
#include <mutex>

namespace lbj {

class LbjEngine {
public:
    // JNI 层注入的回调（线程安全：实现方负责 AttachEnv）
    std::function<void(const char* msg)> logFn;
    std::function<void(const char* json)> decodeFn;

    static LbjEngine& instance();

    // init：创建/重建 DSP 链（paramsJson 与桌面版 lbj_config 同名字段）
    // 返回 0 成功
    int init(const char* paramsJson);

    // start：mode 0=USB(fd) 1=pipe(fd 为 socketpair/管道读端)
    // 返回 0 成功；负数错误
    int start(int mode, int fd, long long freqHz, int sampleRate,
              int gainCentiDb, int ppm);

    void stop();
    void release();
    int readSpectrum(int32_t* dst); // 返回 seq
    void setParams(const char* paramsJson);

    bool inited() const { return inited_; }
    bool running() const { return running_; }

private:
    LbjEngine() = default;

    void dspLoop();
    void usbLoop();
    void pipeLoop();
    void emitResult(const LbjResult& r);
    void log(const std::string& msg);

    std::atomic<bool> running_{false};
    std::atomic<bool> streamBroken_{false};
    bool inited_ = false;
    int mode_ = 1;

    // 射频与链路参数（init 时固定）
    double freqMhz_ = 821.2375;
    int sampleRate_ = 240000;
    double bwKhz_ = 35.0;
    double dcOffsetHz_ = 50000.0;
    double userOffsetHz_ = 0.0;
    double gainDb_ = 19.7;
    double ppm_ = 1.0;
    int blockSize_ = 65536;
    int fifoBlocks_ = 60;
    double rssiThresholdDb_ = kDefaultRssiThresholdDb;
    double rssiHystDb_ = kDefaultRssiHystDb;
    double rssiHoldMs_ = kDefaultRssiHoldMs;
    bool afcEnable_ = true;
    double afcMaxHz_ = kDefaultAfcMaxHz;
    double afcGain_ = 0.45;
    bool keepAfcAfterPacket_ = false;
    double baudRate_ = 1200;

    // 运行时（start 时重建）
    FrontendChain chain_;
    LbjParser parser_;
    RssiGate gate_{kDefaultRssiThresholdDb};
    SpectrumAnalyzer spectrum_;
    StatusFrameWriter status_;

    SpscFifo fifo_;
    std::thread readerThread_, dspThread_;
    std::mutex devMutex_;       // 保护 rtlsdr 设备句柄
    void* rtlsdrDev_ = nullptr; // rtlsdr_dev_t*
    int pipeFd_ = -1;           // native 持有的 dup(fd)
    bool fdOwned_ = false;

    // 统计
    std::atomic<int> totalBlocks_{0};
    std::atomic<int> droppedBlocks_{0};
    std::atomic<int> reconnectCount_{0};
    int tunerTypeId_ = 0;
    int appliedGainCentiDb_ = 0;
    int actualSampleRate_ = 0;
    int hwFreqHz_ = 0;
    double decodeCpuPct_ = 0;
    std::atomic<int> lastSeqSeen_{0};

    // DSP 工作缓冲
    std::vector<c64> iqBuf_;
    std::vector<float> pcmBuf_;
    std::vector<uint8_t> rawBuf_;

    static LbjEngine* instance_;
};

} // namespace lbj
