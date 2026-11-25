// spectrum.h — 1024 点 FFT + 32 bin 池化平滑（对应 LbjCore._run 内频谱段）
#pragma once
#include <cstdint>
#include <cmath>
#include <vector>
#include <complex>

namespace lbj {

using c64 = std::complex<float>;

// radix-2 就地 FFT（n 为 2 的幂）
inline void fftInplace(c64* a, int n) {
    // 位反转
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2.0 * M_PI / len;
        c64 wlen{(float)cos(ang), (float)sin(ang)};
        for (int i = 0; i < n; i += len) {
            c64 w{1.f, 0.f};
            for (int k = 0; k < len / 2; k++) {
                c64 u = a[i + k], v = a[i + k + len / 2] * w;
                a[i + k] = u + v;
                a[i + k + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

// 频谱统计器：输入原始 IQ（uint8 交错），维护 32 bin 平滑输出
class SpectrumAnalyzer {
public:
    float smoothed[kSpectrumBins];
    SpectrumAnalyzer() { for (int i = 0; i < kSpectrumBins; i++) smoothed[i] = -120.0f; }

    // raw: uint8 交错 IQ；blockBytes >= kNfft*2
    void update(const uint8_t* raw, int blockBytes) {
        if (blockBytes < kNfft * 2) return;
        // hanning 窗
        c64 seg[kNfft];
        double wsum = 0;
        for (int i = 0; i < kNfft; i++) {
            double w = 0.5 - 0.5 * cos(2.0 * M_PI * i / (double)(kNfft - 1));
            wsum += w;
            seg[i] = c64{(float)((raw[2 * i] - 127.5) / 128.0 * w),
                         (float)((raw[2 * i + 1] - 127.5) / 128.0 * w)};
        }
        fftInplace(seg, kNfft);
        // fftshift + 幅度归一（Python: abs(spec)/(nfft*mean(hanning))）
        double norm = kNfft * (wsum / kNfft);
        double db[kNfft];
        for (int i = 0; i < kNfft; i++) {
            int idx = (i + kNfft / 2) % kNfft; // fftshift
            double mag = std::abs(seg[idx]) / norm;
            db[i] = 20.0 * log10(mag > 1e-12 ? mag : 1e-12);
        }
        int chunk = kNfft / kSpectrumBins;
        for (int b = 0; b < kSpectrumBins; b++) {
            double mx = -1e12;
            for (int j = 0; j < chunk; j++) {
                double v = db[b * chunk + j];
                if (v > mx) mx = v;
            }
            smoothed[b] = 0.75 * smoothed[b] + 0.25 * mx;
        }
    }
};

} // namespace lbj
