#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SDR_ALL_LBJ_GUI.py — 基于 RTL-SDR 的中国铁路 LBJ 列车预警器 (PySide6 GUI 版)

作者: BG2GBQ
License: GPL v3

基于 RTL_LBJ_core.py 核心库构建，使用 PySide6 + pyqtgraph 实现 GUI。
支持 OWRX 模式与传统 RTL-TCP 模式，兼容任意 rtl_tcp 协议数据源。
"""

from __future__ import annotations
import sys
import os
import time
import csv
import json
import sqlite3
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import numpy as np

# 核心库
from RTL_LBJ_core import (
    LbjCore, CoreConfig, DecodeResult,
    RTL_SAMPLE_RATE, TCP_HOST, TCP_PORT,
    DEFAULT_BW_KHZ, DEFAULT_RSSI_THRESHOLD_DB, DEFAULT_RSSI_HYST_DB,
    DEFAULT_RSSI_HOLD_MS, DEFAULT_AFC_MAX_HZ, DEFAULT_ETA_MAX_SECONDS,
    HW_GAIN_DB, PPM, BLOCK_SIZE, BASEBAND_RATE,
)
from loco_info import lookup_loco, format_loco_brief

# PySide6
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QUrl
from PySide6.QtGui import QColor, QBrush, QFont, QTextCursor, QIcon, QAction, QPixmap, QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QTabWidget, QGroupBox, QFormLayout, QStatusBar,
    QDialog, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QHeaderView, QMessageBox, QInputDialog, QFrame, QFileDialog, QMenu, QMenuBar,
    QStackedWidget, QScrollArea,
)

# pyqtgraph (使用 PySide6 作为 Qt 后端)
import pyqtgraph as pg

# ---------------------------------------------------------------------------
# pyqtgraph 全局配置
# ---------------------------------------------------------------------------
pg.setConfigOptions(antialias=False, background='#1a1a1a',
                    foreground='#d0d0d0', useOpenGL=False)

# ---------------------------------------------------------------------------
# 暗色主题样式
# ---------------------------------------------------------------------------
DARK_STYLE = """
QMainWindow, QDialog { background-color: #1a1a1a; }
QDialog QWidget { background-color: #1a1a1a; }
QWidget { color: #d0d0d0; background-color: transparent; font-size: 13px; }
QGroupBox {
    border: 1px solid #3a3a3a; border-radius: 4px;
    margin-top: 8px; padding-top: 6px;
    padding-left: 6px; padding-right: 6px; padding-bottom: 4px;
    font-weight: bold;
    background-color: #1e1e1e;
}
QGroupBox::title {
    color: #00cc88; subcontrol-origin: margin;
    left: 10px; padding: 0 5px;
}
QPushButton {
    background-color: #2a2a2a; border: 1px solid #4a4a4a;
    border-radius: 3px; padding: 5px 16px; min-width: 60px;
}
QPushButton:hover { background-color: #3a3a3a; border-color: #00cc88; }
QPushButton:pressed { background-color: #1a1a1a; }
QPushButton:disabled { color: #666; border-color: #333; }
QTableWidget {
    gridline-color: #3a3a3a; background-color: #1e1e1e;
    alternate-background-color: #242424;
    selection-background-color: #005577;
    font-size: 12px;
}
QHeaderView::section {
    background-color: #2a2a2a; border: 1px solid #3a3a3a;
    padding: 4px; font-weight: bold; color: #00cc88;
}
QTextEdit { background-color: #111111; border: 1px solid #3a3a3a;
            font-family: Consolas, monospace; font-size: 12px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #2a2a2a; border: 1px solid #4a4a4a;
    border-radius: 2px; padding: 3px; min-height: 22px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #00cc88; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #1e1e1e; border: 1px solid #3a3a3a;
    selection-background-color: #005577; selection-color: #fff;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; }
QFormLayout { spacing: 4px; }
QLabel { color: #d0d0d0; background-color: transparent; }
QGroupBox QLabel { color: #d0d0d0; }
QMenuBar { background-color: #1a1a1a; border-bottom: 1px solid #3a3a3a; }
QMenuBar::item { padding: 4px 12px; background-color: transparent; }
QMenuBar::item:selected { background-color: #3a3a3a; }
QMenu { background-color: #2a2a2a; border: 1px solid #4a4a4a; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background-color: #3a3a3a; }
QTabWidget::pane { border: 1px solid #3a3a3a; }
QTabBar::tab {
    background-color: #2a2a2a; padding: 6px 16px;
    border: 1px solid #3a3a3a; margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #333; border-bottom: 2px solid #00cc88;
}
QStatusBar { background-color: #111111; border-top: 1px solid #3a3a3a; }
QStatusBar::item { border: none; }
QSplitter::handle { background-color: #333; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QLabel { background-color: transparent; }
"""

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
if getattr(sys, 'frozen', False):
    DATA_DIR = sys._MEIPASS
    USER_DIR = EXE_DIR
else:
    DATA_DIR = SRC_DIR
    USER_DIR = SRC_DIR

CONFIG_PATH = os.path.join(USER_DIR, 'lbj_config.json')
DB_PATH = os.path.join(USER_DIR, 'history.db')
ICON_PATH = os.path.join(DATA_DIR, '国铁.ico')

# 首次运行：从打包模板复制默认配置到用户目录 (如果不存在)
if not os.path.exists(CONFIG_PATH):
    _tmpl = os.path.join(DATA_DIR, 'lbj_config.json') if getattr(sys, 'frozen', False) else None
    if _tmpl and os.path.exists(_tmpl):
        try:
            import shutil
            shutil.copy(_tmpl, CONFIG_PATH)
        except Exception:
            pass

MAX_CURRENT_SECONDS = 600   # 当前列表保留 10 分钟
MAX_LOG_LINES = 500
MAX_HISTORY_ROWS_UI = 1000

CSV_HEADERS = ['时间', '车次', '方向', '速度', '公里标', '机车', '线路', '类别',
               '报文类型', '地址', '功能码', 'BCD', '信号强度', 'AFC', 'FERR', '置信度']


def safeFloat(v, default=None):
    try:
        return float(str(v).replace('KM', '').replace('km', '').strip())
    except Exception:
        return default


# ===========================================================================
# DSP 桥接线程：把 LbjCore 的回调桥接到 Qt 信号
# ===========================================================================
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
class SpectrumPanel(QWidget):
    """实时频谱面板 (pyqtgraph PlotWidget)。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        self.titleLabel = QLabel('实时频谱')
        self.titleLabel.setStyleSheet(
            'color: #00cc88; font-size: 13px; font-weight: bold; padding: 2px;')
        self.titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.titleLabel)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('#1a1a1a')
        # 左侧：幅度(dB)
        self.plot.setLabel('left', '幅度', units='dB')
        # 底部：频率偏移(kHz)
        self.plot.setLabel('bottom', '频率偏移', units='kHz')
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setYRange(-140, 0, padding=0)

        # 隐藏自动缩放按钮，固定视图
        self.plot.getViewBox().setMouseEnabled(x=False, y=False)
        self.plot.getViewBox().setMenuEnabled(False)

        self.curve = self.plot.plot(pen=pg.mkPen('#00cc88', width=2))
        # 用 FillBetweenItem 填充曲线到底部基线
        self._baseline = pg.PlotDataItem([0], [-140])
        self.fill = pg.FillBetweenItem(self.curve, self._baseline,
                                       brush=pg.mkBrush(0, 204, 136, 25))
        self.plot.addItem(self.fill)
        # RSSI 阈值水平线
        self._rssiThresholdDb = DEFAULT_RSSI_THRESHOLD_DB
        self._thresholdLine = pg.InfiniteLine(
            pos=self._rssiThresholdDb, angle=0,
            pen=pg.mkPen('#ff5555', width=1, style=Qt.DashLine))
        self._thresholdLabel = pg.TextItem(
            text=f'阈值 {self._rssiThresholdDb:.0f}dB', color='#ff5555',
            anchor=(1, 1))
        self._thresholdLabel.setPos(0, self._rssiThresholdDb)
        self.plot.addItem(self._thresholdLine)
        self.plot.addItem(self._thresholdLabel)
        layout.addWidget(self.plot)

        self._sampleRate = 960000  # 默认采样率
        self._binCount = 32

    def setSampleRate(self, sr: int):
        """设置采样率，用于计算 X 轴频率刻度。"""
        self._sampleRate = sr
        halfBwKhz = (sr / 2) / 1000.0
        self.plot.setXRange(-halfBwKhz, halfBwKhz, padding=0)

    def setRssiThreshold(self, thresholdDb: float):
        """更新频谱上的 RSSI 阈值标记线。"""
        self._rssiThresholdDb = thresholdDb
        self._thresholdLine.setPos(thresholdDb)
        self._thresholdLabel.setText(f'阈值 {thresholdDb:.0f}dB')
        self._thresholdLabel.setPos(0, thresholdDb)

    def updateSpectrum(self, data: np.ndarray):
        """更新频谱曲线。data 为 32 个 dB 值，对应 -sr/2 ~ +sr/2。"""
        if len(data) == 0:
            return
        n = len(data)
        halfBwKhz = (self._sampleRate / 2) / 1000.0
        # 生成频率偏移数组 (kHz)
        x = np.linspace(-halfBwKhz, halfBwKhz, n)
        self.curve.setData(x=x, y=data)
        # 重新创建填充 (FillBetweenItem 不支持动态更新数据范围)
        self.plot.removeItem(self.fill)
        self._baseline = pg.PlotDataItem([x[0], x[-1]], [-140, -140])
        self.fill = pg.FillBetweenItem(self.curve, self._baseline,
                                       brush=pg.mkBrush(0, 204, 136, 25))
        self.plot.addItem(self.fill)


# ===========================================================================
# 终端风格频谱面板 (仿命令提示符样式，节省资源)
# ===========================================================================
class TerminalSpectrumPanel(QWidget):
    """终端风格频谱面板（仿旧版命令提示符输出样式）。

    使用 QTextEdit + Unicode 块字符 (▂▃▄▅▆▇█) 渲染频谱条形图，
    不依赖 pyqtgraph，渲染开销极低，适合低性能设备或节省 CPU/GPU 资源。
    样式参考旧版 rtl_sdr_lbj_receiver.py 的 _u6() 终端仪表盘渲染函数。
    """

    # 配色 (对应旧版终端 ANSI 配色)
    _C_GREEN = '#00ff66'
    _C_GRAY = '#888888'
    _C_CYAN = '#00cccc'
    _C_RED = '#ff5555'
    _C_YELLOW = '#ffcc00'

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.titleLabel = QLabel('终端频谱 (省资源模式)')
        self.titleLabel.setStyleSheet(
            'color: #00cc88; font-size: 13px; font-weight: bold; padding: 2px;')
        self.titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.titleLabel)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            'QTextEdit { background-color: #0a0a0a; border: 1px solid #3a3a3a; '
            'font-family: Consolas, "Cascadia Mono", "Courier New", monospace; '
            'font-size: 13px; color: #d0d0d0; }')
        layout.addWidget(self.text)

        self._sampleRate = 960000
        self._rssiThresholdDb = DEFAULT_RSSI_THRESHOLD_DB
        self._lastStatus: Dict[str, Any] = {}
        self._lastData = np.full(32, -120.0, dtype=np.float64)
        self._height = 8            # 频谱条形图行数
        self._bins = 32             # 频谱分箱数 (与核心库一致)
        self._lastRenderT = 0.0     # 渲染节流时间戳

    def setSampleRate(self, sr: int):
        """设置采样率（用于状态行显示）。"""
        self._sampleRate = sr

    def setRssiThreshold(self, thresholdDb: float):
        """更新 RSSI 阈值（用于状态行显示）。"""
        self._rssiThresholdDb = thresholdDb

    def updateStatus(self, st: dict):
        """从 getStatus() 更新状态行信息。"""
        self._lastStatus = st
        self._render()

    def updateSpectrum(self, data: np.ndarray):
        """更新频谱数据 (32 个 dB 值) 并重新渲染。"""
        if len(data) > 0:
            self._lastData = np.asarray(data, dtype=np.float64).copy()
        self._render()

    @staticmethod
    def _seg(text: str, color: str = None) -> str:
        """将文本段转为 HTML，空格替换为 &nbsp; 以保留等宽对齐。"""
        safe = text.replace(' ', '&nbsp;')
        if color:
            return f'<span style="color:{color}">{safe}</span>'
        return safe

    def _render(self):
        """渲染频谱条形图与状态行到 QTextEdit。"""
        # 节流: 最多 ~20fps，避免频繁 setHtml
        now = time.time()
        if now - self._lastRenderT < 0.05:
            return
        self._lastRenderT = now

        db_array = self._lastData
        st = self._lastStatus
        height = self._height
        bins = min(len(db_array), self._bins)

        # 动态范围计算 (与旧版 _u6 一致)
        db_max = float(np.max(db_array))
        db_min = float(np.percentile(db_array, 10))
        if db_max - db_min < 20:
            db_max = db_min + 20
        db_range = db_max - db_min

        # 每列映射到 0~(height*8) 的离散等级
        cols_h = [int(max(0.0, min(1.0, (db - db_min) / db_range)) * height * 8)
                  for db in db_array[:bins]]
        chars = [' ', '▂', '▃', '▄', '▅', '▆', '▇', '█']

        html_lines = []

        # ---- 频谱条形图 (从顶到底) ----
        for r in range(height - 1, -1, -1):
            row_db = db_min + (r + 1) * (db_range / height)
            segs = [self._seg(f'{int(row_db):4d}│', self._C_GRAY)]
            for c in range(bins):
                sh = cols_h[c] - r * 8
                if sh >= 8:
                    segs.append(self._seg('█', self._C_GREEN))
                elif sh <= 0:
                    segs.append(self._seg(' '))
                else:
                    segs.append(self._seg(chars[sh], self._C_GREEN))
            html_lines.append(''.join(segs))

        # ---- 底部轴线 ----
        axis = '     └' + '─' * 15 + '┴' + '─' * 16 + '┘'
        html_lines.append(self._seg(axis, self._C_GRAY))

        # ---- 状态行 ----
        freq_mhz = st.get('freqMhz', 0)
        sr_k = st.get('sampleRate', self._sampleRate) // 1000
        gain = st.get('gainDb', 0)
        ppm = st.get('ppm', 0)
        rssi = st.get('rssi', -140)
        thresh = st.get('rssiThreshold', self._rssiThresholdDb)
        gate = st.get('rssiGate', 'OFF')
        afc = st.get('afcHz', 0.0)
        ferr = st.get('afcErrHz', 0.0)
        score = st.get('afcScore', 0.0)
        connected = st.get('connected', False)

        # 频率/增益/PPM/采样率 (青色)
        html_lines.append(self._seg(
            f' ▲ {freq_mhz:.4f}M G:{gain:.1f} P:{ppm} S:{sr_k}k', self._C_CYAN))

        # RSSI/阈值/门控 (高于阈值绿色，否则灰色)
        rssi_color = self._C_GREEN if rssi > thresh else self._C_GRAY
        html_lines.append(self._seg(
            f' RSSI:{rssi:.0f} 阈:{thresh:.0f} RX:{gate}', rssi_color))

        # AFC/FERR/置信度 (偏差大时青色高亮)
        afc_color = self._C_CYAN if (abs(ferr) > 50 or abs(afc) > 50) else self._C_GRAY
        html_lines.append(self._seg(
            f' FERR:{ferr:+.0f} AFC:{afc:+.0f} S:{score:.2f}', afc_color))

        # 连接状态
        conn_color = self._C_GREEN if connected else self._C_RED
        conn_text = '● 已连接' if connected else '● 未连接'
        html_lines.append(self._seg(f' {conn_text}', conn_color))

        html = '<br>'.join(html_lines)
        self.text.setHtml(html)


# ===========================================================================
# 列车信息面板
# ===========================================================================
class TrainInfoPanel(QWidget):
    """实时列车信息显示面板。"""

    def __init__(self):
        super().__init__()
        group = QGroupBox('列车信息')
        grid = QGridLayout(group)
        grid.setSpacing(3)
        grid.setContentsMargins(6, 8, 6, 4)

        self.labels = {}
        fields = [
            ('train', '车次'), ('direction', '方向'), ('speed', '速度'),
            ('position', '公里标'), ('loco', '机车'), ('route', '线路'),
            ('category', '类别'), ('etaTime', '到达时间'), ('etaDistanceKm', '距离'),
            ('currentRouteKmText', '本站'),
        ]
        for i, (key, label) in enumerate(fields):
            r, c = divmod(i, 2)
            lab = QLabel(label)
            lab.setStyleSheet('color: #888; font-size: 12px;')
            val = QLabel('----')
            val.setStyleSheet('color: #d0d0d0; font-size: 15px; font-weight: bold;')
            val.setMinimumWidth(120)
            grid.addWidget(lab, r, c * 2)
            grid.addWidget(val, r, c * 2 + 1)
            self.labels[key] = val

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addWidget(group)

    def updateStatus(self, st: dict):
        """从 getStatus() 字典更新显示。"""
        # train/direction/speed 等需要从最近解码获取，这里只更新可用的
        # 频率/链路/采样率等
        pass

    def updateDecode(self, d: dict):
        """从解码结果更新。"""
        self.labels['train'].setText(str(d.get('train', '----')))
        self.labels['direction'].setText(str(d.get('direction', '未知')))
        spd = d.get('speed', '---')
        self.labels['speed'].setText(f'{spd} km/h' if spd != '---' else '---')
        pos = d.get('position', '---.-')
        self.labels['position'].setText(f'{pos} KM' if pos != '---.-' else '---.-')
        self.labels['loco'].setText(str(d.get('loco', '----')))
        self.labels['route'].setText(str(d.get('route', '----')))
        self.labels['category'].setText(str(d.get('category', '未知')))
        self.labels['etaTime'].setText(str(d.get('etaTime', '--:--:--')))
        dist = d.get('etaDistanceKm')
        self.labels['etaDistanceKm'].setText(f'{dist:.1f} km' if dist is not None else '---')

        # 方向着色
        dirEl = self.labels['direction']
        d_val = d.get('direction', '')
        if d_val == '上行':
            dirEl.setStyleSheet('color: #5599ff; font-size: 15px; font-weight: bold;')
        elif d_val == '下行':
            dirEl.setStyleSheet('color: #00ff66; font-size: 15px; font-weight: bold;')
        else:
            dirEl.setStyleSheet('color: #d0d0d0; font-size: 15px; font-weight: bold;')


# ===========================================================================
# 接收状态面板
# ===========================================================================
class RxStatusPanel(QWidget):
    """接收状态与信号监测面板。"""

    def __init__(self):
        super().__init__()
        group = QGroupBox('接收状态')
        grid = QGridLayout(group)
        grid.setSpacing(2)
        grid.setContentsMargins(6, 8, 6, 4)

        self.labels = {}
        fields = [
            ('rssi', '信号强度'), ('csThreshold', '阈值'), ('rssiGate', 'RX'),
            ('afcHz', 'AFC'), ('afcErrHz', 'FERR'), ('afcScore', '置信度'),
            ('sampleRate', '采样率'), ('connected', '连接'),
        ]
        for i, (key, label) in enumerate(fields):
            r, c = divmod(i, 2)
            lab = QLabel(label)
            lab.setStyleSheet('color: #888; font-size: 11px;')
            val = QLabel('---')
            val.setStyleSheet('color: #d0d0d0; font-size: 12px; font-weight: bold;')
            val.setMinimumWidth(80)
            grid.addWidget(lab, r, c * 2)
            grid.addWidget(val, r, c * 2 + 1)
            self.labels[key] = val

        # 信号建议
        self.adviceLabel = QLabel('等待连接...')
        self.adviceLabel.setStyleSheet('background-color: #2a2a2a; color: #888; '
                                       'padding: 2px; border-radius: 3px; font-size: 11px;')
        grid.addWidget(self.adviceLabel, grid.rowCount(), 0, 1, 4)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addWidget(group)

    def updateStatus(self, st: dict):
        """从 getStatus() 更新。"""
        rssi = st.get('rssi', -140.0)
        thresh = st.get('rssiThreshold', DEFAULT_RSSI_THRESHOLD_DB)
        self.labels['rssi'].setText(f'{rssi:.1f} dB')
        self.labels['csThreshold'].setText(f'{thresh:.1f} dB')
        self.labels['rssiGate'].setText(str(st.get('rssiGate', 'OFF')))
        afc = st.get('afcHz', 0.0)
        self.labels['afcHz'].setText(f'{afc:+.0f} Hz')
        ferr = st.get('afcErrHz', 0.0)
        self.labels['afcErrHz'].setText(f'{ferr:+.0f} Hz')
        score = st.get('afcScore', 0.0)
        self.labels['afcScore'].setText(f'{score:.2f}')
        sr = st.get('sampleRate', 0)
        self.labels['sampleRate'].setText(f'{sr // 1000} kS/s')
        conn = st.get('connected', False)
        self.labels['connected'].setText('已连接' if conn else '未连接')
        self.labels['connected'].setStyleSheet(
            f'color: {"#00ff66" if conn else "#ff5555"}; font-size: 12px; font-weight: bold;')

        # RSSI 颜色
        rssiEl = self.labels['rssi']
        rssiEl.setStyleSheet(
            f'color: {"#00ff66" if rssi > thresh else "#d0d0d0"}; '
            f'font-size: 12px; font-weight: bold;')

        # 信号建议
        self._updateAdvice(st)

    def _updateAdvice(self, st: dict):
        warns = []
        if not st.get('connected', False):
            self.adviceLabel.setStyleSheet('background-color: #3a1a1a; color: #ff5555; '
                                           'padding: 2px; border-radius: 3px; font-size: 11px;')
            self.adviceLabel.setText('● 未连接')
            return
        rssi = st.get('rssi', -140.0)
        thresh = st.get('rssiThreshold', DEFAULT_RSSI_THRESHOLD_DB)
        if rssi < -80:
            warns.append('信号极弱')
        elif rssi < -65:
            warns.append('信号偏弱')
        if abs(st.get('afcErrHz', 0)) > 200:
            warns.append(f'频偏{st["afcErrHz"]:+.0f}Hz')
        if st.get('afcScore', 0) < 0.1 and st.get('rssiGate') == 'ON':
            warns.append('AFC置信度低')
        if not warns:
            self.adviceLabel.setStyleSheet('background-color: #1a2a1a; color: #00ff66; '
                                           'padding: 2px; border-radius: 3px; font-size: 11px;')
            self.adviceLabel.setText('✓ 信号良好')
        else:
            self.adviceLabel.setStyleSheet('background-color: #3a2a00; color: #ffaa00; '
                                           'padding: 2px; border-radius: 3px; font-size: 11px;')
            self.adviceLabel.setText('● ' + '  |  '.join(warns))


# ===========================================================================
# 当前列表面板 (10 分钟内全部解码)
# ===========================================================================
class CurrentPanel(QWidget):
    """当前 10 分钟内的全部解码记录。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.records = []  # [(timestamp, dict), ...]
        self.lock = False

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ['时间', '车次', '方向', '速度', '公里标', '线路', '机车', '类别', '预计到达'])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        self.table.doubleClicked.connect(self._onDoubleClicked)

    def addRecord(self, d: dict):
        """添加一条解码记录。"""
        ts = d.get('timestamp', time.time())
        self.records.append((ts, d))
        # 清理过期
        now = time.time()
        self.records = [(t, r) for t, r in self.records if now - t <= MAX_CURRENT_SECONDS]
        self.refresh()

    def refresh(self):
        """刷新表格显示。"""
        self.lock = True
        self.table.setRowCount(0)
        now = time.time()
        # 倒序：最新在顶部
        for ts, d in reversed(self.records):
            row = self.table.rowCount()
            self.table.insertRow(row)
            timeStr = d.get('timeStr', '').split(' ')[-1] if ' ' in d.get('timeStr', '') else d.get('timeStr', '')
            age = now - ts
            items = [
                timeStr, d.get('train', '----'), d.get('direction', '未知'),
                d.get('speed', '---'), d.get('position', '---.-'),
                d.get('route', '----'), d.get('loco', '----'),
                d.get('category', '未知'), d.get('etaTime', '--:--:--'),
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                # 无车次信息的报文: 整行标红
                isInvalid = (d.get('train', '----') in ('----', '', '未知')
                             and d.get('baseTrain', '----') in ('----', ''))
                if isInvalid:
                    item.setForeground(QColor('#ff5555'))
                elif col == 1:  # 车次加粗
                    f = item.font(); f.setBold(True); item.setFont(f)
                # 方向着色
                if col == 2 and not isInvalid:
                    if text == '下行':
                        item.setForeground(QColor('#00ff66'))
                    elif text == '上行':
                        item.setForeground(QColor('#5599ff'))
                # 过期变暗
                if age > 180 and not isInvalid:
                    item.setForeground(QColor('#666'))
                self.table.setItem(row, col, item)
        self.lock = False

    def _onDoubleClicked(self, index):
        """双击当前列表行，弹出详情对话框。"""
        row = index.row()
        if row < 0:
            return
        # records 是正序列表，表格是倒序显示，需反转索引
        actual = len(self.records) - 1 - row
        if actual < 0 or actual >= len(self.records):
            return
        _, d = self.records[actual]
        dlg = RecordDetailDialog(d, self)
        dlg.exec()


# ===========================================================================
# 历史记录数据库 (SQLite)
# ===========================================================================
class HistoryDb:
    """SQLite 历史记录数据库管理。

    保存完整的解码结果（含原始码字 rawCodewords），支持从原始数据重新解码。
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        timeStr TEXT,
        train TEXT,
        baseTrain TEXT,
        prefix TEXT,
        direction TEXT,
        speed TEXT,
        position TEXT,
        loco TEXT,
        locoCode TEXT,
        route TEXT,
        category TEXT,
        isDetailed INTEGER,
        routeValid INTEGER,
        msgTypeError INTEGER,
        rawAddr INTEGER,
        rawFunc INTEGER,
        rawBcd TEXT,
        rawCodewords TEXT,
        rawIsShort INTEGER,
        rawIsMerged INTEGER,
        rawIsStandalone INTEGER,
        rssi REAL,
        afcHz REAL,
        afcErrHz REAL,
        afcScore REAL,
        etaSeconds REAL,
        etaTime TEXT,
        etaDistanceKm REAL,
        etaStatus TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_time ON records(timestamp);
    CREATE INDEX IF NOT EXISTS idx_train ON records(train);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initDb()

    def _initDb(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self._CREATE_SQL)

    def insert(self, d: dict) -> bool:
        """插入一条解码记录。"""
        sql = """
        INSERT INTO records (
            timestamp, timeStr, train, baseTrain, prefix, direction, speed, position,
            loco, locoCode, route, category, isDetailed, routeValid, msgTypeError,
            rawAddr, rawFunc, rawBcd, rawCodewords, rawIsShort, rawIsMerged, rawIsStandalone,
            rssi, afcHz, afcErrHz, afcScore, etaSeconds, etaTime, etaDistanceKm, etaStatus
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(sql, (
                    d.get('timestamp', 0.0), d.get('timeStr', ''), d.get('train', ''),
                    d.get('baseTrain', ''), d.get('prefix', ''), d.get('direction', ''),
                    d.get('speed', ''), d.get('position', ''), d.get('loco', ''),
                    d.get('locoCode', ''), d.get('route', ''), d.get('category', ''),
                    int(d.get('isDetailed', False)), int(d.get('routeValid', False)),
                    int(d.get('msgTypeError', False)), d.get('rawAddr', 0),
                    d.get('rawFunc', 0), d.get('rawBcd', ''),
                    json.dumps(d.get('rawCodewords', [])),
                    int(d.get('rawIsShort', False)), int(d.get('rawIsMerged', False)),
                    int(d.get('rawIsStandalone', False)), d.get('rssi', -140.0),
                    d.get('afcHz', 0.0), d.get('afcErrHz', 0.0), d.get('afcScore', 0.0),
                    d.get('etaSeconds', None), d.get('etaTime', '--:--:--'),
                    d.get('etaDistanceKm', None), d.get('etaStatus', '等待信号'),
                ))
            return True
        except Exception:
            return False

    def queryRecent(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """查询最近的记录（含 id 供详情查询）。"""
        sql = """
        SELECT id, timeStr, train, direction, speed, position, route, loco, category,
               isDetailed, rawBcd, rawAddr, rawFunc
        FROM records ORDER BY id DESC LIMIT ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            return []

    def queryAll(self) -> List[Dict[str, Any]]:
        """查询所有记录（含原始数据）。"""
        sql = "SELECT * FROM records ORDER BY id DESC"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql)
                rows = []
                for row in cur.fetchall():
                    d = dict(row)
                    d['rawCodewords'] = json.loads(d.get('rawCodewords', '[]'))
                    d['isDetailed'] = bool(d.get('isDetailed', 0))
                    d['routeValid'] = bool(d.get('routeValid', 0))
                    d['msgTypeError'] = bool(d.get('msgTypeError', 0))
                    d['rawIsShort'] = bool(d.get('rawIsShort', 0))
                    d['rawIsMerged'] = bool(d.get('rawIsMerged', 0))
                    d['rawIsStandalone'] = bool(d.get('rawIsStandalone', 0))
                    rows.append(d)
                return rows
        except Exception:
            return []

    def count(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                return conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        except Exception:
            return 0

    def queryById(self, record_id: int) -> Optional[Dict[str, Any]]:
        """按 id 查询单条完整记录（含原始数据）。"""
        sql = "SELECT * FROM records WHERE id = ?"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, (record_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                d = dict(row)
                d['rawCodewords'] = json.loads(d.get('rawCodewords', '[]'))
                d['isDetailed'] = bool(d.get('isDetailed', 0))
                d['routeValid'] = bool(d.get('routeValid', 0))
                d['msgTypeError'] = bool(d.get('msgTypeError', 0))
                d['rawIsShort'] = bool(d.get('rawIsShort', 0))
                d['rawIsMerged'] = bool(d.get('rawIsMerged', 0))
                d['rawIsStandalone'] = bool(d.get('rawIsStandalone', 0))
                return d
        except Exception:
            return None

    def clear(self) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM records")
                conn.execute("VACUUM")
            return True
        except Exception:
            return False

    def exportToCsv(self, path: str) -> bool:
        """导出为 CSV（兼容旧格式）。"""
        headers = ['时间', '车次', '方向', '速度', '公里标', '机车', '线路', '类别',
                   '报文类型', '地址', '功能码', 'BCD', '信号强度', 'AFC', 'FERR', '置信度']
        try:
            rows = self.queryAll()
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([
                        r.get('timeStr', ''), r.get('train', ''), r.get('direction', ''),
                        r.get('speed', ''), r.get('position', ''), r.get('loco', ''),
                        r.get('route', ''), r.get('category', ''),
                        '详细' if r.get('isDetailed') else '短报文',
                        r.get('rawAddr', ''), r.get('rawFunc', ''), r.get('rawBcd', ''),
                        r.get('rssi', ''), r.get('afcHz', ''), r.get('afcErrHz', ''),
                        r.get('afcScore', ''),
                    ])
            return True
        except Exception:
            return False


# ===========================================================================
# 机车详情对话框 (显示图片 + 详细信息 + 来源标注)
# ===========================================================================
class LocoDetailDialog(QDialog):
    """机车详情对话框：展示机车图片、技术参数和来源标注。

    图片与数据来源: Trainfanz.com (我们的火车站)
    """

    def __init__(self, loco_info: Optional[dict], loco_number: str = '', parent=None):
        super().__init__(parent)
        name = loco_info.get('name', '') if loco_info else loco_number
        self.setWindowTitle(f'机车详情 — {name}')
        self.setMinimumSize(560, 520)
        self.resize(640, 640)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)

        self._loco_info = loco_info or {}
        self._nam: Optional[QNetworkAccessManager] = None
        self._reply: Optional[QNetworkReply] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ===== 1. 标题 =====
        titleLabel = QLabel(name or '未知机车')
        titleLabel.setStyleSheet('color: #00cc88; font-size: 18px; font-weight: bold;')
        titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titleLabel)

        # ===== 2. 图片区域 =====
        self._imageLabel = QLabel('图片加载中...')
        self._imageLabel.setAlignment(Qt.AlignCenter)
        self._imageLabel.setMinimumHeight(260)
        self._imageLabel.setStyleSheet(
            'color: #888; font-size: 12px; '
            'background-color: #111111; border: 1px solid #3a3a3a; border-radius: 4px;')
        layout.addWidget(self._imageLabel)

        # ===== 3. 技术参数 (2 列网格) =====
        infoGroup = QGroupBox('技术参数')
        infoGrid = QGridLayout(infoGroup)
        infoGrid.setSpacing(4)
        infoGrid.setContentsMargins(8, 16, 8, 4)

        info_items = [
            ('机型名称', self._loco_info.get('name', '—')),
            ('机车类型', self._loco_info.get('type', '—')),
            ('制造厂商', self._loco_info.get('maker', '—')),
            ('轴式', self._loco_info.get('axle', '—')),
            ('功率', self._loco_info.get('power', '—')),
            ('最高速度', self._loco_info.get('speed', '—')),
        ]
        for i, (k, v) in enumerate(info_items):
            r, c = divmod(i, 2)
            lab = QLabel(f'{k}:')
            lab.setStyleSheet('color: #00cc88; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet('color: #d0d0d0; font-size: 12px;')
            val.setWordWrap(True)
            infoGrid.addWidget(lab, r, c * 2)
            infoGrid.addWidget(val, r, c * 2 + 1)

        brief = self._loco_info.get('brief', '')
        if brief:
            briefLab = QLabel('简介:')
            briefLab.setStyleSheet('color: #00cc88; font-weight: bold; font-size: 12px;')
            briefVal = QLabel(brief)
            briefVal.setStyleSheet('color: #d0d0d0; font-size: 12px;')
            briefVal.setWordWrap(True)
            infoGrid.addWidget(briefLab, 3, 0)
            infoGrid.addWidget(briefVal, 3, 1, 1, 3)

        layout.addWidget(infoGroup)

        # ===== 4. 来源标注 =====
        sourceBox = QFrame()
        sourceBox.setStyleSheet(
            'QFrame { background-color: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; }')
        sourceLayout = QHBoxLayout(sourceBox)
        sourceLayout.setContentsMargins(8, 6, 8, 6)
        sourceIcon = QLabel('📷')
        sourceIcon.setStyleSheet('font-size: 14px; border: none; background: transparent;')
        sourceText = QLabel(
            f'<span style="color:#aaa;">图片与数据来源:</span> '
            f'<a href="{self._loco_info.get("sourceUrl", "")}" '
            f'style="color:#5599ff; text-decoration:none;">'
            f'{self._loco_info.get("source", "Trainfanz.com (我们的火车站)")}</a>')
        sourceText.setOpenExternalLinks(True)
        sourceText.setStyleSheet('font-size: 11px; border: none; background: transparent;')
        sourceLayout.addWidget(sourceIcon)
        sourceLayout.addWidget(sourceText)
        sourceLayout.addStretch()
        layout.addWidget(sourceBox)

        # ===== 按钮 =====
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)

        # 启动图片加载
        self._loadImage()

    def _loadImage(self):
        """异步加载机车图片。"""
        url = self._loco_info.get('imageUrl', '')
        if not url:
            self._imageLabel.setText('暂无该机型图片')
            return
        try:
            self._nam = QNetworkAccessManager(self)
            req = QNetworkRequest(QUrl(url))
            req.setHeader(QNetworkRequest.UserAgentHeader,
                          'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            self._reply = self._nam.get(req)
            self._reply.finished.connect(self._onImageLoaded)
        except Exception as e:
            self._imageLabel.setText(f'图片加载失败: {e}')

    def _onImageLoaded(self):
        """图片下载完成回调。"""
        if not self._reply:
            return
        try:
            if self._reply.error() != QNetworkReply.NoError:
                self._imageLabel.setText('图片加载失败 (网络错误)')
                return
            data = self._reply.readAll()
            if not data:
                self._imageLabel.setText('图片数据为空')
                return
            img = QImage()
            if img.loadFromData(data):
                # 等比缩放至合适尺寸
                scaled = img.scaled(
                    580, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._imageLabel.setPixmap(QPixmap.fromImage(scaled))
                self._imageLabel.setText('')
            else:
                self._imageLabel.setText('图片解析失败')
        except Exception as e:
            self._imageLabel.setText(f'图片显示失败: {e}')
        finally:
            self._reply.deleteLater()
            self._reply = None


# ===========================================================================
# 记录详情对话框 (双击历史/当前列表弹出)
# ===========================================================================
class RecordDetailDialog(QDialog):
    """展示单条记录的完整解码结果、原始数据和解码过程推演。"""

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        train = record.get('train', '----')
        time_str = record.get('timeStr', record.get('time', ''))
        self.setWindowTitle(f'记录详情 — {train} ({time_str})')
        self.setMinimumSize(720, 640)
        self.resize(820, 720)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # ===== 1. 解码结果 (2 列网格) =====
        resultGroup = QGroupBox('解码结果')
        resultGrid = QGridLayout(resultGroup)
        resultGrid.setSpacing(4)
        resultGrid.setContentsMargins(8, 16, 8, 4)

        func_str = self._funcLabel(record.get('rawFunc', record.get('raw_func', 0)))
        msg_type = self._msgTypeLabel(record)

        # 机车信息
        loco_number = record.get('loco', '')
        loco_code = record.get('locoCode', record.get('loco_code', ''))
        loco_info = lookup_loco(loco_code=loco_code, loco_number=loco_number)

        result_items = [
            ('时间', record.get('timeStr', record.get('time', ''))),
            ('车次', record.get('train', '----')),
            ('纯数字车次', record.get('baseTrain', '----')),
            ('前缀', record.get('prefix', '') or '无'),
            ('方向', record.get('direction', '未知')),
            ('速度', f"{record.get('speed', '---')} km/h"),
            ('公里标', f"{record.get('position', '---.-')} km"),
            ('机车号', loco_number or '----'),
            ('机车代号', loco_code or '---'),
            ('线路', record.get('route', '----')),
            ('类别', record.get('category', '未知')),
            ('报文类型', msg_type),
            ('线路校验', '通过' if record.get('routeValid', record.get('route_valid', False)) else '未通过'),
            ('BCH纠错', '有错误' if record.get('msgTypeError', False) else '正常'),
            ('预计到达', record.get('etaTime', record.get('eta_time', '--:--:--'))),
            ('预计距离', f"{record.get('etaDistanceKm', record.get('eta_distance_km', '---'))} km"
             if record.get('etaDistanceKm', record.get('eta_distance_km')) else '---'),
        ]
        for i, (k, v) in enumerate(result_items):
            r, c = divmod(i, 2)
            lab = QLabel(f'{k}:')
            lab.setStyleSheet('color: #00cc88; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet('color: #d0d0d0; font-size: 12px;')
            val.setWordWrap(True)
            resultGrid.addWidget(lab, r, c * 2)
            resultGrid.addWidget(val, r, c * 2 + 1)

        # 机车简介（左侧文字 + 右侧"机车详情"按钮，类似 12306 时刻表按钮）
        loco_row = (len(result_items) + 1) // 2
        loco_intro = QLabel('机车简介:')
        loco_intro.setStyleSheet('color: #00cc88; font-weight: bold; font-size: 12px;')
        self._locoIntroLabel = QLabel('')
        self._locoIntroLabel.setStyleSheet(
            'color: #d0d0d0; font-size: 11px; padding: 3px; '
            'background-color: #1a1a1a; border-radius: 3px;')
        self._locoIntroLabel.setWordWrap(True)
        self._locoInfoData: Optional[dict] = loco_info
        self._locoNumberStr = loco_number or ''
        if loco_info:
            self._locoIntroLabel.setText(
                f"{loco_info.get('name', '')}  |  {loco_info.get('type', '')}  |  "
                f"{loco_info.get('power', '')}  |  {loco_info.get('speed', '')}\n"
                f"{loco_info.get('brief', '')}"
            )
        else:
            self._locoIntroLabel.setText('暂无该车型资料')
        # 机车详情按钮 (双击效果: 弹出图片+详细信息)
        self._locoDetailBtn = QPushButton('机车详情')
        self._locoDetailBtn.setStyleSheet(
            'background-color: #005577; color: #fff; font-size: 10px; padding: 1px 4px;')
        self._locoDetailBtn.setEnabled(bool(loco_info))
        self._locoDetailBtn.clicked.connect(self._openLocoDetail)
        resultGrid.addWidget(loco_intro, loco_row, 0)
        resultGrid.addWidget(self._locoIntroLabel, loco_row, 1, 1, 2)
        resultGrid.addWidget(self._locoDetailBtn, loco_row, 3)

        # 12306 查询结果（仅详细报文查询，放在机车简介下一行）
        row = loco_row + 1
        self._trainQueryLabel = QLabel('12306: 查询中...')
        self._trainQueryLabel.setStyleSheet(
            'color: #5599ff; font-size: 11px; font-weight: bold; padding: 2px;')
        self._trainQueryLabel.setWordWrap(True)
        self._trainQueryBtn = QPushButton('时刻表')
        self._trainQueryBtn.setStyleSheet(
            'background-color: #005577; color: #fff; font-size: 10px; padding: 1px 4px;')
        self._trainQueryBtn.setEnabled(False)
        self._trainQueryData: Optional[dict] = None
        self._trainQueryBtn.clicked.connect(self._openTrainQueryResult)
        resultGrid.addWidget(QLabel('12306:'), row, 0)
        resultGrid.addWidget(self._trainQueryLabel, row, 1, 1, 2)
        resultGrid.addWidget(self._trainQueryBtn, row, 3)

        layout.addWidget(resultGroup)

        # 启动 12306 后台查询（仅详细报文）
        if record.get('isDetailed'):
            self._startTrainQuery(record)
        else:
            self._trainQueryLabel.setText('非详细报文，不查询')
            self._trainQueryLabel.setStyleSheet('color: #888; font-size: 11px;')

        # ===== 2. 原始数据 (2 列网格) =====
        rawGroup = QGroupBox('原始数据')
        rawGrid = QGridLayout(rawGroup)
        rawGrid.setSpacing(4)
        rawGrid.setContentsMargins(8, 16, 8, 4)

        rssi_val = record.get('rssi', record.get('rssi', -140.0))
        afc_hz = record.get('afcHz', record.get('afc_hz', 0.0))
        ferr = record.get('afcErrHz', record.get('afc_err_hz', 0.0))
        score = record.get('afcScore', record.get('afc_score', 0.0))
        raw_addr = record.get('rawAddr', record.get('raw_addr', 0))
        raw_func = record.get('rawFunc', record.get('raw_func', 0))

        raw_items = [
            ('报文地址', str(raw_addr)),
            ('功能码', func_str),
            ('信号强度', f"{rssi_val:.1f} dB" if isinstance(rssi_val, (int, float)) else str(rssi_val)),
            ('AFC补偿', f"{afc_hz:+.0f} Hz" if isinstance(afc_hz, (int, float)) else str(afc_hz)),
            ('频率误差', f"{ferr:+.0f} Hz" if isinstance(ferr, (int, float)) else str(ferr)),
            ('AFC置信度', f"{score:.2f}" if isinstance(score, (int, float)) else str(score)),
            ('短报文', '是' if record.get('rawIsShort', False) else '否'),
            ('合并报文', '是' if record.get('rawIsMerged', False) else '否'),
            ('独立长报文', '是' if record.get('rawIsStandalone', False) else '否'),
            ('到达状态', record.get('etaStatus', record.get('eta_status', '等待信号'))),
        ]
        for i, (k, v) in enumerate(raw_items):
            r, c = divmod(i, 2)
            lab = QLabel(f'{k}:')
            lab.setStyleSheet('color: #ffaa00; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet('color: #d0d0d0; font-size: 12px;')
            rawGrid.addWidget(lab, r, c * 2)
            rawGrid.addWidget(val, r, c * 2 + 1)

        layout.addWidget(rawGroup)

        # ===== 3. BCD 原始数据 =====
        bcdGroup = QGroupBox('BCD 原始数据')
        bcdLayout = QVBoxLayout(bcdGroup)
        bcdLayout.setContentsMargins(8, 16, 8, 4)
        bcdText = QTextEdit()
        bcdText.setReadOnly(True)
        bcdText.setStyleSheet(
            'font-family: Consolas, "Courier New", monospace; font-size: 12px; '
            'background-color: #0d0d0d; color: #00ff66; border: 1px solid #3a3a3a;')
        bcdText.setMaximumHeight(120)
        bcd_raw = record.get('rawBcd', record.get('raw_bcd', ''))
        if bcd_raw:
            lines = [bcd_raw[i:i + 10] for i in range(0, len(bcd_raw), 10)]
            bcd_display = f'长度: {len(bcd_raw)} 字符\n\n' + \
                '\n'.join(f'{i * 10:4d}: {line}' for i, line in enumerate(lines))
            bcdText.setPlainText(bcd_display)
        else:
            bcdText.setPlainText('（无 BCD 数据）')
        bcdLayout.addWidget(bcdText)
        layout.addWidget(bcdGroup)

        # ===== 4. 解码过程推演 =====
        procGroup = QGroupBox('解码过程推演')
        procLayout = QVBoxLayout(procGroup)
        procLayout.setContentsMargins(8, 16, 8, 4)
        procText = QTextEdit()
        procText.setReadOnly(True)
        procText.setStyleSheet(
            'font-family: Consolas, "Courier New", monospace; font-size: 11px; '
            'background-color: #0d0d0d; color: #aaaacc; border: 1px solid #3a3a3a;')
        procText.setPlainText(self._buildDecodeProcess(record))
        procLayout.addWidget(procText)
        layout.addWidget(procGroup)

        # ===== 5. 码字列表 =====
        codewords = record.get('rawCodewords', [])
        if codewords:
            cwGroup = QGroupBox(f'纠错后码字 ({len(codewords)} 个)')
            cwLayout = QVBoxLayout(cwGroup)
            cwLayout.setContentsMargins(8, 16, 8, 4)
            cwText = QTextEdit()
            cwText.setReadOnly(True)
            cwText.setStyleSheet(
                'font-family: Consolas, "Courier New", monospace; font-size: 11px; '
                'background-color: #0d0d0d; color: #ffaa44; border: 1px solid #3a3a3a;')
            cwText.setMaximumHeight(100)
            cw_lines = []
            for i, cw in enumerate(codewords):
                cw_bin = format(cw, '031b') if isinstance(cw, int) else str(cw)
                cw_lines.append(f'  [{i:2d}] {cw_bin}  (0x{cw:08X})' if isinstance(cw, int) else f'  [{i:2d}] {cw}')
            cwText.setPlainText('\n'.join(cw_lines))
            cwLayout.addWidget(cwText)
            layout.addWidget(cwGroup)

        # ===== 按钮 =====
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)

    def _startTrainQuery(self, record: dict):
        """启动后台 12306 查询。"""
        train = record.get('train', '')
        if not train or train == '----':
            self._trainQueryLabel.setText('无车次')
            self._trainQueryLabel.setStyleSheet('color: #888; font-size: 11px;')
            return
        dateStr = record.get('timeStr', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))[:10].replace('-', '')
        if len(dateStr) != 8:
            dateStr = datetime.now().strftime('%Y%m%d')
        self._worker = TrainQueryWorker(train, dateStr)
        self._worker.resultReady.connect(self._onTrainQueryResult)
        self._worker.queryFailed.connect(self._onTrainQueryFailed)
        self._worker.start()

    def _onTrainQueryResult(self, data: dict):
        self._trainQueryData = data
        code = data.get('trainCode', '')
        startSt = data.get('startStation', '')
        endSt = data.get('endStation', '')
        startTime = data.get('startTime', '')
        endTime = data.get('endTime', '')
        stations = data.get('stations', [])
        text = f'{startSt}({startTime}) → {code} → {endSt}({endTime})'
        self._trainQueryLabel.setText(text)
        self._trainQueryLabel.setStyleSheet(
            'color: #00cc88; font-size: 11px; font-weight: bold; padding: 2px;')
        self._trainQueryBtn.setEnabled(True)

    def _onTrainQueryFailed(self, err: str):
        if '网络' in err or 'URLError' in err:
            self._trainQueryLabel.setText('此功能需连接互联网使用')
            self._trainQueryLabel.setStyleSheet('color: #ff5555; font-size: 11px;')
        else:
            self._trainQueryLabel.setText(err)
            self._trainQueryLabel.setStyleSheet('color: #ffaa00; font-size: 11px;')

    def _openTrainQueryResult(self):
        if self._trainQueryData:
            dlg = TimetableDialog(self._trainQueryData, self)
            dlg.exec()

    def _openLocoDetail(self):
        """弹出机车详情对话框 (图片+信息+来源标注)。"""
        dlg = LocoDetailDialog(self._locoInfoData, self._locoNumberStr, self)
        dlg.exec()

    def _funcLabel(self, func: int) -> str:
        """功能码转中文标签。"""
        if func == 1:
            return '下行 (1)'
        elif func == 3:
            return '上行 (3)'
        return str(func)

    def _msgTypeLabel(self, record: dict) -> str:
        """报文类型标签。"""
        if record.get('isDetailed'):
            return '详细报文'
        if record.get('rawIsMerged'):
            return '合并报文'
        if record.get('rawIsStandalone'):
            return '独立长报文'
        if record.get('rawIsShort'):
            return '短报文'
        return '未知'

    def _buildDecodeProcess(self, record: dict) -> str:
        """根据记录字段推演解码过程说明。"""
        lines = []
        addr = record.get('rawAddr', record.get('raw_addr', 0))
        func = record.get('rawFunc', record.get('raw_func', 0))
        bcd = record.get('rawBcd', record.get('raw_bcd', ''))
        is_detailed = record.get('isDetailed', False)
        is_short = record.get('rawIsShort', False)
        is_merged = record.get('rawIsMerged', False)
        is_standalone = record.get('rawIsStandalone', False)
        train = record.get('train', '----')
        direction = record.get('direction', '未知')
        speed = record.get('speed', '---')
        position = record.get('position', '---.-')
        loco = record.get('loco', '----')
        route = record.get('route', '----')
        rssi = record.get('rssi', -140.0)
        afc_err = record.get('afcErrHz', record.get('afc_err_hz', 0.0))
        bch_err = record.get('msgTypeError', False)

        lines.append('=== 1. 接收与信号检测 ===')
        lines.append(f'  信号强度 RSSI = {rssi:.1f} dB')
        lines.append(f'  AFC 频偏估计 = {afc_err:+.0f} Hz')
        if rssi > -55:
            lines.append(f'  → RSSI 超过阈值，触发接收门控')
        else:
            lines.append(f'  → RSSI 低于阈值，信号微弱但已捕获')

        lines.append('')
        lines.append('=== 2. DPLL 比特恢复 ===')
        lines.append(f'  从 IQ 基带流中恢复比特序列')
        lines.append(f'  波特率: 1200 bps, 基带采样率: 48000 Hz')
        lines.append(f'  每比特采样数: {48000 // 1200} samples/bit')

        lines.append('')
        lines.append('=== 3. 帧同步 ===')
        lines.append(f'  搜索 LBJ 帧同步字 (18 bit 地址 + 2 bit 功能码)')
        lines.append(f'  地址码: {addr} (0x{addr:05X})')
        lines.append(f'  功能码: {func} ({self._funcLabel(func)})')

        lines.append('')
        lines.append('=== 4. BCH(31,21) 译码 ===')
        if bch_err:
            lines.append(f'  ⚠ BCH 译码检测到不可纠错位')
            lines.append(f'  码字可能存在错误，解码结果仅供参考')
        else:
            lines.append(f'  ✓ BCH 译码通过，最多纠正 2 bit 错误')
        codewords = record.get('rawCodewords', [])
        lines.append(f'  码字数: {len(codewords)}')

        lines.append('')
        lines.append('=== 5. BCD 数据提取 ===')
        if bcd:
            lines.append(f'  BCD 字符串长度: {len(bcd)} 字符')
            lines.append(f'  BCD 内容: {bcd[:60]}{"..." if len(bcd) > 60 else ""}')
        else:
            lines.append(f'  （无 BCD 数据）')

        lines.append('')
        lines.append('=== 6. 报文类型判断 ===')
        if is_short:
            lines.append(f'  → 短报文 (仅含车次、方向)')
        elif is_merged:
            lines.append(f'  → 合并报文 (短报文 + 后续详细数据)')
        elif is_standalone:
            lines.append(f'  → 独立长报文 (单次发送完整数据)')
        elif is_detailed:
            lines.append(f'  → 详细报文 (含机车、线路、公里标等)')
        else:
            lines.append(f'  → 报文类型未确定')

        lines.append('')
        lines.append('=== 7. 字段解析 ===')
        lines.append(f'  车次号: {train}')
        lines.append(f'  方向:   {direction}')
        if speed != '---':
            lines.append(f'  速度:   {speed} km/h')
        if position != '---.-':
            lines.append(f'  公里标: {position} km')
        if loco != '----':
            lines.append(f'  机车:   {loco}')
        if route != '----':
            lines.append(f'  线路:   {route}')

        lines.append('')
        lines.append('=== 完成 ===')
        return '\n'.join(lines)


# ===========================================================================
# 历史记录面板
# ===========================================================================
class HistoryPanel(QWidget):
    """历史记录面板：从 SQLite 数据库读取并显示。"""

    def __init__(self):
        super().__init__()
        self.db = HistoryDb(DB_PATH)
        self._rowIds = []  # 每行对应的数据库 id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        self.refreshBtn = QPushButton('刷新')
        self.clearBtn = QPushButton('清空')
        self.exportBtn = QPushButton('导出 CSV...')
        self.countLabel = QLabel('0 条')
        self.countLabel.setStyleSheet('color: #888;')
        toolbar.addWidget(self.refreshBtn)
        toolbar.addWidget(self.clearBtn)
        toolbar.addWidget(self.exportBtn)
        toolbar.addStretch()
        toolbar.addWidget(self.countLabel)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ['时间', '车次', '方向', '速度', '公里标', '线路', '机车', '类别', '报文', 'BCD'])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self.refreshBtn.clicked.connect(self.loadFromDb)
        self.clearBtn.clicked.connect(self.clearDb)
        self.exportBtn.clicked.connect(self.exportCsv)
        self.table.doubleClicked.connect(self._onDoubleClicked)

    def addRecord(self, d: dict):
        """添加记录到 SQLite 数据库 (不影响表格显示)。"""
        self.db.insert(d)

    def loadFromDb(self):
        """从 SQLite 加载历史记录到表格。"""
        self.table.setRowCount(0)
        self._rowIds = []
        try:
            rows = self.db.queryRecent(MAX_HISTORY_ROWS_UI)
            for r in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._rowIds.append(r.get('id', 0))
                vals = [
                    r.get('timeStr', ''), r.get('train', ''), r.get('direction', ''),
                    r.get('speed', ''), r.get('position', ''), r.get('route', ''),
                    r.get('loco', ''), r.get('category', ''),
                    '详细' if r.get('isDetailed') else '短报文',
                    r.get('rawBcd', ''),
                ]
                for col, val in enumerate(vals):
                    item = QTableWidgetItem(str(val))
                    if col == 1:
                        f = item.font(); f.setBold(True); item.setFont(f)
                    if col == 2:
                        if val == '下行':
                            item.setForeground(QColor('#00ff66'))
                        elif val == '上行':
                            item.setForeground(QColor('#5599ff'))
                    self.table.setItem(row, col, item)
            self.countLabel.setText(f'{self.table.rowCount()} 条 / 共 {self.db.count()} 条')
        except Exception as e:
            QMessageBox.warning(self, '错误', f'读取数据库失败: {e}')

    def _onDoubleClicked(self, index):
        """双击历史记录行，弹出详情对话框。"""
        row = index.row()
        if row < 0 or row >= len(self._rowIds):
            return
        record_id = self._rowIds[row]
        record = self.db.queryById(record_id)
        if record is None:
            QMessageBox.warning(self, '错误', '无法读取该记录')
            return
        dlg = RecordDetailDialog(record, self)
        dlg.exec()

    def clearDb(self):
        ret = QMessageBox.question(self, '确认', '确定要清空历史数据库吗？')
        if ret != QMessageBox.Yes:
            return
        if self.db.clear():
            self.loadFromDb()
            QMessageBox.information(self, '成功', '已清空历史数据库')
        else:
            QMessageBox.warning(self, '错误', '清空失败')

    def exportCsv(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', 'lbj_history.csv',
                                              'CSV Files (*.csv)')
        if not path:
            return
        if self.db.exportToCsv(path):
            QMessageBox.information(self, '成功', f'已导出到 {path}')
        else:
            QMessageBox.warning(self, '错误', '导出失败')


# ===========================================================================
# 配置面板
# ===========================================================================
class ConfigPanel(QWidget):
    """配置面板：基于 CoreConfig 编辑，分组 2 列网格布局。"""

    configChanged = Signal()

    def __init__(self, config: CoreConfig):
        super().__init__()
        self.config = config
        self._updating_mode = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)

        # ---- 顶部：连接设置 + 射频设置 (2 列) ----
        topGrid = QGridLayout()
        topGrid.setSpacing(6)
        topGrid.setColumnStretch(0, 1)
        topGrid.setColumnStretch(1, 1)

        # 连接设置
        connGroup = QGroupBox('连接设置')
        connForm = QFormLayout(connGroup)
        connForm.setSpacing(4)
        connForm.setContentsMargins(8, 16, 8, 4)

        self.hostEdit = QLineEdit(config.host)
        self.portSpin = QSpinBox()
        self.portSpin.setRange(1, 65535)
        self.portSpin.setValue(config.port)

        self.srCombo = QComboBox()
        for sr in [480000, 960000, 1920000, 2048000, 2400000, 2880000]:
            self.srCombo.addItem(f'{sr // 1000} kS/s', sr)
        idx = self.srCombo.findData(config.sampleRate)
        if idx >= 0:
            self.srCombo.setCurrentIndex(idx)
        else:
            self.srCombo.addItem(f'{config.sampleRate // 1000} kS/s', config.sampleRate)
            self.srCombo.setCurrentIndex(self.srCombo.count() - 1)

        self.blockSpin = QSpinBox()
        self.blockSpin.setRange(1024, 262144)
        self.blockSpin.setSingleStep(1024)
        self.blockSpin.setValue(config.blockSize)

        self.modeCombo = QComboBox()
        self.modeCombo.addItem('OWRX 模式', True)
        self.modeCombo.addItem('传统 RTL-TCP 模式', False)
        self.modeCombo.setCurrentIndex(0 if config.owrxMode else 1)
        self.modeCombo.currentIndexChanged.connect(self._onModeChanged)

        self.dcSpin = QDoubleSpinBox()
        self.dcSpin.setRange(-500000, 500000)
        self.dcSpin.setDecimals(0)
        self.dcSpin.setSuffix(' Hz')
        self.dcSpin.setValue(config.dcOffsetHz)

        connForm.addRow('主机:', self.hostEdit)
        connForm.addRow('端口:', self.portSpin)
        connForm.addRow('采样率:', self.srCombo)
        connForm.addRow('块大小:', self.blockSpin)
        connForm.addRow('模式:', self.modeCombo)
        connForm.addRow('DC 偏移:', self.dcSpin)

        topGrid.addWidget(connGroup, 0, 0)

        # 射频设置
        rfGroup = QGroupBox('射频设置')
        rfForm = QFormLayout(rfGroup)
        rfForm.setSpacing(4)
        rfForm.setContentsMargins(8, 16, 8, 4)

        self.freqSpin = QDoubleSpinBox()
        self.freqSpin.setRange(0.1, 3000.0)
        self.freqSpin.setDecimals(4)
        self.freqSpin.setSuffix(' MHz')
        self.freqSpin.setValue(config.freqMhz)

        self.gainSpin = QDoubleSpinBox()
        self.gainSpin.setRange(0.0, 50.0)
        self.gainSpin.setDecimals(1)
        self.gainSpin.setSuffix(' dB')
        self.gainSpin.setValue(config.gainDb)

        self.ppmSpin = QSpinBox()
        self.ppmSpin.setRange(-200, 200)
        self.ppmSpin.setSuffix(' ppm')
        self.ppmSpin.setValue(int(config.ppm))

        self.bwSpin = QDoubleSpinBox()
        self.bwSpin.setRange(1.0, 500.0)
        self.bwSpin.setDecimals(1)
        self.bwSpin.setSuffix(' kHz')
        self.bwSpin.setValue(config.bwKhz)

        rfForm.addRow('中心频率:', self.freqSpin)
        rfForm.addRow('硬件增益:', self.gainSpin)
        rfForm.addRow('PPM 校正:', self.ppmSpin)
        rfForm.addRow('信道带宽:', self.bwSpin)

        topGrid.addWidget(rfGroup, 0, 1)
        outer.addLayout(topGrid)

        # ---- 中部：RSSI 门控 + AFC 设置 (2 列) ----
        midGrid = QGridLayout()
        midGrid.setSpacing(6)
        midGrid.setColumnStretch(0, 1)
        midGrid.setColumnStretch(1, 1)

        # RSSI 门控设置
        rssiGroup = QGroupBox('RSSI 门控设置')
        rssiForm = QFormLayout(rssiGroup)
        rssiForm.setSpacing(4)
        rssiForm.setContentsMargins(8, 16, 8, 4)

        self.threshSpin = QDoubleSpinBox()
        self.threshSpin.setRange(-150.0, 0.0)
        self.threshSpin.setDecimals(1)
        self.threshSpin.setSuffix(' dB')
        self.threshSpin.setValue(config.rssiThresholdDb)

        self.hystSpin = QDoubleSpinBox()
        self.hystSpin.setRange(0.0, 30.0)
        self.hystSpin.setDecimals(1)
        self.hystSpin.setSuffix(' dB')
        self.hystSpin.setValue(config.rssiHystDb)

        self.holdSpin = QDoubleSpinBox()
        self.holdSpin.setRange(0.0, 10000.0)
        self.holdSpin.setDecimals(0)
        self.holdSpin.setSuffix(' ms')
        self.holdSpin.setValue(config.rssiHoldMs)

        rssiForm.addRow('打开阈值:', self.threshSpin)
        rssiForm.addRow('释放迟滞:', self.hystSpin)
        rssiForm.addRow('保持时间:', self.holdSpin)

        midGrid.addWidget(rssiGroup, 0, 0)

        # AFC 设置
        afcGroup = QGroupBox('AFC 设置')
        afcForm = QFormLayout(afcGroup)
        afcForm.setSpacing(4)
        afcForm.setContentsMargins(8, 16, 8, 4)

        self.afcCheck = QCheckBox('启用 AFC 自动频率控制')
        self.afcCheck.setChecked(config.afcEnable)

        self.afcMaxSpin = QDoubleSpinBox()
        self.afcMaxSpin.setRange(100.0, 50000.0)
        self.afcMaxSpin.setDecimals(0)
        self.afcMaxSpin.setSuffix(' Hz')
        self.afcMaxSpin.setValue(config.afcMaxHz)

        self.afcGainSpin = QDoubleSpinBox()
        self.afcGainSpin.setRange(0.01, 2.0)
        self.afcGainSpin.setDecimals(2)
        self.afcGainSpin.setValue(config.afcGain)

        self.keepAfcCheck = QCheckBox('释放信号后保留 AFC 修正')
        self.keepAfcCheck.setChecked(config.keepAfcAfterPacket)

        afcForm.addRow('', self.afcCheck)
        afcForm.addRow('最大修正范围:', self.afcMaxSpin)
        afcForm.addRow('环路增益:', self.afcGainSpin)
        afcForm.addRow('', self.keepAfcCheck)

        midGrid.addWidget(afcGroup, 0, 1)
        outer.addLayout(midGrid)

        # ---- 底部：到达估算设置 (全宽) ----
        etaGroup = QGroupBox('到达估算设置')
        etaForm = QFormLayout(etaGroup)
        etaForm.setSpacing(4)
        etaForm.setContentsMargins(8, 16, 8, 4)

        self.userKmSpin = QDoubleSpinBox()
        self.userKmSpin.setRange(-1.0, 9999.9)
        self.userKmSpin.setDecimals(1)
        self.userKmSpin.setSuffix(' km')
        self.userKmSpin.setValue(config.userKm if config.userKm is not None else -1.0)
        self.userKmSpin.setSpecialValueText('未设置')

        self.routeKmEdit = QLineEdit(', '.join(config.routeKm) if config.routeKm else '')
        self.routeKmEdit.setPlaceholderText('格式: 京沪线=123.4, 京九线=567.8')

        self.etaMaxSpin = QDoubleSpinBox()
        self.etaMaxSpin.setRange(1.0, 1440.0)
        self.etaMaxSpin.setDecimals(0)
        self.etaMaxSpin.setSuffix(' 分钟')
        self.etaMaxSpin.setValue(config.etaMaxMin)

        etaForm.addRow('本站公里标:', self.userKmSpin)
        etaForm.addRow('线路公里标:', self.routeKmEdit)
        etaForm.addRow('最大估算时间:', self.etaMaxSpin)

        outer.addWidget(etaGroup)

        # ---- 按钮 ----
        btnLayout = QHBoxLayout()
        self.saveBtn = QPushButton('保存配置')
        self.saveBtn.setStyleSheet('background-color: #00cc88; color: #1a1a1a; font-weight: bold;')
        self.hotBtn = QPushButton('热更新 (不重启)')
        self.restartBtn = QPushButton('应用并重启 DSP')
        btnLayout.addWidget(self.saveBtn)
        btnLayout.addWidget(self.hotBtn)
        btnLayout.addWidget(self.restartBtn)
        outer.addLayout(btnLayout)

        self.saveBtn.clicked.connect(self._save)
        self.hotBtn.clicked.connect(self._hotUpdate)
        self.restartBtn.clicked.connect(self._restart)

    def _onModeChanged(self, index: int):
        """模式切换时，对传统模式给出 DC 偏移推荐。"""
        if self._updating_mode:
            return
        is_owrx = self.modeCombo.currentData()
        if not is_owrx:
            sr = self.srCombo.currentData()
            if sr is None:
                sr = 960000
            recommended = sr // 4
            current_dc = self.dcSpin.value()
            if abs(current_dc) < 1:
                ret = QMessageBox.question(
                    self, '传统 RTL-TCP 模式',
                    f'检测到您切换到传统 RTL-TCP 模式。\n\n'
                    f'传统模式下建议使用 DC 偏移来避开零频干扰。\n'
                    f'根据采样率 {sr // 1000} kS/s，推荐值为:\n\n'
                    f'    DC 偏移 = {recommended} Hz\n\n'
                    f'是否调整为推荐值？\n'
                    f'（选择"否"将保留当前值 {current_dc:.0f} Hz）',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if ret == QMessageBox.Yes:
                    self.dcSpin.setValue(recommended)
        else:
            if self.dcSpin.value() != 0:
                ret = QMessageBox.question(
                    self, 'OWRX 模式',
                    'OWRX 模式提供零中频 IQ 流，DC 偏移通常应设为 0。\n\n'
                    f'当前值: {self.dcSpin.value():.0f} Hz\n'
                    '是否将 DC 偏移重置为 0？',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if ret == QMessageBox.Yes:
                    self.dcSpin.setValue(0)

    def _readConfig(self) -> Optional[CoreConfig]:
        try:
            cfg = CoreConfig()
            cfg.host = self.hostEdit.text().strip()
            cfg.port = self.portSpin.value()
            cfg.sampleRate = self.srCombo.currentData() or 960000
            cfg.freqMhz = self.freqSpin.value()
            cfg.gainDb = self.gainSpin.value()
            cfg.ppm = float(self.ppmSpin.value())
            cfg.bwKhz = self.bwSpin.value()
            cfg.blockSize = self.blockSpin.value()
            cfg.dcOffsetHz = self.dcSpin.value()
            cfg.owrxMode = self.modeCombo.currentData()
            cfg.rssiThresholdDb = self.threshSpin.value()
            cfg.rssiHystDb = self.hystSpin.value()
            cfg.rssiHoldMs = self.holdSpin.value()
            cfg.afcEnable = self.afcCheck.isChecked()
            cfg.afcMaxHz = self.afcMaxSpin.value()
            cfg.afcGain = self.afcGainSpin.value()
            cfg.keepAfcAfterPacket = self.keepAfcCheck.isChecked()
            v = self.userKmSpin.value()
            cfg.userKm = None if v < 0 else v
            txt = self.routeKmEdit.text().strip()
            cfg.routeKm = [s.strip() for s in txt.split(',') if s.strip()] if txt else []
            cfg.etaMaxMin = self.etaMaxSpin.value()
            # 保留频谱显示模式 (配置对话框不包含此字段)
            cfg.spectrumMode = getattr(self.config, 'spectrumMode', 'graph')
            return cfg
        except Exception as e:
            QMessageBox.warning(self, '错误', f'配置格式错误: {e}')
            return None

    def _save(self):
        cfg = self._readConfig()
        if cfg is None:
            return
        if cfg.save(CONFIG_PATH):
            self.config = cfg
            QMessageBox.information(self, '成功', f'配置已保存到\n{CONFIG_PATH}')
        else:
            QMessageBox.warning(self, '错误', '保存失败')

    def _hotUpdate(self):
        cfg = self._readConfig()
        if cfg is None:
            return
        self.config = cfg
        self.configChanged.emit()

    def _restart(self):
        cfg = self._readConfig()
        if cfg is None:
            return
        self.config = cfg
        self.configChanged.emit()


# ===========================================================================
# 配置对话框
# ===========================================================================
class ConfigDialog(QDialog):
    """配置对话框：弹出式编辑运行配置。"""

    def __init__(self, config: CoreConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle('SDR-LBJ 配置')
        self.setMinimumSize(680, 620)
        self.resize(760, 680)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        self.panel = ConfigPanel(config)
        self.panel.saveBtn.hide()
        self.panel.hotBtn.hide()
        self.panel.restartBtn.hide()
        layout.addWidget(self.panel)
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        okBtn = QPushButton('确定')
        okBtn.setStyleSheet('background-color: #00cc88; color: #1a1a1a; font-weight: bold;')
        okBtn.clicked.connect(self._onOk)
        cancelBtn = QPushButton('取消')
        cancelBtn.clicked.connect(self.reject)
        btnLayout.addWidget(okBtn)
        btnLayout.addWidget(cancelBtn)
        layout.addLayout(btnLayout)
        self._resultConfig: Optional[CoreConfig] = None

    def _onOk(self):
        cfg = self.panel._readConfig()
        if cfg is not None:
            self._resultConfig = cfg
            self.accept()

    def getConfig(self) -> Optional[CoreConfig]:
        return self._resultConfig


# ===========================================================================
# 日志面板
# ===========================================================================
class LogPanel(QTextEdit):
    """日志输出面板 (QTextEdit 子类)。"""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self._maxLines = MAX_LOG_LINES
        self._lineCount = 0

    def appendLog(self, msg: str):
        """追加一条日志，超过上限时自动截断。"""
        ts = datetime.now().strftime('%H:%M:%S')
        color = '#aaa'
        if '[错误]' in msg or '[断连]' in msg or '[问题]' in msg:
            color = '#ff5555'
        elif '[警告]' in msg:
            color = '#ffaa00'
        elif '[连接]' in msg or '[启动]' in msg or '[诊断]' in msg:
            color = '#00ff66'
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(f'<span style="color:{color}">[{ts}] {msg}</span>')
        cursor.insertBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        self._lineCount += 1
        if self._lineCount > self._maxLines:
            self._trimLines()

    def _trimLines(self):
        """删除最老的日志行，保持总行数不超过上限。"""
        doc = self.document()
        while doc.blockCount() > self._maxLines:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.Start)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()


# ===========================================================================
# 使用手册对话框
# ===========================================================================
class ManualDialog(QDialog):
    """使用手册对话框：传统 TCP 与 OWRX 配置说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('使用手册')
        self.setFixedSize(620, 560)
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        contentLayout = QVBoxLayout(content)

        # ---- 传统 RTL-TCP 模式 ----
        title1 = QLabel('一、传统 RTL-TCP 模式')
        title1.setStyleSheet('color: #00cc88; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title1)

        text1 = QLabel(
            '<p>使用 RTL-SDR Blog v4 等硬件接收器，通过 <b>rtl_tcp</b> 服务将 IQ 数据'
            '通过网络传输到本程序。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 安装 RTL-SDR 驱动：使用 <b>Zadig</b> 将 RTL2832U 设备的 Windows 驱动'
            '替换为 <b>WinUSB</b>（在 Zadig 中勾选 "List All Devices"，选择 RTL2832U，'
            '选择 WinUSB 后点击 Replace Driver）。</p>'
            '<p>2. 启动 rtl_tcp 服务：在命令行中运行<br>'
            '<code>rtl_tcp -a 127.0.0.1 -p 1234</code></p>'
            '<p>3. 在本程序配置中设置：</p>'
            '<ul style="margin-left: 20px;">'
            '<li>模式：传统 RTL-TCP</li>'
            '<li>主机：127.0.0.1</li>'
            '<li>端口：1234</li>'
            '<li>DC 偏移：50000 Hz（推荐值，避开零频 DC 干扰）</li>'
            '<li>采样率：960000 Hz</li>'
            '<li>频率：821.2375 MHz</li>'
            '<li>增益：15.7 dB（根据信号强度调整）</li>'
            '<li>PPM 校正：1.0（根据晶振偏差调整）</li>'
            '<li>信道带宽：35 kHz</li>'
            '<li>AFC：建议开启</li>'
            '</ul>'
            '<p><b>说明：</b>传统模式下，SDR 硬件调谐在目标频率 - DC偏移 处，'
            '通过 DDC（数字下变频）将信号搬移到基带，避免零频 DC 分量干扰。</p>'
        )
        text1.setWordWrap(True)
        text1.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet('background-color: #3a3a3a;')
        contentLayout.addWidget(sep1)

        # ---- OWRX 模式 ----
        title2 = QLabel('二、OWRX 兼容模式')
        title2.setStyleSheet('color: #5599ff; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title2)

        text2 = QLabel(
            '<p>使用 OpenWebRX 服务器提供的 IQ 流进行解码，无需本地 SDR 硬件。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 确保已部署 OpenWebRX 服务器，并启用了 rtl_tcp 兼容接口。</p>'
            '<p>2. 在本程序配置中设置：</p>'
            '<ul style="margin-left: 20px;">'
            '<li>模式：OWRX 兼容模式</li>'
            '<li>主机：OpenWebRX 服务器地址（如 127.0.0.1 或远程 IP）</li>'
            '<li>端口：OpenWebRX 的 rtl_tcp 端口（通常为 1234）</li>'
            '<li>DC 偏移：0 Hz（OWRX 提供零中频 IQ 流，无需 DC 避让）</li>'
            '<li>采样率：与 OpenWebRX 设置一致（通常 960000 Hz）</li>'
            '<li>频率：821.2375 MHz</li>'
            '<li>增益：由 OpenWebRX 服务端控制，本地设置可保持默认</li>'
            '<li>AFC：建议开启</li>'
            '</ul>'
            '<p><b>说明：</b>OWRX 模式下，OpenWebRX 服务端已经完成调谐和 IQ 采样，'
            '本程序直接接收零中频 IQ 流，因此 DC 偏移必须设为 0。'
            '增益等射频参数由服务端控制，本地设置不生效。</p>'
        )
        text2.setWordWrap(True)
        text2.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet('background-color: #3a3a3a;')
        contentLayout.addWidget(sep2)

        # ---- 通用说明 ----
        title3 = QLabel('三、通用说明')
        title3.setStyleSheet('color: #ffaa00; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title3)

        text3 = QLabel(
            '<p><b>RSSI 门控：</b>当信号强度超过阈值（默认 -55 dB）时开始解码，'
            '低于阈值后保持 700ms 再停止，避免信号波动导致频繁启停。</p>'
            '<p><b>AFC（自动频率控制）：</b>跟踪并修正接收信号的频偏，'
            '确保信号锁定在信道中心。建议始终开启。</p>'
            '<p><b>干扰告警：</b>当 BCH 译码检测到不可纠正的错误时，'
            '说明信号受到干扰，程序会在日志和状态栏显示告警。</p>'
            '<p><b>当前列表：</b>显示最近 10 分钟内的解码记录，'
            '无车次信息或受干扰的记录以红色标注，不存入历史数据库。</p>'
        )
        text3.setWordWrap(True)
        text3.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text3)

        contentLayout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btnClose = QPushButton('关闭')
        btnClose.clicked.connect(self.accept)
        layout.addWidget(btnClose)


# ===========================================================================
# 关于对话框
# ===========================================================================
class AboutDialog(QDialog):
    """关于对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于')
        self.setFixedSize(520, 460)
        layout = QVBoxLayout(self)

        title = QLabel('中国铁路 LBJ 列车预警器解码程序')
        title.setStyleSheet('color: #00cc88; font-size: 16px; font-weight: bold;')
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(self._sep())

        info = QLabel(
            '<p>本项目兼容 RTL_TCP 模式与 OpenWebRX 作为数据源，'
            '对中国铁路机车在 821.2375 MHz 频段发送的 LBJ 列车预警信号'
            '进行实时接收与解码，可解析车次、机车、线路、公里标、'
            '方向、速度等报文信息，并支持 ETA 到达时间估算。</p>'
            '<p>机车图片与资料引自 <b>Trainfanz.com (我们的火车站)</b>。</p>'
            '<p style="margin-top: 10px;">参考 Sdr-Is-Fun 等 GitHub 上众多 LBJ 解码相关代码，'
            '并使用 PySide6 等技术构建 GUI 界面。</p>'
            '<p>特别鸣谢 <b>BI7AIG</b> 对 OWRX 测试提供的帮助。</p>'
            '<p style="margin-top: 12px;"><b>作者：BG2GBQ</b></p>'
        )
        info.setWordWrap(True)
        info.setStyleSheet('font-size: 13px; line-height: 1.6;')
        layout.addWidget(info)

        layout.addWidget(self._sep())

        declTitle = QLabel('声明')
        declTitle.setStyleSheet('color: #ffaa00; font-size: 14px; font-weight: bold;')
        layout.addWidget(declTitle)

        decl = QLabel(
            '<p style="color:#ffaa00"><b>本程序仅供学习与研究使用。</b></p>'
            '<p>不得用于任何商业或非法用途。</p>'
        )
        decl.setWordWrap(True)
        decl.setStyleSheet('font-size: 13px; line-height: 1.6;')
        layout.addWidget(decl)

        layout.addWidget(self._sep())

        license = QLabel('License: GPL v3 | Copyright (C) 2026 BG2GBQ')
        license.setStyleSheet('color: #666; font-size: 11px;')
        license.setAlignment(Qt.AlignCenter)
        layout.addWidget(license)

    def _sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet('background-color: #3a3a3a;')
        return line


# ===========================================================================
# 12306 联网车次查询
# ===========================================================================
class TrainQueryWorker(QThread):
    """异步查询 12306 车次时刻表。"""
    resultReady = Signal(dict)
    queryFailed = Signal(str)

    def __init__(self, trainCode: str, dateStr: str):
        super().__init__()
        self.trainCode = trainCode
        self.dateStr = dateStr  # YYYYMMDD

    def _httpGet(self, url: str, timeout: int = 10) -> dict:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
        return json.loads(raw)

    def run(self):
        try:
            # Step 1: 搜索车次
            keyword = urllib.parse.quote(self.trainCode)
            searchUrl = (f'https://search.12306.cn/search/v1/train/search?'
                         f'keyword={keyword}&date={self.dateStr}')
            searchData = self._httpGet(searchUrl)
            if not searchData.get('status') or not searchData.get('data'):
                self.queryFailed.emit(f'未找到车次 {self.trainCode}')
                return
            first = searchData['data'][0]
            trainNo = first['train_no']
            trainCode = first.get('station_train_code', self.trainCode)

            # Step 2: 查询详细时刻表
            detailDate = f'{self.dateStr[:4]}-{self.dateStr[4:6]}-{self.dateStr[6:8]}'
            detailUrl = (f'https://kyfw.12306.cn/otn/queryTrainInfo/query?'
                         f'leftTicketDTO.train_no={trainNo}&'
                         f'leftTicketDTO.train_date={detailDate}&rand_code=')
            detailData = self._httpGet(detailUrl)
            if not detailData.get('status') or not detailData.get('data', {}).get('data'):
                self.queryFailed.emit(f'无法获取时刻表')
                return

            stations = []
            for s in detailData['data']['data']:
                stations.append({
                    'no': int(s.get('station_no', 0)),
                    'name': s.get('station_name', ''),
                    'arriveTime': s.get('arrive_time', '----'),
                    'departTime': s.get('start_time', '----'),
                    'runningTime': s.get('running_time', ''),
                    'isStart': s.get('is_start') == 'Y',
                    'className': s.get('train_class_name', ''),
                    'dayDiff': int(s.get('arrive_day_diff', 0)),
                })

            # 起点 / 终点
            startSt = stations[0] if stations else {}
            endSt = stations[-1] if stations else {}

            result = {
                'trainCode': trainCode,
                'trainNo': trainNo,
                'startStation': startSt.get('name', ''),
                'endStation': endSt.get('name', ''),
                'startTime': startSt.get('departTime', ''),
                'endTime': endSt.get('arriveTime', ''),
                'className': startSt.get('className', ''),
                'stations': stations,
                'queryDate': self.dateStr,
            }
            self.resultReady.emit(result)

        except urllib.error.URLError as e:
            self.queryFailed.emit(f'网络连接失败: {e.reason}')
        except Exception as e:
            self.queryFailed.emit(f'查询失败: {e}')


class TimetableDialog(QDialog):
    """详细时刻表对话框。"""

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        trainCode = data.get('trainCode', '----')
        startSt = data.get('startStation', '')
        endSt = data.get('endStation', '')
        className = data.get('className', '')
        self.setWindowTitle(f'时刻表 — {trainCode} ({startSt} → {endSt})')
        self.setMinimumSize(560, 560)
        self.resize(620, 640)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # 标题
        titleLabel = QLabel(f'{startSt} → {trainCode} → {endSt}')
        titleLabel.setStyleSheet('color: #00cc88; font-size: 16px; font-weight: bold;')
        titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titleLabel)

        infoLabel = QLabel(
            f'类型: {className}  |  '
            f'发车: {data.get("startTime", "")}  |  '
            f'到达: {data.get("endTime", "")}  |  '
            f'共 {len(data.get("stations", []))} 站')
        infoLabel.setStyleSheet('color: #aaa; font-size: 12px;')
        infoLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(infoLabel)

        # 时刻表表格
        stations = data.get('stations', [])
        self.table = QTableWidget(len(stations), 6)
        self.table.setHorizontalHeaderLabels(['站序', '站名', '到达', '发车', '历时', '标志'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        for i, s in enumerate(stations):
            arr = s.get('arriveTime', '----')
            dep = s.get('departTime', '----')
            dayDiff = s.get('dayDiff', 0)
            flag = ''
            if s.get('isStart'):
                flag = '始发'
            elif i == len(stations) - 1:
                flag = '终到'

            vals = [str(s.get('no', '')), s.get('name', ''), arr, dep,
                    s.get('runningTime', ''), flag]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 1:
                    f = item.font(); f.setBold(True); item.setFont(f)
                if flag:
                    item.setForeground(QColor('#ffaa00'))
                self.table.setItem(i, col, item)

        layout.addWidget(self.table)

        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)


class TrainQueryPanel(QWidget):
    """12306 联网车次查询面板：紧凑卡片式显示。"""

    doubleClicked = Signal()

    def __init__(self):
        super().__init__()
        self._cache: Dict[str, dict] = {}  # {trainCode: result}
        self._worker: Optional[TrainQueryWorker] = None
        self._lastQueryCode = ''
        self._currentData: Optional[dict] = None
        self._online = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(2)

        # 左右分栏：左侧 12306，右侧机车信息
        h = QHBoxLayout()
        h.setSpacing(4)

        # 左侧：12306 查询
        leftGroup = QGroupBox('12306 车次查询')
        leftGroup.setStyleSheet('QGroupBox { font-size: 12px; }')
        leftLayout = QVBoxLayout(leftGroup)
        leftLayout.setSpacing(2)
        leftLayout.setContentsMargins(6, 14, 6, 4)

        self.titleLabel = QLabel('等待详细报文...')
        self.titleLabel.setStyleSheet(
            'color: #555; font-size: 12px; padding: 4px; '
            'background-color: #1a1a1a; border-radius: 3px;')
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignCenter)
        leftLayout.addWidget(self.titleLabel)

        self.hintLabel = QLabel('双击查看详细时刻表')
        self.hintLabel.setStyleSheet('color: #555; font-size: 10px;')
        self.hintLabel.setAlignment(Qt.AlignCenter)
        leftLayout.addWidget(self.hintLabel)

        h.addWidget(leftGroup, stretch=3)

        # 右侧：机车信息
        rightGroup = QGroupBox('机车信息')
        rightGroup.setStyleSheet('QGroupBox { font-size: 12px; }')
        rightLayout = QVBoxLayout(rightGroup)
        rightLayout.setSpacing(2)
        rightLayout.setContentsMargins(6, 14, 6, 4)

        self.locoTitleLabel = QLabel('等待详细报文...')
        self.locoTitleLabel.setStyleSheet(
            'color: #555; font-size: 11px; font-weight: bold; padding: 2px;')
        self.locoTitleLabel.setWordWrap(True)
        self.locoTitleLabel.setAlignment(Qt.AlignCenter)
        rightLayout.addWidget(self.locoTitleLabel)

        self.locoDetailLabel = QLabel('')
        self.locoDetailLabel.setStyleSheet(
            'color: #aaa; font-size: 10px; padding: 2px;')
        self.locoDetailLabel.setWordWrap(True)
        self.locoDetailLabel.setAlignment(Qt.AlignCenter)
        rightLayout.addWidget(self.locoDetailLabel)

        self.locoBriefLabel = QLabel('')
        self.locoBriefLabel.setStyleSheet(
            'color: #888; font-size: 10px; padding: 2px; '
            'background-color: #1a1a1a; border-radius: 3px;')
        self.locoBriefLabel.setWordWrap(True)
        self.locoBriefLabel.setAlignment(Qt.AlignCenter)
        rightLayout.addWidget(self.locoBriefLabel)

        h.addWidget(rightGroup, stretch=2)
        outer.addLayout(h)

    def mouseDoubleClickEvent(self, event):
        if self._currentData:
            self.doubleClicked.emit()

    def _openTimetable(self):
        if self._currentData:
            dlg = TimetableDialog(self._currentData, self)
            dlg.exec()

    def onTrainDecoded(self, d: dict):
        """当解码到详细车次信息时触发查询。

        仅对旅客列车类型 (K/Z/T/G/D/C/Y/普通旅客列车) 查询 12306。
        """
        # 只有详细报文才查询 12306
        if not d.get('isDetailed'):
            self.titleLabel.setText('等待详细报文...')
            self.titleLabel.setStyleSheet(
                'color: #555; font-size: 12px; padding: 4px; '
                'background-color: #1a1a1a; border-radius: 3px;')
            self.locoTitleLabel.setText('等待详细报文...')
            self.locoTitleLabel.setStyleSheet(
                'color: #555; font-size: 11px; font-weight: bold; padding: 2px;')
            self.locoDetailLabel.setText('')
            self.locoBriefLabel.setText('')
            return

        # 更新机车信息
        self._updateLocoInfo(d)

        train = d.get('train', '')
        category = d.get('category', '')
        if not train or train == '----':
            return

        # 仅旅客列车类型查询 12306
        passenger_categories = {
            '快速旅客列车', '直达特快列车', '特快旅客列车',
            '高速动车组', '动车组列车', '城际动车组',
            '旅游旅客列车', '普通旅客列车',
        }
        if category not in passenger_categories:
            self.titleLabel.setText(f'{category}，不查询12306')
            self.titleLabel.setStyleSheet(
                'color: #888; font-size: 11px; padding: 4px; '
                'background-color: #1a1a1a; border-radius: 3px;')
            return

        # 使用缓存
        if train in self._cache:
            self._currentData = self._cache[train]
            self._displayResult(self._currentData)
            return

        # 避免重复查询
        if self._lastQueryCode == train and self._worker and self._worker.isRunning():
            return

        self._lastQueryCode = train
        self.titleLabel.setText(f'查询中: {train} ...')
        self.titleLabel.setStyleSheet(
            'color: #5599ff; font-size: 12px; padding: 4px; '
            'background-color: #1a2a2a; border-radius: 3px;')

        dateStr = datetime.now().strftime('%Y%m%d')
        self._worker = TrainQueryWorker(train, dateStr)
        self._worker.resultReady.connect(self._onQueryResult)
        self._worker.queryFailed.connect(self._onQueryFailed)
        self._worker.start()

    def _onQueryResult(self, data: dict):
        code = data.get('trainCode', '')
        self._cache[code] = data
        # 限制缓存大小
        if len(self._cache) > 20:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._currentData = data
        self._displayResult(data)

    def _onQueryFailed(self, err: str):
        self._online = not ('网络' in err or 'URLError' in err)
        self.titleLabel.setText(f'⚠ {err}')
        self.titleLabel.setStyleSheet(
            'color: #ff5555; font-size: 11px; padding: 4px; '
            'background-color: #2a1a1a; border-radius: 3px;')
        if not self._online:
            self.titleLabel.setText('⚠ 此功能需连接互联网使用')
            self.hintLabel.setText('')

    def _displayResult(self, data: dict):
        startSt = data.get('startStation', '')
        endSt = data.get('endStation', '')
        startTime = data.get('startTime', '')
        endTime = data.get('endTime', '')
        code = data.get('trainCode', '')
        className = data.get('className', '')

        self.titleLabel.setText(
            f'{startSt}({startTime})\n→ {code} →\n{endSt}({endTime})')
        self.titleLabel.setStyleSheet(
            'color: #00cc88; font-size: 12px; font-weight: bold; padding: 4px; '
            'background-color: #1a2a1a; border-radius: 3px;')
        self.hintLabel.setText('双击查看详细时刻表')

    def _updateLocoInfo(self, d: dict):
        """根据解码记录更新机车信息卡片。"""
        loco_number = d.get('loco', '')
        loco_code = d.get('locoCode', d.get('loco_code', ''))
        info = lookup_loco(loco_code=loco_code, loco_number=loco_number)
        if info:
            self.locoTitleLabel.setText(info.get('name', '未知车型'))
            self.locoTitleLabel.setStyleSheet(
                'color: #00cc88; font-size: 11px; font-weight: bold; padding: 2px;')
            detail = f"{info.get('type', '')} | {info.get('maker', '')} | {info.get('axle', '')}"
            self.locoDetailLabel.setText(detail)
            self.locoBriefLabel.setText(info.get('brief', ''))
        else:
            self.locoTitleLabel.setText(loco_number or '未知机车')
            self.locoTitleLabel.setStyleSheet(
                'color: #ffaa00; font-size: 11px; font-weight: bold; padding: 2px;')
            self.locoDetailLabel.setText(f"代号: {loco_code}" if loco_code else '')
            self.locoBriefLabel.setText('暂无该车型资料')


# ===========================================================================
# 主窗口
# ===========================================================================
class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self, config: CoreConfig):
        super().__init__()
        self.config = config
        self.worker: Optional[DspBridge] = None

        self.setWindowTitle('中国铁路 LBJ 列车预警器解码程序')
        self.setMinimumSize(1200, 800)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self._buildMenu()
        self._buildUi()

        # 从配置初始化频谱显示模式
        mode = getattr(self.config, 'spectrumMode', 'graph')
        if mode == 'terminal':
            self.spectrumModeCombo.setCurrentIndex(1)
            self.spectrumStack.setCurrentIndex(1)

        # 自动启动
        QTimer.singleShot(500, self.startDsp)

    def _buildMenu(self):
        menubar = self.menuBar()

        fileMenu = menubar.addMenu('文件(&F)')
        actStart = QAction('启动 DSP', self)
        actStart.triggered.connect(self.startDsp)
        fileMenu.addAction(actStart)
        actStop = QAction('停止 DSP', self)
        actStop.triggered.connect(self.stopDsp)
        fileMenu.addAction(actStop)
        fileMenu.addSeparator()
        actQuit = QAction('退出', self, shortcut='Ctrl+Q')
        actQuit.triggered.connect(self.close)
        fileMenu.addAction(actQuit)

        configMenu = menubar.addMenu('配置(&C)')
        actConfig = QAction('配置...', self, shortcut='Ctrl+,')
        actConfig.triggered.connect(self._openConfig)
        configMenu.addAction(actConfig)

        helpMenu = menubar.addMenu('帮助(&H)')
        actManual = QAction('使用手册', self)
        actManual.triggered.connect(lambda: ManualDialog(self).exec())
        helpMenu.addAction(actManual)
        helpMenu.addSeparator()
        actAbout = QAction('关于', self)
        actAbout.triggered.connect(lambda: AboutDialog(self).exec())
        helpMenu.addAction(actAbout)

    def _buildUi(self):
        # 整体布局：垂直三段
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btnStart = QPushButton('▶ 开始')
        self.btnStart.setStyleSheet(
            'QPushButton { background-color: #1a3a1a; border: 1px solid #00cc88; '
            'border-radius: 3px; padding: 6px 18px; font-weight: bold; color: #00ff66; }'
            'QPushButton:hover { background-color: #2a5a2a; }')
        self.btnStart.clicked.connect(self.startDsp)
        self.btnStop = QPushButton('■ 停止')
        self.btnStop.setStyleSheet(
            'QPushButton { background-color: #3a1a1a; border: 1px solid #cc5555; '
            'border-radius: 3px; padding: 6px 18px; font-weight: bold; color: #ff5555; }'
            'QPushButton:hover { background-color: #5a2a2a; }')
        self.btnStop.clicked.connect(self.stopDsp)
        self.freqLabel = QLabel('频率: -- MHz')
        self.freqLabel.setStyleSheet('color: #00cc88; font-weight: bold; font-size: 14px;')
        self.connIndicator = QLabel('● 未连接')
        self.connIndicator.setStyleSheet('color: #ff5555; font-size: 14px; font-weight: bold;')
        toolbar.addWidget(self.btnStart)
        toolbar.addWidget(self.btnStop)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.freqLabel)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.connIndicator)
        toolbar.addStretch()
        # 频谱显示模式切换
        spectrumLabel = QLabel('频谱:')
        spectrumLabel.setStyleSheet('color: #00cc88; font-size: 12px;')
        toolbar.addWidget(spectrumLabel)
        self.spectrumModeCombo = QComboBox()
        self.spectrumModeCombo.addItem('图形频谱')
        self.spectrumModeCombo.addItem('终端频谱 (省资源)')
        self.spectrumModeCombo.setStyleSheet('QComboBox { min-width: 140px; }')
        self.spectrumModeCombo.currentIndexChanged.connect(self._onSpectrumModeChanged)
        toolbar.addWidget(self.spectrumModeCombo)
        root.addLayout(toolbar)

        # ---- 中部：水平 splitter ----
        midSplitter = QSplitter(Qt.Horizontal)

        # 左侧：垂直布局 (频谱 + 列车信息 | 接收状态 + 信号监测)
        leftWidget = QWidget()
        leftLayout = QVBoxLayout(leftWidget)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.setSpacing(4)

        # 左上：频谱 (可切换图形/终端模式) + 列车信息
        topLeftSplitter = QSplitter(Qt.Vertical)
        self.spectrumPanel = SpectrumPanel()
        self.terminalSpectrumPanel = TerminalSpectrumPanel()
        self.spectrumStack = QStackedWidget()
        self.spectrumStack.addWidget(self.spectrumPanel)           # index 0: 图形频谱
        self.spectrumStack.addWidget(self.terminalSpectrumPanel)   # index 1: 终端频谱
        self.trainPanel = TrainInfoPanel()
        topLeftSplitter.addWidget(self.spectrumStack)
        topLeftSplitter.addWidget(self.trainPanel)
        topLeftSplitter.setStretchFactor(0, 4)  # 频谱占更多
        topLeftSplitter.setStretchFactor(1, 1)  # 列车信息紧凑
        leftLayout.addWidget(topLeftSplitter, stretch=1)

        midSplitter.addWidget(leftWidget)

        # 右侧：当前/历史记录 tabs + 12306 查询面板 (垂直分割)
        rightSplitter = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.currentPanel = CurrentPanel()
        self.historyPanel = HistoryPanel()
        self.configPanel = ConfigPanel(self.config)
        self.tabs.addTab(self.currentPanel, '当前')
        self.tabs.addTab(self.historyPanel, '历史记录')
        self.tabs.currentChanged.connect(self._onTabChanged)
        rightSplitter.addWidget(self.tabs)

        # 12306 联网车次查询面板
        self.trainQueryPanel = TrainQueryPanel()
        self.trainQueryPanel.setMaximumHeight(140)
        self.trainQueryPanel.doubleClicked.connect(self._openTimetable)
        rightSplitter.addWidget(self.trainQueryPanel)

        rightSplitter.setSizes([500, 140])
        rightSplitter.setStretchFactor(0, 4)
        rightSplitter.setStretchFactor(1, 1)
        midSplitter.addWidget(rightSplitter)

        midSplitter.setSizes([600, 700])
        midSplitter.setStretchFactor(0, 1)
        midSplitter.setStretchFactor(1, 2)
        root.addWidget(midSplitter, stretch=8)  # 中部占主要空间

        # ---- 底部：日志 + 接收状态 + 系统状态 三栏并排 ----
        bottomSplitter = QSplitter(Qt.Horizontal)

        # 日志面板
        self.logPanel = LogPanel()
        bottomSplitter.addWidget(self.logPanel)

        # 接收状态面板
        self.rxPanel = RxStatusPanel()
        self.rxPanel.setMaximumHeight(180)
        bottomSplitter.addWidget(self.rxPanel)

        # 系统状态面板
        self.infoPanel = QGroupBox('系统状态')
        infoLayout = QVBoxLayout(self.infoPanel)
        infoLayout.setSpacing(1)
        infoLayout.setContentsMargins(6, 8, 6, 4)
        self.infoLabels = {}
        infoFields = [
            ('sampleRate', '采样率'), ('blockSize', '块大小'),
            ('bytesRecv', '接收字节'), ('reconnectCount', '重连'),
            ('blocksPerSec', '块率'), ('jitterCv', '抖动CV'),
            ('dataRateMbps', '速率'), ('uptime', '运行时长'),
            ('diagnostics', '诊断'),
        ]
        for key, label in infoFields:
            row = QHBoxLayout()
            row.setSpacing(4)
            lab = QLabel(f'{label}:')
            lab.setStyleSheet('color: #888; font-size: 11px;')
            val = QLabel('--')
            val.setStyleSheet('color: #d0d0d0; font-size: 11px; font-weight: bold;')
            val.setMaximumWidth(90)
            row.addWidget(lab)
            row.addWidget(val)
            row.addStretch()
            infoLayout.addLayout(row)
            self.infoLabels[key] = val
        infoLayout.addStretch()
        self.infoPanel.setMaximumHeight(180)
        bottomSplitter.addWidget(self.infoPanel)

        bottomSplitter.setSizes([400, 180, 150])
        bottomSplitter.setStretchFactor(0, 4)
        bottomSplitter.setStretchFactor(1, 1)
        bottomSplitter.setStretchFactor(2, 1)
        root.addWidget(bottomSplitter, stretch=1)  # 底部占较小空间

        # 状态栏
        self.statusBar().showMessage('就绪')

    # ---- DSP 控制 ----
    def startDsp(self):
        if self.worker and self.worker.isRunning():
            return
        self.spectrumPanel.setSampleRate(self.config.sampleRate)
        self.terminalSpectrumPanel.setSampleRate(self.config.sampleRate)
        self.worker = DspBridge(self.config)
        self.worker.statusUpdated.connect(self._onStatus)
        self.worker.spectrumUpdated.connect(self._onSpectrum)
        self.worker.trainDecoded.connect(self._onDecode)
        self.worker.logMessage.connect(self.logPanel.appendLog)
        self.worker.connectionChanged.connect(self._onConnection)
        self.worker.diagnosticsUpdated.connect(self._onDiagnostics)
        self.worker.interferenceAlert.connect(self._onInterference)
        self.worker.start()
        self.statusBar().showMessage('DSP 运行中')

    def stopDsp(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.worker = None
        self._onConnection(False)  # 立即更新 UI 为断开状态
        self.statusBar().showMessage('已停止')

    def _onConfigChanged(self, new: CoreConfig):
        """配置变更：区分热更新与重启。"""
        old = self.config
        # 保留频谱显示模式偏好 (配置对话框不包含此字段)
        new.spectrumMode = old.spectrumMode
        restartFields = ['host', 'port', 'sampleRate', 'freqMhz', 'gainDb', 'ppm',
                         'bwKhz', 'blockSize', 'dcOffsetHz', 'owrxMode',
                         'afcEnable', 'afcMaxHz', 'afcGain', 'etaMaxMin']
        needRestart = any(getattr(old, f) != getattr(new, f) for f in restartFields)
        if needRestart:
            self.stopDsp()
            self.config = new
            self.startDsp()
        else:
            if self.worker and self.worker.core:
                self.worker.core.applyHotConfig(new)
                self.config = new
            self.logPanel.appendLog('[配置] 已热更新')

    def _openConfig(self):
        """打开配置对话框。"""
        dlg = ConfigDialog(self.config, self)
        if dlg.exec() == QDialog.Accepted:
            new = dlg.getConfig()
            if new is not None:
                if new.save(CONFIG_PATH):
                    self.configPanel.config = new  # 同步面板内部引用
                    self._onConfigChanged(new)
                    self.logPanel.appendLog('[配置] 已保存到文件')
                else:
                    self.logPanel.appendLog('[配置错误] 保存失败')

    # ---- 信号槽 ----
    def _onStatus(self, st: dict):
        self.rxPanel.updateStatus(st)
        # 更新频率标签
        freqMhz = st.get('freqMhz', 0)
        if freqMhz:
            self.freqLabel.setText(f'频率: {freqMhz:.4f} MHz')
        # 更新频谱上的 RSSI 阈值线
        rssiThresh = st.get('rssiThreshold', DEFAULT_RSSI_THRESHOLD_DB)
        if rssiThresh != self.spectrumPanel._rssiThresholdDb:
            self.spectrumPanel.setRssiThreshold(rssiThresh)
        # 更新终端频谱面板状态 (添加 gain/ppm 从 config)
        if self.spectrumStack.currentIndex() == 1:
            st_term = dict(st)
            st_term['gainDb'] = self.config.gainDb
            st_term['ppm'] = self.config.ppm
            self.terminalSpectrumPanel.setRssiThreshold(rssiThresh)
            self.terminalSpectrumPanel.updateStatus(st_term)
        # 更新连接指示器
        conn = st.get('connected', False)
        if conn:
            self.connIndicator.setText('● 已连接')
            self.connIndicator.setStyleSheet('color: #00ff66; font-size: 12px; font-weight: bold;')
        else:
            self.connIndicator.setText('● 未连接')
            self.connIndicator.setStyleSheet('color: #ff5555; font-size: 12px; font-weight: bold;')
        # 更新系统状态面板
        self._updateInfoPanel(st)

    def _onSpectrum(self, data: np.ndarray):
        if self.spectrumStack.currentIndex() == 0:
            self.spectrumPanel.updateSpectrum(data)
        else:
            self.terminalSpectrumPanel.updateSpectrum(data)

    def _onSpectrumModeChanged(self, index: int):
        """切换频谱显示模式 (图形/终端)。"""
        self.spectrumStack.setCurrentIndex(index)
        self.config.spectrumMode = 'terminal' if index == 1 else 'graph'
        self.config.save(CONFIG_PATH)
        mode_name = '终端 (省资源)' if index == 1 else '图形'
        self.logPanel.appendLog(f'[频谱] 已切换到{mode_name}模式')

    def _onDecode(self, d: dict):
        self.trainPanel.updateDecode(d)
        self.currentPanel.addRecord(d)
        # 无车次信息的报文: 不存入历史数据库
        isInvalid = (d.get('train', '----') in ('----', '', '未知')
                     and d.get('baseTrain', '----') in ('----', ''))
        if not isInvalid:
            self.historyPanel.addRecord(d)
        # 触发 12306 联网查询
        self.trainQueryPanel.onTrainDecoded(d)

    def _onInterference(self, direction: str, warnText: str):
        """干扰告警: 在日志面板和状态栏显示。"""
        self.logPanel.appendLog(f'[告警] {warnText}')
        self.statusBar().showMessage(warnText, 5000)

    def _openTimetable(self):
        """打开 12306 时刻表对话框。"""
        self.trainQueryPanel._openTimetable()

    def _onTabChanged(self, index: int):
        """切换标签页时，切换到历史记录自动刷新。"""
        if self.tabs.tabText(index) == '历史记录':
            self.historyPanel.loadFromDb()

    def _onConnection(self, connected: bool):
        self.statusBar().showMessage('已连接' if connected else '未连接')
        if connected:
            self.connIndicator.setText('● 已连接')
            self.connIndicator.setStyleSheet('color: #00ff66; font-size: 12px; font-weight: bold;')
        else:
            self.connIndicator.setText('● 未连接')
            self.connIndicator.setStyleSheet('color: #ff5555; font-size: 12px; font-weight: bold;')

    def _updateInfoPanel(self, st: dict):
        """更新底部系统状态面板。"""
        sr = st.get('sampleRate', 0)
        self.infoLabels['sampleRate'].setText(f'{sr // 1000} kS/s')
        self.infoLabels['blockSize'].setText(str(self.config.blockSize))
        # 从 worker 获取统计
        if self.worker and hasattr(self.worker, '_lastStats'):
            stats = self.worker._lastStats
            self.infoLabels['bytesRecv'].setText(
                f'{stats.get("bytesRecv", 0) / 1024 / 1024:.1f} MB')
            self.infoLabels['reconnectCount'].setText(
                str(stats.get('reconnectCount', 0)))
            # 网络诊断字段
            bps = stats.get('blocksPerSec', 0.0)
            self.infoLabels['blocksPerSec'].setText(f'{bps:.1f} /s')
            cv = stats.get('jitterCv', 0.0)
            cvEl = self.infoLabels['jitterCv']
            cvEl.setText(f'{cv:.2f}')
            # 抖动 CV 着色: >0.5 红色, >0.3 黄色, 否则绿色
            if cv > 0.5:
                cvEl.setStyleSheet('color: #ff5555; font-size: 12px; font-weight: bold;')
            elif cv > 0.3:
                cvEl.setStyleSheet('color: #ffaa00; font-size: 12px; font-weight: bold;')
            else:
                cvEl.setStyleSheet('color: #00ff66; font-size: 12px; font-weight: bold;')
            rate = stats.get('dataRateMbps', 0.0)
            self.infoLabels['dataRateMbps'].setText(f'{rate:.2f} Mbps')
            uptime = stats.get('uptime', 0)
            h, rem = divmod(int(uptime), 3600)
            m, s = divmod(rem, 60)
            self.infoLabels['uptime'].setText(f'{h:02d}:{m:02d}:{s:02d}')
            diagText = stats.get('diagnostics', 'OK')
            self.infoLabels['diagnostics'].setText(diagText)
            # 诊断摘要着色
            diagEl = self.infoLabels['diagnostics']
            if '未连接' in diagText or '问题' in diagText or '抖动' in diagText or '低' in diagText or '积压' in diagText or '丢弃' in diagText or '重连' in diagText:
                diagEl.setStyleSheet('color: #ff5555; font-size: 12px; font-weight: bold;')
            elif '正常' in diagText:
                diagEl.setStyleSheet('color: #00ff66; font-size: 12px; font-weight: bold;')
            else:
                diagEl.setStyleSheet('color: #ffaa00; font-size: 12px; font-weight: bold;')

    def _onDiagnostics(self, diag: dict):
        """网络诊断信号回调: 触发系统状态面板刷新。"""
        if self.worker and hasattr(self.worker, '_lastStats'):
            # _emitDiagnostics 已更新 _lastStats，这里直接刷新显示
            self._updateInfoPanel({'sampleRate': self.config.sampleRate})

    # ---- 关闭事件 ----
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        # 保存配置
        self.config.save(CONFIG_PATH)
        event.accept()


# ===========================================================================
# 主函数
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description='SDR-LBJ GUI (PySide6)')
    parser.add_argument('--host', type=str, default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--sr', type=int, default=None, help='采样率 (Hz)')
    parser.add_argument('-f', '--freq', type=float, default=None, help='频率 (MHz)')
    parser.add_argument('--gain', type=float, default=None)
    parser.add_argument('--no-autostart', action='store_true')
    args = parser.parse_args()

    # 加载配置
    config = CoreConfig.load(CONFIG_PATH)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.sr:
        config.sampleRate = args.sr
    if args.freq:
        config.freqMhz = args.freq
    if args.gain:
        config.gainDb = args.gain

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = MainWindow(config)
    if args.no_autostart:
        window.statusBar().showMessage('点击 文件 → 启动 DSP 开始')
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
