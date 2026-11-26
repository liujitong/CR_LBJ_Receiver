#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""query_ui.py — 车次查询 / 机车配属查询对话框（v3.0）。

一个对话框、两个页签，对应值班时最常问的两件事：

    ① 车次查询   输入 G7 / K1234 → 等级、担当局、客运段、配属段、车型、
                 开行日、交路、全程时刻表
    ② 机车配属   输入 HXD1D 0123 / HXD1D-0123 / 韶山4-0123 → 配属局段、
                 号段区间、制造厂、车型技术参数

数据层（另一份代码，不在本模块）：
    `cr_lbj.data.train_info`  车次查询（RailGo 优先，失败退 12306）
    `cr_lbj.data.loco_roster` 号段表查询（内置快照 + 用户可写覆盖层）

两个约定：

* **网络查询一律在 QThread 里**：`train_info.query()` 最长 ~20 秒（两个源各 10 秒
  超时），放 UI 线程就是界面假死。
* **号段表查询是本地 CSV**：818 KB 的表首次解析约 0.1~0.3 秒，直接同步调用即可，
  超过一千次/秒也不会卡（表只解析一次，进程内缓存）。

对外接口：
    QueryDialog(config=None, parent=None, tab='train', train='', loco='')
        tab:'train' 车次页 / 'loco' 配属页；train/loco 预填并自动查询
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from cr_lbj.data import loco_roster, train_info
from cr_lbj.ui import data_update

from cr_lbj.runtime import *  # noqa: F401,F403


# ===========================================================================
# 后台线程：车次查询
# ===========================================================================
class TrainInfoThread(QThread):
    """后台跑 `train_info.query()`，结果一次性回主线程。"""

    done = Signal(dict)

    def __init__(self, train: str, prefer: str = 'auto',
                 dateStr: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.train = str(train or '')
        self.prefer = str(prefer or 'auto')
        self.dateStr = dateStr

    def run(self):
        try:
            res = train_info.query(self.train, prefer=self.prefer,
                                   dateStr=self.dateStr)
        except Exception as e:                       # noqa: BLE001 - 界面不允许崩
            res = {'ok': False, 'error': '查询异常：%s' % (e or e.__class__.__name__),
                   'train': self.train, 'source': ''}
        if not isinstance(res, dict):
            res = {'ok': False, 'error': '数据层返回结构异常', 'train': self.train}
        self.done.emit(res)


# ===========================================================================
# 小工具
# ===========================================================================
def _keepThread(worker) -> None:
    """登记线程保活（见 `cr_lbj/ui/ui_threads.py`：关窗/退出时不能有运行中的线程）。"""
    from cr_lbj.ui.ui_threads import keep_thread
    keep_thread(worker)


def _fmt(v: Any, default: str = '—') -> str:
    """空值统一显示成「—」，避免界面上出现一片空白/None。"""
    if v is None:
        return default
    s = str(v).strip()
    return s if s and s not in ('----', '---', '--') else default


def _dash_if_unknown(v: Any) -> str:
    """里程等「可能没有」的字段：没有就显示 —。"""
    try:
        f = float(v)
        return ('%g' % f) if f > 0 else '—'
    except (TypeError, ValueError):
        return '—'


def _clear_layout(lay) -> None:
    """清空一个布局里的所有控件（结果区每次重画）。"""
    while lay.count():
        item = lay.takeAt(0)
        if item is None:
            continue
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            _clear_layout(sub)
            sub.deleteLater()


class _Card(QGroupBox if not K.FLUENT else QWidget):
    """结果卡片：Fluent 下自绘一张圆角面板，降级时退回 QGroupBox。"""

    def __init__(self, title: str = '', parent=None):
        super().__init__(parent)
        if K.FLUENT:
            self.setObjectName('queryCard')
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.body = QVBoxLayout(self)
            self.body.setContentsMargins(spx(10), spx(8), spx(10), spx(10))
            self.body.setSpacing(spx(4))
            if title:
                lab = QLabel(title)
                K.setLabelStyle(lab, size=12, color=CLR('accent'), bold=True)
                self.body.addWidget(lab)
            self.setStyleSheet(
                'QWidget#queryCard {'
                f' background-color: {CLR("panel2")};'
                f' border: 1px solid {CLR("border")}; border-radius: 6px; }}')
        else:
            self.setTitle(title)
            self.body = QVBoxLayout(self)
            self.body.setContentsMargins(8, 16, 8, 6)
            self.body.setSpacing(4)


# ===========================================================================
# 主对话框
# ===========================================================================
class QueryDialog(QDialog):
    """车次 / 机车配属查询对话框（两个页签）。"""

    def __init__(self, config=None, parent=None, tab: str = 'train',
                 train: str = '', loco: str = ''):
        super().__init__(parent)
        self.config = config
        self._thread: Optional[TrainInfoThread] = None
        self._train_result: Dict[str, Any] = {}
        self._loco_result: Dict[str, Any] = {}

        self.setWindowTitle('车次 / 机车配属查询')
        self.setMinimumSize(spx(620), spx(480))
        self.resize(spx(860), spx(720))
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        K.paintBackground(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(spx(10), spx(10), spx(10), spx(8))
        layout.setSpacing(spx(6))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._buildTrainPage(), '车次查询')
        self.tabs.addTab(self._buildLocoPage(), '机车配属查询')
        layout.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        self.statusLabel = QLabel('')
        K.setLabelStyle(self.statusLabel, size=11, color=CLR('dim'))
        btns.addWidget(self.statusLabel, 1)
        closeBtn = K.button('关闭', primary=True)
        closeBtn.clicked.connect(self.accept)
        btns.addWidget(closeBtn)
        layout.addLayout(btns)

        if str(tab) == 'loco':
            self.tabs.setCurrentIndex(1)
        if train:
            self.trainEdit.setText(train)
            QTimer.singleShot(120, self._queryTrain)
        elif loco:
            self.locoEdit.setText(loco)
            QTimer.singleShot(120, self._queryLoco)
        else:
            self.statusLabel.setText('数据来源：%s'
                                     % (data_update.last_check_text()
                                        if loco_roster.available() else '未内置配属表'))

    # ------------------------------------------------------------------
    # ① 车次查询页
    # ------------------------------------------------------------------
    def _buildTrainPage(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(spx(8), spx(8), spx(8), spx(8))
        v.setSpacing(spx(6))

        row = QHBoxLayout()
        row.setSpacing(spx(6))
        self.trainEdit = QLineEdit('')
        self.trainEdit.setPlaceholderText('车次号，如 G7 / K1234 / Z21')
        self.trainEdit.setClearButtonEnabled(True)
        self.trainEdit.returnPressed.connect(self._queryTrain)
        row.addWidget(self.trainEdit, 1)

        self.sourceCombo = QComboBox()
        self.sourceCombo.addItem('自动（RailGo → 12306）', 'auto')
        self.sourceCombo.addItem('RailGo（字段全）', 'railgo')
        self.sourceCombo.addItem('12306（官方兜底）', '12306')
        prefer = str(getattr(self.config, 'trainQuerySource', 'auto') or 'auto')
        i = self.sourceCombo.findData(prefer)
        self.sourceCombo.setCurrentIndex(i if i >= 0 else 0)
        self.sourceCombo.setToolTip('车次数据源；默认跟随配置里的「车次数据源」')
        self.sourceCombo.setMinimumWidth(spx(150))
        row.addWidget(self.sourceCombo)

        self.trainQueryBtn = K.button('查询', primary=True)
        self.trainQueryBtn.clicked.connect(self._queryTrain)
        row.addWidget(self.trainQueryBtn)
        v.addLayout(row)

        self.trainHint = QLabel('RailGo 字段全（担当 / 配属 / 车型），'
                                '12306 为官方兜底（只有时刻表）。')
        K.setLabelStyle(self.trainHint, size=11, color=CLR('faint'))
        self.trainHint.setWordWrap(True)
        v.addWidget(self.trainHint)

        self.trainScroll = QScrollArea()
        self.trainScroll.setWidgetResizable(True)
        self.trainScroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        self.trainResultLayout = QVBoxLayout(holder)
        self.trainResultLayout.setContentsMargins(spx(2), spx(2), spx(2), spx(2))
        self.trainResultLayout.setSpacing(spx(6))
        self.trainResultLayout.addStretch(1)
        self.trainScroll.setWidget(holder)
        v.addWidget(self.trainScroll, 1)
        return page

    def _prefer(self) -> str:
        return str(self.sourceCombo.currentData() or 'auto')

    def _queryTrain(self, prefer: Optional[str] = None):
        train = train_info.normalize_train(self.trainEdit.text())
        if not train:
            self._trainFail('请输入车次号，例如 G7、K1234')
            return
        if not train_info.is_train_code(train):
            self._trainFail('车次号格式不对：%s（应为 1~2 个字母 + 1~5 位数字）' % train)
            return
        if self._thread is not None and self._thread.isRunning():
            return                       # 上一次还在飞，别叠请求
        self.trainQueryBtn.setEnabled(False)
        self.trainQueryBtn.setText('查询中…')
        self.statusLabel.setText('正在查询 %s（%s）…'
                                 % (train, self.sourceCombo.currentText()))
        self._trainQuerying(train, prefer or self._prefer())

    def _trainQuerying(self, train: str, prefer: str):
        self.trainEdit.setText(train)
        # 线程不挂 parent：挂上就会随对话框一起被 C++ 析构，运行中的 QThread 被
        # 销毁会直接崩程序；改用模块级 _LIVE_THREADS 保活到 finished。
        self._thread = TrainInfoThread(train, prefer, parent=None)
        _keepThread(self._thread)
        self._thread.done.connect(self._onTrainDone)
        self._thread.start()

    def _onTrainDone(self, res: dict):
        self.trainQueryBtn.setEnabled(True)
        self.trainQueryBtn.setText('查询')
        self._train_result = res if isinstance(res, dict) else {}
        if self._train_result.get('ok'):
            self._renderTrain(self._train_result)
            self.statusLabel.setText(train_info.summary_line(self._train_result))
        else:
            self._trainFail(str(self._train_result.get('error') or '未查询到该车次'),
                            prefer=str(self._train_result.get('source') or ''))

    # ---- 渲染 ----
    def _renderTrain(self, res: dict):
        _clear_layout(self.trainResultLayout)
        lay = self.trainResultLayout

        code = _fmt(res.get('train'))
        head = QLabel('%s  %s' % (code, _fmt(res.get('category'), '')))
        K.setLabelStyle(head, size=19, color=CLR('accent'), bold=True)
        lay.addWidget(head)

        sub = QLabel('%s（%s） → %s（%s）   全程 %s   开行 %s 天' % (
            _fmt(res.get('start')), _fmt(res.get('startTime')),
            _fmt(res.get('end')), _fmt(res.get('endTime')),
            ('%s km' % _dash_if_unknown(res.get('distance')))
            if _dash_if_unknown(res.get('distance')) != '—' else '里程未知',
            int(res.get('rundaysCount') or 0) or '—'))
        K.setLabelStyle(sub, size=12, color=CLR('text'))
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # 信息网格：担当局 / 客运段 / 配属段 / 车型 / 开行日 / 数据来源
        days = res.get('rundays') or []
        info_items = [
            ('担当局', _fmt(res.get('bureau'))),
            ('客运段', _fmt(res.get('runner'))),
            ('配属段', _fmt(res.get('carOwner'))),
            ('车型', _fmt(res.get('car'))),
            ('开行日', ('%d 天：%s' % (len(days), '、'.join(days[:6])
                                      + ('…' if len(days) > 6 else '')))
             if days else '—'),
            ('数据来源', _source_label(res)),
        ]
        card = _Card('担当与配属')
        grid = QGridLayout()
        grid.setHorizontalSpacing(spx(12))
        grid.setVerticalSpacing(spx(5))
        for i, (k, val) in enumerate(info_items):
            r, c = divmod(i, 3)
            lab = QLabel(k)
            K.setLabelStyle(lab, size=11, color=CLR('dim'))
            vlab = QLabel(val)
            K.setLabelStyle(vlab, size=12, color=CLR('text'), bold=True)
            vlab.setWordWrap(True)
            vlab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(lab, r * 2, c)
            grid.addWidget(vlab, r * 2 + 1, c)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        card.body.addLayout(grid)
        lay.addWidget(card)

        # 交路（有则显示）
        diagram = res.get('diagram') or []
        if diagram:
            dcard = _Card('交路（车次贯通）')
            for seg in diagram[:12]:
                lab = QLabel('%s  %s %s → %s %s' % (
                    _fmt(seg.get('number')), _fmt(seg.get('fromStation')),
                    _fmt(seg.get('fromTime')), _fmt(seg.get('toStation')),
                    _fmt(seg.get('toTime'))))
                K.setLabelStyle(lab, size=11.5, color=CLR('accent2'))
                lab.setWordWrap(True)
                dcard.body.addWidget(lab)
            lay.addWidget(dcard)

        # 时刻表
        stops = res.get('stops') or []
        if stops:
            tcard = _Card('全程时刻表（%d 站）' % len(stops))
            table = QTableWidget(len(stops), 5)
            table.setHorizontalHeaderLabels(['站名', '到点', '发点', '停站', '里程'])
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.verticalHeader().setVisible(False)
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            for c in (1, 2, 3, 4):
                header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
            for r, s in enumerate(stops):
                stop_min = s.get('stop') or 0
                vals = [
                    str(s.get('station') or ''),
                    _fmt(s.get('arrive')),
                    _fmt(s.get('depart')),
                    ('%d 分' % int(stop_min)) if stop_min else '—',
                    _dash_if_unknown(s.get('distance')),
                ]
                for c, val in enumerate(vals):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignCenter if c else
                                          (Qt.AlignLeft | Qt.AlignVCenter))
                    if c == 0:
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    table.setItem(r, c, item)
            table.setMinimumHeight(spx(220))
            table.resizeRowsToContents()
            tcard.body.addWidget(table)
            lay.addWidget(tcard, 1)

        foot = QLabel('查询时间 %s   数据来源：%s%s' % (
            datetime.now().strftime('%H:%M:%S'), _source_label(res),
            ('（%s 失败后自动回退）' % res.get('fallbackFrom'))
            if res.get('fallbackFrom') else ''))
        K.setLabelStyle(foot, size=10.5, color=CLR('faint'))
        foot.setWordWrap(True)
        lay.addWidget(foot)

        lay.addStretch(1)

    def _trainFail(self, message: str, prefer: str = ''):
        """失败：原因 + 「改用 12306 重试」按钮（当前源不是 12306 时才有）。"""
        _clear_layout(self.trainResultLayout)
        lay = self.trainResultLayout
        card = _Card('')
        warn = QLabel('⚠  %s' % message)
        K.setLabelStyle(warn, size=13, color=CLR('warn'), bold=True)
        warn.setWordWrap(True)
        card.body.addWidget(warn)
        tip = QLabel('可以换一个数据源重试；没有外网时车次/配属查询都用不了，'
                     '但地图与解码不受影响。')
        K.setLabelStyle(tip, size=11, color=CLR('faint'))
        tip.setWordWrap(True)
        card.body.addWidget(tip)
        row = QHBoxLayout()
        row.setSpacing(spx(6))
        if self._prefer() != '12306':
            btn = K.small_button('改用 12306 重试', h=26, px=11.5)
            btn.clicked.connect(lambda: self._retryWith('12306'))
            row.addWidget(btn)
        if self._prefer() != 'railgo':
            btn2 = K.small_button('改用 RailGo 重试', h=26, px=11.5)
            btn2.clicked.connect(lambda: self._retryWith('railgo'))
            row.addWidget(btn2)
        row.addStretch(1)
        card.body.addLayout(row)
        lay.addWidget(card)
        lay.addStretch(1)
        self.statusLabel.setText(message)

    def _retryWith(self, prefer: str):
        idx = self.sourceCombo.findData(prefer)
        if idx >= 0:
            self.sourceCombo.setCurrentIndex(idx)
        self._queryTrain(prefer)

    # ------------------------------------------------------------------
    # ② 机车配属查询页
    # ------------------------------------------------------------------
    def _buildLocoPage(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(spx(8), spx(8), spx(8), spx(8))
        v.setSpacing(spx(6))

        row = QHBoxLayout()
        row.setSpacing(spx(6))
        self.locoEdit = QLineEdit('')
        self.locoEdit.setPlaceholderText('HXD1D 0123 / HXD1D-0123 / 韶山4-0123')
        self.locoEdit.setClearButtonEnabled(True)
        self.locoEdit.returnPressed.connect(self._queryLoco)
        row.addWidget(self.locoEdit, 2)

        self.locoModelCombo = QComboBox()
        self.locoModelCombo.addItem('型号（自动识别）', '')
        try:
            for m in loco_roster.models():
                self.locoModelCombo.addItem(m, m)
        except Exception:
            pass
        self.locoModelCombo.setToolTip('也可以直接选型号，再填机车号')
        self.locoModelCombo.setMinimumWidth(spx(140))
        self.locoModelCombo.currentIndexChanged.connect(self._onModelPicked)
        row.addWidget(self.locoModelCombo, 1)

        self.locoNumEdit = QLineEdit('')
        self.locoNumEdit.setPlaceholderText('机车号')
        self.locoNumEdit.setMaximumWidth(spx(110))
        self.locoNumEdit.returnPressed.connect(self._queryLoco)
        row.addWidget(self.locoNumEdit)

        self.locoQueryBtn = K.button('查询', primary=True)
        self.locoQueryBtn.clicked.connect(self._queryLoco)
        row.addWidget(self.locoQueryBtn)
        v.addLayout(row)

        has_table = loco_roster.available()
        try:
            st = loco_roster.stats()
        except Exception:
            st = {}
        self.locoHint = QLabel(
            ('号段表：%d 行 / %d 个型号 · %s' % (
                int(st.get('rows') or 0), int(st.get('models') or 0),
                data_update.last_check_text()))
            if has_table else
            '未内置配属表（shared/data/loco_roster.csv 缺失），只能查车型技术参数。')
        K.setLabelStyle(self.locoHint, size=11,
                        color=CLR('faint') if has_table else CLR('warn'))
        self.locoHint.setWordWrap(True)
        v.addWidget(self.locoHint)

        if not has_table:
            self.locoQueryBtn.setEnabled(False)
            self.locoEdit.setEnabled(False)
            self.locoModelCombo.setEnabled(False)
            self.locoNumEdit.setEnabled(False)

        self.locoScroll = QScrollArea()
        self.locoScroll.setWidgetResizable(True)
        self.locoScroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        self.locoResultLayout = QVBoxLayout(holder)
        self.locoResultLayout.setContentsMargins(spx(2), spx(2), spx(2), spx(2))
        self.locoResultLayout.setSpacing(spx(6))
        intro = QLabel('未内置配属表（shared/data/loco_roster.csv 缺失），'
                       '无法按号段查配属；车型技术参数仍可查询。'
                       if not has_table else '输入型号与机车号后点「查询」，'
                       '例如 HXD1D 0123。')
        K.setLabelStyle(intro, size=12,
                        color=CLR('warn') if not has_table else CLR('faint'))
        intro.setWordWrap(True)
        self.locoResultLayout.addWidget(intro)
        self.locoResultLayout.addStretch(1)
        self.locoScroll.setWidget(holder)
        v.addWidget(self.locoScroll, 1)
        return page

    def _onModelPicked(self, _index: int):
        """选了型号 → 填进输入框；号码框不变（用户可能已经填了号）。"""
        model = str(self.locoModelCombo.currentData() or '')
        if not model:
            return
        num = self.locoNumEdit.text().strip()
        self.locoEdit.setText(('%s %s' % (model, num)).strip())

    def _queryLoco(self):
        model = str(self.locoModelCombo.currentData() or '')
        num = self.locoNumEdit.text().strip()
        text = self.locoEdit.text().strip()
        if not model and not text:
            self._locoFail('请输入「型号 + 机车号」，例如 HXD1D 0123；'
                           '也可以只填型号看技术参数。')
            return
        try:
            if num:
                res = loco_roster.lookup(model or text, num)
            else:
                res = loco_roster.lookup_loco(text)
        except Exception as e:                       # noqa: BLE001
            self._locoFail('查询失败：%s' % (e or e.__class__.__name__))
            return
        self._loco_result = res if isinstance(res, dict) else {}
        self._renderLoco(self._loco_result)

    def _renderLoco(self, res: dict):
        _clear_layout(self.locoResultLayout)
        lay = self.locoResultLayout
        model = str(res.get('model') or '')
        num_text = str(res.get('numberText') or '')
        name = str(res.get('name') or '')

        # ---- 标题 ----
        title = ('%s %s' % (model, num_text)).strip() or name or '未知机车'
        head = QLabel(title)
        K.setLabelStyle(head, size=19, color=CLR('accent'), bold=True)
        lay.addWidget(head)
        if name and name != model:
            sub = QLabel(name + ('（型号 %s）' % model if model else ''))
            K.setLabelStyle(sub, size=12, color=CLR('dim'))
            sub.setWordWrap(True)
            lay.addWidget(sub)

        # ---- 配属卡 ----
        card = _Card('配属')
        if res.get('exact'):
            depot = str(res.get('depot') or '').strip() or '（原表未标注配属）'
            dlab = QLabel(depot)
            K.setLabelStyle(dlab, size=16, color=CLR('ok'), bold=True)
            dlab.setWordWrap(True)
            dlab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.body.addWidget(dlab)
        elif res.get('ok'):
            dlab = QLabel('配属未知')
            K.setLabelStyle(dlab, size=15, color=CLR('warn'), bold=True)
            card.body.addWidget(dlab)
            why = QLabel(str(res.get('reason') or '号段表内无该编号（可能新造/未收录）'))
            K.setLabelStyle(why, size=11.5, color=CLR('faint'))
            why.setWordWrap(True)
            card.body.addWidget(why)
        else:
            dlab = QLabel('未命中')
            K.setLabelStyle(dlab, size=15, color=CLR('warn'), bold=True)
            card.body.addWidget(dlab)
            why = QLabel(str(res.get('reason') or '配属号段表未收录该型号'))
            K.setLabelStyle(why, size=11.5, color=CLR('faint'))
            why.setWordWrap(True)
            card.body.addWidget(why)

        items = [
            ('型号', model or '—'),
            ('机车号', num_text or '—'),
            ('号段区间', ('%s' % res.get('range')) if res.get('range') else '—'),
            ('制造厂', _fmt(res.get('maker'))),
            ('备注', _fmt(res.get('remark'))),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(spx(12))
        grid.setVerticalSpacing(spx(5))
        for i, (k, val) in enumerate(items):
            r, c = divmod(i, 2)
            lab = QLabel(k)
            K.setLabelStyle(lab, size=11, color=CLR('dim'))
            vlab = QLabel(str(val))
            K.setLabelStyle(vlab, size=12, color=CLR('text'), bold=True)
            vlab.setWordWrap(True)
            grid.addWidget(lab, r * 2, c)
            grid.addWidget(vlab, r * 2 + 1, c)
        for c in range(2):
            grid.setColumnStretch(c, 1)
        card.body.addLayout(grid)

        try:
            st = loco_roster.stats()
        except Exception:
            st = {}
        src = QLabel('数据来源：机车配属号段表（%d 行 / %d 个型号）· %s' % (
            int(st.get('rows') or 0), int(st.get('models') or 0),
            data_update.last_check_text()))
        K.setLabelStyle(src, size=10.5, color=CLR('faint'))
        src.setWordWrap(True)
        card.body.addWidget(src)
        lay.addWidget(card)

        # 同号段另有候选（同一编号落在多个区间时）
        alts = res.get('alternatives') or []
        if alts:
            acard = _Card('同编号的其他候选号段')
            for a in alts[:8]:
                lab = QLabel('号段 %s → %s' % (_fmt(a.get('range')),
                                               _fmt(a.get('depot'))))
                K.setLabelStyle(lab, size=11.5, color=CLR('accent2'))
                lab.setWordWrap(True)
                acard.body.addWidget(lab)
            lay.addWidget(acard)

        # ---- 车型参数卡 ----
        specs = {}
        try:
            specs = loco_roster.specs_for(model or name) or {}
        except Exception:
            specs = {}
        if specs:
            scard = _Card('车型技术参数')
            pairs = [
                ('类型', _fmt(specs.get('type'))),
                ('轴式', _fmt(specs.get('axle'))),
                ('功率', _fmt(specs.get('power'))),
                ('构造速度', _fmt(specs.get('speed'))),
                ('制造厂', _fmt(specs.get('maker'))),
            ]
            g = QGridLayout()
            g.setHorizontalSpacing(spx(12))
            g.setVerticalSpacing(spx(5))
            for i, (k, val) in enumerate(pairs):
                r, c = divmod(i, 2)
                lab = QLabel(k)
                K.setLabelStyle(lab, size=11, color=CLR('dim'))
                vlab = QLabel(str(val))
                K.setLabelStyle(vlab, size=12, color=CLR('text'), bold=True)
                vlab.setWordWrap(True)
                g.addWidget(lab, r * 2, c)
                g.addWidget(vlab, r * 2 + 1, c)
            for c in range(2):
                g.setColumnStretch(c, 1)
            scard.body.addLayout(g)
            brief = str(specs.get('brief') or '').strip()
            if brief:
                blab = QLabel(brief)
                K.setLabelStyle(blab, size=11.5, color=CLR('text'))
                blab.setWordWrap(True)
                scard.body.addWidget(blab)
            try:
                meta = loco_roster.specs_meta()
            except Exception:
                meta = {}
            if meta.get('revision') or meta.get('source'):
                flab = QLabel('参数版本 %s · %s' % (_fmt(meta.get('revision')),
                                                  _fmt(meta.get('source'))))
                K.setLabelStyle(flab, size=10.5, color=CLR('faint'))
                flab.setWordWrap(True)
                scard.body.addWidget(flab)
            lay.addWidget(scard)
        else:
            nocard = QLabel('暂无该车型的技术参数（shared/data/loco_specs.json 未收录）。')
            K.setLabelStyle(nocard, size=11, color=CLR('faint'))
            nocard.setWordWrap(True)
            lay.addWidget(nocard)

        # ---- 相近型号（未命中时给出，点一下直接查）----
        suggest = res.get('suggest') or []
        if suggest and not res.get('ok'):
            sugcard = _Card('相近型号（点击直接查询）')
            row = QHBoxLayout()
            row.setSpacing(spx(6))
            for m in suggest[:6]:
                b = K.small_button(str(m), h=26, px=11.5)
                b.clicked.connect(lambda _c=False, mm=str(m): self._pickModel(mm))
                row.addWidget(b)
            row.addStretch(1)
            sugcard.body.addLayout(row)
            lay.addWidget(sugcard)

        if res.get('aliasFrom'):
            alab = QLabel('型号 %s 已并入 %s 统计。'
                          % (res.get('aliasFrom'), model))
            K.setLabelStyle(alab, size=10.5, color=CLR('faint'))
            alab.setWordWrap(True)
            lay.addWidget(alab)

        lay.addStretch(1)
        self.statusLabel.setText(
            loco_roster.format_depot(res) if loco_roster.available()
            else '未内置配属表')

    def _pickModel(self, model: str):
        """点「相近型号」：填进输入框并重新查询。"""
        idx = self.locoModelCombo.findData(model)
        if idx >= 0:
            self.locoModelCombo.setCurrentIndex(idx)
        self.locoEdit.setText(('%s %s' % (model, self.locoNumEdit.text().strip())).strip())
        self._queryLoco()

    def _locoFail(self, message: str):
        _clear_layout(self.locoResultLayout)
        lab = QLabel('⚠  %s' % message)
        K.setLabelStyle(lab, size=13, color=CLR('warn'), bold=True)
        lab.setWordWrap(True)
        self.locoResultLayout.addWidget(lab)
        self.locoResultLayout.addStretch(1)
        self.statusLabel.setText(message)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        """关窗时如果查询还在飞，等它自己结束（Qt 会自动断开信号）。"""
        th = self._thread
        if th is not None and th.isRunning():
            try:
                th.wait(1500)
            except Exception:
                pass
        super().closeEvent(event)


def _source_label(res: dict) -> str:
    """数据来源的中文说法。"""
    src = str(res.get('source') or '')
    return {'railgo': 'RailGo（社区接口）', '12306': '12306（官方）'}.get(src, src or '—')
