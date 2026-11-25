#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DSP 桥接线程：把 LbjCore 的回调桥接到 Qt 信号。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class DspBridge(QThread):
    """在 QThread 中运行 LbjCore，通过 Qt 信号向 UI 推送事件。"""

    statusUpdated = Signal(dict)
    spectrumUpdated = Signal(np.ndarray)
    trainDecoded = Signal(dict)
    logMessage = Signal(str)
    connectionChanged = Signal(bool)
    diagnosticsUpdated = Signal(dict)
    interferenceAlert = Signal(str, str)  # (方向, 告警文本)

    def __init__(self, config: CoreConfig):
        super().__init__()
        self.config = config
        self.core: Optional[LbjCore] = None
        self._lastStatusT = 0.0
        self._lastSpectrumT = 0.0
        self._lastDiagT = 0.0
        self._startTime = 0.0
        self._lastStats = {
            'bytesRecv': 0, 'reconnectCount': 0, 'uptime': 0, 'diagnostics': 'OK',
            'blocksPerSec': 0.0, 'jitterCv': 0.0, 'dataRateMbps': 0.0,
        }

    def run(self):
        """线程入口：构造 LbjCore 并运行。"""
        core = LbjCore(config=self.config)
        self.core = core
        self._startTime = time.time()

        # 回调 -> Qt 信号
        core.onDecode = self._onDecode
        core.onLog = lambda msg: self.logMessage.emit(msg)
        core.onConnectionChange = lambda c: self.connectionChanged.emit(c)
        core.onInterference = lambda d, t: self.interferenceAlert.emit(d, t)

        self.logMessage.emit(
            f'[启动] 连接 {core.host}:{core.port} 采样率 {core.sampleRate // 1000}k '
            f'频率 {core.freqMhz:.4f} MHz')
        self.logMessage.emit(f'[链路] {core.frontend.chainDesc}')

        core.start()

        # 主循环：定时推送状态 + 频谱 + 诊断
        while core.running and not self.isInterruptionRequested():
            now = time.time()
            # 状态 ~10fps
            if now - self._lastStatusT >= 0.1:
                self._emitStatus()
                self._lastStatusT = now
            # 频谱 ~25fps
            if now - self._lastSpectrumT >= 0.04:
                self._emitSpectrum()
                self._lastSpectrumT = now
            # 网络诊断 ~每10秒
            if now - self._lastDiagT >= 10.0:
                self._emitDiagnostics()
                self._lastDiagT = now
            QThread.msleep(40)

        core.stop()
        self.logMessage.emit('[停止] DSP 线程已退出')

    def _emitStatus(self):
        if not self.core:
            return
        st = self.core.getStatus()
        # 更新统计
        self._lastStats['uptime'] = time.time() - self._startTime
        self._lastStats['bytesRecv'] = getattr(self.core, '_bytesRecv', 0)
        # 诊断摘要: 未连接时覆盖；连接时保留 _emitDiagnostics 的最新结果
        if not st.get('connected', False):
            self._lastStats['diagnostics'] = '未连接'
        self.statusUpdated.emit(st)

    def _emitDiagnostics(self):
        """发射网络诊断信息到日志和信号 (每 10 秒一次)。"""
        if not self.core:
            return
        diag = self.core.getNetworkDiagnostics()
        # 更新 _lastStats 中的网络字段
        self._lastStats['reconnectCount'] = diag.get('reconnectCount', 0)
        self._lastStats['blocksPerSec'] = diag.get('blocksPerSec', 0.0)
        self._lastStats['jitterCv'] = diag.get('jitterCv', 0.0)
        self._lastStats['dataRateMbps'] = diag.get('dataRateMbps', 0.0)
        self._lastStats['droppedBlocks'] = diag.get('droppedBlocks', 0)
        issues = diag.get('issues', [])
        # 更新诊断摘要
        if issues:
            self._lastStats['diagnostics'] = issues[0]
        elif diag.get('blocksPerSec', 0) > 0:
            self._lastStats['diagnostics'] = '网络正常'
        else:
            self._lastStats['diagnostics'] = '等待数据'
        # 发射结构化信号
        self.diagnosticsUpdated.emit(diag)
        # 输出诊断日志
        bps = diag.get('blocksPerSec', 0.0)
        intervalMs = diag.get('avgIntervalMs', 0.0)
        blkSize = diag.get('avgBlockSize', 0.0)
        rate = diag.get('dataRateMbps', 0.0)
        qSize = diag.get('queueSize', 0)
        qMax = diag.get('queueMax', 30)
        total = diag.get('totalBlocks', 0)
        rc = diag.get('reconnectCount', 0)
        dropped = diag.get('droppedBlocks', 0)
        diagLine = (
            f'[诊断] 块率:{bps:.1f}/s  间隔:{intervalMs:.0f}ms  '
            f'块大小:{blkSize:.0f}  速率:{rate:.2f}Mbps  '
            f'队列:{qSize}/{qMax}  总块:{total}  丢弃:{dropped}  重连:{rc}'
        )
        self.logMessage.emit(diagLine)
        if issues:
            self.logMessage.emit(f'[问题] {"  ".join(issues)}')

    def _emitSpectrum(self):
        """发射 LbjCore 已计算的平滑频谱。"""
        if not self.core:
            return
        try:
            data = self.core.spectrumSmoothed.copy()
            self.spectrumUpdated.emit(data)
        except Exception:
            pass

    def _onDecode(self, result: DecodeResult):
        """解码回调：转换为 dict 后发射信号。"""
        d = result.toDict()
        self.trainDecoded.emit(d)

    def stop(self):
        """请求停止 DSP。"""
        if self.core:
            self.core.running = False
        self.requestInterruption()


# ===========================================================================
# 频谱面板
# ===========================================================================
