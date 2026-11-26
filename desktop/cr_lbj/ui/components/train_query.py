#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""车次查询线程、时刻表、车次信息与机车信息面板。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

from cr_lbj.data import depot_names
from cr_lbj.data import loco_roster   # v3.0：机车配属号段表（型号 + 号 → 局段）
from cr_lbj.ui.info_lookup import (
    TrainFullQueryWorker, source_name, timetable_data, train_display)
from cr_lbj.ui.ui_threads import keep_thread as _keepWorker


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
        # 底色自己铺：QSS 里的 QDialog 规则会被后面的 QWidget{transparent} 盖掉，
        # 不铺就会露出系统白底，深色主题下按钮直接看不见
        K.paintBackground(self)

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
    """车次信息卡片（v3.1.1）：RailGo 车次信息 + 时刻表入口。

    数据源按 `train_info.query(train, prefer)` 走——默认先 RailGo（字段全），
    失败自动退 12306；结果异步取回，不阻塞解码。展示内容：

        ① 始发 → 终到（带车次）
        ② 等级 · 担当局+担当段（全称直接拼接，如「南昌局南昌客运段」）
        ③ 配属段 / 车辆段 · 车型
        ④ 来源（RailGo / 12306）与时刻表提示

    「查看时刻表」按钮在拿到 stops 后可用；时刻表同样来自这份查询结果
    （RailGo 的 timetable 或 12306 兜底），不再单独发第二次请求。
    """

    doubleClicked = Signal()

    def __init__(self):
        super().__init__()
        self._cache: Dict[str, dict] = {}  # {train: train_info.query 结果}
        self._worker: Optional[TrainFullQueryWorker] = None
        self._lastQueryCode = ''
        self._currentData: Optional[dict] = None

        # 横向排：左边结论 + 说明，右边按钮——整行宽度都用得上
        outer = QHBoxLayout(self)
        outer.setContentsMargins(spx(10), spx(8), spx(10), spx(6))
        outer.setSpacing(spx(10))

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(spx(2))
        col.addStretch(1)

        self.titleLabel = QLabel('等待详细报文...')
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.titleLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(self.titleLabel)

        self.dutyLabel = QLabel('')
        self.dutyLabel.setWordWrap(True)
        self.dutyLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.dutyLabel)

        self.ownerLabel = QLabel('')
        self.ownerLabel.setWordWrap(True)
        self.ownerLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.ownerLabel)

        self.hintLabel = QLabel('')
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.hintLabel)
        col.addStretch(1)
        outer.addLayout(col, 1)

        self.openBtn = QPushButton('查看时刻表')
        self.openBtn.setToolTip('双击卡片也可打开（RailGo 时刻表 / 12306 兜底）')
        self.openBtn.setEnabled(False)
        self.openBtn.setMinimumWidth(spx(96))
        self.openBtn.clicked.connect(self._openTimetable)
        outer.addWidget(self.openBtn, 0, Qt.AlignVCenter)
        self._reset()

    # ------------------------------------------------------------------
    # 状态样式
    # ------------------------------------------------------------------
    def _setLabels(self, title: str, duty: str = '', owner: str = '',
                   hint: str = '', kind: str = 'idle'):
        """统一更新卡片文字/配色/按钮可用性（kind: idle/info/ok/warn/err）。"""
        colors = {
            'idle': CLR('faint'), 'info': CLR('dim'), 'ok': CLR('ok'),
            'warn': CLR('warn'), 'err': CLR('err'),
        }
        fg = colors.get(kind, colors['idle'])
        weight = 'bold' if kind in ('ok', 'err', 'info') else 'normal'
        self.titleLabel.setText(title)
        self.titleLabel.setStyleSheet(
            f'color: {fg}; font-size: {spx(13)}px; font-weight: {weight};'
            ' background: transparent;')
        self.dutyLabel.setText(duty)
        self.dutyLabel.setStyleSheet(
            f'color: {CLR("text")}; font-size: {spx(11)}px;'
            ' background: transparent;')
        self.dutyLabel.setVisible(bool(duty))
        self.ownerLabel.setText(owner)
        self.ownerLabel.setStyleSheet(
            f'color: {CLR("dim")}; font-size: {spx(10)}px;'
            ' background: transparent;')
        self.ownerLabel.setVisible(bool(owner))
        self.hintLabel.setText(hint)
        self.hintLabel.setStyleSheet(
            f'color: {CLR("faint")}; font-size: {spx(10)}px;'
            ' background: transparent;')

    def _reset(self, title: str = '等待详细报文...',
               hint: str = '收到长报文后自动查询车次信息'):
        self._currentData = None
        self._setLabels(title, hint=hint)
        self.openBtn.setEnabled(False)
        self.openBtn.setText('暂无可查时刻表')

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if self._currentData:
            self.doubleClicked.emit()

    def _openTimetable(self):
        if self._currentData and self._currentData.get('stops'):
            dlg = TimetableDialog(timetable_data(self._currentData), self)
            dlg.exec()
        else:
            QMessageBox.information(
                self, '提示', '还没有可查询的时刻表。\n\n'
                '收到长报文后会自动查询车次（RailGo 优先，失败退 12306）；'
                '货运、路用、回送等未收录车次没有时刻表数据。')

    # ------------------------------------------------------------------
    # 数据入口
    # ------------------------------------------------------------------
    def onTrainDecoded(self, d: dict, prefer: str = 'auto'):
        """当解码到详细车次信息时触发异步查询（RailGo 优先，12306 兜底）。"""
        if not d.get('isDetailed'):
            self._reset()
            return

        train = str(d.get('train', '') or '')
        if not train or train in ('----', '未知'):
            self._reset('等待车次号...', '收到详细报文后自动查询')
            return

        # 已有结果（成功或失败都缓存）：直接显示，避免每帧重复请求
        if train in self._cache:
            self._displayResult(self._cache[train])
            return
        if self._lastQueryCode == train and self._worker and self._worker.isRunning():
            return

        self._lastQueryCode = train
        self._currentData = None
        self._setLabels(f'查询中: {train} …',
                        hint='正在请求车次数据（RailGo 优先，失败退 12306）',
                        kind='info')
        self.openBtn.setEnabled(False)
        self.openBtn.setText('暂无可查时刻表')

        self._worker = TrainFullQueryWorker(train, prefer or 'auto')
        _keepWorker(self._worker)      # 防止旧线程在运行中被回收
        self._worker.ready.connect(lambda res, t=train: self._onQueryResult(t, res))
        self._worker.start()

    def _onQueryResult(self, train: str, res: dict):
        # 失败也缓存（负缓存）：同一车次不反复打网络，换个车次再查
        self._cache[train] = res or {}
        while len(self._cache) > 20:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._displayResult(self._cache[train])

    def _displayResult(self, res: dict):
        res = res or {}
        disp = train_display(res)
        self._currentData = res if res.get('stops') else None
        canOpen = bool(res.get('stops'))
        self.openBtn.setEnabled(canOpen)
        self.openBtn.setText('查看时刻表' if canOpen else '暂无可查时刻表')

        if not disp['ok']:
            err = disp['error'] or 'RailGo / 12306 均未返回数据'
            self._setLabels(f'未查询到 {disp["train"] or "该车次"} 的车次信息',
                            hint=f'{err} · 不影响解码与地图定位', kind='warn')
            return

        title = disp['range_text'] or disp['train'] or '车次信息'
        if disp['range_text'] and disp['train']:
            title = f'{disp["train"]}  {disp["range_text"]}'
        if disp['start_time'] or disp['end_time']:
            title += '  (%s / %s)' % (disp['start_time'] or '--:--',
                                      disp['end_time'] or '--:--')
        duty_bits = []
        if disp['grade']:
            duty_bits.append(disp['grade'])
        if disp['duty']:
            duty_bits.append('担当 ' + disp['duty'])
        owner_bits = []
        if disp['owner']:
            owner_bits.append('配属 ' + disp['owner'])
        if disp['model']:
            owner_bits.append('车型 ' + disp['model'])
        hint = '来源 %s' % source_name(disp['source'])
        hint += ' · 双击查看详细时刻表' if canOpen else ' · 未返回时刻表数据'
        self._setLabels(title, duty=' · '.join(duty_bits),
                        owner=' · '.join(owner_bits), hint=hint, kind='ok')


class LocoInfoPanel(QWidget):
    """机车信息卡片：车型 + **配属单位全称** + 制造厂全称 + 参数摘要。

    数据来自两处，各有分工：
        cr_lbj/data/loco_info.py     报文「机车代号」→ 车型名/类型/轴式/简介
        cr_lbj/data/loco_roster.py   型号 + 机车号 → 配属局段（号段表命中）

    v3.1.1：号段表里的配属是简称（`上局沪段`），卡片按用户要求显示全称
    （`上海局上海机务段`），制造厂同理（`中车株洲电力机车有限公司`）；
    配属与制造厂各占一行、自动换行，不再截断拼接。
    """

    detailRequested = Signal(dict)

    def __init__(self):
        super().__init__()
        self._last: dict = {}

        # 横向排：左侧机型/配属/参数，右侧「配属查询」按钮
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

        # 配属单位（v3.0 新增）：命中号段时绿色，只认出型号时黄色
        self.depotLabel = QLabel('')
        self.depotLabel.setStyleSheet(f'color: {CLR("dim")}; font-size: {spx(10)}px;')
        self.depotLabel.setWordWrap(True)
        self.depotLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.depotLabel)

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

        self.detailBtn = QPushButton('配属查询')
        self.detailBtn.setToolTip('打开「机车配属查询」，可看号段、制造厂与完整参数')
        self.detailBtn.setMinimumWidth(spx(96))
        self.detailBtn.setEnabled(False)
        self.detailBtn.clicked.connect(
            lambda: self.detailRequested.emit(self._last))
        outer.addWidget(self.detailBtn, 0, Qt.AlignVCenter)

    def updateLoco(self, d: dict):
        """根据解码记录更新机车卡片（车型 + 配属 + 参数摘要）。"""
        self._last = dict(d or {})
        loco_number = d.get('loco', '') if d else ''
        loco_code = d.get('locoCode', d.get('loco_code', '')) if d else ''
        if not d or not d.get('isDetailed'):
            self.nameLabel.setText('等待详细报文...')
            self.nameLabel.setStyleSheet(
                f'color: {CLR("faint")}; font-size: {spx(12)}px; font-weight: bold;')
            self.depotLabel.setText('')
            self.detailLabel.setText('')
            self.briefLabel.setText(
                '收到扩展长报文（1234002 / 1234001）后自动填充机型、配属与牵引参数')
            self.detailBtn.setEnabled(False)
            return

        info = lookup_loco(loco_code=loco_code, loco_number=loco_number)
        roster = {}
        try:
            roster = loco_roster.lookup_loco(loco_number, loco_code) or {}
        except Exception:
            roster = {}

        # ---- 标题：机车号 + 车型名（两个数据源互相补位）----
        model_name = (info or {}).get('name', '') or roster.get('name', '') \
            or roster.get('model', '')
        head = loco_number or model_name or '未知机车'
        if model_name and model_name not in head:
            head = '%s  %s' % (head, model_name)
        self.nameLabel.setText(head)
        hit = bool(roster.get('exact'))
        self.nameLabel.setStyleSheet(
            f'color: {CLR("ok") if (info or hit) else CLR("warn")};'
            f' font-size: {spx(12)}px; font-weight: bold;')

        # ---- 配属（v3.1.1）：命中号段 → 全称局段 + 号段 + 全称制造厂（分两行） ----
        specs = {}
        try:
            specs = loco_roster.specs_for(roster.get('model') or model_name) or {}
        except Exception:
            specs = {}
        maker_raw = (str(roster.get('maker') or '').strip()
                     or str((info or {}).get('maker') or '').strip()
                     or str(specs.get('maker') or '').strip())
        if hit:
            depot = depot_names.full_depot(str(roster.get('depot') or '').strip())
            depot = depot or '（原表未标注配属）'
            range_txt = str(roster.get('range') or '').strip()
            head = '配属：' + depot
            if range_txt:
                head += '（号段 %s）' % range_txt
            maker = depot_names.full_maker(maker_raw)
            lines = [head]
            if maker:
                lines.append('制造厂：' + maker)
            self.depotLabel.setText('\n'.join(lines))
            self.depotLabel.setStyleSheet(
                f'color: {CLR("ok")}; font-size: {spx(10)}px; font-weight: bold;')
        elif roster.get('ok'):
            self.depotLabel.setText('配属：未知（%s）'
                                    % (roster.get('reason') or '号段未收录'))
            self.depotLabel.setStyleSheet(
                f'color: {CLR("warn")}; font-size: {spx(10)}px;')
        else:
            self.depotLabel.setText('配属：%s'
                                    % (roster.get('reason') or '配属表未收录该型号'))
            self.depotLabel.setStyleSheet(
                f'color: {CLR("faint")}; font-size: {spx(10)}px;')

        # ---- 参数摘要：编码器给的简介优先，其次号段表的 specs ----
        maker_full = depot_names.full_maker(maker_raw)
        if info:
            self.detailLabel.setText(
                f"{info.get('type', '')} | {maker_full or info.get('maker', '')}"
                f" | {info.get('axle', '')}")
        elif specs:
            self.detailLabel.setText(' | '.join(x for x in (
                str(specs.get('type') or ''), maker_full,
                str(specs.get('axle') or '')) if x))
        else:
            self.detailLabel.setText(f'代号: {loco_code}' if loco_code else '')

        brief = (info or {}).get('brief', '') or str(specs.get('brief') or '')
        pows = str(specs.get('power') or '').strip()
        spds = str(specs.get('speed') or '').strip()
        head_bits = [x for x in (pows, spds) if x]
        if head_bits and brief:
            brief = ' · '.join(head_bits) + '\n' + brief
        elif head_bits:
            brief = ' · '.join(head_bits)
        self.briefLabel.setText(brief or '暂无该车型资料')
        self.detailBtn.setEnabled(True)

    def refreshRoster(self):
        """号段表更新后重算一次配属（主窗口在数据更新完成时调用）。"""
        if self._last:
            self.updateLoco(self._last)


# ===========================================================================
# 主窗口
# ===========================================================================
