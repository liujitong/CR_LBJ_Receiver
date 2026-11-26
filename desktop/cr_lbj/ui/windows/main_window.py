#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主窗口、运行状态仪表板与配置归一化函数。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

from cr_lbj.ui import config_ext
from cr_lbj.ui import data_update
from cr_lbj.ui.info_lookup import TrainInfoService, merge_info


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self, config: CoreConfig):
        super().__init__()
        # v3.0 的配置字段（底图/铁路图层/天地图 tk/车次数据源/数据自动更新）
        # 由 UI 层兜底补到实例上，老配置文件不用手改也不会读空
        config_ext.ensure(config)
        self.config = config
        self.worker: Optional[DspBridge] = None

        # 日志中枢：底部只显示最新一条，「帮助 → 实时日志」看全量
        self.logBus = LogBus()
        self.logPanel = self.logBus          # 兼容旧调用点
        self._logWindow: Optional[LogWindow] = None
        self._dashWindow = None
        self._queryWindow = None
        self._dataThread = None
        self._dataBox = None
        self._isFullScreen = False
        # 多屏混合 DPI：记录窗口当前所在屏，换屏时重新适配（见 _onScreenChanged）
        self._lastScreen = None
        self._geomBusy = False

        self.setWindowTitle('中国铁路 LBJ 列车预警器解码程序  v3.2.1')
        # 最小尺寸不能写死：200% 缩放屏的逻辑可用区可能只有 640×400，
        # 写死 880×560 会把窗口顶出屏幕。按启动屏的可用区收紧。
        self._applyMinSizeForScreen()
        self._applyWindowGeometry()
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self._buildMenu()
        self._buildUi()
        # 启动时先让地图底图跟界面主题对齐（老配置里的 mapNight 可能是手设的）
        self._syncMapNight()

        # 从配置初始化频谱显示模式
        mode = getattr(self.config, 'spectrumMode', 'graph')
        if mode == 'terminal':
            self.spectrumModeCombo.setCurrentIndex(1)
            self.spectrumStack.setCurrentIndex(1)

        # 自动启动
        QTimer.singleShot(500, self.startDsp)

    # ---- 多屏 / 混合 DPI 适配（v2.5） ----
    def _currentScreen(self):
        """窗口实际所在屏。窗口还没 show 时用鼠标所在屏兜底。

        旧版一律用 primaryScreen()：本机主屏 1920×1080@100%，笔记本副屏
        1280×800@200%(dpr=2.0)。按主屏算出的窗口拖到副屏会被 Qt 再放大一倍，
        于是右下整片被裁。这里改成跟着窗口走。
        """
        try:
            h = self.windowHandle()
            if h is not None and h.screen() is not None:
                return h.screen()
        except Exception:
            pass
        try:
            s = QApplication.screenAt(QCursor.pos())
            if s is not None:
                return s
        except Exception:
            pass
        return QApplication.primaryScreen()

    def _applyMinSizeForScreen(self, scr=None):
        """按所在屏的**逻辑**可用区收紧窗口下限。

        200% 缩放屏的逻辑可用区可能只有 640×400，写死 spx(880)×spx(560)
        会把窗口顶出屏幕，Qt 布局再怎么自适应都救不回来。
        """
        try:
            s = scr or self._currentScreen()
            avail = s.availableGeometry() if s is not None else None
            if avail is None:
                self.setMinimumSize(spx(880), spx(560))
                return
            self.setMinimumSize(
                min(spx(880), max(320, avail.width() - spx(8))),
                min(spx(560), max(240, avail.height() - spx(8))))
        except Exception:
            self.setMinimumSize(spx(880), spx(560))

    def _applyWindowGeometry(self, scr=None):
        """按**窗口所在屏**的可用区自适应，窗口永远不超出这块屏。"""
        try:
            s = scr or self._currentScreen()
            if s is None:
                self.resize(spx(1000), spx(660))
                return
            avail = s.availableGeometry()
            w = min(int(avail.width() * 0.94), spx(1600))
            h = min(int(avail.height() * 0.92), spx(1000))
            # 下限想要大窗口，但绝不能超过这块屏：旧版 max() 会把窗口顶出去
            w = min(max(w, spx(1000)), avail.width())
            h = min(max(h, spx(660)), avail.height())
            self.resize(w, h)
            self.move(avail.x() + max(0, (avail.width() - w) // 2),
                      avail.y() + max(0, (avail.height() - h) // 3))
        except Exception:
            self.resize(spx(1000), spx(660))

    def _onScreenChanged(self, scr=None):
        """换屏或首次显示：收紧尺寸、重排三段、让地图重绘。

        注意 UI_SCALE 故意**不**跟着屏幕变：所有 spx() 尺寸在构造时已烘焙进
        控件，动态改倍率只会让部分控件变、部分不变，反而更乱。逻辑布局两屏
        保持一致，物理大小交给 Qt 按各自 dpr 渲染，这才是系统级正确行为。
        """
        if self._geomBusy:
            return
        s = scr or self._currentScreen()
        if s is None:
            return
        self._lastScreen = s
        self._geomBusy = True
        try:
            g = s.availableGeometry()
            cur = self.geometry()
            nw = min(cur.width(), int(g.width() * 0.94))
            nh = min(cur.height(), int(g.height() * 0.92))
            nx, ny = cur.x(), cur.y()
            # 只有窗口已经跑到这块屏外面时，才把它挪回屏内；否则保留用户拖的位置
            if (nx + nw > g.right() or nx < g.x() or
                    ny + nh > g.bottom() or ny < g.y()):
                nx = g.x() + max(0, (g.width() - nw) // 2)
                ny = g.y() + max(0, (g.height() - nh) // 3)
            self.setGeometry(nx, ny, nw, nh)
            self._applyMinSizeForScreen(s)
            self._applyResponsive(force=True)
            QTimer.singleShot(60, self._afterFullScreen)
        finally:
            self._geomBusy = False

    def showEvent(self, event):
        super().showEvent(event)
        # 窗口句柄在首次显示后才有效，这时才拿得到真正的所在屏
        QTimer.singleShot(0, self._initScreenFit)

    def _initScreenFit(self):
        try:
            h = self.windowHandle()
            if h is not None:
                h.screenChanged.connect(self._onScreenChanged)
        except Exception:
            pass
        s = self._currentScreen()
        if s is not None:
            self._onScreenChanged(s)

    # ---- 窗口几何 / 全屏 ----

    def toggleFullScreen(self, on: Optional[bool] = None):
        """全屏切换 (F11)。全屏时隐藏菜单栏以最大化内容区。"""
        if on is None:
            on = not self._isFullScreen
        if on == self._isFullScreen:
            return
        if on:
            self._normalGeom = self.geometry()
            self.menuBar().setVisible(False)
            self.showFullScreen()
        else:
            self.showNormal()
            self.menuBar().setVisible(True)
            geom = getattr(self, '_normalGeom', None)
            if geom is not None:
                self.setGeometry(geom)
        self._isFullScreen = bool(on)
        if hasattr(self, 'actFullScreen'):
            self.actFullScreen.setChecked(bool(on))
        # 地图与频谱需要重新布局
        self._applyResponsive(force=True)
        QTimer.singleShot(60, self._afterFullScreen)

    def _afterFullScreen(self):
        """尺寸变化后让地图重算视口（Leaflet 必须收到 resize，否则瓦片错位）。"""
        try:
            if hasattr(self, 'mapPanel'):
                self.mapPanel.host.resize()
        except Exception:
            pass

    def _onMapConsoleLine(self, message: str):
        """地图页面的 JS 控制台 → 日志（JS 报错不再无声无息）。"""
        text = str(message or '').strip()
        if text:
            self.logPanel.appendLog(text)

    # ---- 自适应布局（v2.2） ----
    def _applyResponsive(self, force: bool = False):
        """按窗口尺寸自动排三段比例与最小宽度，不需要用户手拖。

        只在“尺寸档位”变化时重算（比如 1440→1024、全屏切换），
        同一档位内用户拖动分隔条的结果不会被覆盖。
        """
        if not hasattr(self, 'mainSplit'):
            return
        # 用真实窗口尺寸。旧版 max(640/480) 会在窗口被拖小（或高 DPI 屏
        # 逻辑区本来就小）时按 640 宽去分配左右列，把子控件顶出父窗口。
        w = max(320, self.width())
        h = max(240, self.height())
        key = (w // 160, h // 120)
        if not force and key == getattr(self, '_respKey', None):
            return
        self._respKey = key

        chrome = spx(96)                       # 工具栏 + 状态栏
        avail = max(spx(300), h - chrome)
        # ③ 底栏：只有一行文字，不需要卡片标题，压到 34~46 px
        outH = int(min(max(avail * 0.045, spx(34)), spx(46)))
        rest = max(spx(240), avail - outH)
        # ② 中段（频谱 | 车次 | 机车）：能看清就行，约 24%，夹在 96~180
        band2H = int(min(max(rest * 0.24, spx(96)), spx(180)))
        # ① 上段（地图 + 解码）吃掉剩下的——这一块才是主战场
        band1H = max(spx(180), rest - band2H)
        # 极小逻辑窗（如 200% 缩放下的 400×400 逻辑屏）：中段三张卡片
        # 已经装不下内容，直接收起，把全部高度让给地图与解码——
        # 这也符合「上段优先」的设计。
        ultraTiny = (w < spx(620) or h < spx(500))
        if ultraTiny:
            outH = min(outH, spx(28))
            band2H = 0
            band1H = max(spx(120), avail - outH)
        self.mainSplit.setSizes([band1H, band2H, outH])
        if hasattr(self, 'band2'):
            self.band2.setVisible(not ultraTiny)

        # 所有下限都要跟着当前窗口/所在屏收紧，否则高 DPI 小逻辑屏会被
        # 一堆「最小宽/高」联手顶出屏幕（v2.5 修）。
        mapMinW = min(spx(240) if w < spx(1100) else spx(320),
                      max(spx(140), int(w * 0.42)))
        cardMinH = min(spx(104), max(spx(52), int(h * 0.18)))
        maxCardW = max(spx(110), int(w / 3.6))
        # 极小逻辑窗口（如 200% 缩放下的 400×400 逻辑屏）：再压一档下限，
        # 否则一堆「最小宽/高」联手把子控件顶出父窗口。
        if w < spx(700) or h < spx(520):
            mapMinW = min(mapMinW, max(spx(100), int(w * 0.35)))
            cardMinH = min(cardMinH, max(spx(28), int(h * 0.10)))
            maxCardW = max(spx(80), int(w / 4.2))

        # ① 左右比例：地图约 62%
        if hasattr(self, 'band1'):
            self.band1.setSizes([int(w * 0.62), w - int(w * 0.62)])
        if hasattr(self, 'mapPanel'):
            self.mapPanel.setMinimumWidth(mapMinW)

        # ② 三块比例：频谱 5 : 车次 3 : 机车 3
        if hasattr(self, 'band2'):
            unit = w / 11.0
            self.band2.setSizes([int(unit * 5), int(unit * 3), int(unit * 3)])
            for card in (getattr(self, 'specCard', None),
                         getattr(self, 'queryCard', None),
                         getattr(self, 'locoCard', None)):
                if card is not None:
                    card.setMinimumHeight(cardMinH)

        # 窄窗口收紧最小宽度，否则整窗被顶宽（出现横向滚动条）
        narrow = w < spx(1100)
        if hasattr(self, 'specCard'):
            self.specCard.setMinimumWidth(
                min(spx(200) if narrow else spx(300), maxCardW))
        for card in (getattr(self, 'queryCard', None), getattr(self, 'locoCard', None)):
            if card is not None:
                card.setMinimumWidth(
                    min(spx(168) if narrow else spx(210), maxCardW))

        # 地图重绘（尺寸变了，Leaflet 必须收到 resize）
        QTimer.singleShot(0, self._afterFullScreen)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._applyResponsive()

    def moveEvent(self, event):
        """窗口被拖到另一块屏时（screenChanged 有时滞后）兜底触发一次适配。"""
        super().moveEvent(event)
        if self._geomBusy:
            return
        try:
            s = self._currentScreen()
            if s is not None and s is not self._lastScreen:
                self._onScreenChanged(s)
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.toggleFullScreen()
            return
        if event.key() == Qt.Key_Escape and self._isFullScreen:
            self.toggleFullScreen(False)
            return
        super().keyPressEvent(event)

    def _buildMenu(self):
        """菜单栏即顶栏（v2.6）：菜单在左，接收开关与连接指示在右侧角标。

        旧版在菜单栏下面还有一整行「标题 + 接收开关 + 夜间 + 全屏」，字大、
        占一行高度，还和菜单功能重复——全屏本来就是 视图→全屏 (F11)，
        夜间切换是 视图→切换日间/夜间 (Ctrl+T)，标题则由操作系统标题栏显示。
        「文件」菜单里只剩启动/停止/退出三项，前两项归入接收开关，退出挪进
        帮助菜单底部，于是整个文件菜单撤掉，窗口省出一行。
        """
        menubar = self.menuBar()

        viewMenu = menubar.addMenu('视图(&V)')
        self.actReceive = QAction('开始接收', self, shortcut='Ctrl+R')
        self.actReceive.setCheckable(True)
        self.actReceive.setToolTip('启动 / 停止 DSP 接收；全屏时也可用 Ctrl+R')
        self.actReceive.triggered.connect(self._onRxSwitch)
        viewMenu.addAction(self.actReceive)
        viewMenu.addSeparator()

        self.actFullScreen = QAction('全屏', self, shortcut='F11')
        self.actFullScreen.setCheckable(True)
        self.actFullScreen.triggered.connect(
            lambda checked: self.toggleFullScreen(checked))
        viewMenu.addAction(self.actFullScreen)

        themeMenu = viewMenu.addMenu('外观主题')
        self._themeActs = {}
        for label, val in (('夜间（深色）', 'dark'), ('日间（浅色）', 'light'),
                           ('跟随系统', 'auto')):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(str(getattr(self.config, 'theme', 'dark')) == val)
            act.triggered.connect(lambda _c, v=val: self._setTheme(v))
            themeMenu.addAction(act)
            self._themeActs[val] = act
        viewMenu.addSeparator()

        actToggleTheme = QAction('切换日间 / 夜间', self, shortcut='Ctrl+T')
        actToggleTheme.triggered.connect(self._toggleTheme)
        viewMenu.addAction(actToggleTheme)
        viewMenu.addSeparator()

        self.actMapNight = QAction('地图夜间模式', self)
        self.actMapNight.setCheckable(True)
        self.actMapNight.setChecked(bool(getattr(self.config, 'mapNight', True)))
        self.actMapNight.toggled.connect(self._onMenuMapNight)
        viewMenu.addAction(self.actMapNight)

        # ---- v3.0：铁路图层开关 + 底图子菜单（与地图工具栏双向同步） ----
        self.actRail = QAction('铁路图层（OpenRailwayMap）', self)
        self.actRail.setCheckable(True)
        self.actRail.setChecked(
            config_ext.normalize_rail(config_ext.get(self.config, 'mapRail',
                                                     'orm_standard')) != 'off')
        self.actRail.setToolTip('叠加 OpenRailwayMap 铁路图层（WGS-84 栅格瓦片）')
        self.actRail.toggled.connect(self._onMenuRail)
        viewMenu.addAction(self.actRail)

        baseMenu = viewMenu.addMenu('底图')
        self._baseActs = {}
        try:
            from PySide6.QtGui import QActionGroup
            grp = QActionGroup(self)
            grp.setExclusive(True)
        except Exception:
            grp = None
        cur_base = config_ext.normalize_base(
            config_ext.get(self.config, 'mapBase', 'osm'))
        for _lid, _name in config_ext.BASE_LAYERS:
            _act = QAction(_name, self)
            _act.setCheckable(True)
            _act.setChecked(_lid == cur_base)
            if grp is not None:
                grp.addAction(_act)
            _act.triggered.connect(lambda _c=False, lid=_lid: self._onMenuBase(lid))
            baseMenu.addAction(_act)
            self._baseActs[_lid] = _act

        actToggleMap = QAction('显示/隐藏地图', self)
        actToggleMap.triggered.connect(self._toggleMapVisible)
        viewMenu.addAction(actToggleMap)
        viewMenu.addSeparator()

        scaleMenu = viewMenu.addMenu('界面缩放')
        self._scaleActions = []
        for val in (0.85, 1.0, 1.15, 1.3, 1.5):
            act = QAction(f'{int(val * 100)}%', self)
            act.setCheckable(True)
            act.setChecked(abs(float(getattr(self.config, 'uiScale', 1.0)) - val) < 0.01)
            act.triggered.connect(lambda _c, v=val: self._setUiScale(v))
            scaleMenu.addAction(act)
            self._scaleActions.append((val, act))

        # 配置菜单：直接列出各分项，点哪项就开哪一页，不再用页签让人翻
        configMenu = menubar.addMenu('配置(&C)')
        for _i, _name in enumerate(CONFIG_PAGES):
            _act = QAction(_name + '...', self)
            if _i == 0:
                _act.setShortcut('Ctrl+,')
            _act.triggered.connect(lambda _c=False, n=_name: self._openConfig(n))
            configMenu.addAction(_act)

        # 工具菜单（v3.0）：车次查询 / 机车配属查询 / 第三方数据更新
        toolsMenu = menubar.addMenu('工具(&T)')
        self.actTrainQuery = QAction('车次查询...', self, shortcut='Ctrl+F')
        self.actTrainQuery.setToolTip('按车次号查等级、担当局、配属段与时刻表 (Ctrl+F)')
        self.actTrainQuery.triggered.connect(lambda: self.openQueryDialog('train'))
        toolsMenu.addAction(self.actTrainQuery)

        self.actLocoQuery = QAction('机车配属查询...', self, shortcut='Ctrl+G')
        self.actLocoQuery.setToolTip('按型号 + 机车号查配属局段与车型参数 (Ctrl+G)')
        self.actLocoQuery.triggered.connect(lambda: self.openQueryDialog('loco'))
        toolsMenu.addAction(self.actLocoQuery)
        toolsMenu.addSeparator()

        # v3.2.1：历史记录不再占主界面页签，改到这里按需打开对话框
        self.actHistory = QAction('历史记录...', self, shortcut='Ctrl+H')
        self.actHistory.setToolTip('查看 / 删除历史解码记录，可看单条详情 (Ctrl+H)')
        self.actHistory.triggered.connect(self.openHistoryDialog)
        toolsMenu.addAction(self.actHistory)
        toolsMenu.addSeparator()

        self.actDataUpdate = QAction('检查数据更新（机车配属表）', self)
        self.actDataUpdate.setToolTip('从上游拉取配属号段表增量（校验通过才替换）')
        self.actDataUpdate.triggered.connect(lambda: self.checkDataUpdate(True))
        toolsMenu.addAction(self.actDataUpdate)

        helpMenu = menubar.addMenu('帮助(&H)')
        actManual = QAction('使用手册', self)
        actManual.triggered.connect(lambda: ManualDialog(self).exec())
        helpMenu.addAction(actManual)
        actDash = QAction('运行状态仪表板', self, shortcut='Ctrl+D')
        actDash.triggered.connect(self.openDashboard)
        helpMenu.addAction(actDash)
        actLog = QAction('实时日志', self, shortcut='Ctrl+L')
        actLog.triggered.connect(self.openLogWindow)
        helpMenu.addAction(actLog)
        helpMenu.addSeparator()
        actAbout = QAction('关于', self)
        actAbout.triggered.connect(lambda: AboutDialog(self).exec())
        helpMenu.addAction(actAbout)
        helpMenu.addSeparator()
        actQuit = QAction('退出', self, shortcut='Ctrl+Q')
        actQuit.triggered.connect(self.close)
        helpMenu.addAction(actQuit)

        # ---- 菜单栏右侧角标：连接指示 + 接收开关 ----
        # 接收是最高频操作，不能藏进下拉菜单，放在菜单栏行尾一眼可见；
        # 全屏隐藏菜单栏时仍可用 Ctrl+R 或 Esc 退出全屏后再操作。
        corner = QWidget()
        lay = QHBoxLayout(corner)
        lay.setContentsMargins(spx(4), 0, spx(10), 0)
        lay.setSpacing(spx(10))
        self.connIndicator = QLabel('● 未连接')
        self.connIndicator.setStyleSheet(self._connStyle('err'))
        lay.addWidget(self.connIndicator)
        self.rxSwitch = K.switch('接收', on_text='接收中')
        self.rxSwitch.setToolTip('启动 / 停止 DSP 接收 (Ctrl+R)')
        self.rxSwitch.checkedChanged.connect(self._onRxSwitch)
        lay.addWidget(self.rxSwitch)
        # Qt 文档：corner widget 的生存期由调用方负责，Qt 不会替你删；
        # Python 侧必须长期持有引用，否则对象被 GC，角标整块消失。
        self._menuCorner = corner
        menubar.setCornerWidget(corner, Qt.TopRightCorner)

    @staticmethod
    def _connStyle(color_key: str) -> str:
        """连接指示的统一内联样式（跟随主题色与界面倍率）。"""
        return (f'background: transparent; color: {CLR(color_key)};'
                f' font-size: {spx(12)}px; font-weight: bold;')

    def _setConnIndicator(self, connected: bool):
        """更新菜单栏右侧的连接指示（文本、颜色、提示一次到位）。"""
        ind = getattr(self, 'connIndicator', None)
        if ind is None:
            return
        ind.setText('● 已连接' if connected else '● 未连接')
        ind.setStyleSheet(self._connStyle('ok' if connected else 'err'))
        ind.setToolTip('数据源已连接' if connected else '数据源未连接')

    def _setUiScale(self, value: float):
        self.config.uiScale = float(value)
        self.config.save(CONFIG_PATH)
        for val, act in getattr(self, '_scaleActions', []):
            act.setChecked(abs(val - value) < 0.01)
        QMessageBox.information(
            self, '界面缩放',
            f'界面缩放已设为 {int(value * 100)}%。\n\n'
            '该设置需要重启程序后生效。')

    def _onMenuMapNight(self, checked: bool):
        if hasattr(self, 'mapPanel'):
            self.mapPanel.setNightMode(checked)
        self.config.mapNight = bool(checked)

    # ---- v3.0：地图图层（菜单 ↔ 工具栏 ↔ 页面内下拉 三方同步） ----
    def _onMenuRail(self, checked: bool):
        if hasattr(self, 'mapPanel'):
            self.mapPanel.setRailVisible(bool(checked))
        self._syncMapLayerMenu()

    def _onMenuBase(self, layer_id: str):
        if not hasattr(self, 'mapPanel'):
            return
        if layer_id in config_ext.TDT_LAYERS and not str(
                config_ext.get(self.config, 'tdtKey', '') or '').strip():
            self.logPanel.appendLog(
                '[地图] 天地图需要「浏览器端」tk：请到 配置 → 地图与车次 填写后再选。')
            self._syncMapLayerMenu()
            return
        self.mapPanel.setBase(layer_id)
        self._syncMapLayerMenu()

    def _syncMapLayerMenu(self):
        """把当前的底图/铁路图层状态同步到「视图」菜单的勾选状态。"""
        base = config_ext.normalize_base(
            config_ext.get(self.config, 'mapBase', 'osm'))
        rail = config_ext.normalize_rail(
            config_ext.get(self.config, 'mapRail', 'orm_standard'))
        for lid, act in getattr(self, '_baseActs', {}).items():
            act.blockSignals(True)
            act.setChecked(lid == base)
            act.blockSignals(False)
        act = getattr(self, 'actRail', None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(rail != 'off')
            act.blockSignals(False)

    def _onMapLayersChanged(self, info: dict):
        """地图面板那边（含页面内下拉）改了图层 → 回写配置并刷菜单。"""
        if not isinstance(info, dict):
            return
        base = info.get('base')
        rail = info.get('rail')
        if base:
            self.config.mapBase = str(base)
        if rail:
            self.config.mapRail = str(rail)
        self._syncMapLayerMenu()

    # ---- v3.0：车次 / 配属查询与第三方数据更新 ----
    def openQueryDialog(self, tab: str = 'train', train: str = '', loco: str = ''):
        """打开查询对话框（两个页签，可预填车次/机车并自动查询）。"""
        dlg = QueryDialog(self.config, self, tab=tab, train=train, loco=loco)
        self._queryWindow = dlg
        dlg.setModal(False)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    # ---- v3.2.1：历史记录对话框（工具菜单） ----
    def openHistoryDialog(self):
        """打开历史记录对话框：列表 / 详情 / 删除选中 / 删除全部 / 导出。

        历史数据层仍用 `cr_lbj.data.history.HistoryDb`；对话框关闭后主窗口
        无需刷新（主界面已不再常驻历史表，仪表板的计数实时读库）。
        """
        dlg = HistoryDialog(self)
        dlg.exec()

    def _openQueryForRecord(self, record: Optional[dict], tab: str = 'train'):
        """从表格右键菜单查车次/配属。"""
        record = record or {}
        train = str(record.get('train') or '').strip()
        if tab == 'train':
            if not train or train in ('----', '未知'):
                self.logPanel.appendLog('[查询] 该行没有车次号，无法查车次')
                return
            self.openQueryDialog('train', train=train)
        else:
            loco = str(record.get('loco') or '').strip()
            if not loco or loco in ('----', '未知'):
                self.logPanel.appendLog('[查询] 该行没有机车号，无法查配属')
                return
            self.openQueryDialog('loco', loco=loco)

    def checkDataUpdate(self, force: bool = True):
        """检查配属号段表更新（后台线程；失败只记日志，界面不崩）。"""
        if self._dataThread is not None and self._dataThread.isRunning():
            self.logPanel.appendLog('[数据] 上一次检查还没结束，稍候…')
            return
        self.logPanel.appendLog('[数据] 正在检查配属号段表更新…')
        self._dataThread = data_update.DataUpdateThread(
            force=bool(force),
            interval_days=data_update.interval_days(self.config),
            parent=None)     # 不挂 parent：线程自注册保活，关窗口也不会被析构
        self._dataThread.done.connect(
            lambda res: self._onDataUpdateDone(res, manual=bool(force)))
        self._dataThread.start()

    def _onDataUpdateDone(self, res: dict, manual: bool = True):
        text = data_update.result_text(res)
        ok = bool((res or {}).get('ok'))
        self.logPanel.appendLog('[数据] %s' % text)
        if (res or {}).get('updated'):
            # 数据换了，机车卡与查询缓存都要重算
            self.logPanel.appendLog('[数据] %s' % data_update.last_check_text())
            try:
                self.locoPanel.refreshRoster()
            except Exception:
                pass
        if not manual:
            return                       # 自动检查：静默，成功也只在日志里
        # 手动检查：非模态提示（不挡主界面，也不阻塞 DSP）
        try:
            self._showDataBox(ok, text)
        except Exception:
            pass

    def _showDataBox(self, ok: bool, text: str):
        box = QMessageBox(self)
        box.setWindowTitle('数据更新')
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        box.setText(text)
        box.setInformativeText(data_update.status_text_multiline())
        box.setStandardButtons(QMessageBox.Ok)
        box.setModal(False)
        self._dataBox = box                # 非模态也要保住引用，否则被 GC 掉
        box.show()

    def _autoCheckDataUpdate(self):
        """启动 20 秒后自动检查一次（配置关闭则不动，失败只记日志）。"""
        if not data_update.auto_enabled(self.config):
            self.logPanel.appendLog('[数据] 已关闭自动检查（配置 → 数据更新）')
            return
        self.checkDataUpdate(False)

    def _toggleMapVisible(self):
        if not hasattr(self, 'mapPanel'):
            return
        vis = not self.mapPanel.isVisible()
        self.mapPanel.setVisible(vis)
        if vis:
            self._afterFullScreen()

    def _buildUi(self):
        central = QWidget()
        central.setObjectName('centralPane')
        central.setAttribute(Qt.WA_StyledBackground, True)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(spx(4), spx(4), spx(4), spx(2))
        root.setSpacing(spx(4))

        # 顶栏即菜单栏（见 _buildMenu）：标题交给操作系统标题栏，
        # 接收开关/连接指示是菜单栏角标，日/夜与全屏并入视图菜单。
        # 这里不再单独排一行，窗口纵向省出约一行高度。

        # ---------------- 全景三段式（v2.3） ----------------
        #   ① 上段：地图（约六成） | 当前解码 + 列车信息
        #   ② 中段：接收频谱 | 车次信息 | 机车信息
        #   ③ 底栏：输出 1（日志尾部） | 输出 2（接收状态分块），各占一半
        #   所有内容一屏可见，互不遮挡；历史记录在「工具」菜单里按需打开。
        mainSplit = QSplitter(Qt.Vertical)
        mainSplit.setChildrenCollapsible(False)
        mainSplit.setHandleWidth(spx(8))

        # ---- ① 上段 ----
        band1 = QSplitter(Qt.Horizontal)
        band1.setChildrenCollapsible(False)
        band1.setHandleWidth(spx(8))

        self.mapPanel = MapPanel(self.config)
        self.mapPanel.setMinimumWidth(spx(320))
        self.mapPanel.followChanged.connect(self._onMapFollowChanged)
        self.mapPanel.layersChanged.connect(self._onMapLayersChanged)
        self.mapPanel.consoleMessage.connect(self._onMapConsoleLine)
        band1.addWidget(self.mapPanel)

        # v3.2：车次/机车信息查询服务（异步，结果同时进地图标记）
        self.infoService = TrainInfoService(self)
        self.infoService.infoReady.connect(self._onTrainInfoReady)

        # v3.2.1：主界面只留「当前解码」；历史记录改到「工具 → 历史记录…」，
        # 这里只保留数据库句柄用于写入（界面不再常驻历史表）。
        self.historyDb = HistoryDb(DB_PATH)

        self.currentPanel = CurrentPanel()
        self.trainPanel = TrainInfoPanel()
        self.trainQueryPanel = TrainQueryPanel()
        self.locoPanel = LocoInfoPanel()
        self.trainQueryPanel.doubleClicked.connect(self._openTimetable)
        self.locoPanel.detailRequested.connect(self._openLocoDetail)

        rightCol = QSplitter(Qt.Vertical)
        rightCol.setChildrenCollapsible(False)
        rightCol.setHandleWidth(spx(8))
        self.decodeCard = CardBox('当前解码', self.currentPanel)
        self.trainCard = CardBox('列车信息', self.trainPanel)
        rightCol.addWidget(self.decodeCard)
        rightCol.addWidget(self.trainCard)
        rightCol.setStretchFactor(0, 4)
        rightCol.setStretchFactor(1, 5)
        rightCol.setSizes([spx(280), spx(300)])

        band1.addWidget(rightCol)
        band1.setStretchFactor(0, 3)
        band1.setStretchFactor(1, 2)
        band1.setSizes([spx(760), spx(520)])
        self.band1 = band1
        self.rightCol = rightCol
        mainSplit.addWidget(band1)

        # ---- ② 中段：频谱 | 车次 | 机车 ----
        band2 = QSplitter(Qt.Horizontal)
        band2.setChildrenCollapsible(False)
        band2.setHandleWidth(spx(8))

        self.spectrumPanel = SpectrumPanel()
        self.terminalSpectrumPanel = TerminalSpectrumPanel()
        self.spectrumStack = QStackedWidget()
        self.spectrumStack.addWidget(self.spectrumPanel)           # 0: 图形
        self.spectrumStack.addWidget(self.terminalSpectrumPanel)   # 1: 终端

        # 频谱切换跟着频谱走：放进频谱卡片标题栏右侧，不再占工具栏
        self.spectrumModeCombo = QComboBox()
        self.spectrumModeCombo.addItem('图形')
        self.spectrumModeCombo.addItem('终端')
        self.spectrumModeCombo.setToolTip('图形频谱 / 终端频谱（省资源）')
        self.spectrumModeCombo.setMinimumWidth(spx(72))
        self.spectrumModeCombo.currentIndexChanged.connect(self._onSpectrumModeChanged)

        self.specCard = CardBox('接收频谱', self.spectrumStack,
                                right=self.spectrumModeCombo)
        self.queryCard = CardBox('车次信息', self.trainQueryPanel)
        self.locoCard = CardBox('机车信息', self.locoPanel)
        band2.addWidget(self.specCard)
        band2.addWidget(self.queryCard)
        band2.addWidget(self.locoCard)
        band2.setStretchFactor(0, 5)
        band2.setStretchFactor(1, 3)
        band2.setStretchFactor(2, 3)
        band2.setSizes([spx(560), spx(320), spx(320)])
        self.band2 = band2
        mainSplit.addWidget(band2)

        # ---- ③ 底栏：只有一行——左边最新一条日志，右边一句话状态 ----
        #   v2.5：取消「输出 1 / 输出 2」两张卡片和它们的标题，
        #   左边日志、右边状态提示直接并进同一条细底栏，省下的高度全给上段。
        self.logTail = LogTail()
        self.statusStrip = RxStatusStrip()
        self.statusStrip.clicked.connect(self.openDashboard)
        self.statusStrip.setToolTip('点击打开运行状态仪表板 (Ctrl+D)')

        self.barSep = QFrame()
        self.barSep.setFrameShape(QFrame.VLine)
        self.barSep.setFixedWidth(1)
        self.barSep.setStyleSheet(f'background-color: {CLR("border")}; border: none;')

        bottomBar = QWidget()
        bottomBar.setObjectName('bottomBar')
        bottomBar.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(bottomBar)
        bl.setContentsMargins(spx(10), spx(2), spx(10), spx(2))
        bl.setSpacing(spx(10))
        bl.addWidget(self.logTail, 1)
        bl.addWidget(self.barSep, 0)
        bl.addWidget(self.statusStrip, 1)
        self.bottomBar = bottomBar
        mainSplit.addWidget(bottomBar)

        self.mainSplit = mainSplit
        mainSplit.setStretchFactor(0, 7)
        mainSplit.setStretchFactor(1, 4)
        mainSplit.setStretchFactor(2, 0)
        root.addWidget(mainSplit, 1)
        self.logBus.lineAdded.connect(self._onLogLine)

        # 状态栏：底栏已经承担了状态显示，这里彻底不显示——
        # 留一条空的状态栏只会多出那条“黑条”（重绘跟不上时是纯黑）
        self.statusBar().hide()
        self._applyTouchTweaks()
        self._syncRxSwitch(False)
        self._installQueryMenus()
        # 首次布局完成后按实际窗口尺寸定一次比例
        QTimer.singleShot(0, lambda: self._applyResponsive(force=True))
        # v3.0：启动 20 秒后在后台检查一次第三方数据（失败静默，只进日志）
        QTimer.singleShot(20000, self._autoCheckDataUpdate)

    # ---- v3.0：表格右键菜单（查车次 / 查配属） ----
    def _installQueryMenus(self):
        """给「当前解码」表挂右键菜单。

        双击行已经是「记录详情」，不再抢它；查询走右键，两条路互不影响。
        历史记录表的快捷入口在「工具 → 历史记录…」对话框里（双击即详情）。
        """
        try:
            table = getattr(getattr(self, 'currentPanel', None), 'table', None)
            if table is not None:
                table.setContextMenuPolicy(Qt.CustomContextMenu)
                table.customContextMenuRequested.connect(
                    lambda pos, t=table: self._showRecordMenu(
                        t, self.currentPanel, pos))
        except Exception:
            pass

    def _recordAtRow(self, panel, row: int) -> Optional[dict]:
        """「当前解码」表格行 → 记录字典。"""
        if row < 0 or panel is None:
            return None
        try:
            # CurrentPanel.records 是正序 [(ts, d)]，表格倒序显示
            records = list(getattr(panel, 'records', []) or [])
            idx = len(records) - 1 - row
            return records[idx][1] if 0 <= idx < len(records) else None
        except Exception:
            return None

    def _showRecordMenu(self, table, panel, pos):
        try:
            idx = table.indexAt(pos)
            row = idx.row()
        except Exception:
            row = -1
        record = self._recordAtRow(panel, row)
        menu = QMenu(self)
        actDetail = menu.addAction('记录详情…')
        menu.addSeparator()
        actTrain = menu.addAction('查该车次…')
        actLoco = menu.addAction('查该机车配属…')
        has_train = bool(record and str(record.get('train') or '') not in
                         ('', '----', '未知'))
        has_loco = bool(record and str(record.get('loco') or '') not in
                        ('', '----', '未知'))
        actTrain.setEnabled(bool(has_train))
        actLoco.setEnabled(bool(has_loco))
        actDetail.setEnabled(bool(record))
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is actDetail and record:
            RecordDetailDialog(record, self).exec()
        elif chosen is actTrain:
            self._openQueryForRecord(record, 'train')
        elif chosen is actLoco:
            self._openQueryForRecord(record, 'loco')

    # ---- 触屏 / 高 DPI 细节 ----
    def _applyTouchTweaks(self):
        """加大表格行高与滚动条，并给滚动区域启用触摸惯性滚动。"""
        try:
            from PySide6.QtWidgets import QScroller
            for tb in self.findChildren(QTableWidget):
                tb.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
                tb.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
                tb.verticalHeader().setDefaultSectionSize(spx(26))
                tb.verticalHeader().setMinimumSectionSize(spx(22))
                tb.setWordWrap(False)
                QScroller.grabGesture(tb.viewport(),
                                      QScroller.ScrollerGestureType.TouchGesture)
            for sp in self.findChildren(QSplitter):
                sp.setHandleWidth(spx(7))
            for sa in self.findChildren(QScrollArea):
                QScroller.grabGesture(sa.viewport(),
                                      QScroller.ScrollerGestureType.TouchGesture)
        except Exception:
            pass

    # ---- 日志 ----
    def _onLogLine(self, line: str, level: str):
        """输出 1：把日志追加到尾部窗口（最新的在最下面）。"""
        try:
            self.logTail.appendLine(line, level)
        except Exception:
            pass

    def openLogWindow(self):
        """打开实时日志窗口（复用同一个实例）。"""
        if self._logWindow is None:
            self._logWindow = LogWindow(self.logBus, self)
        self._logWindow.show()
        self._logWindow.raise_()
        self._logWindow.activateWindow()

    # ---- 外观主题（即时生效） ----
    def _toggleTheme(self):
        """工具栏上的日/夜开关：在 dark 与 light 之间即时切换。"""
        cur = TH.P.get('mode', 'dark')
        self._setTheme('light' if cur == 'dark' else 'dark')

    def _remapOldColors(self, oldMode: str, newMode: str) -> Dict[str, str]:
        """旧调色板颜色 → 新调色板颜色 的映射表。

        界面里大量控件的颜色是建 UI 时用 `setStyleSheet(f'color: {CLR("x")}')`
        写死成十六进制串的，光换全局 QSS 只能改到“没单独写样式”的那部分。
        这里把两套调色板同名字段的颜色配成一张表，再对每个控件的样式串做
        一次正则替换（单次扫描，避免 A→B、B→C 连环替换）。
        """
        old = TH.PALETTES.get(oldMode) or {}
        new = TH.PALETTES.get(newMode) or {}
        m: Dict[str, str] = {}
        for k, v in old.items():
            if isinstance(v, str) and v.startswith('#') and isinstance(new.get(k), str):
                m[v.lower()] = new[k]
        # 跨调色板同名但值不同的固定色（CR 红蓝在两套里同名同值，不用管）
        m.setdefault('#ffffff', new.get('sel_text', '#ffffff')
                    if newMode == 'light' else '#ffffff')
        return m

    def _restyleWidgets(self, mapping: Dict[str, str]) -> None:
        """把映射表套到所有控件的内联样式上（含独立对话框、菜单）。"""
        if not mapping:
            return
        pairs = {k: v for k, v in mapping.items() if k != v.lower()}
        if not pairs:
            return
        pat = re.compile('|'.join(re.escape(k) for k in pairs), re.I)

        def _sub(mo):
            return pairs.get(mo.group(0).lower(), mo.group(0))

        for w in QApplication.allWidgets():
            try:
                ss = w.styleSheet()
                if not ss or '#' not in ss:
                    continue
                new = pat.sub(_sub, ss)
                if new != ss:
                    w.setStyleSheet(new)
            except Exception:
                continue

    def _applyThemeLive(self, mode: str) -> str:
        """真正把主题应用到当前界面（不重启）。返回实际生效的 dark/light。"""
        oldMode = TH.P.get('mode', 'dark')
        resolved = TH.applyMode(mode)
        mapping = self._remapOldColors(oldMode, resolved)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(TH.styleSheet())      # 全局 QSS 先换
        K.applyTheme(resolved)                      # Fluent 组件换深浅色
        self._restyleWidgets(mapping)               # 内联颜色跟一遍
        # 表格底色要在换色**之后**再刷：表格的调色板/样式是我们按主题色生成的，
        # 先刷会被上面的“旧色→新色”批量替换改坏（白底被替换成深色文字色）。
        K.refreshTablePalettes()
        # 地图底图跟界面一起深浅色（日间界面配深色底图太割裂）——要在重建页面之前设
        self._syncMapNight(resolved)

        # pyqtgraph：背景、坐标轴、字体颜色
        applyPgTheme()
        for panel in (getattr(self, 'spectrumPanel', None),
                      getattr(self, 'terminalSpectrumPanel', None)):
            try:
                panel.applyTheme()
            except Exception:
                pass
        # 地图：页面里的配色是注入到 HTML 里的，只能重建一次视图
        try:
            self.mapPanel.applyTheme()
        except Exception:
            pass
        # 输出区文字是运行时拼的 HTML，重新渲染一遍
        try:
            self.logTail.relayout()
        except Exception:
            pass
        return resolved

    def _syncMapNight(self, resolved: str = ''):
        """让地图底图与界面深浅色保持一致（界面日间 → 地图日间）。

        地图上的「夜间/日间」按钮仍可临时覆盖，下一轮换肤会再同步回来。
        """
        resolved = resolved or TH.P.get('mode', 'dark')
        night = (resolved == 'dark')
        self.config.mapNight = night
        act = getattr(self, 'actMapNight', None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(night)
            act.blockSignals(False)
        try:
            self.mapPanel.setNightMode(night)
        except Exception:
            pass

    def _setTheme(self, mode: str):
        """切换外观主题：立即生效，不再要求重启。"""
        mode = str(mode or 'dark')
        self.config.theme = mode
        try:
            self.config.save(CONFIG_PATH)
        except Exception:
            pass
        resolved = self._applyThemeLive(mode)
        for k, act in getattr(self, '_themeActs', {}).items():
            act.setChecked(k == mode)
        if hasattr(self, 'statusBar'):
            self.statusBar().showMessage(
                '主题已切换到 %s' % ('日间' if resolved == 'light' else '夜间'), 4000)
        try:
            self.logPanel.appendLog(
                '[主题] 已切换到%s（即时生效）'
                % ('日间' if resolved == 'light' else '夜间'))
        except Exception:
            pass

    def _openLocoDetail(self, d: dict):
        """「机车信息」卡片的按钮：打开配属查询对话框并预填当前机车。

        v3.0 起这里不再是只读的机车参数窗口——用户更常问的是「这车配属哪个
        机务段」，所以直接进「机车配属查询」页，参数卡也在同一页里。
        """
        if not d:
            self.openQueryDialog('loco')
            return
        loco_number = str(d.get('loco', '') or '')
        loco_code = str(d.get('locoCode', d.get('loco_code', '')) or '')
        text = loco_number.strip()
        if not text or text in ('----', '未知'):
            # 只有机车代号（如 240）时先用代号换型号名，再预填
            name = ''
            try:
                from cr_lbj.data import loco_roster
                name = loco_roster.type_name(loco_code)
            except Exception:
                name = ''
            text = name
        self.openQueryDialog('loco', loco=text)


    # ---- DSP 控制 ----
    def _onRxSwitch(self, on: bool):
        """工具栏接收开关：开=启动 DSP，关=停止。"""
        if on:
            self.startDsp()
        else:
            self.stopDsp()

    def _syncRxSwitch(self, on: bool):
        """把开关与菜单项状态同步成实际运行状态（不触发 start/stop）。"""
        sw = getattr(self, 'rxSwitch', None)
        if sw is not None:
            try:
                sw.blockSignals(True)
                sw.setChecked(bool(on))
                sw.blockSignals(False)
            except Exception:
                pass
        act = getattr(self, 'actReceive', None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(bool(on))
            act.setText('停止接收' if on else '开始接收')
            act.blockSignals(False)

    def startDsp(self):
        if self.worker and self.worker.isRunning():
            self._syncRxSwitch(True)
            return
        self.spectrumPanel.setSampleRate(self.config.sampleRate)
        self.terminalSpectrumPanel.setSampleRate(self.config.sampleRate)
        self.worker = DspBridge(self.config)
        self.worker.statusUpdated.connect(self._onStatus)
        self.worker.spectrumUpdated.connect(self._onSpectrum)
        self.worker.trainDecoded.connect(self._onDecode)
        self.worker.logMessage.connect(self.logPanel.appendLog)
        self.worker.connectionChanged.connect(self._onConnection)
        self.worker.diagnosticsUpdated.connect(self._onDiagnostics)
        self.worker.interferenceAlert.connect(self._onInterference)
        self.worker.start()
        self._syncRxSwitch(True)
        self.statusBar().showMessage('DSP 运行中')

    def stopDsp(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.worker = None
        self._syncRxSwitch(False)
        self._onConnection(False)  # 立即更新 UI 为断开状态
        self.statusBar().showMessage('已停止')

    def _onConfigChanged(self, new: CoreConfig):
        """配置变更：区分热更新与重启。"""
        old = self.config
        config_ext.ensure(new)           # v3.0 字段（底图/铁路/车次源/数据更新）
        # 保留频谱显示模式偏好 (配置对话框不包含此字段)
        new.spectrumMode = old.spectrumMode
        restartFields = ['host', 'port', 'sampleRate', 'freqMhz', 'gainDb', 'ppm',
                         'bwKhz', 'blockSize', 'dcOffsetHz', 'owrxMode',
                         'sourceType', 'rtlTcpPath', 'rtlDeviceIndex',
                         'afcEnable', 'afcMaxHz', 'afcGain', 'etaMaxMin']
        needRestart = any(getattr(old, f) != getattr(new, f) for f in restartFields)
        try:
            self.mapPanel.setConfig(new)
            self._syncMapLayerMenu()
        except Exception:
            pass
        if needRestart:
            self.stopDsp()
            self.config = new
            self.startDsp()
        else:
            if self.worker and self.worker.core:
                self.worker.core.applyHotConfig(new)
                self.config = new
            self.logPanel.appendLog('[配置] 已热更新')

    def _onMapFollowChanged(self, on: bool):
        """地图「跟随」被切换（含手动拖图导致自动取消）→ 立即存盘。"""
        self.config.mapFollow = bool(on)
        try:
            self.config.save(CONFIG_PATH)
        except Exception:
            pass
        if not on:
            try:
                self.logPanel.appendLog('[地图] 检测到手动拖动地图，已暂停自动跟随'
                                        '（点「跟随」可恢复）')
            except Exception:
                pass

    def _openConfig(self, page: str = None):
        """打开配置对话框（只显示 `page` 这一页，None 则取第一页）。"""
        dlg = ConfigDialog(self.config, self, page)
        if dlg.exec() == QDialog.Accepted:
            new = dlg.getConfig()
            if new is not None:
                if new.save(CONFIG_PATH):
                    self._onConfigChanged(new)
                    self.logPanel.appendLog('[配置] 已保存到文件')
                else:
                    self.logPanel.appendLog('[配置错误] 保存失败')

    # ---- 信号槽 ----
    def _onStatus(self, st: dict):
        self.statusStrip.updateStatus(st)
        # 频率是写死的常量（821.2375 MHz），工具栏不再显示，避免占地方也避免误以为可调
        # 更新频谱上的 RSSI 阈值线
        rssiThresh = st.get('rssiThreshold', DEFAULT_RSSI_THRESHOLD_DB)
        if rssiThresh != self.spectrumPanel._rssiThresholdDb:
            self.spectrumPanel.setRssiThreshold(rssiThresh)
        # 更新终端频谱面板状态 (添加 gain/ppm 从 config)
        if self.spectrumStack.currentIndex() == 1:
            st_term = dict(st)
            st_term['gainDb'] = self.config.gainDb
            st_term['ppm'] = self.config.ppm
            self.terminalSpectrumPanel.setRssiThreshold(rssiThresh)
            self.terminalSpectrumPanel.updateStatus(st_term)
        # 更新连接指示器
        self._setConnIndicator(bool(st.get('connected', False)))


    def _onSpectrum(self, data: np.ndarray):
        if self.spectrumStack.currentIndex() == 0:
            self.spectrumPanel.updateSpectrum(data)
        else:
            self.terminalSpectrumPanel.updateSpectrum(data)

    def _onSpectrumModeChanged(self, index: int):
        """切换频谱显示模式 (图形/终端)。"""
        self.spectrumStack.setCurrentIndex(index)
        self.config.spectrumMode = 'terminal' if index == 1 else 'graph'
        self.config.save(CONFIG_PATH)
        mode_name = '终端 (省资源)' if index == 1 else '图形'
        self.logPanel.appendLog(f'[频谱] 已切换到{mode_name}模式')

    def _onDecode(self, d: dict):
        self.trainPanel.updateDecode(d)
        self.currentPanel.addRecord(d)
        # v3.2：车次等级/担当局/配属段 + 机车配属/制造厂（机车本地查、车次异步查）
        info = self._decode_info(d)
        # 经纬度 -> 地图 (仅长报文包含)
        try:
            self.mapPanel.updateTrain(d, info)
        except Exception:
            pass
        # 车次信息走后台查询，回来后补进地图标记（车次卡自己也会异步查）
        try:
            train = str(d.get('train') or '')
            if d.get('isDetailed') and train and train != '----':
                self.infoService.lookup(train, self._trainPrefer())
        except Exception:
            pass
        # 无车次信息的报文: 不存入历史数据库
        isInvalid = (d.get('train', '----') in ('----', '', '未知')
                     and d.get('baseTrain', '----') in ('----', ''))
        if not isInvalid:
            try:
                self.historyDb.insert(d)
            except Exception:
                pass
        # 触发车次信息查询（RailGo 优先；「查看时刻表」沿用同一份结果）
        self.trainQueryPanel.onTrainDecoded(d, prefer=self._trainPrefer())
        # 机车信息卡片
        try:
            self.locoPanel.updateLoco(d)
        except Exception:
            pass

    def _trainPrefer(self) -> str:
        """车次查询数据源偏好（配置 → 地图与车次）。"""
        return str(getattr(self.config, 'trainQuerySource', 'auto') or 'auto')

    def _decode_info(self, d: dict) -> dict:
        """解码结果 → 地图/面板用的车次·机车信息（v3.2）。

        机车配属走本地号段表（同步、毫秒级）；车次信息优先取查询服务的缓存，
        没有则由 `_onDecode` 触发后台查询，回来后经 `_onTrainInfoReady` 补充。
        """
        try:
            loco = self.infoService.loco_info(
                d.get('loco'), d.get('locoCode') or d.get('loco_code'))
        except Exception:
            loco = {}
        try:
            train = self.infoService.cached(str(d.get('train') or ''))
        except Exception:
            train = {}
        return merge_info(loco, train)

    def _onTrainInfoReady(self, train: str, info: dict):
        """车次后台查询返回：补进地图标记（列车信息面板已不再重复展示）。"""
        try:
            self.mapPanel.setTrainInfo(train, info)
        except Exception:
            pass

    def _onInterference(self, direction: str, warnText: str):
        """干扰告警：只进日志，底栏状态条只加一个「干扰 N 次」计数。

        以前这里还往状态栏塞同一句话，于是底栏出现两行一模一样的告警（v2.2 修掉）。
        """
        self.logPanel.appendLog(f'[告警] {warnText}')
        try:
            self.statusStrip.noteInterference()
        except Exception:
            pass

    def _openTimetable(self):
        """打开 12306 时刻表对话框。"""
        self.trainQueryPanel._openTimetable()

    def _onConnection(self, connected: bool):
        self.statusBar().showMessage('已连接' if connected else '未连接')
        self._setConnIndicator(connected)

    def _onDiagnostics(self, diag: dict):
        """链路诊断信号回调。

        v2.2 起主界面不再有「系统状态」页签：诊断结果进日志与仪表板
        （Ctrl+D → 链路组），这里只做轻量提示，不参与布局刷新。
        """
        text = ''
        if isinstance(diag, dict):
            text = str(diag.get('diagnostics') or diag.get('message') or '')
        if text and text not in ('OK', '正常'):
            self.logPanel.appendLog(f'[诊断] {text}')

    # ---- 运行状态仪表板 ----
    def openDashboard(self):
        """打开运行状态仪表板（非模态，1 秒刷新）。"""
        if self._dashWindow is None:
            self._dashWindow = StatusDashboard(self, self)
        self._dashWindow.show()
        self._dashWindow.raise_()
        self._dashWindow.activateWindow()
        self._dashWindow.refresh()

    def _infoCols(self) -> str:
        """信息卡片字段网格的列数（全景布局下卡片一直可见，直接读即可）。"""
        grid = getattr(getattr(self, 'trainPanel', None), 'grid', None)
        if grid is None:
            return '-'
        return '%d 列' % grid._cols

    def statusGroups(self) -> List[tuple]:
        """汇总所有实时指标，返回 [(组名, [(项目, 值, 色调)])]。

        色调 '' 正常 / 'ok' 良好 / 'warn' 注意 / 'err' 异常 —— 仪表板据此上色，
        `statusReport()` 再从同一份数据拼成纯文本（复制全部用）。
        """
        cfg = self.config
        stats = {}
        if self.worker and hasattr(self.worker, '_lastStats'):
            stats = self.worker._lastStats or {}
        core = getattr(getattr(self, 'worker', None), 'core', None)
        try:
            st = core.getStatus() if core is not None else {}
        except Exception:
            st = {}
        uptime = int(stats.get('uptime', 0) or 0)
        h, rem = divmod(uptime, 3600)
        m, sec = divmod(rem, 60)
        dd = getattr(core, '_dedupe', None)
        slots = len(getattr(dd, '_slots', {}) or {}) if dd is not None else 0

        groups: List[tuple] = []

        def group(title):
            groups.append((title, []))

        def kv(k, v, tone=''):
            groups[-1][1].append((k, v, tone))

        conn = bool(st.get('connected'))
        rssi = float(st.get('rssi', -140.0) or -140.0)
        thresh = float(st.get('rssiThreshold', 0.0) or 0.0)
        score = float(st.get('afcScore', 0.0) or 0.0)
        ferr = float(st.get('afcErrHz', 0.0) or 0.0)
        diag = str(stats.get('diagnostics', 'OK'))

        group('链路')
        # USB 直连没有端点，只有网络源才显示 host:port
        srcLabel = str(st.get('sourceName') or getattr(cfg, 'sourceType', '-'))
        if getattr(cfg, 'sourceType', '') in ('rtl_tcp', 'owrx'):
            srcLabel += '  %s:%s' % (getattr(cfg, 'host', '-'), getattr(cfg, 'port', '-'))
        kv('数据源', srcLabel)
        kv('连接', '已连接' if conn else '未连接', 'ok' if conn else 'err')
        recon = int(stats.get('reconnectCount', 0) or 0)
        kv('重连次数', str(recon), 'warn' if recon else '')
        kv('接收字节', '%.1f MB' % (stats.get('bytesRecv', 0) / 1024 / 1024))
        kv('块率', '%.1f /s' % stats.get('blocksPerSec', 0.0))
        kv('数据速率', '%.2f Mbps' % stats.get('dataRateMbps', 0.0))
        kv('抖动 CV', '%.2f' % stats.get('jitterCv', 0.0))
        kv('运行时长', '%02d:%02d:%02d' % (h, m, sec))
        kv('诊断', diag, '' if diag in ('OK', '正常', '') else 'warn')

        group('射频与频谱')
        kv('中心频率', '%.4f MHz' % float(getattr(cfg, 'freqMhz', 0)))
        kv('采样率', '%d kS/s' % (int(getattr(cfg, 'sampleRate', 0)) // 1000))
        kv('块大小', str(getattr(cfg, 'blockSize', 0)))
        kv('硬件增益', '%.1f dB' % float(getattr(cfg, 'gainDb', 0)))
        kv('PPM', '%.1f' % float(getattr(cfg, 'ppm', 0)))
        kv('信道带宽', '%.1f kHz' % float(getattr(cfg, 'bwKhz', 0)))
        kv('DC 偏移', '%.0f Hz' % float(getattr(cfg, 'dcOffsetHz', 0)))
        kv('频谱模式', '图形' if getattr(cfg, 'spectrumMode', 'graph') == 'graph' else '终端')

        group('门控与 AFC')
        rTone = ''
        if conn:
            rTone = 'err' if rssi < -80 else ('warn' if rssi < -65 else (
                'ok' if rssi > thresh else ''))
        kv('信号强度', '%.1f dB' % rssi, rTone)
        kv('打开阈值', '%.1f dB' % thresh)
        kv('迟滞 / 保持', '%.1f dB / %.0f ms' % (float(getattr(cfg, 'rssiHystDb', 0)),
                                              float(getattr(cfg, 'rssiHoldMs', 0))))
        kv('RX 门控', str(st.get('rssiGate', 'OFF')),
           'ok' if str(st.get('rssiGate', 'OFF')) == 'ON' else '')
        kv('AFC 当前', '%+.0f Hz' % st.get('afcHz', 0.0))
        kv('频偏 FERR', '%+.0f Hz' % ferr, 'warn' if abs(ferr) > 200 else '')
        kv('AFC 置信度', '%.2f' % score,
           ('warn' if score < 0.10 else 'ok') if conn else '')
        kv('AFC 上限', '%.0f Hz' % float(getattr(cfg, 'afcMaxHz', 0)))
        kv('AFC 环路增益', '%.2f' % float(getattr(cfg, 'afcGain', 0)))
        kv('AFC 状态', '启用' if getattr(cfg, 'afcEnable', True) else '关闭')

        group('解码与去重')
        kv('合并窗口', '%.1f 秒（0=关闭）' % float(getattr(cfg, 'dedupeWindow', 0)))
        kv('合并丢弃', str(getattr(dd, 'dropped', 0) if dd is not None else 0))
        kv('择优升级', str(getattr(dd, 'upgraded', 0) if dd is not None else 0))
        kv('占用槽位', '%d / %d' % (slots, getattr(dd, 'maxSlots', 0) or 0))
        kv('当前列表', '%d 行' % self.currentPanel.table.rowCount())
        kv('历史记录', '%d 条' % self.historyDb.count())
        kv('地图列车', '%d 辆' % len(getattr(self.mapPanel, '_trains', {}) or {}),
           'ok' if getattr(self.mapPanel, '_trains', None) else '')

        group('地图与数据')
        mp = getattr(self, 'mapPanel', None)
        mp_st = dict(getattr(mp, '_status', {}) or {}) if mp is not None else {}
        kv('底图', config_ext.base_name(
            config_ext.normalize_base(config_ext.get(cfg, 'mapBase', 'amap'))))
        kv('铁路图层', config_ext.rail_name(
            config_ext.normalize_rail(config_ext.get(cfg, 'mapRail',
                                                     'orm_standard'))))
        ready = bool(mp is not None and getattr(mp, 'hasMap', False))
        kv('地图页面', '就绪' if ready else '降级 / 未加载', 'ok' if ready else 'warn')
        if ready:
            total = int(mp_st.get('tilesTotal') or 0)
            failed = int(mp_st.get('tilesFailed') or 0)
            kv('瓦片', '%d 张，失败 %d' % (total, failed),
               'warn' if failed else '')
            kv('坐标基准', 'WGS-84')
        try:
            dstat = data_update.status()
        except Exception:
            dstat = {}
        kv('配属号段表', '%d 行 / %d 型号' % (int(dstat.get('rows') or 0),
                                            int(dstat.get('models') or 0)))
        bundled = bool(dstat.get('isBundled', True))
        kv('数据版本', '内置快照' if bundled else '已更新（用户目录）',
           '' if bundled else 'ok')
        kv('上次数据更新', str(dstat.get('fetchedAt') or '—')[:16].replace('T', ' ')
           or '—')
        kv('自动检查', '开（%d 天）' % data_update.interval_days(self.config)
           if data_update.auto_enabled(self.config) else '关')

        group('界面')
        kv('版本', 'v3.2.1')
        kv('主题', {'dark': '夜间', 'light': '日间'}.get(
            TH.P.get('mode', 'dark'), '-') +
           '（%s）' % {'dark': '夜间', 'light': '日间', 'auto': '跟随系统'}.get(
               str(getattr(cfg, 'theme', 'dark')), '夜间'))
        kv('界面缩放', '%.0f%%' % (UI_SCALE * 100))
        kv('窗口尺寸', '%d × %d' % (self.width(), self.height()))
        if hasattr(self, 'band1'):
            kv('上段高度', '%d px' % self.band1.height())
        if hasattr(self, 'band2'):
            kv('中段高度', '%d px' % self.band2.height())
        if hasattr(self, 'bottomBar'):
            kv('输出区高度', '%d px' % self.bottomBar.height())
        kv('字段列数', self._infoCols())
        kv('地图', '显示' if getattr(self, 'mapPanel', None)
           and self.mapPanel.isVisible() else '隐藏')
        icount = getattr(getattr(self, 'statusStrip', None), '_interfCount', 0)
        kv('干扰计数', '%d 次 / 60 秒' % icount, 'warn' if icount else '')
        return groups

    def statusReport(self) -> str:
        """把 statusGroups() 拼成纯文本（仪表板「复制全部」用）。"""
        lines = []
        for title, rows in self.statusGroups():
            lines.append('')
            lines.append('【%s】' % title)
            for k, v, _tone in rows:
                lines.append('  %-12s %s' % (k, v))
        return '\n'.join(lines)

    # ---- 关闭事件 ----
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        # v3.0：短任务线程（12306 查询 / 数据更新检查）可能还在等网络超时。
        # 退出时若不收尾，Python 会先销毁 QThread 对象 → Qt qFatal 崩在退出路径上。
        try:
            from cr_lbj.ui.ui_threads import wait_all
            left = wait_all(1500)
            if left:
                self.logBus.appendLog('[退出] 仍有 %d 个后台请求未结束，已强制终止' % left)
        except Exception:
            pass
        # 保存配置
        self.config.save(CONFIG_PATH)
        event.accept()


# ===========================================================================
# 运行状态仪表板
# ===========================================================================
class StatusDashboard(QDialog):
    """运行状态仪表板：把分散在各处的实时指标集中展示。

    v2.3：从“一整块纯文本”改成**分组卡片 + 指标方块**——每组一张卡，
    每个指标一个方块，正常是灰白，良好标绿、注意标黄、异常标红，
    扫一眼就知道该看哪一项。数值仍是每秒刷新，随时可「复制全部」成文本。
    """

    TONE_COLOR = {'ok': 'ok', 'warn': 'warn', 'err': 'err'}

    def __init__(self, main, parent=None):
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.main = main
        self.setWindowTitle('运行状态仪表板 —— 全部实时指标')
        self.resize(spx(720), spx(660))
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(spx(8), spx(8), spx(8), spx(8))
        outer.setSpacing(spx(6))

        bar = QHBoxLayout()
        bar.setSpacing(spx(8))
        self.hint = QLabel('每 1 秒刷新 · Ctrl+D 开关本窗口')
        self.hint.setStyleSheet(f'color: {CLR("faint")}; font-size: {spx(11)}px;')
        self.autoRefresh = QCheckBox('自动刷新')
        self.autoRefresh.setChecked(True)
        refreshBtn = QPushButton('立即刷新')
        refreshBtn.clicked.connect(self.refresh)
        copyBtn = QPushButton('复制全部')
        copyBtn.clicked.connect(self._copy)
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.close)
        bar.addWidget(self.hint)
        bar.addStretch()
        bar.addWidget(self.autoRefresh)
        bar.addWidget(refreshBtn)
        bar.addWidget(copyBtn)
        bar.addWidget(closeBtn)
        outer.addLayout(bar)

        # 卡片区放进滚动区：小屏上也不挤压，纵向滚动即可
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.bodyLayout = QVBoxLayout(self.body)
        self.bodyLayout.setContentsMargins(0, 0, spx(4), 0)
        self.bodyLayout.setSpacing(spx(6))
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)

        #: (组, 项目) -> (值标签, 方块, 上次色调)
        self.tiles: Dict[tuple, tuple] = {}
        self._structure = None

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._onTick)
        self.timer.start()
        self.refresh()

    # ------------------------------------------------------------------
    def _onTick(self):
        if self.autoRefresh.isChecked() and self.isVisible():
            self.refresh()

    def _clearBody(self):
        while self.bodyLayout.count():
            item = self.bodyLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.tiles.clear()

    def _buildBody(self, groups):
        """按分组结构建卡片与方块（只在项目集合变化时重建一次）。"""
        self._clearBody()
        for title, rows in groups:
            card = QWidget()
            card.setObjectName('card')
            card.setAttribute(Qt.WA_StyledBackground, True)
            v = QVBoxLayout(card)
            v.setContentsMargins(spx(8), spx(5), spx(8), spx(7))
            v.setSpacing(spx(4))

            head = QLabel(title)
            head.setStyleSheet(
                f'color: {CLR("accent")}; font-size: {spx(12)}px; font-weight: bold;'
                ' background: transparent; border: none;')
            v.addWidget(head)

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(spx(6))
            grid.setVerticalSpacing(spx(5))
            cols = 4
            for i, (label, _val, _tone) in enumerate(rows):
                tile = QWidget()
                tile.setObjectName('chip')
                tile.setAttribute(Qt.WA_StyledBackground, True)
                tv = QVBoxLayout(tile)
                tv.setContentsMargins(spx(8), spx(3), spx(8), spx(4))
                tv.setSpacing(0)
                cap = QLabel(label)
                cap.setStyleSheet(
                    f'color: {CLR("faint")}; font-size: {spx(10)}px;'
                    ' background: transparent; border: none;')
                val = QLabel('--')
                val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                val.setStyleSheet(
                    f'color: {CLR("text")}; font-size: {spx(14)}px; font-weight: bold;'
                    ' background: transparent; border: none;')
                tv.addWidget(cap)
                tv.addWidget(val)
                r, c = divmod(i, cols)
                grid.addWidget(tile, r, c)
                self.tiles[(title, label)] = [val, tile, '']
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            v.addLayout(grid)
            self.bodyLayout.addWidget(card)
        self.bodyLayout.addStretch(1)

    def refresh(self):
        try:
            groups = self.main.statusGroups()
        except Exception as e:                     # 绝不让仪表板把主程序带崩
            groups = [('采集失败', [('错误', repr(e), 'err')])]
        structure = tuple((t, tuple(k for k, _v, _x in rows)) for t, rows in groups)
        if structure != self._structure:
            self._structure = structure
            self._buildBody(groups)

        for title, rows in groups:
            for label, value, tone in rows:
                cell = self.tiles.get((title, label))
                if cell is None:
                    continue
                val, tile, old_tone = cell
                val.setText(str(value))
                color = CLR(self.TONE_COLOR.get(tone, 'text'))
                val.setStyleSheet(
                    f'color: {color}; font-size: {spx(14)}px; font-weight: bold;'
                    ' background: transparent; border: none;')
                if tone != old_tone:
                    if tone:
                        tile.setStyleSheet(
                            f'QWidget#chip {{ background-color: {CLR("panel2")};'
                            f' border: 1px solid {CLR(self.TONE_COLOR[tone])};'
                            ' border-radius: 3px; }')
                    else:
                        tile.setStyleSheet('')
                    cell[2] = tone

    def _copy(self):
        try:
            text = self.main.statusReport()
        except Exception as e:
            text = '采集状态失败：%r' % (e,)
        QApplication.clipboard().setText(text)
        self.hint.setText('已复制到剪贴板（%d 行）' % text.count('\n'))


# ===========================================================================
# 主函数
# ===========================================================================
def normalize_sources(config: CoreConfig, first_run: bool = False):
    """补齐数据源列表，必要时把顶层连接参数同步到激活数据源。

    - 老配置没有 sources 时，按原 host/port 生成一条，保证行为不变
    - 首次运行默认选中“本机 USB（自动）”，实现插上即用
    - 始终保证列表里有本机 USB 选项，方便老用户切换
    """
    if not config.sources:
        config.sources = default_sources(config)
    if not any(s.get('type') == 'rtl_usb' for s in config.sources):
        usb = dict(default_sources(config)[0])
        config.sources.insert(0, usb)
        if not first_run:
            config.activeSource = int(getattr(config, 'activeSource', 0)) + 1
    if first_run:
        config.activeSource = next(
            (i for i, s in enumerate(config.sources) if s.get('type') == 'rtl_usb'), 0)
    if not (0 <= int(config.activeSource) < len(config.sources)):
        config.activeSource = 0
    if first_run:
        src = config.sources[config.activeSource]
        config.sourceType = src.get('type', 'rtl_usb')
        config.owrxMode = (config.sourceType == 'owrx')
        config.host = src.get('host', '127.0.0.1')
        config.port = int(src.get('port', 1234))
        config.sampleRate = int(src.get('sampleRate', 960000))
        config.gainDb = float(src.get('gainDb', HW_GAIN_DB))
        config.ppm = float(src.get('ppm', PPM))
        config.dcOffsetHz = float(src.get('dcOffsetHz', 50000.0))


