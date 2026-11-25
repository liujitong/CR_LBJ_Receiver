#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IQ 数据源的块级统计与诊断快照。

网络源（rtl_tcp）与 USB 直连源的「块率 / 块间隔抖动 / 丢块 / 队列积压」
口径必须一致，接收状态面板才能不分数据源地展示。这里把统计累加与诊断
计算抽成两个函数，由各数据源在读取循环里调用。

约定：调用方对象需具备以下属性（RtlTcpSource / RtlSdrDirectSource 都在
__init__ 里初始化）::

    queue, blockCount, bytesRecv, droppedBlocks, reconnectCount,
    lastBlockTime, blockIntervals, blockSizes
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

# 诊断提示语：不同传输介质下同一个指标的可疑原因不一样
_MEDIA_WORDS = {
    'net': {
        'slow': '服务器响应慢',
        'small': '服务器可能限流',
        'jitter': '网络不稳定',
    },
    'usb': {
        'slow': 'USB 传输卡顿（换 USB 2.0 口或降低采样率）',
        'small': '驱动返回长度异常',
        'jitter': 'USB 稳定性差（供电不足或线材问题）',
    },
}


def recordBlock(src: Any, nSamples: int, nBytes: int) -> None:
    """累计一块数据：更新块间隔/块大小窗口、总块数与接收字节数。

    参数:
        src: 数据源对象（提供统计属性）。
        nSamples: 本块 IQ 样本数。
        nBytes: 本块原始字节数（uint8 对，2 字节/样本）。
    """
    now = time.time()
    if src.lastBlockTime > 0:
        src.blockIntervals.append(now - src.lastBlockTime)
        if len(src.blockIntervals) > 30:
            src.blockIntervals.pop(0)
    src.lastBlockTime = now
    src.blockSizes.append(nSamples)   # 样本数
    if len(src.blockSizes) > 30:
        src.blockSizes.pop(0)
    src.blockCount += 1
    src.bytesRecv += nBytes


def buildDiagnostics(src: Any, medium: str = 'net') -> Dict[str, Any]:
    """生成诊断数据快照。

    返回字典包含:
        blocksPerSec: 块率 (块/秒)
        avgIntervalMs: 平均块间隔 (毫秒)
        avgBlockSize: 平均块大小 (样本数)
        dataRateMbps: 等效数据速率 (Mbps, 按 complex64 吞吐计算)
        queueSize: 当前队列积压
        queueMax: 队列容量
        totalBlocks: 累计块数
        reconnectCount: 重连次数
        droppedBlocks: 因队列满丢弃的块数
        jitterCv: 块间隔变异系数 (std/mean)
        issues: 已识别的问题列表
    """
    words = _MEDIA_WORDS.get(medium, _MEDIA_WORDS['net'])
    intervals: List[float] = src.blockIntervals
    sizes: List[int] = src.blockSizes
    avgInterval = sum(intervals) / len(intervals) if intervals else 0.0
    avgSize = sum(sizes) / len(sizes) if sizes else 0.0
    blocksPerSec = (1.0 / avgInterval) if avgInterval > 0 else 0.0
    # 等效数据速率: 样本数 × 8(complex64 bytes/sample) × 8(bits/byte) / 1e6
    dataRateMbps = (avgSize * 8 * 8 * blocksPerSec) / 1e6 if blocksPerSec > 0 else 0.0
    # 抖动 CV = std / mean
    cv = 0.0
    if len(intervals) >= 2 and avgInterval > 0:
        variance = sum((x - avgInterval) ** 2 for x in intervals) / len(intervals)
        cv = (variance ** 0.5) / avgInterval
    queueSize = src.queue.qsize()
    queueMax = src.queue.maxsize
    # 问题识别
    issues: List[str] = []
    if avgInterval > 0.5:
        issues.append(f'块间隔过长 {avgInterval:.2f}s ({words["slow"]})')
    elif avgInterval > 0.1 and blocksPerSec < 15:
        issues.append(f'数据速率低 {blocksPerSec:.1f} 块/s (正常 30+)')
    if queueSize > queueMax - 5:
        issues.append(f'队列积压 {queueSize}/{queueMax} (处理跟不上)')
    if src.droppedBlocks > 0:
        issues.append(f'已丢弃 {src.droppedBlocks} 块 (DSP 跟不上)')
    if src.reconnectCount > 0:
        issues.append(f'已重连 {src.reconnectCount} 次')
    if avgSize > 0 and avgSize < 1024:
        issues.append(f'块过小 {avgSize:.0f} 样本 ({words["small"]})')
    if cv > 0.5:
        issues.append(f'抖动大 CV={cv:.2f} ({words["jitter"]})')
    return {
        'blocksPerSec': blocksPerSec,
        'avgIntervalMs': avgInterval * 1000,
        'avgBlockSize': avgSize,
        'dataRateMbps': dataRateMbps,
        'queueSize': queueSize,
        'queueMax': queueMax,
        'droppedBlocks': src.droppedBlocks,
        'totalBlocks': src.blockCount,
        'reconnectCount': src.reconnectCount,
        'jitterCv': cv,
        'issues': issues,
    }
