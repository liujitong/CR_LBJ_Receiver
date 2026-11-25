#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备检测、数据源编辑、配置面板与配置对话框。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

def setFormRowVisible(form: QFormLayout, field: QWidget, visible: bool):
    """隐藏/恢复 QFormLayout 的一整行（标签 + 字段）。

    USB 直连不需要主机/端口，这两行要在选择「本机 USB (直连)」时整行收起。
    Qt 的 QFormLayout 没有行级可见性 API，只能分别操作标签与字段。
    """
    lab = form.labelForField(field)
    if lab is not None:
        lab.setVisible(visible)
    field.setVisible(visible)


class DeviceDetectThread(QThread):
    """后台检测 RTL-SDR 设备，避免阻塞界面。

    优先用 librtlsdr 直连枚举（能拿到 tuner 型号与可用增益，据此推荐参数）；
    拿不到时退回 rtl_test -t，至少告诉用户设备在不在。
    """

    done = Signal(bool, str, object)

    def run(self):
        info = {'devices': [], 'profiles': [], 'via': 'usb'}
        try:
            info = probeDevices()
            ok, msg = bool(info.get('devices')), info.get('text', '')
        except Exception as e:
            ok, msg = False, f'USB 直连检测失败: {e}'
        if not ok:
            ok2, msg2 = False, ''
            try:
                ok2, msg2 = detect_rtl_devices(10.0)
            except Exception as e:
                msg2 = str(e)
            msg = msg + '\n\n[rtl_test -t]\n' + msg2
            ok = ok or ok2
            if ok2:
                info['via'] = 'rtl_test'
        self.done.emit(ok, msg, info)


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

        self.usbHint = QLabel(
            'USB 直连：程序自动查找本机 RTL-SDR，无需主机与端口。\n'
            '插上棒子后点主配置页的「检测设备」确认 tuner 并应用推荐参数。')
        self.usbHint.setWordWrap(True)
        self.usbHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')

        form.addRow('名称:', self.nameEdit)
        form.addRow('类型:', self.typeCombo)
        form.addRow(self.usbHint)
        form.addRow('主机:', self.hostEdit)
        form.addRow('端口:', self.portSpin)
        form.addRow('采样率:', self.srCombo)
        form.addRow('增益:', self.gainSpin)
        form.addRow('PPM:', self.ppmSpin)
        form.addRow('DC 偏移:', self.dcSpin)
        self._form = form

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
        if t in ('rtl_usb', 'rtl_usb_tcp'):
            self.hostEdit.setText('127.0.0.1')
            if self.dcSpin.value() < 1:
                self.dcSpin.setValue(50000)
        elif t == 'owrx':
            self.dcSpin.setValue(0)
        elif self.dcSpin.value() < 1:
            self.dcSpin.setValue(50000)
        # USB 直连没有「主机/端口」的概念，整行收起，避免让人误以为要填
        direct = (t == 'rtl_usb')
        setFormRowVisible(self._form, self.hostEdit, not direct)
        setFormRowVisible(self._form, self.portSpin, not direct)
        self.usbHint.setVisible(direct)

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
        self.rtlPathEdit.setPlaceholderText('留空自动查找（仅 rtl_tcp 中转模式需要）')
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

        self.usbHint = QLabel(
            'USB 直连：程序自动查找本机 RTL-SDR，无需主机与端口。'
            '插上棒子后点上方「检测设备」确认 tuner 并应用推荐参数；'
            '多支棒子用「设备序号」区分。')
        self.usbHint.setWordWrap(True)
        self.usbHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')

        connForm.addRow(self.usbHint)
        connForm.addRow('主机:', self.hostEdit)
        connForm.addRow('端口:', self.portSpin)
        connForm.addRow('采样率:', self.srCombo)
        connForm.addRow('块大小:', self.blockSpin)
        connForm.addRow('DC 偏移:', self.dcSpin)
        self._connForm = connForm

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
            tag = SOURCE_TYPE_TAGS.get(s.get('type', 'rtl_tcp'), '?')
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
        # 切换数据源时主机/端口行的显隐要跟着类型走（上面的
        # currentIndexChanged 因 _updating_mode 被跳过了）
        self._updateEndpointRows()

    def _updateEndpointRows(self):
        """USB 直连没有「主机/端口」的概念：整行收起并显示设备查找提示。"""
        if not hasattr(self, '_connForm'):
            return
        direct = (self.srcTypeCombo.currentData() == 'rtl_usb')
        setFormRowVisible(self._connForm, self.hostEdit, not direct)
        setFormRowVisible(self._connForm, self.portSpin, not direct)
        self.usbHint.setVisible(direct)

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
        if t in ('rtl_usb', 'rtl_usb_tcp'):
            self.hostEdit.setText('127.0.0.1')
            if abs(self.dcSpin.value()) < 1:
                self.dcSpin.setValue(50000)
        elif t == 'owrx':
            self.dcSpin.setValue(0)
        elif abs(self.dcSpin.value()) < 1:
            self.dcSpin.setValue(50000)
        self._updateEndpointRows()
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

    def _onDetectDone(self, ok: bool, msg: str, info: Optional[dict] = None):
        self.srcDetectBtn.setEnabled(True)
        self.srcDetectBtn.setText('检测设备')
        info = info or {}
        profiles = info.get('profiles') or []
        box = QMessageBox(self)
        box.setWindowTitle('RTL-SDR 设备检测')
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        box.setText('已找到 RTL-SDR 设备' if ok else '未检测到可用设备')
        if profiles:
            p = profiles[0]
            box.setInformativeText(
                f"tuner: {p['tuner']}    推荐 {p['sampleRate'] // 1000} kS/s · "
                f"{p['gainDb']} dB 手动 · AGC 关 · DC {int(p['dcOffsetHz'])} Hz\n"
                '点「应用推荐参数」填进当前数据源（本机 USB 直连）。')
        elif ok:
            box.setInformativeText('设备可用，但未能读取 tuner 型号。'
                                   '可直接使用「本机 USB (直连)」数据源。')
        else:
            box.setInformativeText('请检查 USB 连接与 WinUSB 驱动（Zadig）。'
                                   '若直连不可用，程序会自动回退到 rtl_tcp 中转。')
        box.setDetailedText(msg[-4000:] if msg else '(无输出)')
        applyBtn = None
        if profiles:
            applyBtn = box.addButton('应用推荐参数', QMessageBox.AcceptRole)
        box.addButton('关闭', QMessageBox.RejectRole)
        box.exec()
        if applyBtn is not None and box.clickedButton() is applyBtn:
            self._applyProfile(profiles[0])

    def _applyProfile(self, prof: dict):
        """把推荐参数写进当前数据源，并把类型切到本机 USB 直连。"""
        sr = int(prof.get('sampleRate', 960000))
        idx = self.srCombo.findData(sr)
        if idx < 0:
            self.srCombo.addItem(f'{sr // 1000} kS/s', sr)
            idx = self.srCombo.count() - 1
        self._updating_mode = True
        try:
            self.srCombo.setCurrentIndex(idx)
            self.gainSpin.setValue(float(prof.get('gainDb', 19.7)))
            self.dcSpin.setValue(float(prof.get('dcOffsetHz', 50000.0)))
            self.devIndexSpin.setValue(int(prof.get('index', 0) or 0))
            ti = self.srcTypeCombo.findData('rtl_usb')
            if ti >= 0:
                self.srcTypeCombo.setCurrentIndex(ti)
        finally:
            self._updating_mode = False
        self._storeFieldsToSource(self._activeSource)
        name = f"本机 RTL-SDR ({prof.get('tuner', 'USB')} 直连)"
        self._sources[self._activeSource]['name'] = name
        self._refreshSourceCombo()

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
    """配置对话框：一次只显示一页（由「配置」菜单的分项决定），不再用页签翻。"""

    def __init__(self, config: CoreConfig, parent=None, page: str = None):
        super().__init__(parent)
        self.setWindowTitle('配置 · ' + (page or CONFIG_PAGES[0]))
        self.setMinimumSize(720, 560)
        self.resize(820, 660)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 底色自己铺：QSS 里的 QDialog 规则会被后面的 QWidget{transparent} 盖掉，
        # 不铺就会露出系统白底，深色主题下按钮直接看不见
        K.paintBackground(self)
        layout = QVBoxLayout(self)
        self.panel = ConfigPanel(config)
        self.panel.saveBtn.hide()
        self.panel.hotBtn.hide()
        self.panel.restartBtn.hide()

        # 只留请求的那一页：把页签条藏掉，选中对应索引
        tabs = self.panel.cfgTabs
        idx = 0
        if page:
            for i in range(tabs.count()):
                if tabs.tabText(i) == page:
                    idx = i
                    break
        tabs.setCurrentIndex(idx)
        try:
            tabs.tabBar().hide()
        except Exception:
            pass

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
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
