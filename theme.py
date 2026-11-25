# -*- coding: utf-8 -*-
"""theme.py — CR-LBJ-Receiver 主题（v2.2）

配色取中国铁路视觉识别系统标准色：
    主色    红  Pantone 485C  → #DA291C
    辅助色  蓝  Pantone 286C  → #003DA5

三档模式：dark（夜间）/ light（日间）/ auto（跟随系统）。
样式表由同一份模板 + 调色板生成，避免两套 QSS 各改各的。
"""

from __future__ import annotations

import string

CR_RED = '#DA291C'          # Pantone 485C
CR_RED_DARK = '#A81C12'
CR_RED_LIGHT = '#F0604F'
CR_BLUE = '#003DA5'         # Pantone 286C
CR_BLUE_LIGHT = '#4C8DFF'

# ---------------------------------------------------------------------------
# 调色板
# ---------------------------------------------------------------------------
DARK = {
    'mode': 'dark',
    'bg': '#14161a',          # 窗口底色
    'panel': '#191c21',       # 卡片/分组底色
    'panel2': '#1e2228',      # 表格交替行、次级面板
    'border': '#2b3138',
    'border_strong': '#3a424c',
    'text': '#d8dee6',
    'dim': '#8c97a3',
    'faint': '#626c78',
    'accent': CR_RED,         # 主强调（分组标题、选中下划线、折线）
    'accent_soft': CR_RED_LIGHT,
    'accent2': CR_BLUE_LIGHT,  # 次强调（上行、链接、数值高亮）
    'ok': '#2FBF71',
    'warn': '#F0A020',
    'err': '#E5484D',
    'sel': '#3a1c19',         # 选中行底色（红调）
    'sel_text': '#ffffff',
    'hdr': '#20242a',
    'btn': '#23272d',
    'btn_hover': '#2c3138',
    'input': '#22262c',
    'menu': '#1a1d21',
    'status': '#101215',
    'map_line': '#4C8DFF',    # 地图轨迹（上行）
    'map_line2': '#F0604F',   # 地图轨迹（下行）
}

LIGHT = {
    'mode': 'light',
    'bg': '#f5f7f9',
    'panel': '#ffffff',
    'panel2': '#eef2f6',
    'border': '#d5dce4',
    'border_strong': '#b9c4d0',
    'text': '#1b2026',
    'dim': '#5a6572',
    'faint': '#8b95a1',
    'accent': CR_RED,
    'accent_soft': CR_RED_DARK,
    'accent2': CR_BLUE,
    'ok': '#1F8A4C',
    'warn': '#A96500',
    'err': '#C62828',
    'sel': '#fbe4e1',
    'sel_text': '#1b2026',
    'hdr': '#eef2f6',
    'btn': '#ffffff',
    'btn_hover': '#eef2f6',
    'input': '#ffffff',
    'menu': '#ffffff',
    'status': '#e9eef3',
    'map_line': '#003DA5',
    'map_line2': '#DA291C',
}

PALETTES = {'dark': DARK, 'light': LIGHT}

# 当前生效的调色板（启动时由 applyMode() 决定，运行期不再变）
P = dict(DARK)


def resolveMode(mode: str) -> str:
    """把配置里的主题模式解析成 dark / light。

    auto 时读取系统配色；取不到按夜间（默认面向暗室值守）。
    """
    m = str(mode or 'dark').lower()
    if m in ('dark', 'light'):
        return m
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme() if hints is not None else None
        if scheme == Qt.ColorScheme.Light:
            return 'light'
        if scheme == Qt.ColorScheme.Dark:
            return 'dark'
    except Exception:
        pass
    return 'dark'


def applyMode(mode: str) -> str:
    """设置全局调色板，返回实际生效的模式（dark / light）。"""
    resolved = resolveMode(mode)
    P.clear()
    P.update(PALETTES[resolved])
    P['requested'] = str(mode or 'dark')
    return resolved


def c(key: str, fallback: str = '#888888') -> str:
    """取当前调色板颜色。"""
    return P.get(key, fallback)


# ---------------------------------------------------------------------------
# 样式表模板（$name 由调色板填充；QSS 的 {} 不受影响）
# ---------------------------------------------------------------------------
_QSS = """
QMainWindow, QDialog { background-color: $bg; }
QDialog QWidget { background-color: $bg; }
QWidget { color: $text; background-color: transparent; font-size: 13px; }

QGroupBox {
    border: 1px solid $border; border-radius: 4px;
    margin-top: 8px; padding-top: 6px;
    padding-left: 6px; padding-right: 6px; padding-bottom: 4px;
    font-weight: bold; background-color: $panel;
}
QGroupBox::title {
    color: $accent; subcontrol-origin: margin; left: 10px; padding: 0 5px;
}

QPushButton {
    background-color: $btn; border: 1px solid $border_strong;
    border-radius: 3px; padding: 5px 16px; min-width: 60px; color: $text;
}
QPushButton:hover { background-color: $btn_hover; border-color: $accent; }
QPushButton:pressed { background-color: $bg; }
QPushButton:disabled { color: $faint; border-color: $border; }
QPushButton:checked { border-color: $accent; color: $accent; }

/* 表格：QTableView 这一条是给 Fluent 的 TableWidget 用的——
   它继承自 QTableView 而不是 QTableWidget，只写 QTableWidget 匹配不到，
   结果 Fluent 的透明背景 + Fusion 的白色 Base 会画出大片白底。 */
QTableWidget, QTableView {
    gridline-color: $border; background-color: $panel;
    alternate-background-color: $panel2;
    selection-background-color: $sel; selection-color: $sel_text;
    font-size: 12px; color: $text;
}
QHeaderView::section {
    background-color: $hdr; border: 1px solid $border;
    padding: 4px; font-weight: bold; color: $accent;
}
QTableCornerButton::section { background-color: $hdr; border: 1px solid $border; }

QTextEdit { background-color: $status; border: 1px solid $border;
            font-family: Consolas, monospace; font-size: 12px; color: $text; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: $input; border: 1px solid $border_strong;
    border-radius: 2px; padding: 3px; min-height: 22px; color: $text;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: $accent;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: $panel; border: 1px solid $border;
    selection-background-color: $sel; selection-color: $sel_text;
}

QCheckBox { spacing: 6px; color: $text; }
QCheckBox::indicator { width: 14px; height: 14px; }
QRadioButton { color: $text; }
QFormLayout { spacing: 4px; }
QLabel { color: $text; background-color: transparent; }
QGroupBox QLabel { color: $text; }

QMenuBar { background-color: $bg; border-bottom: 1px solid $border; }
QMenuBar::item { padding: 4px 12px; background-color: transparent; color: $text; }
QMenuBar::item:selected { background-color: $btn_hover; }
QMenu { background-color: $menu; border: 1px solid $border_strong; }
QMenu::item { padding: 6px 24px; color: $text; }
QMenu::item:selected { background-color: $sel; color: $sel_text; }
QMenu::separator { height: 1px; background: $border; margin: 4px 8px; }

QTabWidget::pane { border: 1px solid $border; background-color: $panel; }
QTabBar { background-color: transparent; }
QTabBar::tab {
    background-color: $panel2; padding: 6px 16px; color: $dim;
    border: 1px solid $border; border-bottom: none; margin-right: 2px;
}
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected {
    background-color: $panel; color: $accent;
    border-bottom: 2px solid $accent;
}

/* 全景布局的卡片容器（v2.3） */
QWidget#card {
    background-color: $panel; border: 1px solid $border; border-radius: 4px;
}
QLabel#cardTitle {
    color: $accent; background: transparent; border: none;
    font-weight: bold;
}
QWidget#chip {
    background-color: $panel2; border: 1px solid $border; border-radius: 3px;
}

QStatusBar { background-color: $status; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QSplitter::handle { background-color: $border; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical {
    background: $border_strong; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal {
    background: $border_strong; border-radius: 5px; min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: $accent; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip {
    background-color: $menu; color: $text; border: 1px solid $accent;
    padding: 4px 6px;
}
"""


def styleSheet() -> str:
    """生成当前主题的 QSS。"""
    return string.Template(_QSS).safe_substitute(P)


def mapColors() -> dict:
    """地图页面用的颜色（随主题、也随夜间模式）。"""
    return {
        'up': P.get('map_line', CR_BLUE_LIGHT),
        'down': P.get('map_line2', CR_RED_LIGHT),
        'unknown': '#E0A400',
        'red': CR_RED,
        'blue': P.get('accent2', CR_BLUE),
        'text': P.get('text', '#d8dee6'),
        'bg': P.get('panel', '#191c21'),
    }
