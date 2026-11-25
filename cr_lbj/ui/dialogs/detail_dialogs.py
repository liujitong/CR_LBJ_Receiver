#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机车详情、记录详情对话框。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class LocoDetailDialog(QDialog):
    """机车详情对话框：展示机车技术参数和资料来源。

    v2.5 起移除图片区域——公开图源无法保证与车型精准对应，留着反而误导，
    详情只保留可靠的参数文字与来源链接。
    """

    def __init__(self, loco_info: Optional[dict], loco_number: str = '', parent=None):
        super().__init__(parent)
        name = loco_info.get('name', '') if loco_info else loco_number
        self.setWindowTitle(f'机车详情 — {name}')
        self.setMinimumSize(480, 360)
        self.resize(560, 460)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 底色自己铺：QSS 里的 QDialog 规则会被后面的 QWidget{transparent} 盖掉，
        # 不铺就会露出系统白底，深色主题下按钮直接看不见
        K.paintBackground(self)

        self._loco_info = loco_info or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ===== 1. 标题 =====
        titleLabel = QLabel(name or '未知机车')
        titleLabel.setStyleSheet(f'color: {CLR("accent")}; font-size: 18px; font-weight: bold;')
        titleLabel.setAlignment(Qt.AlignCenter)
        layout.addWidget(titleLabel)

        # ===== 2. 技术参数 (2 列网格) =====
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

        # ===== 3. 资料来源 =====
        sourceBox = QFrame()
        sourceBox.setStyleSheet(
            f'QFrame {{ background-color: {CLR("panel")}; border: 1px solid {CLR("border")}; border-radius: 4px; }}')
        sourceLayout = QHBoxLayout(sourceBox)
        sourceLayout.setContentsMargins(8, 6, 8, 6)
        sourceText = QLabel(
            f'<span style="color:#aaa;">资料来源:</span> '
            f'<a href="{self._loco_info.get("sourceUrl", "")}" '
            f'style="color:{CLR("accent2")}; text-decoration:none;">'
            f'{self._loco_info.get("source", "公开资料核对")}</a>')
        sourceText.setOpenExternalLinks(True)
        sourceText.setStyleSheet('font-size: 11px; border: none; background: transparent;')
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


# ===========================================================================
# 记录详情对话框 (双击历史/当前列表弹出)
# ===========================================================================
class RecordDetailDialog(QDialog):
    """单条记录的完整详情：分成几个页签，不再是一条长滚动条。

    v2.5 改成分页（解码结果 / 原始数据 / BCD / 解码过程 / 纠错码字）——
    原来的做法是把五块全塞进一个对话框，字段挤成四列，标签和值互相压字，
    右边还冒出一条横向滚动条。分页之后每页都能用满宽度，也不会互相挤。
    """

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self._record = record
        train = record.get('train', '----')
        time_str = record.get('timeStr', record.get('time', ''))
        self.setWindowTitle(f'记录详情 — {train} ({time_str})')
        # v2.6.1：用户反馈默认太宽（880）。解码结果是两列网格，值列可换行，
        # 680 就放得下；「解码过程 / 纠错码字」等宽文本页窄了会出横向滚动条，
        # 属可接受的取舍。最小尺寸也跟着收，小屏不会被顶宽。
        self.setMinimumSize(620, 540)
        self.resize(680, 620)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 底色自己铺：QSS 里的 QDialog 规则会被后面的 QWidget{transparent} 盖掉，
        # 不铺就会露出系统白底，深色主题下按钮直接看不见
        K.paintBackground(self)

        layout = QVBoxLayout(self)
        layout.setSpacing(spx(6))
        layout.setContentsMargins(spx(10), spx(10), spx(10), spx(8))

        self.detailTabs = QTabWidget()
        self.detailTabs.setDocumentMode(True)
        layout.addWidget(self.detailTabs, 1)

        self._buildResultPage(record)
        self._buildRawPage(record)
        self._buildBcdPage(record)
        self._buildProcessPage(record)
        self._buildCodewordPage(record)

        # ===== 按钮 =====
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        mapBtn = K.button('在地图中查看')
        hasCoord = isinstance(record.get('latitude'), (int, float)) and \
            isinstance(record.get('longitude'), (int, float))
        mapBtn.setEnabled(hasCoord)
        mapBtn.clicked.connect(lambda: self._openMap(record))
        btnLayout.addWidget(mapBtn)
        closeBtn = K.button('关闭', primary=True)
        closeBtn.clicked.connect(self.accept)
        btnLayout.addWidget(closeBtn)
        layout.addLayout(btnLayout)

        # 启动 12306 后台查询（仅详细报文）
        if record.get('isDetailed'):
            self._startTrainQuery(record)
        else:
            self._trainQueryLabel.setText('非详细报文，不查询')
            K.setLabelStyle(self._trainQueryLabel, color=CLR('faint'))

    # ------------------------------------------------------------------
    # 版面小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _pairGrid(items, lab_color: str, host: QWidget = None) -> QWidget:
        """把 (标签, 值) 两两排成两列，标签定宽右对齐、值占满剩余。

        原来是 divmod 直接往 4 列里塞，没有列宽约束，字段一长就互相压字。
        """
        host = host or QWidget()
        g = QGridLayout(host)
        g.setContentsMargins(spx(10), spx(8), spx(10), spx(8))
        g.setHorizontalSpacing(spx(10))
        g.setVerticalSpacing(spx(7))
        # 标签列定宽（两个标签列同宽），值列吃掉所有剩余宽度
        for col in (0, 2):
            g.setColumnMinimumWidth(col, spx(76))
            g.setColumnStretch(col, 0)
        for col in (1, 3):
            g.setColumnStretch(col, 1)
        for i, (k, v) in enumerate(items):
            r, c = divmod(i, 2)
            lab = QLabel(f'{k}')
            lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            K.setLabelStyle(lab, color=lab_color, bold=True)
            val = QLabel(str(v))
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            K.setLabelStyle(val, color=CLR('text'))
            g.addWidget(lab, r, c * 2)
            g.addWidget(val, r, c * 2 + 1)
        return host

    @staticmethod
    def _monoText(text: str, color: str, px: float = 11.5) -> QTextEdit:
        """等宽只读文本框（BCD / 过程推演 / 码字共用）。"""
        t = QTextEdit()
        t.setReadOnly(True)
        t.setLineWrapMode(QTextEdit.NoWrap)
        t.setStyleSheet(
            'font-family: Consolas, "Courier New", monospace;'
            f' font-size: {K.fontPx(px)}px;'
            f' background-color: {CLR("status")}; color: {color};'
            f' border: 1px solid {CLR("border")};')
        t.setPlainText(text)
        return t

    def _addPage(self, title: str, body: QWidget) -> None:
        self.detailTabs.addTab(body, title)

    # ------------------------------------------------------------------
    # ① 解码结果
    # ------------------------------------------------------------------
    def _buildResultPage(self, record: dict) -> None:
        func_str = self._funcLabel(record.get('rawFunc', record.get('raw_func', 0)))
        msg_type = self._msgTypeLabel(record)

        loco_number = record.get('loco', '')
        loco_code = record.get('locoCode', record.get('loco_code', ''))
        loco_info = lookup_loco(loco_code=loco_code, loco_number=loco_number)
        self._locoInfoData: Optional[dict] = loco_info
        self._locoNumberStr = loco_number or ''

        items = [
            ('时间', record.get('timeStr', record.get('time', ''))),
            ('车次', record.get('train', '----')),
            ('纯数字车次', record.get('baseTrain', '----')),
            ('前缀', record.get('prefix', '') or '无'),
            ('方向', record.get('direction', '未知')),
            ('速度', f"{record.get('speed', '---')} km/h"),
            ('公里标', f"{record.get('position', '---.-')} km"),
            ('线路', record.get('route', '----')),
            ('机车号', loco_number or '----'),
            ('机车代号', loco_code or '---'),
            ('类别', record.get('category', '未知')),
            ('报文类型', msg_type),
            ('经度', f"{record.get('longitude'):.6f}"
             if isinstance(record.get('longitude'), (int, float)) else '----'),
            ('纬度', f"{record.get('latitude'):.6f}"
             if isinstance(record.get('latitude'), (int, float)) else '----'),
            ('线路校验', '通过' if record.get('routeValid', record.get('route_valid', False)) else '未通过'),
            ('BCH 纠错', '有错误' if record.get('msgTypeError', False) else '正常'),
            ('预计到达', record.get('etaTime', record.get('eta_time', '--:--:--'))),
            ('预计距离', f"{record.get('etaDistanceKm', record.get('eta_distance_km', '---'))} km"
             if record.get('etaDistanceKm', record.get('eta_distance_km')) else '---'),
        ]

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(spx(6))
        v.addWidget(self._pairGrid(items, CLR('accent')))

        # 机车简介：整行铺开，右侧挂「机车详情」
        locoBox = QWidget()
        hl = QHBoxLayout(locoBox)
        hl.setContentsMargins(spx(10), 0, spx(10), spx(4))
        hl.setSpacing(spx(8))
        self._locoIntroLabel = QLabel(
            (f"{loco_info.get('name', '')}  |  {loco_info.get('type', '')}  |  "
             f"{loco_info.get('power', '')}  |  {loco_info.get('speed', '')}\n"
             f"{loco_info.get('brief', '')}") if loco_info else '暂无该车型资料')
        self._locoIntroLabel.setWordWrap(True)
        K.setLabelStyle(self._locoIntroLabel, color=CLR('text'))
        self._locoDetailBtn = K.small_button('机车详情', h=26, px=11.5)
        self._locoDetailBtn.setEnabled(bool(loco_info))
        self._locoDetailBtn.clicked.connect(lambda: self._openLocoDetail())
        hl.addWidget(self._locoIntroLabel, 1)
        hl.addWidget(self._locoDetailBtn, 0, Qt.AlignTop)
        v.addWidget(locoBox)

        # 12306 查询结论
        qBox = QWidget()
        ql = QHBoxLayout(qBox)
        ql.setContentsMargins(spx(10), 0, spx(10), spx(6))
        ql.setSpacing(spx(8))
        qTag = QLabel('12306')
        K.setLabelStyle(qTag, color=CLR('accent2'), bold=True)
        self._trainQueryLabel = QLabel('查询中...')
        self._trainQueryLabel.setWordWrap(True)
        K.setLabelStyle(self._trainQueryLabel, color=CLR('accent2'))
        self._trainQueryBtn = K.small_button('时刻表', h=26, px=11.5)
        self._trainQueryBtn.setEnabled(False)
        self._trainQueryData: Optional[dict] = None
        self._trainQueryBtn.clicked.connect(self._openTrainQueryResult)
        ql.addWidget(qTag, 0, Qt.AlignTop)
        ql.addWidget(self._trainQueryLabel, 1)
        ql.addWidget(self._trainQueryBtn, 0, Qt.AlignTop)
        v.addWidget(qBox)
        v.addStretch(1)

        self._addPage('解码结果', page)

    # ------------------------------------------------------------------
    # ② 原始数据
    # ------------------------------------------------------------------
    def _buildRawPage(self, record: dict) -> None:
        func_str = self._funcLabel(record.get('rawFunc', record.get('raw_func', 0)))
        rssi_val = record.get('rssi', -140.0)
        afc_hz = record.get('afcHz', record.get('afc_hz', 0.0))
        ferr = record.get('afcErrHz', record.get('afc_err_hz', 0.0))
        score = record.get('afcScore', record.get('afc_score', 0.0))
        raw_addr = record.get('rawAddr', record.get('raw_addr', 0))

        items = [
            ('报文地址', str(raw_addr)),
            ('功能码', func_str),
            ('信号强度', f"{rssi_val:.1f} dB" if isinstance(rssi_val, (int, float)) else str(rssi_val)),
            ('AFC 补偿', f"{afc_hz:+.0f} Hz" if isinstance(afc_hz, (int, float)) else str(afc_hz)),
            ('频率误差', f"{ferr:+.0f} Hz" if isinstance(ferr, (int, float)) else str(ferr)),
            ('AFC 置信度', f"{score:.2f}" if isinstance(score, (int, float)) else str(score)),
            ('短报文', '是' if record.get('rawIsShort', False) else '否'),
            ('合并报文', '是' if record.get('rawIsMerged', False) else '否'),
            ('独立长报文', '是' if record.get('rawIsStandalone', False) else '否'),
            ('到达状态', record.get('etaStatus', record.get('eta_status', '等待信号'))),
        ]
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._pairGrid(items, CLR('warn')))
        v.addStretch(1)
        self._addPage('原始数据', page)

    # ------------------------------------------------------------------
    # ③ BCD 原始数据
    # ------------------------------------------------------------------
    def _buildBcdPage(self, record: dict) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        bcd_raw = record.get('rawBcd', record.get('raw_bcd', ''))
        if bcd_raw:
            lines = [bcd_raw[i:i + 20] for i in range(0, len(bcd_raw), 20)]
            text = (f'长度：{len(bcd_raw)} 字符（BCD 十进制数，每 2 位 1 字节）\n\n'
                    + '\n'.join(f'{i * 20:4d}: {ln}' for i, ln in enumerate(lines)))
        else:
            text = '（无 BCD 数据）'
        v.addWidget(self._monoText(text, CLR('ok')))
        self._addPage('BCD 原始数据', page)

    # ------------------------------------------------------------------
    # ④ 解码过程推演
    # ------------------------------------------------------------------
    def _buildProcessPage(self, record: dict) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        v.addWidget(self._monoText(self._buildDecodeProcess(record), CLR('dim')))
        self._addPage('解码过程', page)

    # ------------------------------------------------------------------
    # ⑤ 纠错后码字
    # ------------------------------------------------------------------
    def _buildCodewordPage(self, record: dict) -> None:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(spx(10), spx(10), spx(10), spx(10))
        codewords = record.get('rawCodewords', []) or []
        if codewords:
            lines = []
            for i, cw in enumerate(codewords):
                if isinstance(cw, int):
                    lines.append(f'  [{i:2d}] {format(cw, "031b")}  (0x{cw:08X})')
                else:
                    lines.append(f'  [{i:2d}] {cw}')
            text = f'共 {len(codewords)} 个码字（BCH(31,21) 纠错后）\n\n' + '\n'.join(lines)
        else:
            text = '（本条记录没有保存码字）'
        v.addWidget(self._monoText(text, CLR('warn')))
        self._addPage('纠错码字', page)

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
        """弹出机车详情对话框（技术参数 + 资料来源）。"""
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
        try:                       # 数据库里可能存成文本，格式化前先归一
            addr_i = int(addr)
        except (TypeError, ValueError):
            addr_i = 0
        try:
            func_i = int(func)
        except (TypeError, ValueError):
            func_i = 0
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
        lines.append(f'  地址码: {addr_i} (0x{addr_i:05X})')
        lines.append(f'  功能码: {func_i} ({self._funcLabel(func_i)})')

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
