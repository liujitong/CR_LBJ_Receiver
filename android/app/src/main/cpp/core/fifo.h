// fifo.h — SPSC 无锁字节环形缓冲（USB/pipe 读线程 → DSP 线程）
// 满则丢弃整块并计数（与桌面版 queue.Full → droppedBlocks 行为一致）
#pragma once
#include <cstdint>
#include <atomic>
#include <vector>
#include <cstring>

namespace lbj {

class SpscFifo {
public:
    void init(size_t capacity) {
        buf_.assign(capacity, 0);
        mask_ = capacity - 1;
        head_.store(0);
        tail_.store(0);
    }
    size_t capacity() const { return buf_.size(); }

    // 写入 n 字节（生产者）；空间不足返回 false（不部分写入）
    bool write(const uint8_t* data, size_t n) {
        size_t head = head_.load(std::memory_order_relaxed);
        size_t tail = tail_.load(std::memory_order_acquire);
        size_t used = head - tail;
        if (n > buf_.size() - used) return false;
        size_t pos = head & mask_;
        size_t first = std::min(n, buf_.size() - pos);
        memcpy(&buf_[pos], data, first);
        if (n > first) memcpy(&buf_[0], data + first, n - first);
        head_.store(head + n, std::memory_order_release);
        return true;
    }

    // 读取 n 字节（消费者）；可用不足返回实际读取数
    size_t read(uint8_t* out, size_t n) {
        size_t head = head_.load(std::memory_order_acquire);
        size_t tail = tail_.load(std::memory_order_relaxed);
        size_t used = head - tail;
        if (used < n) n = used;
        size_t pos = tail & mask_;
        size_t first = std::min(n, buf_.size() - pos);
        memcpy(out, &buf_[pos], first);
        if (n > first) memcpy(out + first, &buf_[0], n - first);
        tail_.store(tail + n, std::memory_order_release);
        return n;
    }

    size_t used() const {
        return head_.load(std::memory_order_acquire) - tail_.load(std::memory_order_relaxed);
    }

private:
    std::vector<uint8_t> buf_;
    size_t mask_ = 0;
    std::atomic<size_t> head_{0}, tail_{0};
};

} // namespace lbj
