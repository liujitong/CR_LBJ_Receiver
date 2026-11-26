#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_panel.py — 实时位置地图面板（Leaflet + OpenRailwayMap）

地图页是**桌面与安卓共用的** `shared/web/railmap.html`（Leaflet，
底图可切，铁路图源 OpenRailwayMap + 可选本地 GeoJSON）。本模块只负责
「工具栏 + 数据推送 + 状态轮询」，页面本身完全由 `map_host.MapHost` 装载：

    MapPanel（本模块）  ── 工具栏、跟随/夜间、列车字典、1200ms 状态轮询
        └── MapHost    ── QWebEngineView + setHtml(baseUrl=shared/web/) + JS 桥

三个必须记住的点：

1. **底图全部免 Key 或只需天地图 tk**。只有「没有 QtWebEngine」或「缺
   railmap.html」时才降级成提示面板；默认底图高德街道（免 Key、国内通常可达）。
2. **坐标一律 WGS-84 原值**。OSM/天地图为 WGS-84 系（天地图 CGCS2000≈WGS-84，零偏移）；
   高德（GCJ-02）/百度（BD-09）底图下由页面自动纠偏标记，这里 `updateTrain()` 不做任何坐标转换。
3. **换主题不重建页面**。重建会丢全部标记。主题色通过 `applyConfig(colors)`
   推给页面，深浅色只调 `LBJ.setNight()`。

对外契约（main_window 在用，签名不动）：
    MapPanel(config, parent) / hasMap / updateTrain(d) / focusCurrent() / clear()
    setConfig(config) / applyTheme() / setNightMode(b) / centerToDefault()
    updateTrain / coordLabel / followBtn / nightBtn / mapClicked / followChanged
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QComboBox, QCheckBox,
)

from . import config_ext
from . import theme as TH
from . import widgets as K
from .map_host import MapHost, HAS_WEBENGINE


def _c(key: str, fallback: str = '#888888') -> str:
    """取当前主题色（theme 不可用时退回 fallback）。"""
    return TH.c(key, fallback)


def _sx(v: float) -> int:
    """设计像素 → 当前界面倍率下的像素（与其余界面同一套倍率）。"""
    return K.spx(v)


# ---------------------------------------------------------------------------
# 瓦片失败提示门限
# ---------------------------------------------------------------------------
#: 瓦片全失败的门限（失败样本达到这么多次才可能提示「换一张底图」）
_TILE_FAIL_HINT = 6


class MapPanel(QWidget):
    """首页实时地图卡片。

    对外接口:
        setConfig(cfg)      配置变化时调用（底图/铁路/夜间/跟随/中心）
        updateTrain(d)      传入一条解码结果字典（WGS-84 原始坐标）
        focusCurrent()      定位到最近一列车
        clear()             清空所有标记
        applyTheme()        主题切换（不重建页面，只改配色/深浅）
        setNightMode(b)     夜间/日间（按钮与视图菜单共用）
        setBase(id)         切底图（视图菜单用）
        setRailStyle(id)    切铁路图层（视图菜单用）
    """

    mapClicked = Signal(str)
    followChanged = Signal(bool)      # 跟随开关变化（含“手动拖图导致自动取消”）
    layersChanged = Signal(dict)      # 底图/铁路图层变化 {'base':..,'rail':..}
    consoleMessage = Signal(str)      # 页面 JS 控制台（调试/排障用）

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config_ext.ensure(config)
        self._trains: Dict[str, Dict[str, Any]] = {}
        self._last_push = 0.0
        self._last_train_at = 0.0
        self._coord_text = '等待经纬度报文'
        self._tile_bad = False
        self._status: Dict[str, Any] = {}
        # 上一次**由本程序推给页面**的图层值：用来区分“页面里被用户改了”
        # 和“程序自己下发的”，避免把程序下发当成用户操作重复写配置
        self._pushed = {
            'base': config_ext.normalize_base(config_ext.get(self.config, 'mapBase', 'amap')),
            'rail': config_ext.normalize_rail(config_ext.get(self.config, 'mapRail', 'orm_standard')),
        }

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(_sx(2))

        outer.addLayout(self._buildBar())

        self.host = MapHost(self.config, self)
        self.host.readyChanged.connect(self._onHostReady)
        self.host.consoleMessage.connect(self._onMapConsole)
        outer.addWidget(self.host, 1)

        self._buildView()

        # 每 1.2 秒问一次页面状态：跟随是否被用户解锁、底图/铁路是否在页面内被改、
        # 瓦片是否全失败、当前视图中心（缓存进配置，断网下次也能回到原地）。
        self._viewTimer = QTimer(self)
        self._viewTimer.setInterval(1200)
        self._viewTimer.timeout.connect(self._pollView)
        self._viewTimer.start()

    # ------------------------------------------------------------------
    # 工具栏
    # ------------------------------------------------------------------
    def _buildBar(self):
        bar = QHBoxLayout()
        bar.setContentsMargins(_sx(6), _sx(2), _sx(6), _sx(2))
        bar.setSpacing(_sx(6))

        self.titleLabel = QLabel('实时位置')
        self.titleLabel.setStyleSheet(
            f'color: {_c("accent")}; font-weight: bold; font-size: {_sx(12)}px;')
        bar.addWidget(self.titleLabel)

        # 底图下拉：选项来自 config_ext.BASE_LAYERS（与页面登记表逐字一致）
        self.baseCombo = QComboBox()
        for lid, name in config_ext.BASE_LAYERS:
            self.baseCombo.addItem(name, lid)
        self.baseCombo.setToolTip('底图（免 Key；天地图需在配置里填 tk）')
        self.baseCombo.setMinimumWidth(_sx(96))
        self.baseCombo.setMaximumWidth(_sx(160))
        self.baseCombo.currentIndexChanged.connect(self._onBaseCombo)
        bar.addWidget(self.baseCombo)

        self.railCheck = QCheckBox('铁路')
        self.railCheck.setToolTip('叠加 OpenRailwayMap 铁路图层（WGS-84）')
        self.railCheck.setChecked(
            config_ext.normalize_rail(config_ext.get(self.config, 'mapRail',
                                                     'orm_standard')) != 'off')
        self.railCheck.toggled.connect(self._onRailCheck)
        bar.addWidget(self.railCheck)

        self.coordLabel = QLabel(self._coord_text)
        self.coordLabel.setStyleSheet(f'color: {_c("dim")}; font-size: {_sx(11)}px;')
        self.coordLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(self.coordLabel, 1)

        self.followBtn = QPushButton('跟随')
        self.followBtn.setCheckable(True)
        self.followBtn.setChecked(bool(getattr(self.config, 'mapFollow', True)))
        self.followBtn.setToolTip('自动跟着最新列车走（手动拖动地图会自动暂停）')
        self.followBtn.setStyleSheet(
            f'padding: 2px {_sx(8)}px; font-size: {_sx(11)}px;')
        self.followBtn.clicked.connect(self._onFollow)
        bar.addWidget(self.followBtn)

        self.nightBtn = QPushButton()
        self.nightBtn.setCheckable(True)
        self.nightBtn.setChecked(bool(getattr(self.config, 'mapNight', True)))
        self.nightBtn.setToolTip('切换地图夜间 / 日间配色')
        self.nightBtn.setStyleSheet(
            f'padding: 2px {_sx(8)}px; font-size: {_sx(11)}px;')
        self.nightBtn.clicked.connect(self._onNight)
        self._syncNightBtn()
        bar.addWidget(self.nightBtn)

        self.centerBtn = QPushButton('中心')
        self.centerBtn.setToolTip('回到配置里的默认中心（预设城市或经纬度）')
        self.centerBtn.setStyleSheet(
            f'padding: 2px {_sx(8)}px; font-size: {_sx(11)}px;')
        self.centerBtn.clicked.connect(self.centerToDefault)
        bar.addWidget(self.centerBtn)

        self.clearBtn = QPushButton('清除')
        self.clearBtn.setToolTip('清除地图上的列车标记')
        self.clearBtn.setStyleSheet(
            f'padding: 2px {_sx(8)}px; font-size: {_sx(11)}px;')
        self.clearBtn.clicked.connect(self.clear)
        bar.addWidget(self.clearBtn)

        self.browserBtn = QPushButton('网页')
        self.browserBtn.setToolTip('在浏览器中用天地图打开当前位置（WGS-84）')
        self.browserBtn.setStyleSheet(
            f'padding: 2px {_sx(8)}px; font-size: {_sx(11)}px;')
        self.browserBtn.clicked.connect(self._openInBrowser)
        bar.addWidget(self.browserBtn)
        return bar

    # ------------------------------------------------------------------
    # 地图页面
    # ------------------------------------------------------------------
    @property
    def hasMap(self) -> bool:
        """地图页面是否真的在（供主窗口/仪表板判断）。"""
        return self.host.ready

    @property
    def _view(self):
        """兼容旧调用点：主窗口曾直接摸 `mapPanel._view`。"""
        return self.host.view

    @property
    def _page_ready(self) -> bool:
        return self.host.ready

    def _buildView(self):
        """装载共享地图页；缺 QtWebEngine / 缺页面文件时降级为提示面板。"""
        self.host.load()
        self._syncBaseCombo()

    def _onHostReady(self, ok: bool):
        if not ok:
            return
        self._pushed['base'] = config_ext.normalize_base(
            config_ext.get(self.config, 'mapBase', 'amap'))
        self._pushed['rail'] = config_ext.normalize_rail(
            config_ext.get(self.config, 'mapRail', 'orm_standard'))
        self._syncBaseCombo()
        self.railCheck.blockSignals(True)
        self.railCheck.setChecked(self._pushed['rail'] != 'off')
        self.railCheck.blockSignals(False)
        self._push(force=True)

    def _onMapConsole(self, message: str):
        """页面 JS 的控制台输出：转成信号，由主窗口接到日志总线。"""
        self.consoleMessage.emit(str(message))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._applyCompact()
        if self.host.ready:
            self.host.resize()

    def _applyCompact(self):
        """窄卡片收掉次要控件，别让工具栏把地图挤没。

        地图卡片在窄窗口（或 200% 缩放的小逻辑屏）里可能只有 240px 宽，
        工具栏全排开必然溢出。三档：
            >= 430  全显示
            340~430 收「铁路 / 清除 / 网页」，底图下拉保留（换底图是救急操作）
            < 340   只剩 夜间 / 中心 / 跟随 + 一行状态文字
        """
        w = self.width()
        normal = w >= _sx(430)
        mid = _sx(340) <= w < _sx(430)
        for wid in (self.railCheck, self.clearBtn, self.browserBtn):
            wid.setVisible(normal)
        self.baseCombo.setVisible(normal or mid)
        self.titleLabel.setVisible(normal or mid)
        self.baseCombo.setMaximumWidth(max(_sx(70), int(w * 0.32)))

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def setConfig(self, config):
        """配置更新后同步页面（不重建 —— 重建会丢标记）。"""
        old_addr = str(getattr(self.config, 'mapCenterAddress', '') or '').strip()
        old_lat = float(getattr(self.config, 'mapCenterLat', 0) or 0)
        old_lng = float(getattr(self.config, 'mapCenterLng', 0) or 0)
        self.config = config_ext.ensure(config)
        self.followBtn.setChecked(bool(getattr(self.config, 'mapFollow', True)))
        self._syncNightBtn()
        self._syncBaseCombo()
        rail = config_ext.normalize_rail(
            config_ext.get(self.config, 'mapRail', 'orm_standard'))
        self.railCheck.blockSignals(True)
        self.railCheck.setChecked(rail != 'off')
        self.railCheck.blockSignals(False)
        if self.host.ready:
            self.host.apply_config(self.config)
            self._pushed['base'] = config_ext.normalize_base(
                config_ext.get(self.config, 'mapBase', 'amap'))
            self._pushed['rail'] = rail
            self._push(force=True)
            new_addr = str(getattr(self.config, 'mapCenterAddress', '') or '').strip()
            new_lat = float(getattr(self.config, 'mapCenterLat', 0) or 0)
            new_lng = float(getattr(self.config, 'mapCenterLng', 0) or 0)
            if (new_addr != old_addr
                    or abs(new_lat - old_lat) > 1e-6
                    or abs(new_lng - old_lng) > 1e-6):
                self.centerToDefault()
        else:
            # 上一次是降级状态（比如刚装好 Addons）：重新尝试装载
            self._buildView()

    def applyTheme(self):
        """主题切换：只改页面配色 + 深浅，**不重建页面**（标记/轨迹都不丢）。"""
        self._refreshToolbarStyles()
        if not self.host.ready:
            return
        self.host.apply_config(self.config)          # colors 跟着新主题
        self.host.set_night(bool(getattr(self.config, 'mapNight', True)))

    def _refreshToolbarStyles(self):
        try:
            self.titleLabel.setStyleSheet(
                f'color: {_c("accent")}; font-weight: bold; font-size: {_sx(12)}px;')
            self._refreshCoordLabel()
            self._syncNightBtn()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 图层
    # ------------------------------------------------------------------
    def _syncBaseCombo(self):
        base = config_ext.normalize_base(
            config_ext.get(self.config, 'mapBase', 'amap'))
        idx = self.baseCombo.findData(base)
        if idx >= 0:
            self.baseCombo.blockSignals(True)
            self.baseCombo.setCurrentIndex(idx)
            self.baseCombo.blockSignals(False)

    def _onBaseCombo(self, _index: int):
        lid = str(self.baseCombo.currentData() or '')
        if not lid:
            return
        self.setBase(lid)

    def setBase(self, layer_id: str):
        """切换底图（工具栏、视图菜单、页面内下拉共用一条路径）。"""
        lid = config_ext.normalize_base(layer_id, '')
        if not lid:
            return
        if lid in config_ext.TDT_LAYERS and not str(
                config_ext.get(self.config, 'tdtKey', '') or '').strip():
            # 天地图要 tk：不拦着页面提示，但先在这里说清楚并回退下拉
            self._coord_text = '天地图需要浏览器端 tk（配置 → 地图与车次）'
            self._refreshCoordLabel()
            self._syncBaseCombo()
            return
        self.config.mapBase = lid
        self._pushed['base'] = lid
        self._tile_bad = False
        idx = self.baseCombo.findData(lid)
        if idx >= 0:
            self.baseCombo.blockSignals(True)
            self.baseCombo.setCurrentIndex(idx)
            self.baseCombo.blockSignals(False)
        if self.host.ready:
            self.host.set_base(lid)
        self._saveConfig()
        self.layersChanged.emit({'base': lid, 'rail': self.current_rail()})

    def current_rail(self) -> str:
        return config_ext.normalize_rail(
            config_ext.get(self.config, 'mapRail', 'orm_standard'))

    def setRailStyle(self, layer_id: str):
        """切换铁路图层（'off' 表示不显示）。"""
        lid = config_ext.normalize_rail(layer_id, 'orm_standard')
        self.config.mapRail = lid
        self._pushed['rail'] = lid
        self.railCheck.blockSignals(True)
        self.railCheck.setChecked(lid != 'off')
        self.railCheck.blockSignals(False)
        if self.host.ready:
            self.host.set_rail(lid)
        self._saveConfig()
        self.layersChanged.emit({'base': str(self.config.mapBase or ''), 'rail': lid})

    def setRailVisible(self, on: bool):
        """铁路图层开关（复选框/菜单共用）：关掉时记住原来的样式。"""
        if on:
            lid = self.current_rail()
            if lid == 'off':
                lid = 'orm_standard'
            self.setRailStyle(lid)
        else:
            self.setRailStyle('off')

    def _onRailCheck(self, checked: bool):
        self.setRailVisible(bool(checked))

    def _saveConfig(self):
        """只写配置，不弹窗；失败也静默（配置目录只读时不该崩）。"""
        path = _config_path()
        if not path:
            return
        try:
            self.config.save(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------
    def updateTrain(self, d: dict, info: Optional[dict] = None):
        lat = d.get('latitude')
        lon = d.get('longitude')
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return
        train = str(d.get('train') or d.get('baseTrain') or '----')
        # 用纯数字车次做稳定 id：基础帧先到、长报文后补前缀时不会出现两个标记
        tid = str(d.get('baseTrain') or train)
        ts = float(d.get('timestamp') or 0.0)
        item = self._trains.get(tid)
        if item is None:
            item = {}
            self._trains[tid] = item
        # 坐标一律 WGS-84 原值：OSM/天地图零偏移；高德/百度由页面自动纠偏
        item.update({
            'id': tid,
            'train': train,
            'lat': round(float(lat), 6),
            'lon': round(float(lon), 6),
            'time': d.get('timeStr', ''),
            'speed': d.get('speed', '---'),
            'km': d.get('position', '---.-'),
            'route': d.get('route', '----'),
            'loco': d.get('loco', '----'),
            'direction': d.get('direction', '未知'),
            'category': d.get('category', '----'),
            'ts': ts,
        })
        # 车次/机车信息（等级/担当局/配属段/车型/制造厂）：合并而非覆盖，
        # 因为车次查询是异步的、可能比位置帧晚到。
        merged = dict(item.get('info') or {})
        for k, v in (info or {}).items():
            if v:
                merged[k] = v
        if merged:
            item['info'] = merged
        # 清理 15 分钟未更新的列车（用本条报文时间做基准，掉线时不至于全清）
        cutoff = ts - 900
        for k in [k for k, v in self._trains.items() if v.get('ts', 0) < cutoff]:
            self._trains.pop(k, None)

        self._last_train_at = datetime.now().timestamp()
        self._coord_text = '%s  %.5f, %.5f' % (train, float(lat), float(lon))
        self._refreshCoordLabel()
        self._push()

    def _payload(self, focus: Optional[str] = None) -> dict:
        trains = sorted(self._trains.values(),
                        key=lambda x: x.get('ts', 0), reverse=True)
        return {
            'trains': trains,
            'follow': bool(getattr(self.config, 'mapFollow', True)),
            'showTrail': bool(getattr(self.config, 'mapShowTrail', True)),
            'night': bool(getattr(self.config, 'mapNight', True)),
            # 只有显式定位（focusCurrent）才传 focus；否则每帧都会被强制
            # setView，「跟随」开关就失效了
            'focus': focus,
        }

    def _push(self, force: bool = False):
        if not self.host.ready:
            return
        now = datetime.now().timestamp()
        if not force and now - self._last_push < 0.25:
            return
        self._last_push = now
        self.host.update(self._payload())

    def focusCurrent(self):
        if not self._trains:
            return
        tid = max(self._trains.values(), key=lambda x: x.get('ts', 0))['id']
        if self.host.ready:
            self.host.focus(tid)

    def setTrainInfo(self, train_or_id, info: dict):
        """补充某趟车的车次/机车信息（车次查询异步回来后调用）。

        同时写进本地缓存并把整份 payload 重推一次，保证刷新/重开页面后不丢。
        """
        key = str(train_or_id or '').strip()
        if not key or not isinstance(info, dict) or not info:
            return
        hit = False
        for tid, item in self._trains.items():
            if tid == key or str(item.get('train') or '') == key:
                merged = dict(item.get('info') or {})
                for k, v in info.items():
                    if v:
                        merged[k] = v
                if merged:
                    item['info'] = merged
                    hit = True
        if not hit:
            return
        if self.host.ready:
            self.host.set_train_info(key, {k: v for k, v in info.items() if v})
            self._push(force=True)

    def clear(self):
        self._trains.clear()
        self._coord_text = '等待经纬度报文'
        self._refreshCoordLabel()
        if self.host.ready:
            self.host.clear()

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _refreshCoordLabel(self):
        """工具栏提示文字：瓦片全失败时优先提示「换一张底图」。"""
        if self._tile_bad:
            self.coordLabel.setText('底图不可达，换一张')
            self.coordLabel.setStyleSheet(
                f'color: {_c("warn")}; font-size: {_sx(11)}px; font-weight: bold;')
            self.coordLabel.setToolTip(
                '当前底图瓦片连续加载失败，可能是网络/代理问题；'
                '点左侧「底图」下拉换一张（高德 / 百度 / OSM / 天地图）。')
        else:
            self.coordLabel.setText(self._coord_text)
            self.coordLabel.setStyleSheet(
                f'color: {_c("dim")}; font-size: {_sx(11)}px;')
            self.coordLabel.setToolTip('最新一条带经纬度的报文（原始 WGS-84 坐标）')

    def _onFollow(self, checked: bool):
        self.config.mapFollow = bool(checked)
        if self.host.ready:
            self.host.set_follow(bool(checked))
            if checked:
                self.focusCurrent()
        self._push(force=True)
        self._saveConfig()
        self.followChanged.emit(bool(checked))

    def _onNight(self, checked: bool):
        self.setNightMode(checked)
        self._push(force=True)

    def centerToDefault(self):
        """把地图挪回默认中心（预设城市/经纬度，页面不加标记）。"""
        lat = float(getattr(self.config, 'mapCenterLat', 0) or 0)
        lng = float(getattr(self.config, 'mapCenterLng', 0) or 0)
        addr = str(getattr(self.config, 'mapCenterAddress', '') or '').strip()
        # 用户主动看固定中心，就先让开「跟随」；否则下一帧列车一动又被拉走
        if self.followBtn.isChecked():
            self.followBtn.setChecked(False)
            self.config.mapFollow = False
            if self.host.ready:
                self.host.set_follow(False)
            self.followChanged.emit(False)
        if not self.host.ready:
            return
        # 页面只认 CONFIG.center（离线，不做地名解析）；先推坐标再居中
        self.host.apply_config(self.config)
        self.host.center_to(addr)
        self._coord_text = '中心：%s' % (addr or ('%.4f, %.4f' % (lat, lng)
                                                if lat or lng else '（未设置）'))
        self._tile_bad = False
        self._refreshCoordLabel()

    def setNightMode(self, on: bool):
        """切换夜间/日间配色（按钮与视图菜单共用）。"""
        self.config.mapNight = bool(on)
        self._syncNightBtn()
        if self.host.ready:
            self.host.set_night(bool(on))

    def _syncNightBtn(self):
        on = bool(getattr(self.config, 'mapNight', True))
        self.nightBtn.setText('夜间' if on else '日间')
        self.nightBtn.setChecked(on)
        self.nightBtn.setToolTip('当前：%s（点击切换）' % ('夜间' if on else '日间'))

    # ------------------------------------------------------------------
    # 轮询页面状态
    # ------------------------------------------------------------------
    def _pollView(self):
        if not self.host.ready:
            return
        self.host.status(self._onStatusPoll)

    def _onStatusPoll(self, st):
        if not isinstance(st, dict):
            return
        self._status = st
        # ① 用户手动拖过地图 → 取消勾选「跟随」，让按钮状态和实际行为一致
        if st.get('locked') and self.followBtn.isChecked():
            self.followBtn.setChecked(False)
            self.config.mapFollow = False
            self.followChanged.emit(False)
        # ② 夜间：以页面实际状态为准（页面没有自己的夜间按钮，正常不会不一致）
        night = bool(st.get('night'))
        if night != self.nightBtn.isChecked():
            self._syncNightBtn()
        # ③ 图层：页面内被用户改过就回写配置；坐标不混叠导致的自动关图层不算
        self._syncLayersFromPage(st)
        # ④ 瓦片：底图真的不可达时才给一句「换一张」，不弹窗
        try:
            total = int(st.get('tilesTotal') or 0)
            failed = int(st.get('tilesFailed') or 0)
        except (TypeError, ValueError):
            total, failed = 0, 0
        # 页面 status() 的 tilesTotal/tilesFailed **只统计底图**（v3.2 起铁路单独统计），
        # 所以这里不会被 ORM 403 带偏。
        # total 是**成功**张数，加载中 total 可能很小：要求失败≥6 且失败率 ≥95%
        # （failed >= total*19）才算不可达，避免「明明可达却被判不可达」。
        bad = bool(failed >= _TILE_FAIL_HINT
                   and (total == 0 or failed >= total * 19))
        if bad != self._tile_bad:
            self._tile_bad = bad
            self._refreshCoordLabel()
        # ⑤ 顺手缓存视图中心，断网下次启动也有中心可用
        self.host.center(self._onCenterPoll)

    def _syncLayersFromPage(self, st: dict):
        base = str(st.get('base') or '')
        rail = str(st.get('rail') or '')
        changed = {}
        if base and base != self._pushed['base']:
            # 用户在网页面板里换了底图 → 回写配置，工具栏下拉同步
            self.config.mapBase = base
            self._pushed['base'] = base
            self._syncBaseCombo()
            changed['base'] = base
        if rail and rail != self._pushed['rail']:
            # 用户在网页面板里关的/换的铁路图层：记住偏好
            self._pushed['rail'] = rail
            self.railCheck.blockSignals(True)
            self.railCheck.setChecked(rail != 'off')
            self.railCheck.blockSignals(False)
            self.config.mapRail = rail
            changed['rail'] = rail
        if changed:
            changed.setdefault('base', str(config_ext.get(self.config, 'mapBase', '')))
            changed.setdefault('rail', str(config_ext.get(self.config, 'mapRail', '')))
            self._saveConfig()
            self.layersChanged.emit(changed)

    def _onCenterPoll(self, center):
        try:
            if isinstance(center, list) and len(center) == 2 and center[0]:
                lng, lat = float(center[0]), float(center[1])
                # 只有明显变化才写，避免每次刷新都落盘
                if (abs(lng - float(getattr(self.config, 'mapCenterLng', 0) or 0)) > 1e-4
                        or abs(lat - float(getattr(self.config, 'mapCenterLat', 0) or 0))
                        > 1e-4):
                    self.config.mapCenterLng = lng
                    self.config.mapCenterLat = lat
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 浏览器
    # ------------------------------------------------------------------
    def _openInBrowser(self):
        """在系统浏览器里用天地图打开当前列车位置（天地图为 WGS-84 系，零偏移）。"""
        if not self._trains:
            QDesktopServices.openUrl(QUrl('https://map.tianditu.gov.cn/'))
            return
        t = max(self._trains.values(), key=lambda x: x.get('ts', 0))
        lat, lon = float(t.get('lat') or 0), float(t.get('lon') or 0)
        url = ('https://map.tianditu.gov.cn/#/map?center={lon:.6f},{lat:.6f}&zoom=15'
               ).format(lon=lon, lat=lat)
        QDesktopServices.openUrl(QUrl(url))


def _config_path() -> str:
    """兜底取配置路径（正常走 runtime.CONFIG_PATH）。"""
    try:
        from cr_lbj.runtime import CONFIG_PATH
        return CONFIG_PATH
    except Exception:
        return ''
