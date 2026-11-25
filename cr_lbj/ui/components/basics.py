#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础展示组件：字段网格、单行日志尾。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

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
        lay.setContentsMargins(0, 0, 0, 0)
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
