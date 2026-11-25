#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实时频谱面板与终端频谱面板。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

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
