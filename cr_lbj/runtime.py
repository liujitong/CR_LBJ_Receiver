#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享运行时：路径、常量、界面缩放、控件别名与主题辅助。

本模块由原 SDR_ALL_LBJ_GUI.py 的模块级部分抽出，是 GUI 各实现模块唯一的
公共依赖。运行时状态（界面倍率、主题色）通过 ui/widgets.py 与 ui/theme.py
的模块对象共享，拆分模块后不会各自持有过期副本。
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
from cr_lbj.core.decoder import (
    LbjCore, CoreConfig, DecodeResult,
    RTL_SAMPLE_RATE, TCP_HOST, TCP_PORT,
    DEFAULT_BW_KHZ, DEFAULT_RSSI_THRESHOLD_DB, DEFAULT_RSSI_HYST_DB,
    DEFAULT_RSSI_HOLD_MS, DEFAULT_AFC_MAX_HZ, DEFAULT_ETA_MAX_SECONDS,
    HW_GAIN_DB, PPM, BLOCK_SIZE, BASEBAND_RATE,
    detect_rtl_devices, find_rtl_tool,
)
from cr_lbj.data.loco_info import lookup_loco, format_loco_brief
from cr_lbj.ui.map_panel import MapPanel, HAS_WEBENGINE
from cr_lbj.ui import theme as TH
from cr_lbj.ui.theme import c as CLR

# Fluent Design 外观层（qfluentwidgets 封装，见 ui_kit.py；缺库自动退回原生控件）
from cr_lbj.ui import widgets as K
from cr_lbj.ui.widgets import CardBox


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
from PySide6.QtGui import (QColor, QBrush, QFont, QFontMetrics, QTextCursor,
                           QIcon, QAction, QDesktopServices,
                           QCursor, QGuiApplication)
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
    """设计像素 -> 当前倍率下的像素。

    倍率统一存放在 ui/widgets.py（K.setScale / K.scale）：拆分模块后所有
    spx() 调用读的是同一份状态，不会因各模块各自持有 UI_SCALE 而失步。
    """
    return max(1, int(round(float(v) * K.scale())))


def scale_qss(text: str) -> str:
    """按 UI_SCALE 缩放 QSS 中的所有 NNpx（pt 不动）。"""
    if abs(K.scale() - 1.0) < 0.01:
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
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


from cr_lbj.utils.helpers import safeFloat  # noqa: E402


# ===========================================================================
# DSP 桥接线程：把 LbjCore 的回调桥接到 Qt 信号
# ===========================================================================
