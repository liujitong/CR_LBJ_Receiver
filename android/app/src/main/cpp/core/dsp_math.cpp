// dsp_math.cpp — scipy 窗函数与 firwin 的 C++ 等价实现（供对拍逐位一致）
#include "dsp_math.h"
#include <cmath>

namespace lbj {

std::vector<double> blackmanharris(int n) {
    // scipy 1.18 _general_cosine: fac = linspace(-π, π, M)（M=n）
    // a = [0.35875, 0.48829, 0.14128, 0.01168]（新版系数，与旧版 0.010641 不同）
    // 对称展开：w[k] = a0 - a1·cos(2πk/(M-1)) + a2·cos(4πk/(M-1)) - a3·cos(6πk/(M-1))
    static const double a0 = 0.35875, a1 = 0.48829, a2 = 0.14128, a3 = 0.01168;
    std::vector<double> w(n);
    if (n == 1) { w[0] = 1.0; return w; }
    double M1 = (double)(n - 1);
    for (int k = 0; k < n; k++) {
        double f = 2.0 * M_PI * k / M1;
        w[k] = a0 - a1 * cos(f) + a2 * cos(2 * f) - a3 * cos(3 * f);
    }
    return w;
}

std::vector<double> gaussianWindow(int n, double std) {
    // scipy: exp(-0.5 * ((x - (M-1)/2) / std)^2), x = 0..M-1
    std::vector<double> w(n);
    double c = (n - 1) / 2.0;
    for (int x = 0; x < n; x++) {
        double d = (x - c) / std;
        w[x] = exp(-0.5 * d * d);
    }
    return w;
}

std::vector<float> firwinLowpass(int nt, double cut, double fs, const std::vector<double>& window) {
    // scipy.signal.firwin(numtaps, cut, fs=fs, window=w):
    //   f = cut / nyq, nyq = fs/2（fs 未给定时 nyq=1，即 f=cut）
    //   m = arange(nt) - (nt-1)/2
    //   h = f * sinc(f * m) * window（double 全程）
    //   h /= sum(h)；.astype(np.float32) 一次性截断
    std::vector<double> h(nt, 0.0);
    double f = cut / (fs / 2.0);
    double m0 = (nt - 1) / 2.0;
    double sum = 0.0;
    for (int i = 0; i < nt; i++) {
        double v = f * sinc(f * (i - m0)) * (window.empty() ? 1.0 : window[i]);
        h[i] = v;
        sum += v;
    }
    if (sum != 0.0) {
        for (int i = 0; i < nt; i++) h[i] = h[i] / sum;
    }
    return std::vector<float>(h.begin(), h.end());
}

std::vector<double> firwinLowpassD(int nt, double cut, double fs, const std::vector<double>& window) {
    // 与 firwinLowpass 相同公式，但保留 double（decoder.py bSmooth 无 astype）
    std::vector<double> h(nt, 0.0);
    double f = cut / (fs / 2.0);
    double m0 = (nt - 1) / 2.0;
    double sum = 0.0;
    for (int i = 0; i < nt; i++) {
        double v = f * sinc(f * (i - m0)) * (window.empty() ? 1.0 : window[i]);
        h[i] = v;
        sum += v;
    }
    if (sum != 0.0) {
        for (int i = 0; i < nt; i++) h[i] = h[i] / sum;
    }
    return h;
}

float npPairwiseSumF32(const float* a, int n) {
    // numpy pairwise_sum（float32 累加，PW_BLOCKSIZE=128，8 路展开）位级复刻
    if (n < 8) {
        float r = 0.0f;
        for (int i = 0; i < n; i++) r += a[i];
        return r;
    }
    if (n <= 128) {
        float r[8];
        for (int j = 0; j < 8; j++) r[j] = a[j];
        int lim = n - (n % 8);
        for (int i = 8; i < lim; i += 8)
            for (int j = 0; j < 8; j++) r[j] += a[i + j];
        float res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (int i = lim; i < n; i++) res += a[i];
        return res;
    }
    int n2 = n / 2;
    n2 -= n2 % 8;
    return npPairwiseSumF32(a, n2) + npPairwiseSumF32(a + n2, n - n2);
}

std::vector<float> firwinBh(int nt, double cut, double fs) {
    return firwinLowpass(nt, cut, fs, blackmanharris(nt));
}

} // namespace lbj
