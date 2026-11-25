// dsp_math.h — scipy 移植：窗函数与 firwin 低通设计
// 对应 decoder.py 中 scipy.signal.firwin(..., window='blackmanharris'|('gaussian',std))
#pragma once
#include <vector>
#include <cstdint>

namespace lbj {

// Blackman-Harris 窗（scipy.signal.windows.blackmanharris，对称）
std::vector<double> blackmanharris(int n);

// Gaussian 窗（scipy.signal.windows.gaussian(M, std)）
std::vector<double> gaussianWindow(int n, double std);

// scipy.signal.firwin 低通（fs 给定时 f = cut/(fs/2)；未给定时 fs=2 即 f=cut）
// scale=True（默认）：double 全程归一化，最后一次性截断 float32（与 .astype(np.float32) 一致）
std::vector<float> firwinLowpass(int nt, double cut, double fs, const std::vector<double>& window);

// 同上，但保留 double（decoder.py bSmooth = firwin(...)/sum，无 astype）
std::vector<double> firwinLowpassD(int nt, double cut, double fs, const std::vector<double>& window);

// 便捷封装：blackmanharris 窗低通
std::vector<float> firwinBh(int nt, double cut, double fs);

// numpy add.reduce float32 的 pairwise 求和（位级对齐 np.mean/np.sum 的累加顺序）
float npPairwiseSumF32(const float* a, int n);

inline double sinc(double x) {
    if (x == 0.0) return 1.0;
    double px = M_PI * x;
    return sin(px) / px;
}

inline int popcount32(uint32_t x) {
    x = x - ((x >> 1) & 0x55555555u);
    x = (x & 0x33333333u) + ((x >> 2) & 0x33333333u);
    x = (x + (x >> 4)) & 0x0F0F0F0Fu;
    return (int)((x * 0x01010101u) >> 24);
}

} // namespace lbj
