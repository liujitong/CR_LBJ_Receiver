#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""车次信息、接收状态、当前解码面板。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

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
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spx(8))
        self.dot = QLabel('●')
        self.mainLabel = QLabel(self._main)
        self.mainLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.briefLabel = QLabel(self._brief)
        self.briefLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)
        lay.addWidget(self.mainLabel, 0, Qt.AlignVCenter)
        lay.addWidget(self.briefLabel, 1, Qt.AlignVCenter)
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
            f' font-size: {max(10.0, px * 0.72):.1f}px;')
        self._elide()

    def _elide(self):
        # 一行排开：结论优先保宽度，读数按剩余宽度省略
        fm = self.mainLabel.fontMetrics()
        self.mainLabel.setText(self._main)
        used = fm.horizontalAdvance(self._main) + spx(24)
        fm2 = self.briefLabel.fontMetrics()
        avail = max(40, self.width() - used)
        self.briefLabel.setText(
            fm2.elidedText(self._brief, Qt.ElideRight, avail))

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
