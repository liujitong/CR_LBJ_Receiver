#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""车次查询线程、时刻表、车次信息与机车信息面板。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

from cr_lbj.data import loco_roster   # v3.0：机车配属号段表（型号 + 号 → 局段）
from cr_lbj.ui.ui_threads import keep_thread as _keepWorker

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
        _keepWorker(self._worker)      # 防止旧线程在运行中被回收
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
    """机车信息卡片（v3.0）：车型 + **配属局段** + 参数摘要，入口进配属查询。

    数据来自两处，各有分工：
        cr_lbj/data/loco_info.py     报文「机车代号」→ 车型名/类型/轴式/简介
        cr_lbj/data/loco_roster.py   型号 + 机车号 → 配属局段（号段表命中）
    后者是 v3.0 新增的「车次/机车配属查询」的数据基础，同一套 CSV 也给安卓端用。
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

        # ---- 配属（v3.0）：命中号段 → 局段 + 区间；否则说明原因 ----
        if hit:
            depot = str(roster.get('depot') or '').strip() or '（原表未标注配属）'
            note = ('号段 %s' % roster.get('range')) if roster.get('range') else ''
            maker = str(roster.get('maker') or '').strip()
            bits = [depot]
            if note:
                bits.append(note)
            if maker:
                bits.append(maker)
            self.depotLabel.setText('配属：' + ' · '.join(bits))
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
        specs = {}
        try:
            specs = loco_roster.specs_for(roster.get('model') or model_name) or {}
        except Exception:
            specs = {}
        if info:
            self.detailLabel.setText(
                f"{info.get('type', '')} | {info.get('maker', '')} | {info.get('axle', '')}")
        elif specs:
            self.detailLabel.setText(' | '.join(x for x in (
                str(specs.get('type') or ''), str(specs.get('maker') or ''),
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
