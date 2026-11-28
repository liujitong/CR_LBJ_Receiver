// status_frame.h — StatusFrame 双缓冲写入（频谱 + RSSI + 链路统计，seq 递增）
// 布局（小端，float/int32 各 4 字节，见 Kotlin StatusFramePoller 同一定义）：
//  [0]  int32 seq
//  [1]  int32 gateState   (0=OFF 1=ARM 2=ON 3=HOLD 4=BYPASS)
//  [2]  float rssiDb
//  [3]  float afcHz
//  [4]  float afcErrHz
//  [5]  float afcScore
//  [6]  int32 tunerTypeId
//  [7]  int32 appliedGainCentiDb
//  [8]  int32 actualSampleRate
//  [9]  int32 hwFreqHz
//  [10] float blocksPerSec
//  [11] int32 totalBlocks
//  [12] int32 droppedBlocks
//  [13] int32 reconnectCount
//  [14] float decodeCpuPct
//  [15] float bufferLevel  (0..1)
//  [16] int32 running      (0/1)
//  [17] int32 linkMode     (0=usb 1=pipe)
//  [18] int32 errorState   (0=ok 1=streamBroken)
//  [20..275] float spectrum[256]  (v4.0: 32 -> 256 bin，瀑布更细腻)
//  共 276 * 4 = 1104 字节
#pragma once
#include <cstdint>
#include <cstring>
#include <mutex>

namespace lbj {

constexpr int kStatusFrameWords = 276;

class StatusFrameWriter {
public:
    void setInt(int idx, int32_t v) {
        std::lock_guard<std::mutex> lk(m_);
        writeBuf_[idx] = v;
    }
    void setFloat(int idx, float v) {
        std::lock_guard<std::mutex> lk(m_);
        float f = v;
        int32_t iv;
        memcpy(&iv, &f, 4);
        writeBuf_[idx] = iv;
    }
    void setFloats(int idx, const float* v, int count) {
        std::lock_guard<std::mutex> lk(m_);
        for (int i = 0; i < count; i++) {
            int32_t iv;
            memcpy(&iv, &v[i], 4);
            writeBuf_[idx + i] = iv;
        }
    }
    // 发布：切换双缓冲并递增 seq
    void publish() {
        std::lock_guard<std::mutex> lk(m_);
        writeBuf_[0] = ++seq_;
        memcpy(readBuf_, writeBuf_, kStatusFrameWords * 4);
    }

    // 拷贝最近一帧到 dst（dst 需 ≥ kStatusFrameWords*4 字节），返回 seq
    int32_t copyLatest(int32_t* dst) {
        std::lock_guard<std::mutex> lk(m_);
        memcpy(dst, readBuf_, kStatusFrameWords * 4);
        return seq_;
    }

private:
    std::mutex m_;
    int32_t writeBuf_[kStatusFrameWords] = {0};
    int32_t readBuf_[kStatusFrameWords] = {0};
    int32_t seq_ = 0;
};

} // namespace lbj
