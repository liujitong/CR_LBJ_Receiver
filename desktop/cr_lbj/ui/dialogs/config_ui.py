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
        page('数据源与射频').addWidget(srcGroup)

        # ---- 连接与射频（v3.1.1：数据源 + 射频合并为一页，字段按「源 → 采样 → 射频」排） ----
        # 顺序：源类型（在上面的数据源组）/ 主机 / 端口 → 采样率 → 中心频率 /
        #       硬件增益 / PPM / 信道带宽 / DC 偏移 → 块大小。
        rfGroup = QGroupBox('连接与射频')
        rfForm = QFormLayout(rfGroup)
        rfForm.setSpacing(4)
        rfForm.setContentsMargins(8, 16, 8, 4)

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

        self.dcSpin = QDoubleSpinBox()
        self.dcSpin.setRange(-500000, 500000)
        self.dcSpin.setDecimals(0)
        self.dcSpin.setSuffix(' Hz')
        self.dcSpin.setValue(config.dcOffsetHz)

        self.blockSpin = QSpinBox()
        self.blockSpin.setRange(1024, 262144)
        self.blockSpin.setSingleStep(1024)
        self.blockSpin.setValue(config.blockSize)

        self.usbHint = QLabel(
            'USB 直连：程序自动查找本机 RTL-SDR，无需主机与端口。'
            '插上棒子后点上方「检测设备」确认 tuner 并应用推荐参数；'
            '多支棒子用「设备序号」区分。')
        self.usbHint.setWordWrap(True)
        self.usbHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')

        rfForm.addRow(self.usbHint)
        rfForm.addRow('主机:', self.hostEdit)
        rfForm.addRow('端口:', self.portSpin)
        rfForm.addRow('采样率:', self.srCombo)
        rfForm.addRow('中心频率:', self.freqSpin)
        rfForm.addRow('硬件增益:', self.gainSpin)
        rfForm.addRow('PPM 校正:', self.ppmSpin)
        rfForm.addRow('信道带宽:', self.bwSpin)
        rfForm.addRow('DC 偏移:', self.dcSpin)
        rfForm.addRow('块大小:', self.blockSpin)
        self._connForm = rfForm

        page('数据源与射频').addWidget(rfGroup)

        # ---- 中部：RSSI 门控 + AFC 设置（同属「数据源与射频」页，两列并排） ----
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

        midGrid.addWidget(rssiGroup, 0, 0)

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

        midGrid.addWidget(afcGroup, 0, 1)
        page('数据源与射频').addLayout(midGrid)

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

        # ---- 地图与车次（Leaflet + OpenRailwayMap） ----
        from PySide6.QtWidgets import QSlider           # runtime 未导出 QSlider
        from cr_lbj.ui import config_ext
        from cr_lbj.ui import data_update

        mapGroup = QGroupBox('地图底图与铁路图层')
        mapForm = QFormLayout(mapGroup)
        mapForm.setSpacing(4)
        mapForm.setContentsMargins(8, 16, 8, 4)

        # 底图（免 Key；天地图需要 tk）
        self.mapBaseCombo = QComboBox()
        for _lid, _name in config_ext.BASE_LAYERS:
            self.mapBaseCombo.addItem(_name, _lid)
        _curBase = config_ext.normalize_base(
            config_ext.get(config, 'mapBase', 'amap'))
        _bi = self.mapBaseCombo.findData(_curBase)
        self.mapBaseCombo.setCurrentIndex(_bi if _bi >= 0 else 0)
        self.mapBaseCombo.setToolTip(
            '底图可选 高德 / 百度（免 Key）、OSM、天地图（需 tk）；高德为 GCJ-02、百度为 BD-09，标记会自动纠偏；'
            '天地图需在下方填浏览器端 tk')

        # 铁路图层（OpenRailwayMap）
        self.mapRailCombo = QComboBox()
        for _rid, _rname in config_ext.RAIL_LAYERS:
            self.mapRailCombo.addItem(_rname, _rid)
        _curRail = config_ext.normalize_rail(
            config_ext.get(config, 'mapRail', 'orm_standard'))
        _ri = self.mapRailCombo.findData(_curRail)
        self.mapRailCombo.setCurrentIndex(_ri if _ri >= 0 else 1)

        self.mapRailOpacity = QSlider(Qt.Horizontal)
        self.mapRailOpacity.setRange(20, 100)
        self.mapRailOpacity.setSingleStep(5)
        self.mapRailOpacity.setPageStep(10)
        try:
            _op = int(round(float(config_ext.get(config, 'mapRailOpacity',
                                                 0.85) or 0.85) * 100))
        except (TypeError, ValueError):
            _op = 85
        self.mapRailOpacity.setValue(max(20, min(100, _op)))
        self.mapRailOpacityLabel = QLabel('%d%%' % self.mapRailOpacity.value())
        self.mapRailOpacityLabel.setMinimumWidth(spx(38))
        self.mapRailOpacity.valueChanged.connect(
            lambda v: self.mapRailOpacityLabel.setText('%d%%' % v))
        railRow = QWidget()
        railLay = QHBoxLayout(railRow)
        railLay.setContentsMargins(0, 0, 0, 0)
        railLay.setSpacing(spx(6))
        railLay.addWidget(self.mapRailOpacity, 1)
        railLay.addWidget(self.mapRailOpacityLabel, 0)

        self.mapNightCheck = QCheckBox('地图夜间模式（深色底图）')
        self.mapNightCheck.setChecked(bool(getattr(config, 'mapNight', True)))
        self.mapFollowCheck = QCheckBox('自动跟随最新列车')
        self.mapFollowCheck.setChecked(bool(getattr(config, 'mapFollow', True)))
        self.mapTrailCheck = QCheckBox('显示历史轨迹（最多 240 点）')
        self.mapTrailCheck.setChecked(bool(getattr(config, 'mapShowTrail', True)))

        # 天地图 tk（只在选天地图底图时才需要）
        self.tdtKeyEdit = QLineEdit(str(config_ext.get(config, 'tdtKey', '') or ''))
        self.tdtKeyEdit.setPlaceholderText('天地图「浏览器端」tk，留空则天地图不可用')
        self.tdtKeyEdit.setClearButtonEnabled(True)

        # 天地图 Referer 白名单域名：file:// 页面没有合法 Referer，
        # 宿主（桌面拦截器 / 安卓 WebView）按此域名给天地图请求附加 Referer
        self.tdtRefererEdit = QLineEdit(str(config_ext.get(config, 'tdtReferer', '') or ''))
        self.tdtRefererEdit.setPlaceholderText('申请 tk 时登记的白名单域名，如 example.com；留空则不附加')
        self.tdtRefererEdit.setClearButtonEnabled(True)
        self.tdtRefererEdit.setToolTip(
            '天地图「浏览器端」tk 按域名白名单校验 Referer。本地 file:// 页面没有合法 '
            'Referer，填了这里后程序会给 *.tianditu.gov.cn 请求附加 '
            'Referer: https://<域名>/。只填域名本身，不带 http:// 前缀。')

        # 默认中心：预设城市下拉 + 经纬度，双向同步
        self._places = config_ext.load_places()
        self.mapCenterCity = QComboBox()
        self.mapCenterCity.addItem('自定义经纬度', '')
        for _p in self._places:
            self.mapCenterCity.addItem(
                '%s（%.2f, %.2f）' % (_p['name'], _p['lat'], _p['lng']), _p['name'])

        self.mapCenterLngSpin = QDoubleSpinBox()
        self.mapCenterLngSpin.setRange(-180.0, 180.0)
        self.mapCenterLngSpin.setDecimals(4)
        self.mapCenterLngSpin.setSingleStep(0.01)
        self.mapCenterLngSpin.setSuffix(' °E')
        self.mapCenterLatSpin = QDoubleSpinBox()
        self.mapCenterLatSpin.setRange(-90.0, 90.0)
        self.mapCenterLatSpin.setDecimals(4)
        self.mapCenterLatSpin.setSingleStep(0.01)
        self.mapCenterLatSpin.setSuffix(' °N')

        _curLng = float(getattr(config, 'mapCenterLng', 0) or 0)
        _curLat = float(getattr(config, 'mapCenterLat', 0) or 0)
        self._centerAddress = str(getattr(config, 'mapCenterAddress', '') or '').strip()
        if abs(_curLng) < 1e-6 and abs(_curLat) < 1e-6 and self._centerAddress:
            # 老配置只存了地名：按名字在内置城市表里反查一次
            for _p in self._places:
                if _p['name'] == self._centerAddress:
                    _curLat, _curLng = float(_p['lat']), float(_p['lng'])
                    break
        self._updating_center = True
        try:
            self.mapCenterLngSpin.setValue(_curLng)
            self.mapCenterLatSpin.setValue(_curLat)
            _name = self._centerAddress or config_ext.nearest_place(_curLat, _curLng,
                                                                    self._places) or ''
            if not _name:
                _name = config_ext.nearest_place(_curLat, _curLng, self._places) or ''
            _ci = self.mapCenterCity.findData(_name)
            self.mapCenterCity.setCurrentIndex(_ci if _ci > 0 else 0)
            self._centerAddress = _name if _ci > 0 else ''
        finally:
            self._updating_center = False
        self.mapCenterCity.currentIndexChanged.connect(self._onCenterCityPicked)
        self.mapCenterLngSpin.valueChanged.connect(self._onCenterSpinChanged)
        self.mapCenterLatSpin.valueChanged.connect(self._onCenterSpinChanged)

        centerRow = QWidget()
        centerLay = QHBoxLayout(centerRow)
        centerLay.setContentsMargins(0, 0, 0, 0)
        centerLay.setSpacing(spx(6))
        centerLay.addWidget(self.mapCenterCity, 2)
        centerLay.addWidget(self.mapCenterLngSpin, 1)
        centerLay.addWidget(self.mapCenterLatSpin, 1)

        self.mapZoomSpin = QSpinBox()
        self.mapZoomSpin.setRange(3, 18)
        self.mapZoomSpin.setValue(int(getattr(config, 'mapZoom', 12) or 12))

        mapForm.addRow('底图:', self.mapBaseCombo)
        mapForm.addRow('铁路图层:', self.mapRailCombo)
        mapForm.addRow('图层不透明度:', railRow)
        mapForm.addRow('', self.mapNightCheck)
        mapForm.addRow('', self.mapFollowCheck)
        mapForm.addRow('', self.mapTrailCheck)
        mapForm.addRow('天地图 tk:', self.tdtKeyEdit)
        mapForm.addRow('天地图 Referer 域名:', self.tdtRefererEdit)
        mapForm.addRow('默认中心:', centerRow)
        mapForm.addRow('默认缩放:', self.mapZoomSpin)

        mapHint = QLabel(
            '铁路图源用 <b>OpenRailwayMap</b>（WGS-84 栅格瓦片，免 Key），也可选'
            '「本地铁路线」加载 <code>shared/web/rail_local.geojson</code>（自建方式见 '
            'docs/地图与图源.md）。底图可随时在界面左上角的下拉里切换，'
            'OSM/天地图为 WGS-84 系（零偏移）；高德 GCJ-02、百度 BD-09 会自动纠偏标记，'
            '偏移坐标系底图下铁路图层自动隐藏。<br>'
            '默认底图 <b>高德 街道</b>（免 Key，国内通常可达）；天地图需到 '
            '<a href="https://console.tianditu.gov.cn/">tianditu.gov.cn</a> 免费申请'
            '「<b>浏览器端</b>」类型的 tk 填进来，并把申请时登记的白名单域名填到'
            '「天地图 Referer 域名」（留空则不附加 Referer）。<br>'
            '「默认中心」选预设城市会自动填经纬度；手改经纬度则城市名清空。'
            '中心只用于开机定位，不会在地图上打标记。')
        mapHint.setWordWrap(True)
        mapHint.setOpenExternalLinks(True)
        mapHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')
        mapForm.addRow('', mapHint)
        page('地图与车次').addWidget(mapGroup)

        # ---- 车次与配属查询 ----
        queryGroup = QGroupBox('车次与配属查询')
        queryForm = QFormLayout(queryGroup)
        queryForm.setSpacing(4)
        queryForm.setContentsMargins(8, 16, 8, 4)
        self.trainQuerySourceCombo = QComboBox()
        self.trainQuerySourceCombo.addItem('自动（RailGo → 12306）', 'auto')
        self.trainQuerySourceCombo.addItem('RailGo（字段全）', 'railgo')
        self.trainQuerySourceCombo.addItem('12306（官方兜底）', '12306')
        _qi = self.trainQuerySourceCombo.findData(
            str(getattr(config, 'trainQuerySource', 'auto') or 'auto'))
        self.trainQuerySourceCombo.setCurrentIndex(_qi if _qi >= 0 else 0)
        self.trainQuerySourceCombo.setToolTip(
            '「工具 → 车次查询」和车次信息卡默认用这个数据源')
        queryForm.addRow('车次数据源:', self.trainQuerySourceCombo)
        qHint = QLabel('RailGo 字段全（担当局 / 客运段 / 配属段 / 车型 / 交路），'
                       '12306 为官方兜底（只有时刻表，没有担当配属）。')
        qHint.setWordWrap(True)
        qHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')
        queryForm.addRow('', qHint)
        page('地图与车次').addWidget(queryGroup)

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

        # ---- 第三方数据（自动更新） ----
        dataGroup = QGroupBox('第三方数据（机车配属号段表）')
        dataForm = QFormLayout(dataGroup)
        dataForm.setSpacing(4)
        dataForm.setContentsMargins(8, 16, 8, 4)

        self.dataAutoUpdateCheck = QCheckBox('自动检查数据更新（默认每周一次）')
        self.dataAutoUpdateCheck.setChecked(
            bool(getattr(config, 'dataAutoUpdate', True)))
        self.dataAutoUpdateCheck.setToolTip(
            '启动 20 秒后在后台检查上游号段表；失败只记日志，不影响使用')

        self.dataIntervalSpin = QSpinBox()
        self.dataIntervalSpin.setRange(1, 90)
        self.dataIntervalSpin.setSuffix(' 天')
        self.dataIntervalSpin.setValue(int(getattr(config, 'dataUpdateIntervalDays', 7)
                                           or 7))
        self.dataIntervalSpin.setToolTip('两次自动检查之间的最小间隔')

        self.dataStatusLabel = QLabel(data_update.status_text_multiline())
        self.dataStatusLabel.setWordWrap(True)
        self.dataStatusLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dataStatusLabel.setStyleSheet(
            f'color: {CLR("text")}; font-size: 11px;'
            f' background-color: {CLR("panel")}; border: 1px solid {CLR("border")};'
            f' border-radius: 4px; padding: 6px;'
            ' font-family: Consolas, "Microsoft YaHei", monospace;')

        self.dataCheckBtn = K.small_button('立即检查更新', h=28, px=12)
        self.dataCheckBtn.clicked.connect(self._checkDataUpdate)

        dataForm.addRow('', self.dataAutoUpdateCheck)
        dataForm.addRow('检查间隔:', self.dataIntervalSpin)
        dataForm.addRow('当前数据:', self.dataStatusLabel)
        dataForm.addRow('', self.dataCheckBtn)
        dataHint = QLabel(
            '配属号段表来自开源项目 <b>LBJ_Console</b>（GPL-3.0），装在程序里的是一份'
            '快照；勾选自动检查后会定期从上游拉取增量并<b>严格校验</b>（行数 / 型号数 / '
            '号段合法性），校验不过不会覆盖现有数据。更新写入用户目录 '
            '<code>%LOCALAPPDATA%\\CR-LBJ-Receiver\\data</code>，内置快照始终保留可回退。')
        dataHint.setWordWrap(True)
        dataHint.setStyleSheet(f'color: {CLR("dim")}; font-size: 11px;')
        dataForm.addRow('', dataHint)
        page('数据更新').addWidget(dataGroup)

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

    # ---- 地图默认中心（城市 ↔ 经纬度 双向同步） ----
    def _onCenterCityPicked(self, _index: int):
        """选预设城市 → 填经纬度；选「自定义」只是清掉城市名，不动坐标。"""
        if getattr(self, '_updating_center', False):
            return
        name = str(self.mapCenterCity.currentData() or '')
        if not name:
            self._centerAddress = ''
            return
        for p in getattr(self, '_places', []):
            if p['name'] == name:
                self._updating_center = True
                try:
                    self.mapCenterLngSpin.setValue(float(p['lng']))
                    self.mapCenterLatSpin.setValue(float(p['lat']))
                finally:
                    self._updating_center = False
                self._centerAddress = name
                return

    def _onCenterSpinChanged(self, _value: float = 0.0):
        """手改经纬度 → 城市名清空（自定义中心）。"""
        if getattr(self, '_updating_center', False):
            return
        self._updating_center = True
        try:
            self.mapCenterCity.setCurrentIndex(0)
        finally:
            self._updating_center = False
        self._centerAddress = ''

    # ---- 第三方数据更新 ----
    def _checkDataUpdate(self):
        """手动检查更新：后台线程跑，结果写回状态框（不阻塞配置窗口）。"""
        if getattr(self, '_dataThread', None) is not None and \
                self._dataThread.isRunning():
            return
        from cr_lbj.ui.data_update import DataUpdateThread, result_text
        self.dataCheckBtn.setEnabled(False)
        self.dataCheckBtn.setText('检查中…')
        self.dataStatusLabel.setText('正在连接上游……（最长约 20 秒）')
        # 线程不挂 parent：配置窗口随时会被关掉，运行中的 QThread 被 C++ 析构
        # 就是崩溃；data_update 内部会保留引用到 finished。
        self._dataThread = DataUpdateThread(force=True,
                                            interval_days=self.dataIntervalSpin.value(),
                                            parent=None)
        self._dataThread.done.connect(
            lambda res: self._onDataChecked(res, result_text(res)))
        self._dataThread.start()

    def _onDataChecked(self, res: dict, text: str):
        from cr_lbj.ui import data_update
        self.dataCheckBtn.setEnabled(True)
        self.dataCheckBtn.setText('立即检查更新')
        ok = bool((res or {}).get('ok'))
        tone = CLR('ok') if ok else CLR('warn')
        # 第一行放本次结果（成功/跳过/失败都看得见），后面接当前数据状态
        self.dataStatusLabel.setText('%s\n\n%s'
                                     % (text, data_update.status_text_multiline()))
        self.dataStatusLabel.setStyleSheet(
            f'color: {tone}; font-size: 11px;'
            f' background-color: {CLR("panel")}; border: 1px solid {CLR("border")};'
            f' border-radius: 4px; padding: 6px;')

    def _readConfig(self) -> Optional[CoreConfig]:
        try:
            from cr_lbj.ui import config_ext
            cfg = CoreConfig()
            config_ext.ensure(cfg)       # v3.0 字段要有实例属性，toDict 才写得进去
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
            # ---- 地图与车次 ----
            cfg.mapBase = str(self.mapBaseCombo.currentData() or 'amap')
            cfg.mapRail = str(self.mapRailCombo.currentData() or 'orm_standard')
            cfg.mapRailOpacity = self.mapRailOpacity.value() / 100.0
            cfg.tdtKey = self.tdtKeyEdit.text().strip()
            cfg.tdtReferer = self.tdtRefererEdit.text().strip()
            cfg.mapZoom = self.mapZoomSpin.value()
            cfg.mapFollow = self.mapFollowCheck.isChecked()
            cfg.mapShowTrail = self.mapTrailCheck.isChecked()
            cfg.mapNight = self.mapNightCheck.isChecked()
            # 默认中心：城市名只当标签（页面离线，靠经纬度居中）
            cfg.mapCenterAddress = str(getattr(self, '_centerAddress', '') or '')
            newLng = float(self.mapCenterLngSpin.value())
            newLat = float(self.mapCenterLatSpin.value())
            oldLng = float(getattr(self.config, 'mapCenterLng', 0.0) or 0.0)
            oldLat = float(getattr(self.config, 'mapCenterLat', 0.0) or 0.0)
            moved = (abs(newLng - oldLng) > 1e-6 or abs(newLat - oldLat) > 1e-6)
            cfg.mapCenterLng = newLng
            cfg.mapCenterLat = newLat
            if moved:
                # 坐标换了：地图面板收到 setConfig 会自己挪视图
                pass
            cfg.trainQuerySource = str(
                self.trainQuerySourceCombo.currentData() or 'auto')
            # ---- 第三方数据自动更新 ----
            cfg.dataAutoUpdate = self.dataAutoUpdateCheck.isChecked()
            cfg.dataUpdateIntervalDays = int(self.dataIntervalSpin.value())
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
