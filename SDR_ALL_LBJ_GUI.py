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
import re
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
    detect_rtl_devices, find_rtl_tool,
)
from loco_info import lookup_loco, format_loco_brief
from map_panel import MapPanel, HAS_WEBENGINE
import theme as TH
from theme import c as CLR

# Fluent Design 外观层（qfluentwidgets 封装，见 ui_kit.py；缺库自动退回原生控件）
import ui_kit as K
from ui_kit import CardBox


def themeColors() -> dict:
    """当前主题的关键颜色，供子控件内联样式使用。"""
    return {
        'accent': CLR('accent'), 'accent2': CLR('accent2'),
        'text': CLR('text'), 'dim': CLR('dim'), 'faint': CLR('faint'),
        'ok': CLR('ok'), 'warn': CLR('warn'), 'err': CLR('err'),
        'panel': CLR('panel'), 'panel2': CLR('panel2'),
        'border': CLR('border'), 'bg': CLR('bg'), 'status': CLR('status'),
    }

# PySide6
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QUrl, QObject
from PySide6.QtGui import (QColor, QBrush, QFont, QTextCursor, QIcon, QAction,
                           QPixmap, QImage, QDesktopServices)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QTableWidget, QTableWidgetItem,
    QTextEdit, QTabWidget, QGroupBox, QFormLayout, QStatusBar,
    QDialog, QHeaderView, QMessageBox, QInputDialog, QFrame, QFileDialog,
    QMenu, QMenuBar, QStackedWidget, QScrollArea, QSizePolicy,
)

# 控件统一由 ui_kit（Fluent）提供，名字保持原样，界面代码无需改动
QPushButton = K.PushButton
QComboBox = K.ComboBox
QLineEdit = K.LineEdit
QCheckBox = K.CheckBox
QSpinBox = K.SpinBox
QDoubleSpinBox = K.DoubleSpinBox
QTableWidget = K.TableWidget

# pyqtgraph (使用 PySide6 作为 Qt 后端)
import pyqtgraph as pg

# ---------------------------------------------------------------------------
# pyqtgraph 全局配置
# ---------------------------------------------------------------------------
def applyPgTheme():
    """pyqtgraph 全局配色跟随当前主题（曲线/坐标轴/背景）。"""
    pg.setConfigOptions(antialias=False, background=CLR('panel'),
                        foreground=CLR('text'), useOpenGL=False)


applyPgTheme()


# ---------------------------------------------------------------------------
# UI 缩放 (v2.1)
#   目标：不同分辨率 / 不同系统缩放比例的屏幕上保持清晰一致。
#   Qt6 已按系统 DPI 缩放控件，这里的 UI_SCALE 是“用户偏好倍率”，
#   用于把 QSS 里写死的 px 与关键控件尺寸整体放大/缩小。
# ---------------------------------------------------------------------------
UI_SCALE = 1.0


def spx(v: float) -> int:
    """设计像素 -> 当前倍率下的像素。"""
    return max(1, int(round(float(v) * UI_SCALE)))


def scale_qss(text: str) -> str:
    """按 UI_SCALE 缩放 QSS 中的所有 NNpx（pt 不动）。"""
    if abs(UI_SCALE - 1.0) < 0.01:
        return text
    import re as _re

    def _rep(m):
        return '%dpx' % spx(int(m.group(1)))

    return _re.sub(r'(\d+)px', _rep, text)


def autoUiScale(app) -> float:
    """按屏幕可用尺寸给出建议倍率（宽高一起看，取更紧的那一边）。

    基准是 1920×1040 ≈ 1.0。只做“界面宽容度”微调，不乘系统 DPI ——
    Qt6 已经按系统缩放处理过一次，再乘会双重放大。
    布局本身（FieldGrid / 分栏比例）会随窗口自适应，这里只定字号与控件尺寸的基准。
    """
    try:
        scr = app.primaryScreen()
        if scr is None:
            return 1.0
        geo = scr.availableGeometry()
        rw = geo.width() / 1920.0
        rh = geo.height() / 1040.0
        r = min(rw, rh)
        if r >= 1.25:
            return 1.25
        if r >= 1.10:
            return 1.15
        if r >= 0.98:
            return 1.12
        if r >= 0.80:
            return 1.00
        return 0.92
    except Exception:
        return 1.0


def resolveUiScale(config) -> float:
    """定下本次运行的界面缩放倍率。

    配置里 `uiScale = 0` 才是「按屏幕自动」，但老版本把 100% 当默认值写进了配置，
    等于把自动缩放永久关掉——大屏上就一直显示小字。所以 v2.4 起 1.0 也按自动处理。
    """
    app = QApplication.instance()
    try:
        raw = float(getattr(config, 'uiScale', 0.0) or 0.0)
    except Exception:
        raw = 0.0
    if raw <= 0.0 or abs(raw - 1.0) < 0.01:
        return autoUiScale(app)
    return max(0.8, min(1.6, raw))


# 触屏友好补充样式（Surface 等设备的可点区域与滚动条）
TOUCH_STYLE = """
QPushButton { min-height: 28px; }
QTableWidget::item { padding: 4px 6px; }
QScrollBar:vertical { width: 14px; }
QScrollBar:horizontal { height: 14px; }
QScrollBar::handle:vertical { min-height: 32px; }
QScrollBar::handle:horizontal { min-width: 32px; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QTabBar::tab { padding: 8px 18px; }
QHeaderView::section { padding: 6px 4px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QComboBox::drop-down { width: 26px; }
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
# 注意：FIRST_RUN 必须在复制之前求值，否则 main() 里永远拿不到“首次”状态
FIRST_RUN = not os.path.exists(CONFIG_PATH)
if FIRST_RUN:
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
    """实时频谱（紧凑版）：只回答“现在有没有输出”。

    一条曲线 + 门限虚线 + 一行结论，坐标轴/网格/标题全部去掉。
    文字按宽度省略、绘图区不设固定高度，因此任何窗口宽度下都不会撑出边界。
    """

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        # 左右下留一点内边距：曲线的两端不会顶到面板边框，看起来才不像“溢出”
        layout.setContentsMargins(spx(8), spx(3), spx(8), spx(6))
        layout.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(spx(10))
        self.verdictLabel = QLabel('等待数据')
        self.verdictLabel.setStyleSheet(
            f'color: {CLR("faint")}; font-size: {spx(10)}px;')
        # 注意：不能用 Ignored 策略——布局会把它压成 0 宽（文字直接看不见）。
        # 文字由 _elide() 主动截断，宽度自然 <= 可用宽度。
        self.verdictLabel.setMinimumWidth(0)
        self.infoLabel = QLabel('')
        self.infoLabel.setStyleSheet(
            f'color: {CLR("dim")}; font-size: {spx(10)}px;')
        self.infoLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.infoLabel.setMinimumWidth(0)
        bar.addWidget(self.verdictLabel, 0)
        bar.addStretch(1)
        bar.addWidget(self.infoLabel, 0)
        layout.addLayout(bar)

        self.plot = pg.PlotWidget()
        self.plot.setBackground(CLR('panel'))
        self.plot.setMenuEnabled(False)
        self.plot.hideAxis('left')
        self.plot.hideAxis('bottom')
        self.plot.getViewBox().setMouseEnabled(x=False, y=False)
        self.plot.getViewBox().setMenuEnabled(False)
        self.plot.getViewBox().setDefaultPadding(0)
        self.plot.getViewBox().setLimits(xMin=-1200, xMax=1200, yMin=-150, yMax=10)
        self.plot.setYRange(-140, 0, padding=0)
        self.plot.setMinimumHeight(spx(48))
        self.plot.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        self._accent = QColor(CLR('accent'))
        self._fillCol = QColor(CLR('accent'))
        self._fillCol.setAlpha(38)

        self.curve = self.plot.plot(pen=pg.mkPen(CLR('accent'), width=1.6))
        self._baseline = pg.PlotDataItem([0], [-140])
        self.fill = pg.FillBetweenItem(self.curve, self._baseline,
                                       brush=pg.mkBrush(self._fillCol))
        self.plot.addItem(self.fill)

        self._rssiThresholdDb = DEFAULT_RSSI_THRESHOLD_DB
        self._thresholdLine = pg.InfiniteLine(
            pos=self._rssiThresholdDb, angle=0,
            pen=pg.mkPen(CLR('dim'), width=1, style=Qt.DashLine))
        self.plot.addItem(self._thresholdLine)

        layout.addWidget(self.plot, 1)

        self._sampleRate = 960000
        self._binCount = 32
        self._peak = None
        self._verdictText = '等待数据'
        self._verdictColor = CLR('faint')
        self._verdictBold = False
        self._infoText = ''
        self._refreshInfo()          # 首屏就有“±带宽 · 门限”这行

    # ------------------------------------------------------------------
    # 文字省略：窄窗口下不撑破面板
    # ------------------------------------------------------------------
    def _elide(self):
        total = max(0, self.width() - spx(20))
        if total <= 0:
            return
        fm = self.verdictLabel.fontMetrics()
        vW = int(total * 0.42)
        iW = max(spx(60), total - vW - spx(16))
        self.verdictLabel.setText(
            fm.elidedText(self._verdictText, Qt.ElideRight, max(spx(40), vW)))
        self.infoLabel.setText(
            fm.elidedText(self._infoText, Qt.ElideRight, iW))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _setVerdict(self, text: str, color: str, bold: bool = False):
        self._verdictText = text
        self._verdictColor = color
        self._verdictBold = bold
        weight = 'bold' if bold else 'normal'
        self.verdictLabel.setStyleSheet(
            f'color: {color}; font-size: {spx(10)}px; font-weight: {weight};')
        self._elide()

    def setSampleRate(self, sr: int):
        """设置采样率，用于计算 X 轴范围。"""
        self._sampleRate = sr
        halfBwKhz = (sr / 2) / 1000.0
        self.plot.setXRange(-halfBwKhz, halfBwKhz, padding=0)
        self._refreshInfo()

    def setRssiThreshold(self, thresholdDb: float):
        """更新门限线位置。"""
        self._rssiThresholdDb = thresholdDb
        self._thresholdLine.setPos(thresholdDb)
        self._refreshInfo()

    def _refreshInfo(self):
        span = self._sampleRate / 2000.0
        txt = f'±{span:.0f} kHz · 门限 {self._rssiThresholdDb:.0f} dB'
        if self._peak is not None:
            txt += f' · 峰值 {self._peak:.0f} dB'
        self._infoText = txt
        self._elide()

    def applyTheme(self):
        """主题切换后重刷配色（pyqtgraph 的画笔/画刷是建对象时固化的）。"""
        self.plot.setBackground(CLR('panel'))
        self._accent = QColor(CLR('accent'))
        self._fillCol = QColor(CLR('accent'))
        self._fillCol.setAlpha(38)
        self.curve.setPen(pg.mkPen(CLR('accent'), width=1.6))
        self.fill.setBrush(pg.mkBrush(self._fillCol))
        self._thresholdLine.setPen(
            pg.mkPen(CLR('dim'), width=1, style=Qt.DashLine))
        self.infoLabel.setStyleSheet(
            f'color: {CLR("dim")}; font-size: {spx(10)}px;')
        # 结论文字的颜色由“哪一档”决定，按当前档位拿新颜色重画
        if self._verdictText == '有信号':
            self._setVerdict('有信号', CLR('ok'), bold=True)
        elif self._verdictText == '弱信号':
            self._setVerdict('弱信号', CLR('warn'))
        else:
            self._setVerdict(self._verdictText, CLR('faint'))
        self._refreshInfo()

    def updateSpectrum(self, data: np.ndarray):
        """更新频谱曲线。data 为 32 个 dB 值，对应 -sr/2 ~ +sr/2。"""
        if len(data) == 0:
            return
        n = len(data)
        halfBwKhz = (self._sampleRate / 2) / 1000.0
        x = np.linspace(-halfBwKhz, halfBwKhz, n)
        self.curve.setData(x=x, y=data)
        self._baseline.setData([x[0], x[-1]], [-140.0, -140.0])
        try:
            self._peak = float(np.max(data))
        except Exception:
            self._peak = None
        # 有没有“明显高于噪声底”的凸起，一句话给结论
        try:
            floor = float(np.median(data))
            peak = float(np.max(data))
            if peak - floor > 18:
                self._setVerdict('有信号', CLR('ok'), bold=True)
            elif peak > self._rssiThresholdDb:
                self._setVerdict('弱信号', CLR('warn'))
            else:
                self._setVerdict('静噪', CLR('faint'))
        except Exception:
            pass
        self._refreshInfo()


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
    _C_GREEN = f'{CLR("ok")}'
    _C_GRAY = f'{CLR("faint")}'
    _C_CYAN = f'{CLR("accent2")}'
    _C_RED = f'{CLR("err")}'
    _C_YELLOW = f'{CLR("warn")}'

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.titleLabel = QLabel('终端频谱（省资源模式）')
        self.titleLabel.setStyleSheet(
            f'color: {CLR("accent")}; font-size: {spx(11)}px; font-weight: bold;'
            f' padding: {spx(2)}px;')
        self.titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.titleLabel)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            f'QTextEdit {{ background-color: {CLR("status")}; border: 1px solid {CLR("border")}; '
            'font-family: Consolas, "Cascadia Mono", "Courier New", monospace; '
            f'font-size: {spx(11)}px; color: {CLR("text")}; }}')
        layout.addWidget(self.text)

        self._sampleRate = 960000
        self._rssiThresholdDb = DEFAULT_RSSI_THRESHOLD_DB
        self._lastStatus: Dict[str, Any] = {}
        self._lastData = np.full(32, -120.0, dtype=np.float64)
        self._height = 8            # 频谱条形图行数
        self._bins = 32             # 频谱分箱数 (与核心库一致)
        self._lastRenderT = 0.0     # 渲染节流时间戳

    def applyTheme(self):
        """主题切换：重算这套字符画用的颜色并立即重画。"""
        self._C_GREEN = CLR('ok')
        self._C_GRAY = CLR('faint')
        self._C_CYAN = CLR('accent2')
        self._C_RED = CLR('err')
        self._C_YELLOW = CLR('warn')
        self.titleLabel.setStyleSheet(
            f'color: {CLR("accent")}; font-size: {spx(11)}px; font-weight: bold;'
            f' padding: {spx(2)}px;')
        self.text.setStyleSheet(
            f'QTextEdit {{ background-color: {CLR("status")};'
            f' border: 1px solid {CLR("border")}; '
            'font-family: Consolas, "Cascadia Mono", "Courier New", monospace; '
            f'font-size: {spx(11)}px; color: {CLR("text")}; }}')
        self._lastRenderT = 0.0
        self._render()

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

    def _colRepeat(self, bins: int) -> int:
        """每个频点横向重复几格。

        核心只给 32 个频点，宽屏下若不重复，字符图只占左边一小条，
        右边全是空的。这里按「可视宽度 / 每格字符宽」算出重复倍数。
        """
        if bins <= 0:
            return 1
        try:
            fm = self.text.fontMetrics()
            cw = max(1, fm.horizontalAdvance('█'))
            avail = max(self.text.viewport().width(), cw * (bins + 5))
            return max(1, min(24, int(avail // (cw * (bins + 5)))))
        except Exception:
            return 1

    def _graphRows(self) -> int:
        """按当前可视高度决定画几行条形图。

        面板矮（中段卡片只有 130 px 左右高）时若固定画 8 行，底部 4 行状态
        （频率 / RSSI / AFC / 连接）会被挤出可视区，得手动滚动才能看全。
        这里把行数交给高度算：永远给状态行留 5 行位置。
        """
        rows = self._height
        try:
            fm = self.text.fontMetrics()
            lh = max(1, fm.lineSpacing())
            avail = self.text.viewport().height()
            if avail > 0:
                rows = int(avail // (lh + 1)) - 5     # 1 行轴线 + 4 行状态
        except Exception:
            pass
        return max(2, min(self._height, rows))

    def _render(self):
        """渲染频谱条形图与状态行到 QTextEdit。"""
        # 节流: 最多 ~20fps，避免频繁 setHtml
        now = time.time()
        if now - self._lastRenderT < 0.05:
            return
        self._lastRenderT = now

        db_array = self._lastData
        st = self._lastStatus
        height = self._graphRows()
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
        rep = self._colRepeat(bins)          # 每个频点横向重复几格，把宽度吃满

        html_lines = []

        # ---- 频谱条形图 (从顶到底) ----
        for r in range(height - 1, -1, -1):
            row_db = db_min + (r + 1) * (db_range / height)
            segs = [self._seg(f'{int(row_db):4d}│', self._C_GRAY)]
            for c in range(bins):
                sh = cols_h[c] - r * 8
                if sh >= 8:
                    ch = '█'
                elif sh <= 0:
                    ch = ' '
                else:
                    ch = chars[sh]
                segs.append(self._seg(ch * rep, self._C_GREEN))
            html_lines.append(''.join(segs))

        # ---- 底部轴线（宽度跟着条形图走）----
        inner = bins * rep
        axis = ('     └' + '─' * (inner // 2) + '┴'
                + '─' * max(0, inner - inner // 2 - 1) + '┘')
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

    def resizeEvent(self, event):
        """面板高度变了要重画：条形图行数是按可视高度算的。"""
        super().resizeEvent(event)
        if hasattr(self, 'text'):
            self._lastRenderT = 0.0
            self._render()


# ===========================================================================
# 响应式字段网格 (v2.2)
#   同一批 label/value，按可用宽度自动决定排几列：宽屏 5 列、窄屏 2 列。
#   底部卡片区因此不需要用户自己拖分隔条来“凑”布局。
# ===========================================================================
class FieldGrid(QWidget):
    """自动换列的 label/value 网格。"""

    MIN_CELL_W = 150          # 单列最小宽度（设计像素）
    MAX_COLS = 6              # 最多 6 列：再多会挤到看不清经纬度那种长值

    def __init__(self, fields, minCellW: int = 0):
        super().__init__()
        self._fields = list(fields)
        self._minCellW = int(minCellW or self.MIN_CELL_W)
        self._cols = 0
        self.labels: Dict[str, QLabel] = {}
        self.captions: Dict[str, QLabel] = {}
        self._cells: Dict[str, QWidget] = {}

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(spx(16))
        self._grid.setVerticalSpacing(spx(2))

        for key, label in self._fields:
            box = QWidget()
            box.setMinimumWidth(spx(24))
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            lab = QLabel(label)
            lab.setStyleSheet(f'color: {CLR("faint")}; font-size: {spx(10)}px;')
            val = QLabel('----')
            val.setStyleSheet(
                f'color: {CLR("text")}; font-size: {spx(14)}px; font-weight: bold;')
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            v.addStretch(1)
            v.addWidget(lab)
            v.addWidget(val)
            v.addStretch(1)
            self.labels[key] = val
            self.captions[key] = lab
            self._cells[key] = box

        self._compact = False
        self._rowH = (0, 0)
        self._reflow(force=True)

    # ------------------------------------------------------------------
    TARGET_CELL_W = 210       # 理想列宽
    MIN_ROW_H = 36            # 一行至少要占的高度（字段名 14px + 值 19px）

    def _colsForWidth(self, width: int, height: int = 0) -> int:
        """选列数：既不挤到看不清，也尽量别让最后一行只剩一个。"""
        n = len(self._fields)
        if n <= 1:
            return 1
        maxCols = max(1, min(n, self.MAX_COLS,
                             int(max(1, width) // max(1, spx(self._minCellW)))))
        if maxCols <= 1:
            return 1

        best, bestScore = maxCols, None
        for c in range(2, maxCols + 1):
            rows = -(-n // c)                     # ceil
            if height > 0 and rows * spx(self.MIN_ROW_H) > height and c < maxCols:
                continue                          # 放不下这么多行，往多列走
            cellw = width / c
            if cellw < spx(self._minCellW):
                continue
            last = n - (rows - 1) * c             # 最后一行几项
            penalty = 0.0
            if last < max(1, c // 2):
                penalty = (max(1, c // 2) - last) * 80.0
            score = abs(cellw - spx(self.TARGET_CELL_W)) + penalty
            if bestScore is None or score < bestScore:
                best, bestScore = c, score
        return best

    def _reflow(self, force: bool = False):
        width = self.width()
        height = self.height()
        if width < spx(24):                      # 还没布局出来，先按 4 列占位
            width = spx(self._minCellW * 4)
        cols = self._colsForWidth(width, height)
        if cols == self._cols and not force:
            return
        self._cols = cols
        for box in self._cells.values():
            self._grid.removeWidget(box)
        for i, (key, _label) in enumerate(self._fields):
            r, c = divmod(i, cols)
            self._grid.addWidget(self._cells[key], r, c)
        rows = -(-len(self._fields) // cols)
        # 先把所有行/列拉伸清零：换列数后旧布局会留下空行，
        # 空行若还带 stretch 会把多出来的高度吃掉，看起来像“内容挤在上半截”。
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)
        for r in range(rows):                    # 行均分高度，卡片区不空荡
            self._grid.setRowStretch(r, 1)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)
        self._grid.activate()
        self._applyDensity()

    def _applyDensity(self):
        """卡片高度不够时切到紧凑模式：隐藏字段名，只留值。

        窗口矮的时候右列「列车信息」只有 150~200 px 高，11 个字段分 2 列要
        6 行，带字段名放不下会被裁掉。标题在卡片顶上已经写着「列车信息」，
        字段名先藏起来不影响判断，鼠标停在值上仍有 tooltip。
        """
        if not self._fields:
            return
        # 用真实控件量一次行高，别用魔数猜
        if self._rowH[0] <= 0:
            key = self._fields[0][0]
            val = self.labels[key]
            cap = self.captions[key]
            vh = val.minimumSizeHint().height()
            ch = cap.minimumSizeHint().height()
            sp = self._grid.verticalSpacing()
            self._rowH = (vh + ch + sp, vh + sp)      # (带字段名, 不带)
        rows = -(-len(self._fields) // max(1, self._cols))
        avail = self.height() - spx(2)
        compact = rows * self._rowH[0] > avail
        if compact == self._compact:
            return
        self._compact = compact
        for key, lab in self.captions.items():
            lab.setVisible(not compact)
            val = self.labels.get(key)
            if val is not None:
                val.setToolTip(lab.text() if compact else '')
        self._grid.activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()
        self._applyDensity()

    def setColumnHint(self, cols: int):
        """按“希望几列”重排（给不想按宽度算的场景用）。"""
        cols = max(1, min(len(self._fields), int(cols)))
        if cols == self._cols:
            return
        self._cols = cols
        for box in self._cells.values():
            self._grid.removeWidget(box)
        for i, (key, _label) in enumerate(self._fields):
            r, c = divmod(i, cols)
            self._grid.addWidget(self._cells[key], r, c)
        self._grid.activate()


# ===========================================================================
# 卡片容器：改用 ui_kit.CardBox（Fluent SimpleCardWidget）
#   原来这里是一段自绘 QSS 卡片，v2.4 起交给 qfluentwidgets，
#   只保留同名同签名的封装，界面代码不用改。
# ===========================================================================


# ===========================================================================
# 输出 1：最新一条日志（v2.4 改成单行大字，点击开完整日志窗口）
# ===========================================================================
class LogTail(QWidget):
    """底栏左半边「输出 1」：只显示**最新一条**日志。

    底栏就是个底栏——不做滚动区，一行大字，按级别着色（正常灰白、告警黄、错误红），
    放不下就省略号截断，完整内容挂在 tooltip 上；点一下开实时日志窗口（Ctrl+L）。
    """

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip('最新一条日志（点击查看完整日志 Ctrl+L）')
        self._text = '等待日志…'
        self._level = 'info'

        lay = QHBoxLayout(self)
        lay.setContentsMargins(spx(8), 0, spx(8), 0)
        lay.setSpacing(spx(8))

        self.dot = QLabel('●')
        self.label = QLabel(self._text)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)
        lay.addWidget(self.label, 1, Qt.AlignVCenter)

        self.applyTheme()

    # ------------------------------------------------------------------
    def _color(self) -> str:
        return {'ok': CLR('ok'), 'warn': CLR('warn'),
                'err': CLR('err')}.get(self._level, CLR('text'))

    def applyTheme(self):
        """主题变化后重新着色（颜色写在样式里，不跟 QSS 走）。"""
        px = K.barFontPx()
        self.dot.setStyleSheet(
            f'background: transparent; color: {self._color()};'
            f' font-size: {px * 0.62:.1f}px;')
        self.label.setStyleSheet(
            f'background: transparent; color: {self._color()};'
            f' font-size: {px:.1f}px; font-weight: 600;'
            ' font-family: "Microsoft YaHei UI", "Microsoft YaHei", Consolas;')
        self._elide()

    def _elide(self):
        # 单行显示：按当前宽度省略，完整文本放 tooltip
        w = max(60, self.label.width() - spx(4))
        fm = self.label.fontMetrics()
        self.label.setText(fm.elidedText(self._text, Qt.ElideRight, w))
        self.setToolTip(self._text + '\n点击查看完整日志 (Ctrl+L)')

    def appendLine(self, line: str, level: str = 'info'):
        self._text = str(line)
        self._level = level or 'info'
        self.applyTheme()

    def relayout(self):
        self.applyTheme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def mousePressEvent(self, event):
        # 点一下打开完整日志窗口（由主窗口连过去）
        try:
            self.window().openLogWindow()
        except Exception:
            pass
        event.accept()


# ===========================================================================
# 列车信息面板
# ===========================================================================
class TrainInfoPanel(QWidget):
    """实时列车信息：字段按宽度自动分列（宽屏一行放 5~6 组）。"""

    FIELDS = [
        ('train', '车次'), ('direction', '方向'), ('speed', '速度'),
        ('position', '公里标'), ('loco', '机车'), ('route', '线路'),
        ('category', '类别'), ('etaTime', '到达时间'), ('etaDistanceKm', '距离'),
        ('coord', '经纬度'), ('currentRouteKmText', '本站'),
    ]

    def __init__(self):
        super().__init__()
        # 页签本身已经写着「列车信息」，不再套一层 GroupBox 重复标题
        outer = QVBoxLayout(self)
        outer.setContentsMargins(spx(10), spx(8), spx(10), spx(6))
        outer.setSpacing(spx(4))

        self.grid = FieldGrid(self.FIELDS)
        self.labels = self.grid.labels
        outer.addWidget(self.grid, 1)

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
        lat, lon = d.get('latitude'), d.get('longitude')
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            self.labels['coord'].setText(f'{lat:.5f}, {lon:.5f}')
            self.labels['coord'].setStyleSheet(
                f'color: {CLR("ok")}; font-size: {spx(13)}px; font-weight: bold;')
        else:
            self.labels['coord'].setText('等待详细报文')
            self.labels['coord'].setStyleSheet(
                f'color: {CLR("faint")}; font-size: {spx(12)}px; font-weight: normal;')

        # 方向着色
        dirEl = self.labels['direction']
        d_val = d.get('direction', '')
        if d_val == '上行':
            dirEl.setStyleSheet(f'color: {CLR("accent2")}; font-size: {spx(14)}px; font-weight: bold;')
        elif d_val == '下行':
            dirEl.setStyleSheet(f'color: {CLR("ok")}; font-size: {spx(14)}px; font-weight: bold;')
        else:
            dirEl.setStyleSheet(f'color: {CLR("text")}; font-size: {spx(14)}px; font-weight: bold;')


# ===========================================================================
# 输出 2：接收状态提示（v2.4 改回「一句话」形态）
# ===========================================================================
class RxStatusStrip(QWidget):
    """底栏右边「输出 2」：把接收状态归纳成**一句人能读懂的话**。

    正常时显示「接收正常」加一行小字指标；出问题时直接说哪不对，例如
    「AFC 置信度偏低」「信号偏弱」「近 60 秒干扰 12 次」，黄色是注意、红色是严重。
    多项同时异常时主提示给最严重的一条，其余用「·」跟在后面。
    整条可点，点开运行状态仪表板（Ctrl+D）。
    """

    clicked = Signal()

    #: 主提示文案：信号弱 / AFC 置信度低 / 干扰多 / 断链
    def __init__(self):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('接收状态：点击打开运行状态仪表板 (Ctrl+D)')
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._interfCount = 0
        self._interfTs = 0.0
        self._issues: List[str] = []
        self._main = '等待连接'
        self._tone = 'dim'
        self._brief = '尚未开始接收'

        lay = QHBoxLayout(self)
        lay.setContentsMargins(spx(8), 0, spx(8), 0)
        lay.setSpacing(spx(8))
        self.dot = QLabel('●')
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.mainLabel = QLabel(self._main)
        self.mainLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.briefLabel = QLabel(self._brief)
        self.briefLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(self.mainLabel)
        col.addWidget(self.briefLabel)
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)
        lay.addLayout(col, 1)
        self.applyTheme()

    # ------------------------------------------------------------------
    def _color(self) -> str:
        return {'ok': CLR('ok'), 'warn': CLR('warn'),
                'err': CLR('err')}.get(self._tone, CLR('dim'))

    def applyTheme(self):
        px = K.barFontPx()
        self.dot.setStyleSheet(
            f'background: transparent; color: {self._color()};'
            f' font-size: {px * 0.62:.1f}px;')
        self.mainLabel.setStyleSheet(
            f'background: transparent; color: {self._color()};'
            f' font-size: {px:.1f}px; font-weight: 600;')
        self.briefLabel.setStyleSheet(
            f'background: transparent; color: {CLR("dim")};'
            f' font-size: {max(9.0, px * 0.66):.1f}px;')
        self._elide()

    def _elide(self):
        fm = self.mainLabel.fontMetrics()
        w = max(60, self.mainLabel.width() - spx(4))
        self.mainLabel.setText(fm.elidedText(self._main, Qt.ElideRight, w))
        fm2 = self.briefLabel.fontMetrics()
        self.briefLabel.setText(
            fm2.elidedText(self._brief, Qt.ElideRight, max(60, self.briefLabel.width() - spx(4))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    # ------------------------------------------------------------------
    def _set(self, main: str, tone: str, brief: str):
        if (main, tone, brief) == (self._main, self._tone, self._brief):
            return
        self._main, self._tone, self._brief = main, tone, brief
        self.applyTheme()

    def noteInterference(self):
        """记一次干扰告警（BCH 错包），60 秒窗口内累计。"""
        now = time.time()
        if now - self._interfTs > 60.0:
            self._interfCount = 0
        self._interfTs = now
        self._interfCount += 1

    def updateStatus(self, st: dict):
        rssi = float(st.get('rssi', -140.0) or -140.0)
        thresh = float(st.get('rssiThreshold', DEFAULT_RSSI_THRESHOLD_DB))
        gate = str(st.get('rssiGate', 'OFF'))
        score = float(st.get('afcScore', 0.0) or 0.0)
        err = float(st.get('afcErrHz', 0.0) or 0.0)
        conn = bool(st.get('connected', False))

        # 干扰窗口过期归零
        if self._interfCount and time.time() - self._interfTs > 60.0:
            self._interfCount = 0

        # ① 先按严重程度收集“问题”，② 没有问题时才是“正常”
        errs: List[str] = []
        warns: List[str] = []
        if not conn:
            errs.append('链路已断开')
        else:
            if rssi < -80:
                errs.append('信号极弱')
            elif rssi < -65:
                warns.append('信号偏弱')
            if score < 0.10 and gate == 'ON':
                warns.append('AFC 置信度偏低')
            if abs(err) > 200:
                warns.append(f'频偏 {err:+.0f} Hz')
            if self._interfCount >= 5:
                warns.append(f'干扰偏多 {self._interfCount} 次')
            elif self._interfCount:
                warns.append(f'干扰 {self._interfCount} 次')

        if errs:
            main, tone = errs[0], 'err'
        elif warns:
            main, tone = warns[0], 'warn'
        elif conn:
            main, tone = '接收正常', 'ok'
        else:
            main, tone = '未连接', 'dim'

        rest = (errs + warns)
        rest = [x for x in rest if x != main]

        # 小字补充：关键指标一行
        bits = []
        if conn:
            bits.append(f'信号 {rssi:.0f} dB')
            bits.append(f'AFC {score:.2f}')
            bits.append(f'门控 {gate}')
        else:
            bits.append('点「开始」接收')
        if rest:
            bits.insert(0, ' · '.join(rest[:2]) + ('…' if len(rest) > 2 else ''))
        brief = ' · '.join(bits)

        self._issues = errs + warns
        self._set(main, tone, brief)
        tip = ('● ' + ' · '.join(self._issues)) if self._issues else '✓ 接收链路正常'
        self.setToolTip(tip + '\n点击打开运行状态仪表板 (Ctrl+D)')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


# ===========================================================================
# 当前列表面板 (10 分钟内全部解码)
# ===========================================================================
# ===========================================================================
# 「当前解码」与「历史记录」共用的列定义（v2.4）
#   两个页签的列必须完全一致——值班时来回切，不能换个表就换一套字段。
#   差异列的处理：预计到达（原来只有当前表有）、报文（原来只有历史表有，BCD 收进详情框）。
# ===========================================================================
DECODE_COLUMNS = ['时间', '车次', '方向', '速度', '公里标', '线路',
                  '机车', '类别', '预计到达', '报文']

#: 可伸缩列（报文最长，吃掉剩余宽度）
DECODE_STRETCH_COL = DECODE_COLUMNS.index('报文')


def decodeRowValues(d: dict) -> List[str]:
    """一条解码记录 → 与 DECODE_COLUMNS 一一对应的显示文本。"""
    def txt(key: str, default: str = '') -> str:
        v = d.get(key, default)
        return default if v is None or v == '' else str(v)

    return [
        txt('timeStr', '--:--:--'),
        txt('train', '----'),
        txt('direction', '未知'),
        txt('speed', '---'),
        txt('position', '---.-'),
        txt('route', '----'),
        txt('loco', '----'),
        txt('category', '未知'),
        txt('etaTime', '--:--:--'),
        '详细' if d.get('isDetailed') else '短报文',
    ]


def styleDecodeItem(item: 'QTableWidgetItem', col: int, text: str,
                    invalid: bool = False, age: float = 0.0) -> None:
    """统一的单元格着色：无车次标红、车次加粗、方向配色、过期变暗。"""
    if invalid:
        item.setForeground(QColor(CLR('err')))
        return
    if col == 1:                       # 车次加粗
        f = item.font()
        f.setBold(True)
        item.setFont(f)
    elif col == 2:                     # 方向配色（红涨绿跌之外的另一套：下行绿/上行蓝）
        if text == '下行':
            item.setForeground(QColor(CLR('ok')))
        elif text == '上行':
            item.setForeground(QColor(CLR('accent2')))
    if age > 180:
        item.setForeground(QColor(CLR('faint')))


def initDecodeTable(table: 'QTableWidget') -> None:
    """把一张表配成标准的解码列表（列名、只读、整行选、列宽策略）。"""
    table.setColumnCount(len(DECODE_COLUMNS))
    table.setHorizontalHeaderLabels(DECODE_COLUMNS)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(DECODE_STRETCH_COL, QHeaderView.Stretch)
    table.verticalHeader().setVisible(False)


class CurrentPanel(QWidget):
    """当前 10 分钟内的全部解码记录。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.records = []  # [(timestamp, dict), ...]
        self.lock = False

        self.table = QTableWidget(0, len(DECODE_COLUMNS))
        initDecodeTable(self.table)
        layout.addWidget(self.table)
        self.table.doubleClicked.connect(self._onDoubleClicked)

    def addRecord(self, d: dict):
        """添加或替换一条解码记录。

        v2.1：同一 uid（同一次发射被更优记录替换）走就地更新，不新增行。
        """
        ts = d.get('timestamp', time.time())
        uid = str(d.get('uid') or '')
        if uid:
            for i, (t, r) in enumerate(self.records):
                if str(r.get('uid') or '') == uid:
                    self.records[i] = (t, d)
                    self.refresh()
                    return
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
            age = now - ts
            # 无车次信息的报文: 整行标红
            isInvalid = (d.get('train', '----') in ('----', '', '未知')
                         and d.get('baseTrain', '----') in ('----', ''))
            for col, text in enumerate(decodeRowValues(d)):
                item = QTableWidgetItem(str(text))
                styleDecodeItem(item, col, text, invalid=isInvalid, age=age)
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
        latitude REAL,
        longitude REAL,
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
        etaStatus TEXT,
        uid TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_time ON records(timestamp);
    CREATE INDEX IF NOT EXISTS idx_train ON records(train);
    """

    # 历史库结构版本：1 = v2.1（uid 去重）
    _SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._initDb()

    def _initDb(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self._CREATE_SQL)
            # 老版本数据库迁移: 补充经纬度列
            cols = {r[1] for r in conn.execute('PRAGMA table_info(records)')}
            if 'latitude' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN latitude REAL')
            if 'longitude' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN longitude REAL')
            if 'uid' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN uid TEXT')
            conn.commit()
            ver = conn.execute('PRAGMA user_version').fetchone()[0]
            if ver < self._SCHEMA_VERSION:
                self._migrateV21(conn)
                conn.execute(f'PRAGMA user_version = {self._SCHEMA_VERSION}')
                conn.commit()

    def _migrateV21(self, conn):
        """v2.1 迁移：为旧记录补 uid，并清理同一车次同一秒的重复行。

        旧版本会因 POCSAG 重复解码而在库里留下 2~4 条同秒记录，
        这里按“详细报文 > 有坐标 > 无 BCH 错 > RSSI 高”保留最优一条。
        """
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uid ON records(uid)")
            conn.execute(
                "UPDATE records SET uid = COALESCE(NULLIF(train,''),'NA') || '-' ||"
                " substr(COALESCE(timeStr,''),1,19) || '-' || id "
                "WHERE uid IS NULL OR uid = ''")
            before = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            conn.execute("""
                DELETE FROM records WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(NULLIF(train,''),'NA'),
                                         substr(COALESCE(timeStr,''),1,19)
                            ORDER BY isDetailed DESC,
                                     (latitude IS NOT NULL) DESC,
                                     msgTypeError ASC,
                                     rssi DESC,
                                     id ASC
                        ) AS rn FROM records
                    ) WHERE rn = 1
                )
            """)
            after = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            self.lastMigrated = max(0, before - after)
        except Exception:
            # 迁移失败不影响正常使用（例如老 SQLite 不支持窗口函数）
            self.lastMigrated = 0

    @staticmethod
    def _values(d: dict) -> list:
        """把解码结果字典摊平成与 SQL 列顺序一致的列表。"""
        return [
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
            d.get('latitude'), d.get('longitude'), d.get('uid', ''),
        ]

    _INSERT_COLS = """timestamp, timeStr, train, baseTrain, prefix, direction, speed, position,
            loco, locoCode, route, category, isDetailed, routeValid, msgTypeError,
            rawAddr, rawFunc, rawBcd, rawCodewords, rawIsShort, rawIsMerged, rawIsStandalone,
            rssi, afcHz, afcErrHz, afcScore, etaSeconds, etaTime, etaDistanceKm, etaStatus,
            latitude, longitude, uid"""

    def insert(self, d: dict) -> str:
        """写入一条解码记录。

        带 uid 且库中已存在时执行 UPDATE（同一车次窗口内被更优记录替换），
        返回 'inserted' / 'updated' / 'failed'。
        """
        uid = str(d.get('uid') or '')
        cols = [c.strip() for c in self._INSERT_COLS.replace('\n', ' ').split(',')]
        vals = self._values(d)
        try:
            with sqlite3.connect(self.db_path) as conn:
                if uid:
                    row = conn.execute('SELECT id FROM records WHERE uid = ?',
                                       (uid,)).fetchone()
                    if row:
                        sets = ', '.join(f'{c} = ?' for c in cols)
                        conn.execute(f'UPDATE records SET {sets} WHERE id = ?',
                                     vals + [row[0]])
                        return 'updated'
                marks = ','.join(['?'] * len(cols))
                conn.execute(f'INSERT INTO records ({self._INSERT_COLS}) '
                             f'VALUES ({marks})', vals)
            return 'inserted'
        except Exception:
            return 'failed'

    def queryRecent(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """查询最近的记录（含 id 供详情查询）。"""
        sql = """
        SELECT id, timeStr, train, direction, speed, position, route, loco, category,
               isDetailed, rawBcd, rawAddr, rawFunc, etaTime, etaDistanceKm
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
                   '报文类型', '地址', '功能码', 'BCD', '信号强度', 'AFC', 'FERR', '置信度',
                   '经度', '纬度']
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
                        r.get('longitude', ''), r.get('latitude', ''),
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
        titleLabel.setStyleSheet(f'color: {CLR("accent")}; font-size: 18px; font-weight: bold;')
        titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titleLabel)

        # ===== 2. 图片区域 =====
        self._imageLabel = QLabel('图片加载中...')
        self._imageLabel.setAlignment(Qt.AlignCenter)
        self._imageLabel.setMinimumHeight(260)
        self._imageLabel.setStyleSheet(
            f'color: {CLR("faint")}; font-size: 12px; '
            f'background-color: {CLR("status")}; border: 1px solid {CLR("border")}; border-radius: 4px;')
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
            lab.setStyleSheet(f'color: {CLR("accent")}; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet(f'color: {CLR("text")}; font-size: 12px;')
            val.setWordWrap(True)
            infoGrid.addWidget(lab, r, c * 2)
            infoGrid.addWidget(val, r, c * 2 + 1)

        brief = self._loco_info.get('brief', '')
        if brief:
            briefLab = QLabel('简介:')
            briefLab.setStyleSheet(f'color: {CLR("accent")}; font-weight: bold; font-size: 12px;')
            briefVal = QLabel(brief)
            briefVal.setStyleSheet(f'color: {CLR("text")}; font-size: 12px;')
            briefVal.setWordWrap(True)
            infoGrid.addWidget(briefLab, 3, 0)
            infoGrid.addWidget(briefVal, 3, 1, 1, 3)

        layout.addWidget(infoGroup)

        # ===== 4. 来源标注 =====
        sourceBox = QFrame()
        sourceBox.setStyleSheet(
            f'QFrame {{ background-color: {CLR("panel")}; border: 1px solid {CLR("border")}; border-radius: 4px; }}')
        sourceLayout = QHBoxLayout(sourceBox)
        sourceLayout.setContentsMargins(8, 6, 8, 6)
        sourceIcon = QLabel('📷')
        sourceIcon.setStyleSheet('font-size: 14px; border: none; background: transparent;')
        sourceText = QLabel(
            f'<span style="color:#aaa;">图片与数据来源:</span> '
            f'<a href="{self._loco_info.get("sourceUrl", "")}" '
            f'style="color:{CLR("accent2")}; text-decoration:none;">'
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
            ('经度', f"{record.get('longitude'):.6f}" if isinstance(record.get('longitude'), (int, float)) else '----'),
            ('纬度', f"{record.get('latitude'):.6f}" if isinstance(record.get('latitude'), (int, float)) else '----'),
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
            lab.setStyleSheet(f'color: {CLR("accent")}; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet(f'color: {CLR("text")}; font-size: 12px;')
            val.setWordWrap(True)
            resultGrid.addWidget(lab, r, c * 2)
            resultGrid.addWidget(val, r, c * 2 + 1)

        # 机车简介（左侧文字 + 右侧"机车详情"按钮，类似 12306 时刻表按钮）
        loco_row = (len(result_items) + 1) // 2
        loco_intro = QLabel('机车简介:')
        loco_intro.setStyleSheet(f'color: {CLR("accent")}; font-weight: bold; font-size: 12px;')
        self._locoIntroLabel = QLabel('')
        self._locoIntroLabel.setStyleSheet(
            f'color: {CLR("text")}; font-size: 11px; padding: 3px; '
            f'background-color: {CLR("panel")}; border-radius: 3px;')
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
        self._locoDetailBtn = K.small_button('机车详情', h=24, px=11)
        self._locoDetailBtn.setEnabled(bool(loco_info))
        self._locoDetailBtn.clicked.connect(self._openLocoDetail)
        resultGrid.addWidget(loco_intro, loco_row, 0)
        resultGrid.addWidget(self._locoIntroLabel, loco_row, 1, 1, 2)
        resultGrid.addWidget(self._locoDetailBtn, loco_row, 3)

        # 12306 查询结果（仅详细报文查询，放在机车简介下一行）
        row = loco_row + 1
        self._trainQueryLabel = QLabel('12306: 查询中...')
        self._trainQueryLabel.setStyleSheet(
            f'color: {CLR("accent2")}; font-size: 11px; font-weight: bold; padding: 2px;')
        self._trainQueryLabel.setWordWrap(True)
        self._trainQueryBtn = K.small_button('时刻表', h=24, px=11)
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
            self._trainQueryLabel.setStyleSheet(f'color: {CLR("faint")}; font-size: 11px;')

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
            lab.setStyleSheet(f'color: {CLR("warn")}; font-weight: bold; font-size: 12px;')
            val = QLabel(str(v))
            val.setStyleSheet(f'color: {CLR("text")}; font-size: 12px;')
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
            f'background-color: {CLR("status")}; color: {CLR("ok")}; border: 1px solid {CLR("border")};')
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
            f'background-color: {CLR("status")}; color: {CLR("dim")}; border: 1px solid {CLR("border")};')
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
                f'background-color: {CLR("status")}; color: {CLR("warn")}; border: 1px solid {CLR("border")};')
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
        mapBtn = QPushButton('在地图中查看')
        hasCoord = isinstance(record.get('latitude'), (int, float)) and \
            isinstance(record.get('longitude'), (int, float))
        mapBtn.setEnabled(hasCoord)
        mapBtn.clicked.connect(lambda: self._openMap(record))
        btnLayout.addWidget(mapBtn)
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)

    def _openMap(self, record: dict):
        """用高德 URI API 在浏览器中定位该列车。"""
        lat = record.get('latitude')
        lon = record.get('longitude')
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        name = f"{record.get('train', '列车')} {record.get('timeStr', '')}".strip()
        enc = QUrl.toPercentEncoding(name).data().decode()
        url = (f'https://uri.amap.com/marker?position={lon:.6f},{lat:.6f}'
               f'&name={enc}&src=crlbj&coordinate=gaode&callnative=1')
        QDesktopServices.openUrl(QUrl(url))

    def _startTrainQuery(self, record: dict):
        """启动后台 12306 查询。"""
        train = record.get('train', '')
        if not train or train == '----':
            self._trainQueryLabel.setText('无车次')
            self._trainQueryLabel.setStyleSheet(f'color: {CLR("faint")}; font-size: 11px;')
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
            f'color: {CLR("accent")}; font-size: 11px; font-weight: bold; padding: 2px;')
        self._trainQueryBtn.setEnabled(True)

    def _onTrainQueryFailed(self, err: str):
        if '网络' in err or 'URLError' in err:
            self._trainQueryLabel.setText('此功能需连接互联网使用')
            self._trainQueryLabel.setStyleSheet(f'color: {CLR("err")}; font-size: 11px;')
        else:
            self._trainQueryLabel.setText(err)
            self._trainQueryLabel.setStyleSheet(f'color: {CLR("warn")}; font-size: 11px;')

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
        lat = record.get('latitude')
        lon = record.get('longitude')
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            lines.append(f'  经度:   {lon:.6f} (WGS-84)')
            lines.append(f'  纬度:   {lat:.6f} (WGS-84)')
            lines.append('  说明:   长报文字符 30..38 经度 / 39..46 纬度，'
                         '格式为“度 + 分/60”')

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
        self._reloadPending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        self.refreshBtn = K.small_button('刷新', h=28, px=12)
        self.clearBtn = K.small_button('清空', h=28, px=12)
        self.exportBtn = K.small_button('导出 CSV...', h=28, px=12)
        self.countLabel = QLabel('0 条')
        self.countLabel.setStyleSheet(f'background: transparent; color: {CLR("faint")};')
        toolbar.addWidget(self.refreshBtn)
        toolbar.addWidget(self.clearBtn)
        toolbar.addWidget(self.exportBtn)
        toolbar.addStretch()
        toolbar.addWidget(self.countLabel)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(DECODE_COLUMNS))
        initDecodeTable(self.table)
        layout.addWidget(self.table)

        self.refreshBtn.clicked.connect(self.loadFromDb)
        self.clearBtn.clicked.connect(self.clearDb)
        self.exportBtn.clicked.connect(self.exportCsv)
        self.table.doubleClicked.connect(self._onDoubleClicked)

    def addRecord(self, d: dict):
        """写入一条记录；若为窗口内择优替换，1.2 秒后刷新表格。"""
        res = self.db.insert(d)
        if res == 'updated' and self.isVisible() and not self._reloadPending:
            self._reloadPending = True
            QTimer.singleShot(1200, self._reloadIfNeeded)

    def _reloadIfNeeded(self):
        self._reloadPending = False
        if self.isVisible():
            self.loadFromDb()

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
                for col, val in enumerate(decodeRowValues(r)):
                    item = QTableWidgetItem(str(val))
                    styleDecodeItem(item, col, val)
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
def default_sources(cfg: CoreConfig) -> List[Dict[str, Any]]:
    """首次运行时给出的数据源预设。"""
    base = {'sampleRate': cfg.sampleRate, 'gainDb': cfg.gainDb,
            'ppm': cfg.ppm}
    return [
        dict(base, name='本机 RTL-SDR (USB 自动)', type='rtl_usb',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='本地 rtl_tcp', type='rtl_tcp',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='OWRX 服务器', type='owrx',
             host='127.0.0.1', port=8073, dcOffsetHz=0.0),
    ]


SOURCE_TYPE_LABELS = [
    ('本机 USB (自动启动 rtl_tcp)', 'rtl_usb'),
    ('局域网 / 本地 RTL-TCP', 'rtl_tcp'),
    ('OWRX (OpenWebRX)', 'owrx'),
]


class DeviceDetectThread(QThread):
    """后台检测 RTL-SDR 设备，避免阻塞界面。"""

    done = Signal(bool, str)

    def run(self):
        try:
            ok, msg = detect_rtl_devices(10.0)
        except Exception as e:
            ok, msg = False, str(e)
        self.done.emit(ok, msg)


class SourceEditDialog(QDialog):
    """新增/编辑一个数据源配置。"""

    def __init__(self, source: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('数据源配置')
        self.setMinimumWidth(460)
        src = dict(source or {})
        form = QFormLayout(self)

        self.nameEdit = QLineEdit(src.get('name', '新数据源'))
        self.typeCombo = QComboBox()
        for label, val in SOURCE_TYPE_LABELS:
            self.typeCombo.addItem(label, val)
        idx = self.typeCombo.findData(src.get('type', 'rtl_tcp'))
        self.typeCombo.setCurrentIndex(max(0, idx))

        self.hostEdit = QLineEdit(src.get('host', '127.0.0.1'))
        self.portSpin = QSpinBox()
        self.portSpin.setRange(1, 65535)
        self.portSpin.setValue(int(src.get('port', 1234)))

        self.srCombo = QComboBox()
        for sr in [480000, 960000, 1920000, 2048000, 2400000, 2880000]:
            self.srCombo.addItem(f'{sr // 1000} kS/s', sr)
        i = self.srCombo.findData(int(src.get('sampleRate', 960000)))
        self.srCombo.setCurrentIndex(max(0, i))

        self.gainSpin = QDoubleSpinBox()
        self.gainSpin.setRange(0.0, 50.0)
        self.gainSpin.setDecimals(1)
        self.gainSpin.setSuffix(' dB')
        self.gainSpin.setValue(float(src.get('gainDb', 15.7)))

        self.ppmSpin = QSpinBox()
        self.ppmSpin.setRange(-200, 200)
        self.ppmSpin.setSuffix(' ppm')
        self.ppmSpin.setValue(int(src.get('ppm', 1)))

        self.dcSpin = QDoubleSpinBox()
        self.dcSpin.setRange(-500000, 500000)
        self.dcSpin.setDecimals(0)
        self.dcSpin.setSuffix(' Hz')
        self.dcSpin.setValue(float(src.get('dcOffsetHz', 50000.0)))

        form.addRow('名称:', self.nameEdit)
        form.addRow('类型:', self.typeCombo)
        form.addRow('主机:', self.hostEdit)
        form.addRow('端口:', self.portSpin)
        form.addRow('采样率:', self.srCombo)
        form.addRow('增益:', self.gainSpin)
        form.addRow('PPM:', self.ppmSpin)
        form.addRow('DC 偏移:', self.dcSpin)

        btns = QHBoxLayout()
        btns.addStretch()
        ok = K.button('确定', primary=True)
        ok.clicked.connect(self.accept)
        cancel = K.button('取消')
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow('', btns)

        self.typeCombo.currentIndexChanged.connect(self._onType)
        self._onType()

    def _onType(self):
        t = self.typeCombo.currentData()
        if t == 'rtl_usb':
            self.hostEdit.setText('127.0.0.1')
            if self.dcSpin.value() < 1:
                self.dcSpin.setValue(50000)
        elif t == 'owrx':
            self.dcSpin.setValue(0)
        elif self.dcSpin.value() < 1:
            self.dcSpin.setValue(50000)

    def getSource(self) -> dict:
        return {
            'name': self.nameEdit.text().strip() or '数据源',
            'type': self.typeCombo.currentData(),
            'host': self.hostEdit.text().strip() or '127.0.0.1',
            'port': self.portSpin.value(),
            'sampleRate': self.srCombo.currentData() or 960000,
            'gainDb': self.gainSpin.value(),
            'ppm': float(self.ppmSpin.value()),
            'dcOffsetHz': self.dcSpin.value(),
        }


class ConfigPanel(QWidget):
    """配置面板：基于 CoreConfig 编辑，分组 2 列网格布局。"""

    configChanged = Signal()

    def __init__(self, config: CoreConfig):
        super().__init__()
        self.config = config
        self._updating_mode = False
        self._sources: List[Dict[str, Any]] = [
            dict(s) for s in (getattr(config, 'sources', None) or []) if isinstance(s, dict)]
        if not self._sources:
            self._sources = default_sources(config)
        self._activeSource = int(getattr(config, 'activeSource', 0) or 0)
        if not (0 <= self._activeSource < len(self._sources)):
            self._activeSource = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        outer.setSpacing(6)

        # ---- 分类页签：配置项按用途分开，不再是一条长滚动条 ----
        self.cfgTabs = QTabWidget()
        self._tabPages = {}

        def page(name: str) -> QVBoxLayout:
            """取/建一个分类页，返回它的布局。"""
            if name not in self._tabPages:
                w = QWidget()
                lay = QVBoxLayout(w)
                lay.setContentsMargins(spx(10), spx(10), spx(10), spx(8))
                lay.setSpacing(spx(6))
                self.cfgTabs.addTab(w, name)
                self._tabPages[name] = (w, lay)
            return self._tabPages[name][1]

        self._page = page

        # ---- 数据源管理 ----
        srcGroup = QGroupBox('数据源（可保存多套，随时切换）')
        srcGrid = QGridLayout(srcGroup)
        srcGrid.setSpacing(4)
        srcGrid.setContentsMargins(8, 16, 8, 4)

        self.sourceCombo = QComboBox()
        self.sourceCombo.setMinimumWidth(200)
        self.sourceCombo.currentIndexChanged.connect(self._onSourceSelected)
        self.srcTypeCombo = QComboBox()
        for label, val in SOURCE_TYPE_LABELS:
            self.srcTypeCombo.addItem(label, val)
        self.srcTypeCombo.currentIndexChanged.connect(self._onSourceTypeChanged)

        self.devIndexSpin = QSpinBox()
        self.devIndexSpin.setRange(0, 15)
        self.devIndexSpin.setValue(int(getattr(config, 'rtlDeviceIndex', 0) or 0))
        self.devIndexSpin.setToolTip('多支 RTL-SDR 时选择设备序号 (0 为第一支)')

        self.rtlPathEdit = QLineEdit(getattr(config, 'rtlTcpPath', '') or '')
        self.rtlPathEdit.setPlaceholderText('留空自动查找 rtl_tcp.exe')
        pathBtn = K.small_button('浏览', h=26, px=11.5)
        pathBtn.clicked.connect(self._browseRtlTcp)

        self.srcAddBtn = K.small_button('新增', h=26, px=11.5)
        self.srcEditBtn = K.small_button('编辑', h=26, px=11.5)
        self.srcDelBtn = K.small_button('删除', h=26, px=11.5)
        self.srcDetectBtn = K.small_button('检测设备', h=26, px=11.5)
        self.srcAddBtn.clicked.connect(self._addSource)
        self.srcEditBtn.clicked.connect(self._editSource)
        self.srcDelBtn.clicked.connect(self._delSource)
        self.srcDetectBtn.clicked.connect(self._detectDevice)

        srcGrid.addWidget(QLabel('已保存:'), 0, 0)
        srcGrid.addWidget(self.sourceCombo, 0, 1, 1, 2)
        srcGrid.addWidget(self.srcEditBtn, 0, 3)
        srcGrid.addWidget(self.srcAddBtn, 0, 4)
        srcGrid.addWidget(self.srcDelBtn, 0, 5)
        srcGrid.addWidget(QLabel('类型:'), 1, 0)
        srcGrid.addWidget(self.srcTypeCombo, 1, 1, 1, 2)
        srcGrid.addWidget(QLabel('设备序号:'), 1, 3)
        srcGrid.addWidget(self.devIndexSpin, 1, 4)
        srcGrid.addWidget(self.srcDetectBtn, 1, 5)
        srcGrid.addWidget(QLabel('rtl_tcp 路径:'), 2, 0)
        srcGrid.addWidget(self.rtlPathEdit, 2, 1, 1, 4)
        srcGrid.addWidget(pathBtn, 2, 5)
        srcGrid.setColumnStretch(1, 1)
        page('数据源配置').addWidget(srcGroup)

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

        self.dcSpin = QDoubleSpinBox()
        self.dcSpin.setRange(-500000, 500000)
        self.dcSpin.setDecimals(0)
        self.dcSpin.setSuffix(' Hz')
        self.dcSpin.setValue(config.dcOffsetHz)

        connForm.addRow('主机:', self.hostEdit)
        connForm.addRow('端口:', self.portSpin)
        connForm.addRow('采样率:', self.srCombo)
        connForm.addRow('块大小:', self.blockSpin)
        connForm.addRow('DC 偏移:', self.dcSpin)

        page('数据源配置').addWidget(connGroup)

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

        page('射频设置').addWidget(rfGroup)

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

        page('射频设置').addWidget(rssiGroup)

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

        page('射频设置').addWidget(afcGroup)

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

        page('到达估算').addWidget(etaGroup)

        # ---- 地图 + 车次规则 ----
        mapGroup = QGroupBox('地图与车次规则')
        mapForm = QFormLayout(mapGroup)
        mapForm.setSpacing(4)
        mapForm.setContentsMargins(8, 16, 8, 4)

        self.amapKeyEdit = QLineEdit(getattr(config, 'amapKey', '') or '')
        self.amapKeyEdit.setPlaceholderText('Web端(JS API) Key')
        self.amapSecEdit = QLineEdit(getattr(config, 'amapSecurity', '') or '')
        self.amapSecEdit.setPlaceholderText('安全密钥 securityJsCode')
        self.amapSecEdit.setEchoMode(QLineEdit.Password)
        self.mapCenterEdit = QLineEdit(getattr(config, 'mapCenterAddress', '') or '')
        self.mapCenterEdit.setPlaceholderText('地名即可，如：南昌站 / 向塘站 / 鹰潭东')
        self.mapCenterEdit.setClearButtonEnabled(True)
        self.mapZoomSpin = QSpinBox()
        self.mapZoomSpin.setRange(3, 18)
        self.mapZoomSpin.setValue(int(getattr(config, 'mapZoom', 12) or 12))
        self.mapFollowCheck = QCheckBox('自动跟随最新列车')
        self.mapFollowCheck.setChecked(bool(getattr(config, 'mapFollow', True)))
        self.mapTrailCheck = QCheckBox('显示历史轨迹（最近 12 点）')
        self.mapTrailCheck.setChecked(bool(getattr(config, 'mapShowTrail', True)))
        self.mapNightCheck = QCheckBox('地图夜间模式（深色底图）')
        self.mapNightCheck.setChecked(bool(getattr(config, 'mapNight', True)))
        self.trainSchemeCombo = QComboBox()
        self.trainSchemeCombo.addItem('自动兼容（按速度区分新旧）', 'auto')
        self.trainSchemeCombo.addItem('2026 新版（全部按新规则）', '2026')
        self.trainSchemeCombo.addItem('2014 旧版（过渡期兼容）', 'legacy')
        si = self.trainSchemeCombo.findData(getattr(config, 'trainScheme', 'auto'))
        self.trainSchemeCombo.setCurrentIndex(max(0, si))

        mapForm.addRow('高德 Key:', self.amapKeyEdit)
        mapForm.addRow('安全密钥:', self.amapSecEdit)
        mapForm.addRow('默认中心:', self.mapCenterEdit)
        mapForm.addRow('默认缩放:', self.mapZoomSpin)
        mapForm.addRow('', self.mapFollowCheck)
        mapForm.addRow('', self.mapTrailCheck)
        mapForm.addRow('', self.mapNightCheck)
        mapForm.addRow('车次规则:', self.trainSchemeCombo)
        hint = QLabel('Key 申请：console.amap.com → 应用管理 → 新建 Key（服务平台选 Web端 JS API）。'
                      '「默认中心」填地名即可（如 南昌站），启动时用高德地理编码解析后把视图挪过去，'
                      '不添加任何标记点；留空则显示全国概览。'
                      '详细用法见“帮助 → 使用手册 → 高德地图”。')
        hint.setWordWrap(True)
        hint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')
        mapForm.addRow('', hint)
        page('地图与车次').addWidget(mapGroup)

        # ---- 解码与界面 ----
        miscGroup = QGroupBox('解码与界面')
        miscForm = QFormLayout(miscGroup)
        miscForm.setSpacing(4)
        miscForm.setContentsMargins(8, 16, 8, 4)

        self.dedupeSpin = QDoubleSpinBox()
        self.dedupeSpin.setRange(0.0, 10.0)
        self.dedupeSpin.setSingleStep(0.5)
        self.dedupeSpin.setDecimals(1)
        self.dedupeSpin.setSuffix(' 秒')
        self.dedupeSpin.setValue(float(getattr(config, 'dedupeWindow', 2.5) or 0.0))
        self.dedupeSpin.setToolTip(
            '同一车次在此时间内的重复报文只保留最优一条；0 表示关闭去重')

        self.uiScaleCombo = QComboBox()
        for label, val in (('自动（按屏幕）', 0.0), ('85%', 0.85), ('100%', 1.0),
                           ('115%', 1.15), ('130%', 1.3), ('150%', 1.5)):
            self.uiScaleCombo.addItem(label, val)
        curScale = float(getattr(config, 'uiScale', 0.0) or 0.0)
        si2 = self.uiScaleCombo.findData(curScale)
        self.uiScaleCombo.setCurrentIndex(si2 if si2 >= 0 else 0)

        miscForm.addRow('重复报文合并:', self.dedupeSpin)
        miscForm.addRow('界面缩放:', self.uiScaleCombo)
        hint2 = QLabel('重复报文合并可消除同一秒的多条记录；'
                       '界面缩放需重启程序生效。')
        hint2.setWordWrap(True)
        hint2.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')
        miscForm.addRow('', hint2)
        page('解码与界面').addWidget(miscGroup)

        # ---- 外观主题 ----
        themeGroup = QGroupBox('外观主题（中国铁路标准色）')
        themeForm = QFormLayout(themeGroup)
        themeForm.setSpacing(4)
        themeForm.setContentsMargins(8, 16, 8, 4)
        self.themeCombo = QComboBox()
        self.themeCombo.addItem('夜间（深色）', 'dark')
        self.themeCombo.addItem('日间（浅色）', 'light')
        self.themeCombo.addItem('跟随系统', 'auto')
        curTheme = str(getattr(config, 'theme', 'dark') or 'dark')
        ti = self.themeCombo.findData(curTheme)
        self.themeCombo.setCurrentIndex(ti if ti >= 0 else 0)
        themeForm.addRow('主题:', self.themeCombo)
        swatch = QLabel(
            '<span style="color:#DA291C; font-size:16px;">■</span> 主色 Pantone 485C'
            '　<span style="color:#003DA5; font-size:16px;">■</span> 辅助色 Pantone 286C')
        themeForm.addRow('', swatch)
        themeHint = QLabel('「跟随系统」读取 Windows 的浅色/深色应用模式；'
                           '主题与界面缩放一样需要重启程序生效。')
        themeHint.setWordWrap(True)
        themeHint.setStyleSheet(f'color: {CLR("dim")}; font-size: {spx(11)}px;')
        themeForm.addRow('', themeHint)
        page('外观主题').addWidget(themeGroup)

        # 给所有分类页补一个底部弹簧，内容靠上
        for _w, _lay in self._tabPages.values():
            _lay.addStretch()

        outer.addWidget(self.cfgTabs, 1)

        # ---- 按钮 ----
        btnLayout = QHBoxLayout()
        self.saveBtn = K.button('保存配置', primary=True)
        self.hotBtn = K.button('热更新 (不重启)')
        self.restartBtn = K.button('应用并重启 DSP')
        btnLayout.addWidget(self.saveBtn)
        btnLayout.addWidget(self.hotBtn)
        btnLayout.addWidget(self.restartBtn)
        outer.addLayout(btnLayout)

        self.saveBtn.clicked.connect(self._save)
        self.hotBtn.clicked.connect(self._hotUpdate)
        self.restartBtn.clicked.connect(self._restart)
        self._refreshSourceCombo()

    # ---- 数据源管理 ----
    def _refreshSourceCombo(self):
        self.sourceCombo.blockSignals(True)
        self.sourceCombo.clear()
        for s in self._sources:
            tag = {'rtl_usb': 'USB', 'rtl_tcp': 'TCP', 'owrx': 'OWRX'}.get(
                s.get('type', 'rtl_tcp'), '?')
            self.sourceCombo.addItem(f"{s.get('name', '数据源')}  [{tag}]")
        self.sourceCombo.setCurrentIndex(self._activeSource)
        self.sourceCombo.blockSignals(False)
        self._loadSourceToFields()

    def _loadSourceToFields(self):
        if not (0 <= self._activeSource < len(self._sources)):
            return
        src = self._sources[self._activeSource]
        self._updating_mode = True
        try:
            self.hostEdit.setText(str(src.get('host', '127.0.0.1')))
            self.portSpin.setValue(int(src.get('port', 1234)))
            sr = int(src.get('sampleRate', 960000))
            idx = self.srCombo.findData(sr)
            if idx < 0:
                self.srCombo.addItem(f'{sr // 1000} kS/s', sr)
                idx = self.srCombo.count() - 1
            self.srCombo.setCurrentIndex(idx)
            self.gainSpin.setValue(float(src.get('gainDb', 15.7)))
            self.ppmSpin.setValue(int(src.get('ppm', 1)))
            self.dcSpin.setValue(float(src.get('dcOffsetHz', 0.0)))
            ti = self.srcTypeCombo.findData(src.get('type', 'rtl_tcp'))
            self.srcTypeCombo.setCurrentIndex(max(0, ti))
        finally:
            self._updating_mode = False

    def _storeFieldsToSource(self, idx: int):
        if not (0 <= idx < len(self._sources)):
            return
        src = self._sources[idx]
        src.update({
            'host': self.hostEdit.text().strip() or '127.0.0.1',
            'port': self.portSpin.value(),
            'sampleRate': self.srCombo.currentData() or 960000,
            'gainDb': self.gainSpin.value(),
            'ppm': float(self.ppmSpin.value()),
            'dcOffsetHz': self.dcSpin.value(),
            'type': self.srcTypeCombo.currentData(),
        })

    def _onSourceSelected(self, index: int):
        if index < 0 or index == self._activeSource:
            return
        self._storeFieldsToSource(self._activeSource)
        self._activeSource = index
        self._loadSourceToFields()

    def _onSourceTypeChanged(self):
        if self._updating_mode:
            return
        t = self.srcTypeCombo.currentData()
        if t == 'rtl_usb':
            self.hostEdit.setText('127.0.0.1')
            if abs(self.dcSpin.value()) < 1:
                self.dcSpin.setValue(50000)
        elif t == 'owrx':
            self.dcSpin.setValue(0)
        elif abs(self.dcSpin.value()) < 1:
            self.dcSpin.setValue(50000)
        self._storeFieldsToSource(self._activeSource)

    def _browseRtlTcp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 rtl_tcp.exe', os.path.dirname(self.rtlPathEdit.text() or '.'),
            'rtl_tcp (rtl_tcp.exe);;可执行文件 (*.exe);;所有文件 (*)')
        if path:
            self.rtlPathEdit.setText(path)

    def _addSource(self):
        dlg = SourceEditDialog(None, self)
        if dlg.exec() == QDialog.Accepted:
            self._storeFieldsToSource(self._activeSource)
            self._sources.append(dlg.getSource())
            self._activeSource = len(self._sources) - 1
            self._refreshSourceCombo()

    def _editSource(self):
        dlg = SourceEditDialog(self._sources[self._activeSource], self)
        if dlg.exec() == QDialog.Accepted:
            self._sources[self._activeSource] = dlg.getSource()
            self._refreshSourceCombo()

    def _delSource(self):
        if len(self._sources) <= 1:
            QMessageBox.information(self, '提示', '至少保留一个数据源。')
            return
        if QMessageBox.question(self, '删除数据源',
                                f'确定删除“{self._sources[self._activeSource].get("name")}”？'
                                ) != QMessageBox.Yes:
            return
        self._sources.pop(self._activeSource)
        self._activeSource = max(0, self._activeSource - 1)
        self._refreshSourceCombo()

    def _detectDevice(self):
        self.srcDetectBtn.setEnabled(False)
        self.srcDetectBtn.setText('检测中...')
        self._detectThread = DeviceDetectThread(self)
        self._detectThread.done.connect(self._onDetectDone)
        self._detectThread.start()

    def _onDetectDone(self, ok: bool, msg: str):
        self.srcDetectBtn.setEnabled(True)
        self.srcDetectBtn.setText('检测设备')
        box = QMessageBox(self)
        box.setWindowTitle('RTL-SDR 设备检测')
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        box.setText('已找到 RTL-SDR 设备' if ok else '未检测到可用设备')
        box.setInformativeText('可直接选择“本机 USB (自动启动 rtl_tcp)”数据源。'
                               if ok else '请检查 USB 连接与 WinUSB 驱动（Zadig）。')
        box.setDetailedText(msg[-3000:] if msg else '(无输出)')
        box.exec()

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
            # ---- 数据源 ----
            self._storeFieldsToSource(self._activeSource)
            cfg.sources = [dict(s) for s in self._sources]
            cfg.activeSource = int(self._activeSource)
            active = cfg.sources[self._activeSource]
            cfg.sourceType = active.get('type', 'rtl_tcp')
            cfg.owrxMode = (cfg.sourceType == 'owrx')
            cfg.rtlTcpPath = self.rtlPathEdit.text().strip()
            cfg.rtlDeviceIndex = self.devIndexSpin.value()
            # ---- 地图与车次规则 ----
            cfg.amapKey = self.amapKeyEdit.text().strip()
            cfg.amapSecurity = self.amapSecEdit.text().strip()
            newAddr = self.mapCenterEdit.text().strip()
            if newAddr != str(getattr(self.config, 'mapCenterAddress', '') or ''):
                # 地名变了，旧的解析缓存作废，下次启动重新地理编码
                cfg.mapCenterLng = 0.0
                cfg.mapCenterLat = 0.0
            else:
                cfg.mapCenterLng = float(getattr(self.config, 'mapCenterLng', 0.0) or 0.0)
                cfg.mapCenterLat = float(getattr(self.config, 'mapCenterLat', 0.0) or 0.0)
            cfg.mapCenterAddress = newAddr
            cfg.mapZoom = self.mapZoomSpin.value()
            cfg.mapFollow = self.mapFollowCheck.isChecked()
            cfg.mapShowTrail = self.mapTrailCheck.isChecked()
            cfg.mapNight = self.mapNightCheck.isChecked()
            cfg.trainScheme = self.trainSchemeCombo.currentData() or 'auto'
            # ---- 解码与界面 ----
            cfg.dedupeWindow = float(self.dedupeSpin.value())
            cfg.uiScale = float(self.uiScaleCombo.currentData() or 0.0)
            cfg.theme = str(self.themeCombo.currentData() or 'dark')
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
        self.setMinimumSize(760, 640)
        self.resize(860, 760)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        self.panel = ConfigPanel(config)
        self.panel.saveBtn.hide()
        self.panel.hotBtn.hide()
        self.panel.restartBtn.hide()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.panel)
        layout.addWidget(scroll, 1)
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        okBtn = K.button('确定', primary=True)
        okBtn.clicked.connect(self._onOk)
        cancelBtn = K.button('取消')
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
class LogBus(QObject):
    """日志中枢 (v2.1)：集中保存自启动以来的全部日志。

    界面底部只显示最新一条；「帮助 → 实时日志」里看完整输出。
    保留 appendLog() 方法签名，旧的调用点无需改动。
    """

    lineAdded = Signal(str, str)   # (带时间戳的整行, 级别)
    cleared = Signal()

    def __init__(self, maxLines: int = 20000, parent=None):
        super().__init__(parent)
        self.maxLines = int(maxLines)
        self._lines: List[tuple] = []      # (时间, 消息, 级别)

    @staticmethod
    def levelOf(msg: str) -> str:
        if '[错误]' in msg or '[断连]' in msg or '[问题]' in msg or '[失败]' in msg:
            return 'err'
        if '[告警]' in msg or '[警告]' in msg or '[干扰]' in msg:
            return 'warn'
        if ('[连接]' in msg or '[启动]' in msg or '[诊断]' in msg
                or '[配置]' in msg or '[链路]' in msg):
            return 'ok'
        return 'info'

    def appendLog(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        lvl = self.levelOf(msg)
        self._lines.append((ts, msg, lvl))
        if len(self._lines) > self.maxLines:
            del self._lines[:len(self._lines) - self.maxLines]
        self.lineAdded.emit(f'[{ts}] {msg}', lvl)

    # 兼容旧接口
    def append(self, msg: str):  # pragma: no cover
        self.appendLog(msg)

    def lines(self) -> List[tuple]:
        return list(self._lines)

    def latest(self):
        return self._lines[-1] if self._lines else None

    def count(self) -> int:
        return len(self._lines)

    def formatted(self, limit: int = 0) -> str:
        items = self._lines[-limit:] if limit else self._lines
        return '\n'.join(f'[{ts}] {msg}' for ts, msg, _ in items)

    def clear(self):
        self._lines.clear()
        self.cleared.emit()


# 兼容旧名字
LogPanel = LogBus


class LogWindow(QDialog):
    """实时日志窗口：显示自程序启动以来的全部日志。"""

    LEVEL_COLOR = {'err': f'{CLR("err")}', 'warn': f'{CLR("warn")}',
                   'ok': f'{CLR("ok")}', 'info': f'{CLR("text")}'}

    def __init__(self, bus: LogBus, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.setWindowTitle('实时日志 — 自启动以来的全部输出')
        self.resize(spx(900), spx(560))
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        bar = QHBoxLayout()
        self.countLabel = QLabel('0 行')
        self.countLabel.setStyleSheet(f'color: {CLR("dim")}; font-size: 12px;')
        self.autoScroll = QCheckBox('自动滚动到最新')
        self.autoScroll.setChecked(True)
        pauseBtn = QPushButton('暂停刷新')
        pauseBtn.setCheckable(True)
        pauseBtn.toggled.connect(self._onPause)
        clearBtn = QPushButton('清空记录')
        clearBtn.clicked.connect(self._onClear)
        saveBtn = QPushButton('另存为...')
        saveBtn.clicked.connect(self._onSave)
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.close)
        bar.addWidget(self.countLabel)
        bar.addStretch()
        bar.addWidget(self.autoScroll)
        bar.addWidget(pauseBtn)
        bar.addWidget(clearBtn)
        bar.addWidget(saveBtn)
        bar.addWidget(closeBtn)
        outer.addLayout(bar)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.NoWrap)
        outer.addWidget(self.text, 1)

        self._paused = False
        bus.lineAdded.connect(self._onLine)
        bus.cleared.connect(self._onCleared)
        self._reload()

    # ---- 内部 ----
    def _append(self, line: str, level: str):
        color = self.LEVEL_COLOR.get(level, f'{CLR("text")}')
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(
            '<span style="color:%s; white-space:pre">%s</span><br>'
            % (color, line.replace('&', '&amp;').replace('<', '&lt;')
                            .replace('>', '&gt;')))
        self.text.setTextCursor(cursor)
        if self.autoScroll.isChecked():
            self.text.ensureCursorVisible()

    def _reload(self):
        self.text.clear()
        for ts, msg, lvl in self.bus.lines()[-3000:]:
            self._append(f'[{ts}] {msg}', lvl)
        self.countLabel.setText(f'{self.bus.count()} 行')

    def _onLine(self, line: str, level: str):
        if self._paused:
            return
        self._append(line, level)
        self.countLabel.setText(f'{self.bus.count()} 行')

    def _onCleared(self):
        self.text.clear()
        self.countLabel.setText('0 行')

    def _onPause(self, on: bool):
        self._paused = on
        if not on:
            self._reload()

    def _onClear(self):
        if QMessageBox.question(self, '确认', '清空日志记录？此操作不可恢复。') \
                == QMessageBox.Yes:
            self.bus.clear()

    def _onSave(self):
        path, _ = QFileDialog.getSaveFileName(
            self, '保存日志',
            f'lbj_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
            'Text Files (*.txt)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.bus.formatted())
            QMessageBox.information(self, '成功', f'已保存到\n{path}')
        except Exception as e:
            QMessageBox.warning(self, '错误', f'保存失败: {e}')


# ===========================================================================
# 使用手册对话框
# ===========================================================================
class ManualDialog(QDialog):
    """使用手册对话框：传统 TCP 与 OWRX 配置说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('使用手册')
        self.resize(spx(700), spx(640))
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        contentLayout = QVBoxLayout(content)

        # ---- 传统 RTL-TCP 模式 ----
        title1 = QLabel('一、传统 RTL-TCP 模式')
        title1.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
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
        sep1.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep1)

        # ---- OWRX 模式 ----
        title2 = QLabel('二、OWRX 兼容模式')
        title2.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
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
        sep2.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep2)

        # ---- 通用说明 ----
        title3 = QLabel('三、通用说明')
        title3.setStyleSheet(f'color: {CLR("warn")}; font-size: 15px; font-weight: bold;')
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

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep3)

        # ---- 多数据源 ----
        title4 = QLabel('四、多数据源与免命令行')
        title4.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title4)
        text4 = QLabel(
            '<p>2.0 版支持保存多套数据源，在“配置 → 数据源”中切换：</p>'
            '<ul style="margin-left: 20px;">'
            '<li><b>本机 USB（自动）</b>：插上 RTL-SDR 即可，程序自动查找并启动 '
            '<code>rtl_tcp.exe</code>，退出时自动关闭，无需再开命令行。'
            '要求已用 Zadig 安装 WinUSB 驱动。</li>'
            '<li><b>RTL-TCP</b>：连接局域网或本机已有的 rtl_tcp 服务（默认 1234 端口）。</li>'
            '<li><b>OWRX</b>：连接 OpenWebRX 的 rtl_tcp 兼容端口（DC 偏移设为 0）。</li>'
            '</ul>'
            '<p>发布包已内附 <code>rtl_tcp.exe</code>、<code>rtlsdr.dll</code> 等工具，'
            '装好驱动、插上棒子就能用，无需另外安装工具包。'
            '源码运行时把它们放在项目的 <code>tools/rtl/</code> 目录即可（也兼容'
            '<code>RTL_TCP_Server</code> 子目录与 PATH）；'
            '也可在配置里手动指定路径。“检测设备”按钮会调用 '
            '<code>rtl_test -t</code> 列出本机设备。</p>'
        )
        text4.setWordWrap(True)
        text4.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text4)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.HLine)
        sep4.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep4)

        # ---- 地图 ----
        title5 = QLabel('五、高德地图与经纬度')
        title5.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title5)
        text5 = QLabel(
            '<p><b>经纬度来源：</b>只有扩展长报文（地址 1234002 / 1234001）携带经纬度；'
            '基础帧 1234000 只有车次/速度/公里标。因此地图上出现标记的前提是：'
            '<b>收到同一列车的基础帧 + 长报文</b>。</p>'
            '<p><b>配置步骤：</b></p>'
            '<p>1. 打开 <a href="https://console.amap.com/dev/key/app">高德开放平台控制台</a>，'
            '创建应用并添加 Key，服务平台选择 <b>Web端(JS API)</b>。</p>'
            '<p>2. 复制 <b>Key</b> 与旁边的 <b>安全密钥</b>，填入“配置 → 地图与车次规则”。</p>'
            '<p>3. 同一页的 <b>默认中心</b> 填一个地名（如 <code>南昌站</code>）——'
            '不用填经纬度，程序启动时用高德<b>地理编码</b>把它解析成坐标再把视图挪过去，'
            '<b>不会在图上加任何标记</b>；留空则显示全国概览（不再默认北京）。'
            '解析结果会缓存，断网也能回到上次的位置。</p>'
            '<p>4. 保存后地图立即重建，无需重启 DSP；上段左侧就是实时地图；'
            '点击标记可查看车次、时间、速度、公里标、线路、机车与坐标。'
            '地图卡片上的「中心」按钮可随时回到默认中心。</p>'
            '<p><b>说明：</b>LBJ 经纬度为 WGS-84，高德底图为 GCJ-02。程序在落点前会自动做 '
            'WGS-84 → GCJ-02 纠偏，标记可贴合道路；详情里仍显示原始 WGS-84 坐标。</p>'
            '<p><b>视野与跟随：</b>标签下方的小白球就是<b>真正的坐标点</b>（球心压在报文经纬度上）。'
            '「跟随」只在列车真的移动约 30 米以上时才重新居中；'
            '<b>你一拖动地图或用滚轮缩放，跟随会自动暂停</b>（按钮同步取消勾选），'
            '点一下「跟随」即可恢复。</p>'
            '<p><b>完整文档：</b>程序目录 <code>docs/</code> 下有三份手册——'
            '<code>用户手册.md</code>（操作与排障）、'
            '<code>高德地图配置手册.md</code>（Key 申请与标注开发）、'
            '<code>技术参考.md</code>（报文结构、DSP 链路与车次规则全表）。</p>'
        )
        text5.setWordWrap(True)
        text5.setOpenExternalLinks(True)
        text5.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text5)

        sep5 = QFrame()
        sep5.setFrameShape(QFrame.HLine)
        sep5.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep5)

        # ---- 2026 车次 ----
        title6 = QLabel('六、2026 版车次规则')
        title6.setStyleSheet(f'color: {CLR("warn")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title6)
        text6 = QLabel(
            '<p>2026 版《列车车次编排规定》分两批实施：2026-11-24 起货物/路用列车换新号，'
            '11-25 起普速旅客列车换新号，12 月下旬动车组换新号。</p>'
            '<p><b>新字头：</b>X(350+ 复兴号)、G(350)、T(300)、K(200~250)、D(动集)、'
            'C(城际)、S(市郊)；普速改为 Z(160)、N(140)、V(120)，'
            'V6001~V6998 为普通旅客快车、V7001~V7998 为普通旅客慢车；'
            '货运班列 X → B，新增 DH(动货)。</p>'
            '<p><b>兼容旧车次：</b>“车次规则”默认选“自动兼容”，程序用当前速度区分：'
            'T/K/X 速度 ≥200 km/h 按新动车组解释，低于 200 按旧特快/快速/行包解释；'
            '也可强制选择 2026 新版或 2014 旧版。</p>'
        )
        text6.setWordWrap(True)
        text6.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text6)

        sep6 = QFrame()
        sep6.setFrameShape(QFrame.HLine)
        sep6.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep6)

        # ---- v2.3 界面与操作 ----
        title7 = QLabel('七、界面与操作（v2.3）')
        title7.setStyleSheet(f'color: {CLR("accent2")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title7)
        text7 = QLabel(
            '<p><b>布局（全景式，不用切页签）：</b>一屏分三段——'
            '<b>上段</b>左侧是实时地图（约六成宽），右侧上「当前解码 / 历史记录」两张表、下「列车信息」卡片；'
            '<b>中段</b>三块并排：<b>接收频谱 | 车次信息 | 机车信息</b>；'
            '<b>底栏</b>左右各一半：<b>输出 1 · 日志</b>（滚动显示最近日志，点击打开完整日志窗口）'
            '与 <b>输出 2 · 接收状态</b>。所有内容同屏可见，互不遮挡。</p>'
            '<p><b>频谱切换：</b>「图形 / 终端」下拉框现在就在<b>接收频谱卡片的标题栏右侧</b>，'
            '跟频谱放一起，切完立即生效并记住选择。</p>'
            '<p><b>输出 2 · 接收状态：</b>四个等宽方块——信号 / AFC / 干扰 / 链路。'
            '正常只有灰色描边，哪一项不对整块变黄（注意）或变红（异常），边框和数值一起变色；'
            '<b>点任意方块打开运行状态仪表板</b>（也可以按 Ctrl+D）。'
            '告警原文只出现在输出 1 的日志里，这里不复述。</p>'
            '<p><b>运行状态仪表板：</b>「帮助 → 运行状态仪表板」(Ctrl+D) 已改成'
            '<b>分组卡片 + 指标方块</b>：链路 / 射频与频谱 / 门控与 AFC / 解码与去重 / 界面五组，'
            '良好标绿、注意标黄、异常标红，扫一眼就知道该看哪一项；'
            '每秒自动刷新，可暂停、可「复制全部」成文本。</p>'
            '<p><b>自适应：</b>窗口或屏幕变化时，程序自己调上下段比例、地图最小宽度、'
            '字段列数与标题显隐，不需要手拖分隔条；启动时还会按屏幕尺寸选一个合适的界面缩放基准。'
            '手动「视图 → 界面缩放」仍然保留，作为偏好覆盖。</p>'
            '<p><b>配置分页：</b>配置窗口按「数据源配置 / 射频设置 / 到达估算 / 地图与车次 / '
            '解码与界面 / 外观主题」六页分开，不再是一条长滚动条。</p>'
            '<p><b>外观主题：</b>内置中国铁路标准色——主色 CR 红 #DA291C（Pantone 485C）、'
            '辅色 CR 蓝 #003DA5（Pantone 286C）。'
            '工具栏右上角的 <b>「日间 / 夜间」按钮</b>（或 Ctrl+T、或「视图 → 切换日间 / 夜间」）'
            '<b>点一下立即换色，不需要重启</b>：全局样式、卡片、表格、频谱、地图、仪表板一起变。'
            '也可以「视图 → 外观主题」选 <b>夜间 / 日间 / 跟随系统</b>（跟随系统读取 Windows 的浅色 / 深色设置）。</p>'
            '<p><b>地图：</b>标记按方向着色；车多时会自动避让——放不下的小标记隐藏速度/公里标副行并降低透明度，'
            '放大后恢复；点标记弹出的是不透明信息卡片（含时间、方向、轨迹点数与里程），不再压住底图。'
            '手动拖动/滚轮缩放会自动暂停「跟随」，不会再被下一条报文拉回去；'
            '「中心」按钮回到配置里的默认中心（地名，不加标记）。</p>'
            '<p><b>轨迹：</b>同一列车收到多个详细报文时，按“移动超过约 6 米或间隔超过 3 秒”记录一个点，'
            '最多保留 240 点，画成折线；信息卡片里会显示“N 个点 · x.x km”。</p>'
            '<p><b>实时日志：</b>点底栏「输出 1」里的任一一行，或「帮助 → 实时日志」(Ctrl+L)，'
            '可查看自启动以来的全部输出，支持暂停、清空、另存为。</p>'
            '<p><b>全屏：</b>F11 或「视图 → 全屏」；Esc 退出。全屏时自动隐藏菜单栏。</p>'
            '<p><b>触屏：</b>按钮、表格行高、滚动条已加大，表格支持手指拖动惯性滚动，'
            '适合 Surface 等触屏设备。</p>'
        )
        text7.setWordWrap(True)
        text7.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text7)

        sep7 = QFrame()
        sep7.setFrameShape(QFrame.HLine)
        sep7.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep7)

        title8 = QLabel('八、重复报文合并与记录质量')
        title8.setStyleSheet(f'color: {CLR("ok")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title8)
        text8 = QLabel(
            '<p>同一次 LBJ 发射常被连续解出 2~4 次，表现为“同一车次同一秒出现多条记录”。</p>'
            '<p><b>处理方式：</b>同一车次在“重复报文合并”窗口（默认 2.5 秒）内只保留质量最高的一条：'
            '详细报文优先于基础帧，其次看是否有经纬度、BCH 是否纠错、机车/线路/速度是否完整、'
            '信号强度高低。窗口内后来解出更优的记录会<b>就地替换</b>已显示的那条，'
            '历史库里也是更新而非新增。</p>'
            '<p>窗口可在「配置 → 解码与界面」调整，设为 0 可关闭去重；'
            '“运行状态仪表板”（Ctrl+D 或点底栏右侧状态条）的「解码与去重」组里'
            '可看到「合并丢弃 / 择优升级 / 占用槽位」。</p>'
        )
        text8.setWordWrap(True)
        text8.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text8)

        sep8 = QFrame()
        sep8.setFrameShape(QFrame.HLine)
        sep8.setStyleSheet(f'background-color: {CLR("border")};')
        contentLayout.addWidget(sep8)

        title9 = QLabel('九、车次信息卡与 12306 查询')
        title9.setStyleSheet(f'color: {CLR("accent")}; font-size: 15px; font-weight: bold;')
        contentLayout.addWidget(title9)
        text9 = QLabel(
            '<p>右下角「车次信息」卡片会根据报文里的<b>报文类别</b>自动判断该车次能不能查 12306 时刻表。</p>'
            '<p><b>可查：</b>客运列车——动车组、城际、市郊、旅游、普速（含快速 / 特快旅客列车）、'
            '普通旅客快车 / 慢车、直达特快列车。</p>'
            '<p><b>不查：</b>货运与路用类——快运、货物、班列、始发 / 煤炭 / 石油 / 空车 / 技术直达、'
            '检测、确认、回送、单机、补机、小运转、摘挂、超限、军用、轨道车、路用、救援、试运行、自备等。'
            '这类车次在 12306 上本来就没有时刻表。</p>'
            '<p><b>匹配方式：</b>先剥掉类别串末尾括号里的速度说明（如“快速旅客列车 (160km/h)”），'
            '再按关键字归类，因此类别后面带不带速度后缀都不影响判断。'
            'v2.2 修复了此前“普速旅客列车被误判为不可查询”的问题。</p>'
        )
        text9.setWordWrap(True)
        text9.setStyleSheet('font-size: 13px; line-height: 1.5;')
        contentLayout.addWidget(text9)

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
        self.setFixedSize(spx(540), spx(480))
        layout = QVBoxLayout(self)

        title = QLabel('中国铁路 LBJ 列车预警器解码程序')
        title.setStyleSheet(f'color: {CLR("accent")}; font-size: 16px; font-weight: bold;')
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel('v2.4  ·  2026-11')
        ver.setStyleSheet(f'color: {CLR("dim")}; font-size: 12px;')
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

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
        declTitle.setStyleSheet(f'color: {CLR("warn")}; font-size: 14px; font-weight: bold;')
        layout.addWidget(declTitle)

        decl = QLabel(
            f'<p style="color:{CLR("warn")}"><b>本程序仅供学习与研究使用。</b></p>'
            '<p>不得用于任何商业或非法用途。</p>'
        )
        decl.setWordWrap(True)
        decl.setStyleSheet('font-size: 13px; line-height: 1.6;')
        layout.addWidget(decl)

        layout.addWidget(self._sep())

        license = QLabel('License: GPL v3 | Copyright (C) 2026 BG2GBQ')
        license.setStyleSheet(f'color: {CLR("faint")}; font-size: 11px;')
        license.setAlignment(Qt.AlignCenter)
        layout.addWidget(license)

    def _sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f'background-color: {CLR("border")};')
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
        titleLabel.setStyleSheet(f'color: {CLR("accent")}; font-size: 16px; font-weight: bold;')
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
                    item.setForeground(QColor(CLR("warn")))
                self.table.setItem(i, col, item)

        layout.addWidget(self.table)

        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)


class TrainQueryPanel(QWidget):
    """车次信息卡片：显示 12306 查询到的起终点与时刻。

    v2.2 修复两处体验问题：
    1. 车次类别现在带速度后缀（如「快速旅客列车 (160km/h)」），
       旧代码拿整串去比对白名单，导致普速列车被误判成「不查询 12306」；
       现在先剥掉括号里的速度段再判断，并改成关键字匹配。
    2. 「查看时刻表」按钮只在真正有数据时才可点，避免点了弹「还没有可查询的车次」。
    """

    doubleClicked = Signal()
    openRequested = Signal()

    #: 可查 12306 的（客运列车）。'旅客' 覆盖「旅客列车 / 旅客快车 / 旅客慢车」等写法，
    #: '特快' 用于「直达特快列车」（Z 字头，不带“旅客”二字）
    QUERY_KEYWORDS = ('旅客', '动车组', '城际', '市郊', '旅游', '普速', '特快')
    #: 明确不查的（货运、路用、回送、单机、动检、动货等）
    NOT_QUERY = ('快运', '货运', '货物', '检测', '确认', '回送', '单机', '补机',
                 '小运转', '摘挂', '超限', '军用', '轨道车', '路用', '救援',
                 '试运行', '自备', '班列')
    #: 「直达」两类都有：直达特快列车是客运（可查），始发/煤炭/石油/空车/技术直达都是货运
    DIRECT_RE = ('特快',)

    def __init__(self):
        super().__init__()
        self._cache: Dict[str, dict] = {}  # {trainCode: result}
        self._worker: Optional[TrainQueryWorker] = None
        self._lastQueryCode = ''
        self._currentData: Optional[dict] = None
        self._online = True

        # 横向排：左边一行结论 + 一行说明，右边按钮——整行宽度都用得上
        outer = QHBoxLayout(self)
        outer.setContentsMargins(spx(10), spx(8), spx(10), spx(6))
        outer.setSpacing(spx(10))

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(spx(3))

        col.addStretch(1)
        self.titleLabel = QLabel('等待详细报文...')
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.titleLabel.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        col.addWidget(self.titleLabel, 0, Qt.AlignLeft)

        self.hintLabel = QLabel('')
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setStyleSheet(f'color: {CLR("faint")}; font-size: {spx(10)}px;')
        self.hintLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.hintLabel)
        col.addStretch(1)
        outer.addLayout(col, 1)

        self.openBtn = QPushButton('查看时刻表')
        self.openBtn.setToolTip('双击卡片也可打开')
        self.openBtn.setEnabled(False)
        self.openBtn.setMinimumWidth(spx(96))
        self.openBtn.clicked.connect(self._openTimetable)
        outer.addWidget(self.openBtn, 0, Qt.AlignVCenter)
        self._setState('等待详细报文...', 'idle')

    # ------------------------------------------------------------------
    # 状态样式
    # ------------------------------------------------------------------
    def _setState(self, text: str, kind: str = 'idle', hint: str = '',
                  canOpen: bool = False):
        """统一更新卡片文字/配色/按钮可用性。"""
        colors = {
            'idle': (CLR('faint'), CLR('panel2')),
            'info': (CLR('dim'), CLR('panel2')),
            'ok': (CLR('ok'), CLR('panel2')),
            'warn': (CLR('warn'), CLR('panel2')),
            'err': (CLR('err'), CLR('panel2')),
        }
        fg, bg = colors.get(kind, colors['idle'])
        weight = 'bold' if kind in ('ok', 'err') else 'normal'
        self.titleLabel.setText(text)
        self.titleLabel.setStyleSheet(
            f'color: {fg}; font-size: {spx(12)}px; font-weight: {weight};'
            f'padding: {spx(4)}px; background-color: {bg}; border-radius: 3px;')
        self.hintLabel.setText(hint)
        self.openBtn.setEnabled(bool(canOpen))
        self.openBtn.setText('查看时刻表' if canOpen else '暂无可查时刻表')

    # ------------------------------------------------------------------
    # 类别判断
    # ------------------------------------------------------------------
    @staticmethod
    def baseCategory(category: str) -> str:
        """去掉类别后面的速度/备注括号，如「快速旅客列车 (160km/h)」→「快速旅客列车」。"""
        import re as _re
        return _re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', str(category or '')).strip()

    def isQueryable(self, category: str) -> bool:
        """该类别是否可能出现在 12306（客运列车）。"""
        base = self.baseCategory(category)
        if not base or base in ('未知', '----'):
            return False
        if any(k in base for k in self.NOT_QUERY):
            return False
        # 「直达」需再看一眼：直达特快列车可查，其余（始发/煤炭/石油/空车/技术直达）为货运
        if '直达' in base and not any(k in base for k in self.DIRECT_RE):
            return False
        return any(k in base for k in self.QUERY_KEYWORDS)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if self._currentData:
            self.doubleClicked.emit()

    def _openTimetable(self):
        if self._currentData:
            dlg = TimetableDialog(self._currentData, self)
            dlg.exec()
        elif not self._online:
            QMessageBox.information(self, '提示', '时刻表查询需要连接互联网。')
        else:
            QMessageBox.information(
                self, '提示', '还没有可查询的时刻表。\n\n'
                '只有客运列车（旅客列车、动车组、城际、市郊等）才会到 12306 查询；'
                '货运、路用、回送等类别不提供时刻表。')

    # ------------------------------------------------------------------
    # 数据入口
    # ------------------------------------------------------------------
    def onTrainDecoded(self, d: dict):
        """当解码到详细车次信息时触发 12306 查询。"""
        if not d.get('isDetailed'):
            self._currentData = None
            self._setState('等待详细报文...', 'idle',
                           '收到长报文后可查时刻表')
            return

        train = str(d.get('train', '') or '')
        category = str(d.get('category', '') or '')
        if not train or train == '----':
            self._setState('等待车次号...', 'idle')
            return

        base_cat = self.baseCategory(category)

        # 非客运类别：说明原因，按钮置灰（不再点了才弹提示）
        if not self.isQueryable(category):
            self._currentData = None
            self._setState(f'{base_cat or category}\n不提供 12306 时刻表', 'warn',
                           '货运 / 路用 / 回送等类别不在 12306 售票范围')
            return

        if train in self._cache:
            self._currentData = self._cache[train]
            self._displayResult(self._currentData)
            return

        if self._lastQueryCode == train and self._worker and self._worker.isRunning():
            return

        self._lastQueryCode = train
        self._setState(f'查询中: {train} ...', 'info', '正在请求 12306')

        dateStr = datetime.now().strftime('%Y%m%d')
        self._worker = TrainQueryWorker(train, dateStr)
        self._worker.resultReady.connect(self._onQueryResult)
        self._worker.queryFailed.connect(self._onQueryFailed)
        self._worker.start()

    def _onQueryResult(self, data: dict):
        code = data.get('trainCode', '')
        self._cache[code] = data
        if len(self._cache) > 20:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._currentData = data
        self._displayResult(data)

    def _onQueryFailed(self, err: str):
        self._online = not ('网络' in err or 'URLError' in err)
        if not self._online:
            self._setState('⚠ 此功能需连接互联网使用', 'err', '联网后重新收到详细报文即会重查')
        else:
            self._setState(f'⚠ {err}', 'err', '12306 接口暂不可用，可稍后重试')

    def _displayResult(self, data: dict):
        startSt = data.get('startStation', '')
        endSt = data.get('endStation', '')
        startTime = data.get('startTime', '')
        endTime = data.get('endTime', '')
        code = data.get('trainCode', '')

        self._setState(f'{startSt}({startTime})\n→ {code} →\n{endSt}({endTime})',
                       'ok', '双击查看详细时刻表', canOpen=True)


class LocoInfoPanel(QWidget):
    """机车信息卡片 (v2.1)：型号、参数摘要与详情入口。"""

    detailRequested = Signal(dict)

    def __init__(self):
        super().__init__()
        self._last: dict = {}

        # 横向排：左侧机型/参数/简介，右侧「机车详情」按钮
        outer = QHBoxLayout(self)
        outer.setContentsMargins(spx(10), spx(8), spx(10), spx(6))
        outer.setSpacing(spx(10))

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(spx(2))
        col.addStretch(1)

        self.nameLabel = QLabel('等待详细报文...')
        self.nameLabel.setStyleSheet(
            f'color: {CLR("faint")}; font-size: {spx(12)}px; font-weight: bold;')
        self.nameLabel.setWordWrap(True)
        self.nameLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.nameLabel)

        self.detailLabel = QLabel('')
        self.detailLabel.setStyleSheet(f'color: {CLR("dim")}; font-size: {spx(10)}px;')
        self.detailLabel.setWordWrap(True)
        self.detailLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.detailLabel)

        self.briefLabel = QLabel('')
        self.briefLabel.setStyleSheet(
            f'color: {CLR("dim")}; font-size: {spx(10)}px; padding: {spx(2)}px;'
            f'background-color: {CLR("panel")}; border-radius: 3px;')
        self.briefLabel.setWordWrap(True)
        self.briefLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.briefLabel, 0)
        col.addStretch(1)
        outer.addLayout(col, 1)

        self.detailBtn = QPushButton('机车详情')
        self.detailBtn.setMinimumWidth(spx(96))
        self.detailBtn.setEnabled(False)
        self.detailBtn.clicked.connect(
            lambda: self.detailRequested.emit(self._last))
        outer.addWidget(self.detailBtn, 0, Qt.AlignVCenter)

    def updateLoco(self, d: dict):
        """根据解码记录更新机车卡片。"""
        self._last = dict(d or {})
        loco_number = d.get('loco', '') if d else ''
        loco_code = d.get('locoCode', d.get('loco_code', '')) if d else ''
        if not d or not d.get('isDetailed'):
            self.nameLabel.setText('等待详细报文...')
            self.nameLabel.setStyleSheet(
                f'color: {CLR("faint")}; font-size: {spx(12)}px; font-weight: bold;')
            self.detailLabel.setText('')
            self.briefLabel.setText('收到扩展长报文（1234002 / 1234001）后自动填充机型与牵引参数')
            self.detailBtn.setEnabled(False)
            return

        info = lookup_loco(loco_code=loco_code, loco_number=loco_number)
        if info:
            self.nameLabel.setText(info.get('name', '未知车型'))
            self.nameLabel.setStyleSheet(
                f'color: {CLR("ok")}; font-size: {spx(12)}px; font-weight: bold;')
            self.detailLabel.setText(
                f"{info.get('type', '')} | {info.get('maker', '')} | {info.get('axle', '')}")
            self.briefLabel.setText(info.get('brief', ''))
        else:
            self.nameLabel.setText(loco_number or '未知机车')
            self.nameLabel.setStyleSheet(
                f'color: {CLR("warn")}; font-size: {spx(12)}px; font-weight: bold;')
            self.detailLabel.setText(f'代号: {loco_code}' if loco_code else '')
            self.briefLabel.setText('暂无该车型资料')
        self.detailBtn.setEnabled(True)


# ===========================================================================
# 主窗口
# ===========================================================================
class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self, config: CoreConfig):
        super().__init__()
        self.config = config
        self.worker: Optional[DspBridge] = None

        # 日志中枢：底部只显示最新一条，「帮助 → 实时日志」看全量
        self.logBus = LogBus()
        self.logPanel = self.logBus          # 兼容旧调用点
        self._logWindow: Optional[LogWindow] = None
        self._dashWindow = None
        self._isFullScreen = False

        self.setWindowTitle('中国铁路 LBJ 列车预警器解码程序  v2.4')
        # 下限放低一点：1024×600 的老上网本也能用，布局会自己收（FieldGrid 换列）
        self.setMinimumSize(spx(880), spx(560))
        self._applyWindowGeometry()
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self._buildMenu()
        self._buildUi()
        # 启动时先让地图底图跟界面主题对齐（老配置里的 mapNight 可能是手设的）
        self._syncMapNight()

        # 从配置初始化频谱显示模式
        mode = getattr(self.config, 'spectrumMode', 'graph')
        if mode == 'terminal':
            self.spectrumModeCombo.setCurrentIndex(1)
            self.spectrumStack.setCurrentIndex(1)

        # 自动启动
        QTimer.singleShot(500, self.startDsp)

    # ---- 窗口几何 / 全屏 ----
    def _applyWindowGeometry(self):
        """按可用屏幕自适应：小屏铺满，大屏留边，避免 4K 下窗口过大或小屏溢出。"""
        try:
            scr = QApplication.primaryScreen()
            if scr is None:
                self.resize(spx(1280), spx(820))
                return
            avail = scr.availableGeometry()
            w = min(int(avail.width() * 0.94), spx(1600))
            h = min(int(avail.height() * 0.92), spx(1000))
            w = max(w, spx(1000))
            h = max(h, spx(660))
            self.resize(w, h)
            self.move(avail.x() + max(0, (avail.width() - w) // 2),
                      avail.y() + max(0, (avail.height() - h) // 3))
        except Exception:
            self.resize(spx(1280), spx(820))

    def toggleFullScreen(self, on: Optional[bool] = None):
        """全屏切换 (F11)。全屏时隐藏菜单栏以最大化内容区。"""
        if on is None:
            on = not self._isFullScreen
        if on == self._isFullScreen:
            return
        if on:
            self._normalGeom = self.geometry()
            self.menuBar().setVisible(False)
            self.showFullScreen()
        else:
            self.showNormal()
            self.menuBar().setVisible(True)
            geom = getattr(self, '_normalGeom', None)
            if geom is not None:
                self.setGeometry(geom)
        self._isFullScreen = bool(on)
        if hasattr(self, 'fullBtn'):
            self.fullBtn.setText('退出全屏' if on else '全屏')
        if hasattr(self, 'actFullScreen'):
            self.actFullScreen.setChecked(bool(on))
        # 地图与频谱需要重新布局
        self._applyResponsive(force=True)
        QTimer.singleShot(60, self._afterFullScreen)

    def _afterFullScreen(self):
        try:
            if hasattr(self, 'mapPanel') and self.mapPanel._view is not None:
                self.mapPanel._view.page().runJavaScript(
                    'window.LBJ && window.LBJ.resize();')
        except Exception:
            pass

    # ---- 自适应布局（v2.2） ----
    def _applyResponsive(self, force: bool = False):
        """按窗口尺寸自动排三段比例与最小宽度，不需要用户手拖。

        只在“尺寸档位”变化时重算（比如 1440→1024、全屏切换），
        同一档位内用户拖动分隔条的结果不会被覆盖。
        """
        if not hasattr(self, 'mainSplit'):
            return
        w = max(640, self.width())
        h = max(480, self.height())
        key = (w // 160, h // 120)
        if not force and key == getattr(self, '_respKey', None):
            return
        self._respKey = key

        chrome = spx(96)                       # 工具栏 + 状态栏
        avail = max(spx(300), h - chrome)
        # ③ 输出区（底栏）：只放一行日志 + 一句状态，压到 8% 左右（56~88），
        #    省下来的高度全给上段——底栏就是个底栏，图要大。
        outH = int(min(max(avail * 0.085, spx(56)), spx(88)))
        rest = max(spx(240), avail - outH)
        # ② 中段（频谱 | 车次 | 机车）：约 34%，夹在 110~260
        band2H = int(min(max(rest * 0.34, spx(110)), spx(260)))
        # ① 上段吃掉剩下的
        band1H = max(spx(180), rest - band2H)
        self.mainSplit.setSizes([band1H, band2H, outH])

        # ① 左右比例：地图约 62%
        if hasattr(self, 'band1'):
            self.band1.setSizes([int(w * 0.62), w - int(w * 0.62)])
        if hasattr(self, 'mapPanel'):
            self.mapPanel.setMinimumWidth(spx(240) if w < spx(1100) else spx(320))

        # ② 三块比例：频谱 5 : 车次 3 : 机车 3
        if hasattr(self, 'band2'):
            unit = w / 11.0
            self.band2.setSizes([int(unit * 5), int(unit * 3), int(unit * 3)])
            # 中段三块都有下限：矮窗口里宁可压上段，也别把频谱压成一条缝
            for card in (getattr(self, 'specCard', None),
                         getattr(self, 'queryCard', None),
                         getattr(self, 'locoCard', None)):
                if card is not None:
                    card.setMinimumHeight(spx(126))

        # 窄窗口收紧最小宽度，否则整窗被顶宽（出现横向滚动条）
        narrow = w < spx(1100)
        if hasattr(self, 'specCard'):
            self.specCard.setMinimumWidth(spx(200) if narrow else spx(300))
        for card in (getattr(self, 'queryCard', None), getattr(self, 'locoCard', None)):
            if card is not None:
                card.setMinimumWidth(spx(168) if narrow else spx(210))

        # 很窄时收起左上角标题，把宽度让给频率与连接状态
        if hasattr(self, 'titleLabel'):
            self.titleLabel.setVisible(w >= spx(980))

        # 地图重绘（尺寸变了，Leaflet 必须收到 resize）
        QTimer.singleShot(0, self._afterFullScreen)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._applyResponsive()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.toggleFullScreen()
            return
        if event.key() == Qt.Key_Escape and self._isFullScreen:
            self.toggleFullScreen(False)
            return
        super().keyPressEvent(event)

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

        viewMenu = menubar.addMenu('视图(&V)')
        self.actFullScreen = QAction('全屏', self, shortcut='F11')
        self.actFullScreen.setCheckable(True)
        self.actFullScreen.triggered.connect(
            lambda checked: self.toggleFullScreen(checked))
        viewMenu.addAction(self.actFullScreen)

        themeMenu = viewMenu.addMenu('外观主题')
        self._themeActs = {}
        for label, val in (('夜间（深色）', 'dark'), ('日间（浅色）', 'light'),
                           ('跟随系统', 'auto')):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(str(getattr(self.config, 'theme', 'dark')) == val)
            act.triggered.connect(lambda _c, v=val: self._setTheme(v))
            themeMenu.addAction(act)
            self._themeActs[val] = act
        viewMenu.addSeparator()

        actToggleTheme = QAction('切换日间 / 夜间', self, shortcut='Ctrl+T')
        actToggleTheme.triggered.connect(self._toggleTheme)
        viewMenu.addAction(actToggleTheme)
        viewMenu.addSeparator()

        self.actMapNight = QAction('地图夜间模式', self)
        self.actMapNight.setCheckable(True)
        self.actMapNight.setChecked(bool(getattr(self.config, 'mapNight', True)))
        self.actMapNight.toggled.connect(self._onMenuMapNight)
        viewMenu.addAction(self.actMapNight)

        actToggleMap = QAction('显示/隐藏地图', self)
        actToggleMap.triggered.connect(self._toggleMapVisible)
        viewMenu.addAction(actToggleMap)
        viewMenu.addSeparator()

        scaleMenu = viewMenu.addMenu('界面缩放')
        self._scaleActions = []
        for val in (0.85, 1.0, 1.15, 1.3, 1.5):
            act = QAction(f'{int(val * 100)}%', self)
            act.setCheckable(True)
            act.setChecked(abs(float(getattr(self.config, 'uiScale', 1.0)) - val) < 0.01)
            act.triggered.connect(lambda _c, v=val: self._setUiScale(v))
            scaleMenu.addAction(act)
            self._scaleActions.append((val, act))

        configMenu = menubar.addMenu('配置(&C)')
        actConfig = QAction('配置...', self, shortcut='Ctrl+,')
        actConfig.triggered.connect(self._openConfig)
        configMenu.addAction(actConfig)

        helpMenu = menubar.addMenu('帮助(&H)')
        actManual = QAction('使用手册', self)
        actManual.triggered.connect(lambda: ManualDialog(self).exec())
        helpMenu.addAction(actManual)
        actDash = QAction('运行状态仪表板', self, shortcut='Ctrl+D')
        actDash.triggered.connect(self.openDashboard)
        helpMenu.addAction(actDash)
        actLog = QAction('实时日志', self, shortcut='Ctrl+L')
        actLog.triggered.connect(self.openLogWindow)
        helpMenu.addAction(actLog)
        helpMenu.addSeparator()
        actAbout = QAction('关于', self)
        actAbout.triggered.connect(lambda: AboutDialog(self).exec())
        helpMenu.addAction(actAbout)

    def _setUiScale(self, value: float):
        self.config.uiScale = float(value)
        self.config.save(CONFIG_PATH)
        for val, act in getattr(self, '_scaleActions', []):
            act.setChecked(abs(val - value) < 0.01)
        QMessageBox.information(
            self, '界面缩放',
            f'界面缩放已设为 {int(value * 100)}%。\n\n'
            '该设置需要重启程序后生效。')

    def _onMenuMapNight(self, checked: bool):
        if hasattr(self, 'mapPanel'):
            self.mapPanel.setNightMode(checked)
        self.config.mapNight = bool(checked)

    def _toggleMapVisible(self):
        if not hasattr(self, 'mapPanel'):
            return
        vis = not self.mapPanel.isVisible()
        self.mapPanel.setVisible(vis)
        if vis:
            self._afterFullScreen()

    def _buildUi(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(spx(4), spx(4), spx(4), spx(2))
        root.setSpacing(spx(4))

        # ---------------- 标题栏 ----------------
        header = QHBoxLayout()
        header.setSpacing(spx(8))
        self.titleLabel = QLabel('中国铁路 LBJ 列车预警器')
        self.titleLabel.setStyleSheet(
            f'color: {CLR("accent")}; font-size: {spx(15)}px; font-weight: bold;')
        self.titleLabel.setToolTip('中国铁路 LBJ 列车预警器解码程序 v2.4')
        # 标题固定成文字宽度：既不会被拉伸成一大块空白，也不给窗口垫出多余的宽度下限
        _titleW = self.titleLabel.fontMetrics().horizontalAdvance(
            self.titleLabel.text()) + spx(10)
        self.titleLabel.setMinimumWidth(0)
        self.titleLabel.setMaximumWidth(_titleW)
        self.titleLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        header.addWidget(self.titleLabel, 0)

        # 按钮外观全部交给 Fluent：开始用强调色主按钮，其余为常规按钮
        self.btnStart = K.button('▶  开始', primary=True)
        self.btnStart.setToolTip('启动 DSP 接收 (Ctrl+R)')
        self.btnStart.clicked.connect(self.startDsp)
        self.btnStop = K.button('■  停止')
        self.btnStop.setToolTip('停止接收 (Ctrl+R)')
        self.btnStop.clicked.connect(self.stopDsp)
        header.addWidget(self.btnStart)
        header.addWidget(self.btnStop)
        header.addSpacing(spx(10))

        self.freqLabel = QLabel('频率: -- MHz')
        self.freqLabel.setStyleSheet(
            f'background: transparent; color: {CLR("accent")};'
            f' font-weight: bold; font-size: {spx(14)}px;')
        header.addWidget(self.freqLabel)
        header.addSpacing(spx(10))

        self.connIndicator = QLabel('● 未连接')
        self.connIndicator.setStyleSheet(
            f'background: transparent; color: {CLR("err")};'
            f' font-size: {spx(13)}px; font-weight: bold;')
        header.addWidget(self.connIndicator)
        header.addStretch()

        # 日/夜配色开关（按钮文字是“点一下会切到哪”）
        self.btnTheme = K.button('日间')
        self.btnTheme.setToolTip('切换日间 / 夜间配色，立即生效 (Ctrl+T)')
        self.btnTheme.clicked.connect(self._toggleTheme)
        header.addWidget(self.btnTheme)

        self.fullBtn = K.button('全屏')
        self.fullBtn.setToolTip('全屏显示 (F11)')
        self.fullBtn.clicked.connect(lambda: self.toggleFullScreen())
        header.addWidget(self.fullBtn)
        root.addLayout(header)

        # ---------------- 全景三段式（v2.3） ----------------
        #   ① 上段：地图（约六成） | 当前解码/历史记录 + 列车信息
        #   ② 中段：接收频谱 | 车次信息 | 机车信息
        #   ③ 底栏：输出 1（日志尾部） | 输出 2（接收状态分块），各占一半
        #   页签取消后所有内容一屏可见，互不遮挡。
        mainSplit = QSplitter(Qt.Vertical)
        mainSplit.setChildrenCollapsible(False)
        mainSplit.setHandleWidth(spx(8))

        # ---- ① 上段 ----
        band1 = QSplitter(Qt.Horizontal)
        band1.setChildrenCollapsible(False)
        band1.setHandleWidth(spx(8))

        self.mapPanel = MapPanel(self.config)
        self.mapPanel.setMinimumWidth(spx(320))
        self.mapPanel.followChanged.connect(self._onMapFollowChanged)
        band1.addWidget(self.mapPanel)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.currentPanel = CurrentPanel()
        self.historyPanel = HistoryPanel()
        self.tabs.addTab(self.currentPanel, '当前解码')
        self.tabs.addTab(self.historyPanel, '历史记录')
        self.tabs.currentChanged.connect(self._onTabChanged)

        self.trainPanel = TrainInfoPanel()
        self.trainQueryPanel = TrainQueryPanel()
        self.locoPanel = LocoInfoPanel()
        self.trainQueryPanel.doubleClicked.connect(self._openTimetable)
        self.locoPanel.detailRequested.connect(self._openLocoDetail)

        rightCol = QSplitter(Qt.Vertical)
        rightCol.setChildrenCollapsible(False)
        rightCol.setHandleWidth(spx(8))
        self.decodeCard = CardBox('当前解码 / 历史记录', self.tabs)
        self.trainCard = CardBox('列车信息', self.trainPanel)
        rightCol.addWidget(self.decodeCard)
        rightCol.addWidget(self.trainCard)
        rightCol.setStretchFactor(0, 4)
        rightCol.setStretchFactor(1, 5)
        rightCol.setSizes([spx(280), spx(300)])

        band1.addWidget(rightCol)
        band1.setStretchFactor(0, 3)
        band1.setStretchFactor(1, 2)
        band1.setSizes([spx(760), spx(520)])
        self.band1 = band1
        self.rightCol = rightCol
        mainSplit.addWidget(band1)

        # ---- ② 中段：频谱 | 车次 | 机车 ----
        band2 = QSplitter(Qt.Horizontal)
        band2.setChildrenCollapsible(False)
        band2.setHandleWidth(spx(8))

        self.spectrumPanel = SpectrumPanel()
        self.terminalSpectrumPanel = TerminalSpectrumPanel()
        self.spectrumStack = QStackedWidget()
        self.spectrumStack.addWidget(self.spectrumPanel)           # 0: 图形
        self.spectrumStack.addWidget(self.terminalSpectrumPanel)   # 1: 终端

        # 频谱切换跟着频谱走：放进频谱卡片标题栏右侧，不再占工具栏
        self.spectrumModeCombo = QComboBox()
        self.spectrumModeCombo.addItem('图形')
        self.spectrumModeCombo.addItem('终端')
        self.spectrumModeCombo.setToolTip('图形频谱 / 终端频谱（省资源）')
        self.spectrumModeCombo.setMinimumWidth(spx(72))
        self.spectrumModeCombo.currentIndexChanged.connect(self._onSpectrumModeChanged)

        self.specCard = CardBox('接收频谱', self.spectrumStack,
                                right=self.spectrumModeCombo)
        self.queryCard = CardBox('车次信息', self.trainQueryPanel)
        self.locoCard = CardBox('机车信息', self.locoPanel)
        band2.addWidget(self.specCard)
        band2.addWidget(self.queryCard)
        band2.addWidget(self.locoCard)
        band2.setStretchFactor(0, 5)
        band2.setStretchFactor(1, 3)
        band2.setStretchFactor(2, 3)
        band2.setSizes([spx(560), spx(320), spx(320)])
        self.band2 = band2
        mainSplit.addWidget(band2)

        # ---- ③ 底栏：输出 1（最新一条日志） | 输出 2（状态提示） ----
        self.logTail = LogTail()
        self.statusStrip = RxStatusStrip()
        self.statusStrip.clicked.connect(self.openDashboard)

        self.out1Card = CardBox('输出 1 · 日志', self.logTail, margins=(8, 3, 8, 4))
        self.out2Card = CardBox('输出 2 · 接收状态', self.statusStrip, margins=(8, 3, 8, 4))
        self.out2Card.setToolTip('点击打开运行状态仪表板 (Ctrl+D)')
        for _c in (self.out1Card, self.out2Card):
            _c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        bottomBar = QWidget()
        bl = QHBoxLayout(bottomBar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(spx(6))
        bl.addWidget(self.out1Card, 1)
        bl.addWidget(self.out2Card, 1)
        self.bottomBar = bottomBar
        mainSplit.addWidget(bottomBar)

        self.mainSplit = mainSplit
        mainSplit.setStretchFactor(0, 7)
        mainSplit.setStretchFactor(1, 4)
        mainSplit.setStretchFactor(2, 0)
        root.addWidget(mainSplit, 1)
        self.logBus.lineAdded.connect(self._onLogLine)

        # 状态栏
        self.statusBar().showMessage('就绪')
        self._applyTouchTweaks()
        self._syncThemeButton()
        # 首次布局完成后按实际窗口尺寸定一次比例
        QTimer.singleShot(0, lambda: self._applyResponsive(force=True))

    # ---- 触屏 / 高 DPI 细节 ----
    def _applyTouchTweaks(self):
        """加大表格行高与滚动条，并给滚动区域启用触摸惯性滚动。"""
        try:
            from PySide6.QtWidgets import QScroller
            for tb in self.findChildren(QTableWidget):
                tb.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
                tb.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
                tb.verticalHeader().setDefaultSectionSize(spx(26))
                tb.verticalHeader().setMinimumSectionSize(spx(22))
                tb.setWordWrap(False)
                QScroller.grabGesture(tb.viewport(),
                                      QScroller.ScrollerGestureType.TouchGesture)
            for sp in self.findChildren(QSplitter):
                sp.setHandleWidth(spx(7))
            for sa in self.findChildren(QScrollArea):
                QScroller.grabGesture(sa.viewport(),
                                      QScroller.ScrollerGestureType.TouchGesture)
        except Exception:
            pass

    # ---- 日志 ----
    def _onLogLine(self, line: str, level: str):
        """输出 1：把日志追加到尾部窗口（最新的在最下面）。"""
        try:
            self.logTail.appendLine(line, level)
        except Exception:
            pass

    def openLogWindow(self):
        """打开实时日志窗口（复用同一个实例）。"""
        if self._logWindow is None:
            self._logWindow = LogWindow(self.logBus, self)
        self._logWindow.show()
        self._logWindow.raise_()
        self._logWindow.activateWindow()

    # ---- 外观主题（即时生效） ----
    def _toggleTheme(self):
        """工具栏上的日/夜开关：在 dark 与 light 之间即时切换。"""
        cur = TH.P.get('mode', 'dark')
        self._setTheme('light' if cur == 'dark' else 'dark')

    def _remapOldColors(self, oldMode: str, newMode: str) -> Dict[str, str]:
        """旧调色板颜色 → 新调色板颜色 的映射表。

        界面里大量控件的颜色是建 UI 时用 `setStyleSheet(f'color: {CLR("x")}')`
        写死成十六进制串的，光换全局 QSS 只能改到“没单独写样式”的那部分。
        这里把两套调色板同名字段的颜色配成一张表，再对每个控件的样式串做
        一次正则替换（单次扫描，避免 A→B、B→C 连环替换）。
        """
        old = TH.PALETTES.get(oldMode) or {}
        new = TH.PALETTES.get(newMode) or {}
        m: Dict[str, str] = {}
        for k, v in old.items():
            if isinstance(v, str) and v.startswith('#') and isinstance(new.get(k), str):
                m[v.lower()] = new[k]
        # 跨调色板同名但值不同的固定色（CR 红蓝在两套里同名同值，不用管）
        m.setdefault('#ffffff', new.get('sel_text', '#ffffff')
                    if newMode == 'light' else '#ffffff')
        return m

    def _restyleWidgets(self, mapping: Dict[str, str]) -> None:
        """把映射表套到所有控件的内联样式上（含独立对话框、菜单）。"""
        if not mapping:
            return
        pairs = {k: v for k, v in mapping.items() if k != v.lower()}
        if not pairs:
            return
        pat = re.compile('|'.join(re.escape(k) for k in pairs), re.I)

        def _sub(mo):
            return pairs.get(mo.group(0).lower(), mo.group(0))

        for w in QApplication.allWidgets():
            try:
                ss = w.styleSheet()
                if not ss or '#' not in ss:
                    continue
                new = pat.sub(_sub, ss)
                if new != ss:
                    w.setStyleSheet(new)
            except Exception:
                continue

    def _applyThemeLive(self, mode: str) -> str:
        """真正把主题应用到当前界面（不重启）。返回实际生效的 dark/light。"""
        oldMode = TH.P.get('mode', 'dark')
        resolved = TH.applyMode(mode)
        mapping = self._remapOldColors(oldMode, resolved)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(TH.styleSheet())      # 全局 QSS 先换
        K.applyTheme(resolved)                      # Fluent 组件换深浅色
        self._restyleWidgets(mapping)               # 内联颜色跟一遍
        # 表格底色要在换色**之后**再刷：表格的调色板/样式是我们按主题色生成的，
        # 先刷会被上面的“旧色→新色”批量替换改坏（白底被替换成深色文字色）。
        K.refreshTablePalettes()
        # 地图底图跟界面一起深浅色（日间界面配深色底图太割裂）——要在重建页面之前设
        self._syncMapNight(resolved)

        # pyqtgraph：背景、坐标轴、字体颜色
        applyPgTheme()
        for panel in (getattr(self, 'spectrumPanel', None),
                      getattr(self, 'terminalSpectrumPanel', None)):
            try:
                panel.applyTheme()
            except Exception:
                pass
        # 地图：页面里的配色是注入到 HTML 里的，只能重建一次视图
        try:
            self.mapPanel.applyTheme()
        except Exception:
            pass
        # 输出区文字是运行时拼的 HTML，重新渲染一遍
        try:
            self.logTail.relayout()
        except Exception:
            pass
        # 日/夜按钮文字跟着变（显示的是“点一下会切到哪”）
        try:
            self._syncThemeButton(resolved)
        except Exception:
            pass
        return resolved

    def _syncMapNight(self, resolved: str = ''):
        """让地图底图与界面深浅色保持一致（界面日间 → 地图日间）。

        地图上的「夜间/日间」按钮仍可临时覆盖，下一轮换肤会再同步回来。
        """
        resolved = resolved or TH.P.get('mode', 'dark')
        night = (resolved == 'dark')
        self.config.mapNight = night
        act = getattr(self, 'actMapNight', None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(night)
            act.blockSignals(False)
        try:
            self.mapPanel.setNightMode(night)
        except Exception:
            pass

    def _syncThemeButton(self, resolved: str = ''):
        if not hasattr(self, 'btnTheme'):
            return
        resolved = resolved or TH.P.get('mode', 'dark')
        if resolved == 'dark':
            self.btnTheme.setText('日间')
            self.btnTheme.setToolTip('当前夜间配色 · 点击切到日间 (Ctrl+T)')
        else:
            self.btnTheme.setText('夜间')
            self.btnTheme.setToolTip('当前日间配色 · 点击切到夜间 (Ctrl+T)')

    def _setTheme(self, mode: str):
        """切换外观主题：立即生效，不再要求重启。"""
        mode = str(mode or 'dark')
        self.config.theme = mode
        try:
            self.config.save(CONFIG_PATH)
        except Exception:
            pass
        resolved = self._applyThemeLive(mode)
        for k, act in getattr(self, '_themeActs', {}).items():
            act.setChecked(k == mode)
        if hasattr(self, 'statusBar'):
            self.statusBar().showMessage(
                '主题已切换到 %s' % ('日间' if resolved == 'light' else '夜间'), 4000)
        try:
            self.logPanel.appendLog(
                '[主题] 已切换到%s（即时生效）'
                % ('日间' if resolved == 'light' else '夜间'))
        except Exception:
            pass

    def _openLocoDetail(self, d: dict):
        """打开机车详情对话框。"""
        if not d:
            return
        loco_number = d.get('loco', '')
        loco_code = d.get('locoCode', d.get('loco_code', ''))
        info = lookup_loco(loco_code=loco_code, loco_number=loco_number)
        LocoDetailDialog(info, loco_number, self).exec()


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
                         'sourceType', 'rtlTcpPath', 'rtlDeviceIndex',
                         'afcEnable', 'afcMaxHz', 'afcGain', 'etaMaxMin']
        needRestart = any(getattr(old, f) != getattr(new, f) for f in restartFields)
        try:
            self.mapPanel.setConfig(new)
        except Exception:
            pass
        if needRestart:
            self.stopDsp()
            self.config = new
            self.startDsp()
        else:
            if self.worker and self.worker.core:
                self.worker.core.applyHotConfig(new)
                self.config = new
            self.logPanel.appendLog('[配置] 已热更新')

    def _onMapFollowChanged(self, on: bool):
        """地图「跟随」被切换（含手动拖图导致自动取消）→ 立即存盘。"""
        self.config.mapFollow = bool(on)
        try:
            self.config.save(CONFIG_PATH)
        except Exception:
            pass
        if not on:
            try:
                self.logPanel.appendLog('[地图] 检测到手动拖动地图，已暂停自动跟随'
                                        '（点「跟随」可恢复）')
            except Exception:
                pass

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
        self.statusStrip.updateStatus(st)
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
            self.connIndicator.setStyleSheet(f'color: {CLR("ok")}; font-size: 12px; font-weight: bold;')
        else:
            self.connIndicator.setText('● 未连接')
            self.connIndicator.setStyleSheet(f'color: {CLR("err")}; font-size: 12px; font-weight: bold;')


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
        # 经纬度 -> 地图 (仅长报文包含)
        try:
            self.mapPanel.updateTrain(d)
        except Exception:
            pass
        # 无车次信息的报文: 不存入历史数据库
        isInvalid = (d.get('train', '----') in ('----', '', '未知')
                     and d.get('baseTrain', '----') in ('----', ''))
        if not isInvalid:
            self.historyPanel.addRecord(d)
        # 触发 12306 联网查询
        self.trainQueryPanel.onTrainDecoded(d)
        # 机车信息卡片
        try:
            self.locoPanel.updateLoco(d)
        except Exception:
            pass

    def _onInterference(self, direction: str, warnText: str):
        """干扰告警：只进日志，底栏状态条只加一个「干扰 N 次」计数。

        以前这里还往状态栏塞同一句话，于是底栏出现两行一模一样的告警（v2.2 修掉）。
        """
        self.logPanel.appendLog(f'[告警] {warnText}')
        try:
            self.statusStrip.noteInterference()
        except Exception:
            pass

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
            self.connIndicator.setStyleSheet(f'color: {CLR("ok")}; font-size: 12px; font-weight: bold;')
        else:
            self.connIndicator.setText('● 未连接')
            self.connIndicator.setStyleSheet(f'color: {CLR("err")}; font-size: 12px; font-weight: bold;')

    def _onDiagnostics(self, diag: dict):
        """网络诊断信号回调。

        v2.2 起主界面不再有「系统状态」页签：诊断结果进日志与仪表板
        （Ctrl+D → 链路组），这里只做轻量提示，不参与布局刷新。
        """
        text = ''
        if isinstance(diag, dict):
            text = str(diag.get('diagnostics') or diag.get('message') or '')
        if text and text not in ('OK', '正常'):
            self.logPanel.appendLog(f'[诊断] {text}')

    # ---- 运行状态仪表板 ----
    def openDashboard(self):
        """打开运行状态仪表板（非模态，1 秒刷新）。"""
        if self._dashWindow is None:
            self._dashWindow = StatusDashboard(self, self)
        self._dashWindow.show()
        self._dashWindow.raise_()
        self._dashWindow.activateWindow()
        self._dashWindow.refresh()

    def _infoCols(self) -> str:
        """信息卡片字段网格的列数（全景布局下卡片一直可见，直接读即可）。"""
        grid = getattr(getattr(self, 'trainPanel', None), 'grid', None)
        if grid is None:
            return '-'
        return '%d 列' % grid._cols

    def statusGroups(self) -> List[tuple]:
        """汇总所有实时指标，返回 [(组名, [(项目, 值, 色调)])]。

        色调 '' 正常 / 'ok' 良好 / 'warn' 注意 / 'err' 异常 —— 仪表板据此上色，
        `statusReport()` 再从同一份数据拼成纯文本（复制全部用）。
        """
        cfg = self.config
        stats = {}
        if self.worker and hasattr(self.worker, '_lastStats'):
            stats = self.worker._lastStats or {}
        core = getattr(getattr(self, 'worker', None), 'core', None)
        try:
            st = core.getStatus() if core is not None else {}
        except Exception:
            st = {}
        uptime = int(stats.get('uptime', 0) or 0)
        h, rem = divmod(uptime, 3600)
        m, sec = divmod(rem, 60)
        dd = getattr(core, '_dedupe', None)
        slots = len(getattr(dd, '_slots', {}) or {}) if dd is not None else 0

        groups: List[tuple] = []

        def group(title):
            groups.append((title, []))

        def kv(k, v, tone=''):
            groups[-1][1].append((k, v, tone))

        conn = bool(st.get('connected'))
        rssi = float(st.get('rssi', -140.0) or -140.0)
        thresh = float(st.get('rssiThreshold', 0.0) or 0.0)
        score = float(st.get('afcScore', 0.0) or 0.0)
        ferr = float(st.get('afcErrHz', 0.0) or 0.0)
        diag = str(stats.get('diagnostics', 'OK'))

        group('链路')
        kv('数据源', '%s  %s:%s' % (getattr(cfg, 'sourceType', '-'),
                                 getattr(cfg, 'host', '-'), getattr(cfg, 'port', '-')))
        kv('连接', '已连接' if conn else '未连接', 'ok' if conn else 'err')
        recon = int(stats.get('reconnectCount', 0) or 0)
        kv('重连次数', str(recon), 'warn' if recon else '')
        kv('接收字节', '%.1f MB' % (stats.get('bytesRecv', 0) / 1024 / 1024))
        kv('块率', '%.1f /s' % stats.get('blocksPerSec', 0.0))
        kv('数据速率', '%.2f Mbps' % stats.get('dataRateMbps', 0.0))
        kv('抖动 CV', '%.2f' % stats.get('jitterCv', 0.0))
        kv('运行时长', '%02d:%02d:%02d' % (h, m, sec))
        kv('诊断', diag, '' if diag in ('OK', '正常', '') else 'warn')

        group('射频与频谱')
        kv('中心频率', '%.4f MHz' % float(getattr(cfg, 'freqMhz', 0)))
        kv('采样率', '%d kS/s' % (int(getattr(cfg, 'sampleRate', 0)) // 1000))
        kv('块大小', str(getattr(cfg, 'blockSize', 0)))
        kv('硬件增益', '%.1f dB' % float(getattr(cfg, 'gainDb', 0)))
        kv('PPM', '%.1f' % float(getattr(cfg, 'ppm', 0)))
        kv('信道带宽', '%.1f kHz' % float(getattr(cfg, 'bwKhz', 0)))
        kv('DC 偏移', '%.0f Hz' % float(getattr(cfg, 'dcOffsetHz', 0)))
        kv('频谱模式', '图形' if getattr(cfg, 'spectrumMode', 'graph') == 'graph' else '终端')

        group('门控与 AFC')
        rTone = ''
        if conn:
            rTone = 'err' if rssi < -80 else ('warn' if rssi < -65 else (
                'ok' if rssi > thresh else ''))
        kv('信号强度', '%.1f dB' % rssi, rTone)
        kv('打开阈值', '%.1f dB' % thresh)
        kv('迟滞 / 保持', '%.1f dB / %.0f ms' % (float(getattr(cfg, 'rssiHystDb', 0)),
                                              float(getattr(cfg, 'rssiHoldMs', 0))))
        kv('RX 门控', str(st.get('rssiGate', 'OFF')),
           'ok' if str(st.get('rssiGate', 'OFF')) == 'ON' else '')
        kv('AFC 当前', '%+.0f Hz' % st.get('afcHz', 0.0))
        kv('频偏 FERR', '%+.0f Hz' % ferr, 'warn' if abs(ferr) > 200 else '')
        kv('AFC 置信度', '%.2f' % score,
           ('warn' if score < 0.10 else 'ok') if conn else '')
        kv('AFC 上限', '%.0f Hz' % float(getattr(cfg, 'afcMaxHz', 0)))
        kv('AFC 环路增益', '%.2f' % float(getattr(cfg, 'afcGain', 0)))
        kv('AFC 状态', '启用' if getattr(cfg, 'afcEnable', True) else '关闭')

        group('解码与去重')
        kv('合并窗口', '%.1f 秒（0=关闭）' % float(getattr(cfg, 'dedupeWindow', 0)))
        kv('合并丢弃', str(getattr(dd, 'dropped', 0) if dd is not None else 0))
        kv('择优升级', str(getattr(dd, 'upgraded', 0) if dd is not None else 0))
        kv('占用槽位', '%d / %d' % (slots, getattr(dd, 'maxSlots', 0) or 0))
        kv('车次规则', {'auto': '自动兼容', '2026': '2026 新版',
                     'legacy': '2014 旧版'}.get(
                         str(getattr(cfg, 'trainScheme', 'auto')), '自动兼容'))
        kv('当前列表', '%d 行' % self.currentPanel.table.rowCount())
        kv('历史显示', '%d 行' % self.historyPanel.table.rowCount())
        kv('地图列车', '%d 辆' % len(getattr(self.mapPanel, '_trains', {}) or {}),
           'ok' if getattr(self.mapPanel, '_trains', None) else '')

        group('界面')
        kv('主题', {'dark': '夜间', 'light': '日间'}.get(
            TH.P.get('mode', 'dark'), '-') +
           '（%s）' % {'dark': '夜间', 'light': '日间', 'auto': '跟随系统'}.get(
               str(getattr(cfg, 'theme', 'dark')), '夜间'))
        kv('界面缩放', '%.0f%%' % (UI_SCALE * 100))
        kv('窗口尺寸', '%d × %d' % (self.width(), self.height()))
        if hasattr(self, 'band1'):
            kv('上段高度', '%d px' % self.band1.height())
        if hasattr(self, 'band2'):
            kv('中段高度', '%d px' % self.band2.height())
        if hasattr(self, 'bottomBar'):
            kv('输出区高度', '%d px' % self.bottomBar.height())
        kv('字段列数', self._infoCols())
        kv('地图', '显示' if getattr(self, 'mapPanel', None)
           and self.mapPanel.isVisible() else '隐藏')
        icount = getattr(getattr(self, 'statusStrip', None), '_interfCount', 0)
        kv('干扰计数', '%d 次 / 60 秒' % icount, 'warn' if icount else '')
        return groups

    def statusReport(self) -> str:
        """把 statusGroups() 拼成纯文本（仪表板「复制全部」用）。"""
        lines = []
        for title, rows in self.statusGroups():
            lines.append('')
            lines.append('【%s】' % title)
            for k, v, _tone in rows:
                lines.append('  %-12s %s' % (k, v))
        return '\n'.join(lines)

    # ---- 关闭事件 ----
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        # 保存配置
        self.config.save(CONFIG_PATH)
        event.accept()


# ===========================================================================
# 运行状态仪表板
# ===========================================================================
class StatusDashboard(QDialog):
    """运行状态仪表板：把分散在各处的实时指标集中展示。

    v2.3：从“一整块纯文本”改成**分组卡片 + 指标方块**——每组一张卡，
    每个指标一个方块，正常是灰白，良好标绿、注意标黄、异常标红，
    扫一眼就知道该看哪一项。数值仍是每秒刷新，随时可「复制全部」成文本。
    """

    TONE_COLOR = {'ok': 'ok', 'warn': 'warn', 'err': 'err'}

    def __init__(self, main, parent=None):
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.main = main
        self.setWindowTitle('运行状态仪表板 —— 全部实时指标')
        self.resize(spx(720), spx(660))
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(spx(8), spx(8), spx(8), spx(8))
        outer.setSpacing(spx(6))

        bar = QHBoxLayout()
        bar.setSpacing(spx(8))
        self.hint = QLabel('每 1 秒刷新 · Ctrl+D 开关本窗口')
        self.hint.setStyleSheet(f'color: {CLR("faint")}; font-size: {spx(11)}px;')
        self.autoRefresh = QCheckBox('自动刷新')
        self.autoRefresh.setChecked(True)
        refreshBtn = QPushButton('立即刷新')
        refreshBtn.clicked.connect(self.refresh)
        copyBtn = QPushButton('复制全部')
        copyBtn.clicked.connect(self._copy)
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.close)
        bar.addWidget(self.hint)
        bar.addStretch()
        bar.addWidget(self.autoRefresh)
        bar.addWidget(refreshBtn)
        bar.addWidget(copyBtn)
        bar.addWidget(closeBtn)
        outer.addLayout(bar)

        # 卡片区放进滚动区：小屏上也不挤压，纵向滚动即可
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.bodyLayout = QVBoxLayout(self.body)
        self.bodyLayout.setContentsMargins(0, 0, spx(4), 0)
        self.bodyLayout.setSpacing(spx(6))
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        #: (组, 项目) -> (值标签, 方块, 上次色调)
        self.tiles: Dict[tuple, tuple] = {}
        self._structure = None

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._onTick)
        self.timer.start()
        self.refresh()

    # ------------------------------------------------------------------
    def _onTick(self):
        if self.autoRefresh.isChecked() and self.isVisible():
            self.refresh()

    def _clearBody(self):
        while self.bodyLayout.count():
            item = self.bodyLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.tiles.clear()

    def _buildBody(self, groups):
        """按分组结构建卡片与方块（只在项目集合变化时重建一次）。"""
        self._clearBody()
        for title, rows in groups:
            card = QWidget()
            card.setObjectName('card')
            card.setAttribute(Qt.WA_StyledBackground, True)
            v = QVBoxLayout(card)
            v.setContentsMargins(spx(8), spx(5), spx(8), spx(7))
            v.setSpacing(spx(4))

            head = QLabel(title)
            head.setStyleSheet(
                f'color: {CLR("accent")}; font-size: {spx(12)}px; font-weight: bold;'
                ' background: transparent; border: none;')
            v.addWidget(head)

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(spx(6))
            grid.setVerticalSpacing(spx(5))
            cols = 4
            for i, (label, _val, _tone) in enumerate(rows):
                tile = QWidget()
                tile.setObjectName('chip')
                tile.setAttribute(Qt.WA_StyledBackground, True)
                tv = QVBoxLayout(tile)
                tv.setContentsMargins(spx(8), spx(3), spx(8), spx(4))
                tv.setSpacing(0)
                cap = QLabel(label)
                cap.setStyleSheet(
                    f'color: {CLR("faint")}; font-size: {spx(10)}px;'
                    ' background: transparent; border: none;')
                val = QLabel('--')
                val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                val.setStyleSheet(
                    f'color: {CLR("text")}; font-size: {spx(14)}px; font-weight: bold;'
                    ' background: transparent; border: none;')
                tv.addWidget(cap)
                tv.addWidget(val)
                r, c = divmod(i, cols)
                grid.addWidget(tile, r, c)
                self.tiles[(title, label)] = [val, tile, '']
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            v.addLayout(grid)
            self.bodyLayout.addWidget(card)
        self.bodyLayout.addStretch(1)

    def refresh(self):
        try:
            groups = self.main.statusGroups()
        except Exception as e:                     # 绝不让仪表板把主程序带崩
            groups = [('采集失败', [('错误', repr(e), 'err')])]
        structure = tuple((t, tuple(k for k, _v, _x in rows)) for t, rows in groups)
        if structure != self._structure:
            self._structure = structure
            self._buildBody(groups)

        for title, rows in groups:
            for label, value, tone in rows:
                cell = self.tiles.get((title, label))
                if cell is None:
                    continue
                val, tile, old_tone = cell
                val.setText(str(value))
                color = CLR(self.TONE_COLOR.get(tone, 'text'))
                val.setStyleSheet(
                    f'color: {color}; font-size: {spx(14)}px; font-weight: bold;'
                    ' background: transparent; border: none;')
                if tone != old_tone:
                    if tone:
                        tile.setStyleSheet(
                            f'QWidget#chip {{ background-color: {CLR("panel2")};'
                            f' border: 1px solid {CLR(self.TONE_COLOR[tone])};'
                            ' border-radius: 3px; }')
                    else:
                        tile.setStyleSheet('')
                    cell[2] = tone

    def _copy(self):
        try:
            text = self.main.statusReport()
        except Exception as e:
            text = '采集状态失败：%r' % (e,)
        QApplication.clipboard().setText(text)
        self.hint.setText('已复制到剪贴板（%d 行）' % text.count('\n'))


# ===========================================================================
# 主函数
# ===========================================================================
def normalize_sources(config: CoreConfig, first_run: bool = False):
    """补齐数据源列表，必要时把顶层连接参数同步到激活数据源。

    - 老配置没有 sources 时，按原 host/port 生成一条，保证行为不变
    - 首次运行默认选中“本机 USB（自动）”，实现插上即用
    - 始终保证列表里有本机 USB 选项，方便老用户切换
    """
    if not config.sources:
        config.sources = default_sources(config)
    if not any(s.get('type') == 'rtl_usb' for s in config.sources):
        usb = dict(default_sources(config)[0])
        config.sources.insert(0, usb)
        if not first_run:
            config.activeSource = int(getattr(config, 'activeSource', 0)) + 1
    if first_run:
        config.activeSource = next(
            (i for i, s in enumerate(config.sources) if s.get('type') == 'rtl_usb'), 0)
    if not (0 <= int(config.activeSource) < len(config.sources)):
        config.activeSource = 0
    if first_run:
        src = config.sources[config.activeSource]
        config.sourceType = src.get('type', 'rtl_usb')
        config.owrxMode = (config.sourceType == 'owrx')
        config.host = src.get('host', '127.0.0.1')
        config.port = int(src.get('port', 1234))
        config.sampleRate = int(src.get('sampleRate', 960000))
        config.gainDb = float(src.get('gainDb', HW_GAIN_DB))
        config.ppm = float(src.get('ppm', PPM))
        config.dcOffsetHz = float(src.get('dcOffsetHz', 50000.0))


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
    first_run = FIRST_RUN
    config = CoreConfig.load(CONFIG_PATH)
    normalize_sources(config, first_run)
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

    # 高 DPI：允许非整数缩放（125%/150% 更平滑）。必须在 QApplication 之前设置
    try:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # 外观主题：dark / light / auto（auto 读系统配色），必须在建窗口之前定好
    resolved_theme = TH.applyMode(str(getattr(config, 'theme', 'dark') or 'dark'))
    applyPgTheme()

    # 界面缩放：0（或老的 100%）= 按屏幕自动；其余用配置倍率
    # 大屏给小屏同一条布局，但字号/控件尺寸按档位放大（v2.4：大屏别再看小字）
    global UI_SCALE
    UI_SCALE = resolveUiScale(config)
    K.setScale(UI_SCALE)
    app.setStyleSheet(scale_qss(TH.styleSheet()) + scale_qss(TOUCH_STYLE))

    # Fluent 外观层：强调色、字体、深浅色（qfluentwidgets 缺失时自动降级）
    K.setupApp(app)
    K.applyTheme(resolved_theme)
    # Fluent 控件的字号是构造时 setFont 定的，不吃应用级 QSS —— 用事件过滤器补上缩放
    K.installFontScaler(app)

    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = MainWindow(config)
    if args.no_autostart:
        window.statusBar().showMessage('点击 文件 → 启动 DSP 开始')
    window.show()
    window.logBus.appendLog(
        f'[启动] 主题 {resolved_theme}（{getattr(config, "theme", "dark")}），'
        f'界面缩放 {UI_SCALE:.2f}x，去重窗口 {config.dedupeWindow:.1f}s')

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
