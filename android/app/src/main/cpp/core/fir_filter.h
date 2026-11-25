// fir_filter.h — 流式 FIR，对应 scipy.signal.lfilter(b, [1], x, zi=state)
// scipy 2.x 对 float32/complex64 输入会在内部提升为 double 并输出 float64/complex128，
// 因此本文件的 FIR 一律 double 累加（与 scipy 数值路径一致）。
#pragma once
#include <vector>
#include <complex>
#include <cstdint>

namespace lbj {

using c64 = std::complex<float>;
using c128 = std::complex<double>;

// 复数流式 FIR（double 累加；输入 c64 自动提升，输出 c128）
class C128Fir {
public:
    void setTaps(const std::vector<float>& taps) {
        h_.assign(taps.begin(), taps.end());
        hist_.assign(taps.size() - 1, c128{0.0, 0.0});
    }
    // 输入 n 个样本（c64，对应 complex64 输入提升），输出同长度 c128
    void process64(const c64* in, int n, c128* out) {
        const int L = (int)h_.size();
        for (int i = 0; i < n; i++) {
            c128 s{0.0, 0.0};
            s += h_[0] * c128{(double)in[i].real(), (double)in[i].imag()};
            for (int k = 1; k < L; k++) {
                int j = i - k;
                if (j >= 0) s += h_[k] * c128{(double)in[j].real(), (double)in[j].imag()};
                else s += h_[k] * hist_[(int)hist_.size() + j];
            }
            out[i] = s;
        }
        rollHistory(in, n);
    }
    // 输入 c128（上一级 lfilter 已输出 complex128）
    void process128(const c128* in, int n, c128* out) {
        const int L = (int)h_.size();
        for (int i = 0; i < n; i++) {
            c128 s{0.0, 0.0};
            s += h_[0] * in[i];
            for (int k = 1; k < L; k++) {
                int j = i - k;
                if (j >= 0) s += h_[k] * in[j];
                else s += h_[k] * hist_[(int)hist_.size() + j];
            }
            out[i] = s;
        }
        roll128(in, n);
    }
    const std::vector<double>& taps() const { return h_; }

private:
    void rollHistory(const c64* in, int n) {
        const int keep = (int)hist_.size();
        if (n >= keep) {
            for (int k = 0; k < keep; k++)
                hist_[k] = c128{(double)in[n - keep + k].real(), (double)in[n - keep + k].imag()};
        } else {
            int mv = keep - n;
            for (int k = 0; k < mv; k++) hist_[k] = hist_[k + n];
            for (int k = 0; k < n; k++)
                hist_[mv + k] = c128{(double)in[k].real(), (double)in[k].imag()};
        }
    }
    void roll128(const c128* in, int n) {
        const int keep = (int)hist_.size();
        if (n >= keep) {
            for (int k = 0; k < keep; k++) hist_[k] = in[n - keep + k];
        } else {
            int mv = keep - n;
            for (int k = 0; k < mv; k++) hist_[k] = hist_[k + n];
            for (int k = 0; k < n; k++) hist_[mv + k] = in[k];
        }
    }
    std::vector<double> h_;
    std::vector<c128> hist_;
};

// 实数流式 FIR（DPLL 前的高斯平滑；Python lfilter(float32 in, float64 b) → float64）
class RealFir {
public:
    void setTaps(const std::vector<double>& taps) {
        h_ = taps;
        hist_.assign(taps.size() - 1, 0.0);
    }
    void process(const float* in, int n, double* out) {
        const int L = (int)h_.size();
        for (int i = 0; i < n; i++) {
            double s = 0.0;
            s += h_[0] * (double)in[i];
            for (int k = 1; k < L; k++) {
                int j = i - k;
                if (j >= 0) s += h_[k] * (double)in[j];
                else s += h_[k] * hist_[(int)hist_.size() + j];
            }
            out[i] = s;
        }
        if (n >= L - 1) {
            for (int k = 0; k < L - 1; k++) hist_[k] = (double)in[n - (L - 1) + k];
        } else {
            int keep = (int)hist_.size() - n;
            for (int k = 0; k < keep; k++) hist_[k] = hist_[k + n];
            for (int k = 0; k < n; k++) hist_[keep + k] = (double)in[k];
        }
    }

private:
    std::vector<double> h_;
    std::vector<double> hist_;
};

} // namespace lbj
