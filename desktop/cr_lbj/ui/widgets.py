# -*- coding: utf-8 -*-
"""ui_kit.py — Fluent Design 外观层（v2.4）

**不自造轮子**：全部控件来自 `qfluentwidgets`（PyPI 包 `PySide6-Fluent-Widgets`，
作者 zhiyiYo，GPLv3，与本项目许可一致）。这里只做三件事：

1. 把库的初始化（主题、强调色、字体、DPI 缩放）收在一处；
2. 给界面代码一组稳定的短名字（Button / Combo / Table / Card …），
   换库时只改这一个文件；
3. `qfluentwidgets` 没装或导入失败时**自动退回原生 Qt 控件**，
   程序照样能跑（外观降级为传统样式），打包/源码运行都不会因为缺库而崩。

字号策略：`setScale()` 由主程序按屏幕尺寸传入倍率，
`spx()` 用于布局尺寸，`fontPx()` 用于字号；底栏那种「大字」另有 `barFontPx()`
按小屏/中屏/大屏三档给值。
"""

from __future__ import annotations

from . import theme as TH

from PySide6.QtCore import Qt, QObject, QEvent, Signal
from PySide6.QtGui import QFont, QColor, QPalette, QCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, QPushButton as _QtButton, QComboBox as _QtCombo,
    QLineEdit as _QtLineEdit, QCheckBox as _QtCheck, QSpinBox as _QtSpin,
    QDoubleSpinBox as _QtDSpin, QTableWidget as _QtTable,
)

# ---------------------------------------------------------------------------
# 1. 加载 qfluentwidgets（失败则降级）
# ---------------------------------------------------------------------------
FLUENT = False

try:  # pragma: no cover - 取决于运行环境
    from qfluentwidgets import (
        setTheme, Theme, setThemeColor, setFontFamilies,
        PushButton, PrimaryPushButton, TransparentPushButton,
        ToolButton, TransparentToolButton,
        ComboBox, LineEdit, CheckBox, SpinBox, DoubleSpinBox,
        TableWidget, SimpleCardWidget, CardWidget, ElevatedCardWidget,
        BodyLabel, StrongBodyLabel, CaptionLabel, SubtitleLabel, TitleLabel,
        SegmentedWidget, SwitchButton, IconWidget,
    )
    FLUENT = True
except Exception:  # 缺库 / 版本不符 → 用原生 Qt 顶上
    Theme = None

    class _FakeTheme:  # 占位，保证 applyTheme 不炸
        LIGHT = 'light'
        DARK = 'dark'
        AUTO = 'auto'

    Theme = _FakeTheme

    PushButton = PrimaryPushButton = TransparentPushButton = _QtButton
    ToolButton = TransparentToolButton = _QtButton
    ComboBox = _QtCombo
    LineEdit = _QtLineEdit
    CheckBox = _QtCheck
    SpinBox = _QtSpin
    DoubleSpinBox = _QtDSpin
    TableWidget = _QtTable
    SimpleCardWidget = CardWidget = ElevatedCardWidget = QFrame
    BodyLabel = StrongBodyLabel = CaptionLabel = SubtitleLabel = TitleLabel = QLabel
    SegmentedWidget = QWidget
    SwitchButton = _QtCheck

    def setTheme(*a, **k):
        pass

    def setThemeColor(*a, **k):
        pass

    def setFontFamilies(*a, **k):
        pass


# ---------------------------------------------------------------------------
# 2. 尺寸与字号
# ---------------------------------------------------------------------------
_SCALE = 1.0


def setScale(scale: float) -> None:
    """由主程序按屏幕尺寸/配置传入（0.85 ~ 1.6）。"""
    global _SCALE
    try:
        _SCALE = max(0.75, min(1.6, float(scale)))
    except Exception:
        _SCALE = 1.0


def scale() -> float:
    return _SCALE


def spx(v: float) -> int:
    """布局尺寸：设计像素 → 实际像素。"""
    return max(1, int(round(float(v) * _SCALE)))


def fontPx(base: float) -> float:
    """正文/说明文字字号（保持浮点，QSS 里可写 12.5px）。"""
    return round(float(base) * _SCALE, 1)


def fit_dialog_to_screen(dlg, design_w: float = 0, design_h: float = 0,
                         design_min_w: float = 0, design_min_h: float = 0,
                         margin: float = None) -> None:
    """把二级窗口收进「它所在那块屏」的可用区并居中（v3.2.4）。

    为什么需要：各对话框原先写死 `resize(spx(1040), spx(700))` 这类尺寸。
    在 1366×768、或 1280×800@200%（逻辑可用区只有 640×400）的副屏上，
    spx() 还会按 UI_SCALE 放大，窗口直接顶出屏幕、内容被裁、右/下边缘点不到。

    规则：
      * 取窗口所在屏（`windowHandle().screen()`）；窗口还没 show 时用
        **鼠标所在屏**兜底（与主窗口 `_currentScreen` 同一思路）；
      * 目标尺寸 = min(spx(design), 可用区 - 边距)；下限同理也不超过屏幕；
      * 居中到该屏可用区。

    调用时机：构造完 UI 后调用一次即可（`resize`/`move` 在 show 前也有效）。
    任何异常都退回"按设计尺寸"，绝不让自适应本身把窗口搞崩。
    """
    try:
        scr = None
        try:
            h = dlg.windowHandle()
            if h is not None and h.screen() is not None:
                scr = h.screen()
        except Exception:
            pass
        if scr is None:
            try:
                scr = QApplication.screenAt(QCursor.pos())
            except Exception:
                scr = None
        if scr is None:
            scr = QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr is not None else None
        if avail is None:
            if design_w and design_h:
                dlg.resize(spx(design_w), spx(design_h))
            if design_min_w and design_min_h:
                dlg.setMinimumSize(spx(design_min_w), spx(design_min_h))
            return

        # 边距：约为屏宽 2%，夹在 8~40 设计像素之间（再经 spx 缩放）
        m = int(margin) if margin is not None else max(8, min(40, int(avail.width() * 0.02)))
        mw, mh = spx(m), spx(m)
        max_w = max(spx(320), avail.width() - mw * 2)
        max_h = max(spx(240), avail.height() - mh * 2)

        # 先收紧下限（下限也绝不能超过屏幕）
        if design_min_w and design_min_h:
            dlg.setMinimumSize(min(spx(design_min_w), max_w),
                               min(spx(design_min_h), max_h))
        else:
            dlg.setMinimumSize(min(max(0, dlg.minimumWidth()), max_w),
                               min(max(0, dlg.minimumHeight()), max_h))

        w = min(spx(design_w), max_w) if design_w else min(max_w, max(1, dlg.width()))
        h = min(spx(design_h), max_h) if design_h else min(max_h, max(1, dlg.height()))
        w = max(int(w), dlg.minimumWidth())
        h = max(int(h), dlg.minimumHeight())
        dlg.resize(w, h)
        # 居中到该屏可用区（可用区已扣掉任务栏/状态栏）
        dlg.move(avail.x() + max(0, (avail.width() - w) // 2),
                 avail.y() + max(0, (avail.height() - h) // 2))
    except Exception:
        try:
            if design_w and design_h:
                dlg.resize(spx(design_w), spx(design_h))
        except Exception:
            pass


#: 底栏四档：小屏 / 笔记本 / 中屏 / 大屏（日志与状态提示的“大字”）
def barFontPx() -> float:
    if _SCALE < 1.0:
        return 15.0
    if _SCALE < 1.12:
        return 17.0
    if _SCALE < 1.20:
        return 19.0
    return 21.0


def isDark() -> bool:
    return TH.P.get('mode') == 'dark'


# ---------------------------------------------------------------------------
# 2b. Fluent 控件的字号缩放
# ---------------------------------------------------------------------------
def setFontPx(w: QWidget, px: float) -> None:
    """按设计像素设字号（配色不动，Fluent 的圆角/悬停/强调色全部保留）。

    原值记到 `_uiBasePx` 属性里，屏幕倍率变化时不会重复叠加。
    """
    try:
        f = w.font()
        base = float(px)
        w.setProperty('_uiBasePx', int(round(base)))
        f.setPixelSize(max(1, int(round(base * _SCALE))))
        w.setFont(f)
    except Exception:
        pass


class _FontScaler(QObject):
    """让 qfluentwidgets 的控件也跟着屏幕倍率放大。

    Fluent 的字号是构造时用 `QWidget.setFont()` 定的（14px 之类），**不吃应用级 QSS**，
    所以 `scale_qss()` 管不到它——大屏上会一直显示小字。
    这里挂一个应用级事件过滤器，在控件第一次显示时按 `_SCALE` 放大一次。
    """

    def eventFilter(self, obj, ev):
        try:
            if ev.type() == QEvent.Show and isinstance(obj, QWidget):
                self._scale(obj)
        except Exception:
            pass
        return False

    @staticmethod
    def _scale(w: QWidget) -> None:
        if not FLUENT or abs(_SCALE - 1.0) < 0.02:
            return
        base = w.property('_uiBasePx')
        if base is None:
            px = w.font().pixelSize()
            if not px or px <= 0:          # 用磅值的控件交给 QSS 缩放
                return
            w.setProperty('_uiBasePx', int(px))
            base = int(px)
        f = w.font()
        f.setPixelSize(max(1, int(round(int(base) * _SCALE))))
        w.setFont(f)


_scaler = None


def installFontScaler(app: QApplication) -> None:
    """在构造界面之前调用，之后新建的控件（含对话框）都会自动按倍率放大。"""
    global _scaler
    if not FLUENT:
        return
    try:
        if _scaler is None:
            _scaler = _FontScaler(app)
        app.installEventFilter(_scaler)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3. 初始化与主题
# ---------------------------------------------------------------------------
def setupApp(app: QApplication) -> None:
    """Fluent 初始化：强调色（CR 红）、字体、基础字号。"""
    if FLUENT:
        try:
            setThemeColor(TH.CR_RED)
            setFontFamilies(['Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI'])
        except Exception:
            pass
    try:
        f = QFont('Microsoft YaHei UI')
        f.setPointSizeF(10.0 if _SCALE >= 1.0 else 9.5)
        app.setFont(f)
    except Exception:
        pass


def applyTheme(mode: str) -> None:
    """界面深浅色：直接交给 qfluentwidgets 的 setTheme。"""
    if not FLUENT:
        return
    try:
        setTheme(Theme.DARK if str(mode) == 'dark' else Theme.LIGHT)
    except Exception:
        pass


def cardColor() -> str:
    """当前卡片的底色（给自绘面板/地图留白用）。"""
    return TH.c('panel', '#191c21')


def paintBackground(w: QWidget, color: str = None) -> None:
    """给对话框/容器铺一层实底。

    不能只靠 QSS：`theme._QSS` 里 `QWidget { background-color: transparent }` 排在
    `QDialog { background-color: $bg }` 之后，且 QDialog 也是 QWidget，
    同优先级下后写的赢——结果是对话框根本不刷底色，底下露出系统的白色，
    做法：调色板兜底 + **控件自己**的 ID 选择器样式（优先级高于应用级 QSS）。
    颜色写成 `rgb(r,g,b)` 而不是 `#RRGGBB`，避免换肤时被
    `_restyleWidgets()` 的「旧色→新色」批量替换误伤。
    """
    try:
        col = QColor(color or TH.c('bg', '#14161a'))
        pal = w.palette()
        pal.setColor(QPalette.Window, col)
        w.setPalette(pal)
        w.setAutoFillBackground(True)
        name = w.objectName() or 'paneBg'
        w.setObjectName(name)
        w.setStyleSheet(
            f'#{name} {{ background-color: rgb({col.red()}, {col.green()}, {col.blue()}); }}')
    except Exception:
        pass


def textColor() -> str:
    return TH.c('text', '#d8dee6')


def dimColor() -> str:
    return TH.c('dim', '#8c97a3')


def accentColor() -> str:
    return TH.c('accent', TH.CR_RED)


# ---------------------------------------------------------------------------
# 4. 控件工厂（短名字）
# ---------------------------------------------------------------------------
# 兼容层：qfluentwidgets 的构造函数签名比 Qt 窄（只收 parent），
# 而项目里大量 `QComboBox.addItem(文本, 数据)`、`QTableWidget(行, 列)` 的老写法，
# 直接换类会踩签名。这里用极薄的子类补齐签名，**不改任何调用点**，
# 样式仍然全部来自 qfluentwidgets。
if FLUENT:
    _FC = ComboBox
    _FT = TableWidget
    _FLE = LineEdit

    class ComboBox(_FC):  # noqa: F811
        def addItem(self, text, userData=None, icon=None):
            super().addItem(str(text), icon=icon, userData=userData)

    class LineEdit(_FLE):  # noqa: F811
        """`QLineEdit('初始文本')` 这类老写法在这里继续有效。

        qfluentwidgets 的 LineEdit 只收 parent，把字符串当 parent 传给 QLineEdit
        会直接 ValueError；配置面板一构造就会崩，所以必须补这一层。
        """

        def __init__(self, text: str = '', parent: QWidget = None):
            super().__init__(parent)
            if text:
                self.setText(str(text))

    class TableWidget(_FT):  # noqa: F811
        def __init__(self, rows: int = 0, cols: int = 0, parent: QWidget = None):
            super().__init__(parent)
            if rows:
                self.setRowCount(rows)
            if cols:
                self.setColumnCount(cols)
            applyTablePalette(self)
else:
    class ComboBox(_QtCombo):  # noqa: F811
        pass

    class LineEdit(_QtLineEdit):  # noqa: F811
        def __init__(self, text: str = '', parent: QWidget = None):
            super().__init__(str(text or ''), parent)

    class TableWidget(_QtTable):  # noqa: F811
        pass


def applyTablePalette(table) -> None:
    """修 Fluent 表格在深色主题下的「白底」问题。

    qfluentwidgets 给表格自己的样式是 `QTableView { background: transparent; }`，
    想让卡片底色透上来；但 `QAbstractScrollArea` 的 viewport 不会透——它退回
    `QPalette.Base`，浅色系统调色板下就是**纯白**，深色界面里整张表白得刺眼。
    而它在**控件自带的**样式表里，优先级高于应用的 QSS，光改主题 QSS 覆盖不掉。

    这里做两件事：
    1. 把 Base/AlternateBase 显式设成主题色（调色板兜底）；
    2. 在表格自己的样式表**末尾**追加一条规则（Fluent 的样式在前，后者优先）。
    """
    if not FLUENT:
        return
    panel = TH.c('panel', '#191c21')
    panel2 = TH.c('panel2', '#1e2228')
    text = TH.c('text', '#d8dee6')
    try:
        pal = table.palette()
        pal.setColor(QPalette.Base, QColor(panel))
        pal.setColor(QPalette.AlternateBase, QColor(panel2))
        pal.setColor(QPalette.Window, QColor(panel))
        pal.setColor(QPalette.Text, QColor(text))
        pal.setColor(QPalette.Highlight, QColor(TH.c('sel', '#3a1c19')))
        pal.setColor(QPalette.HighlightedText, QColor('#ffffff'))
        table.setPalette(pal)
        for sub in (table.viewport(), table.horizontalHeader(), table.verticalHeader()):
            if sub is not None:
                sub.setPalette(pal)
    except Exception:
        pass

    try:
        own = table.styleSheet() or ''
        old = table.property('_palQss') or ''
        if old and old in own:                 # 换肤时先把上次追加的那条摘掉
            own = own.replace(old, '')
        chunk = ('\nQTableView { background-color: %s; color: %s;'
                 ' alternate-background-color: %s; }\n' % (panel, text, panel2))
        table.setStyleSheet(own + chunk)
        table.setProperty('_palQss', chunk)
        table.viewport().setStyleSheet('background-color: %s;' % panel)
    except Exception:
        pass


def refreshTablePalettes() -> None:
    """换肤后把已存在的表格调色板刷一遍（新表格构造时自动处理）。"""
    if not FLUENT:
        return
    try:
        for w in QApplication.allWidgets():
            if isinstance(w, _FT):
                applyTablePalette(w)
    except Exception:
        pass


def button(text: str, primary: bool = False, ghost: bool = False,
           parent: QWidget = None) -> QWidget:
    """普通按钮 / 主按钮（强调色填充）/ 无边框按钮。"""
    cls = PrimaryPushButton if primary else (TransparentPushButton if ghost else PushButton)
    btn = cls(text, parent) if FLUENT else cls(text, parent)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def small_button(text: str, primary: bool = False, h: int = 26,
                 px: float = 11.5, parent: QWidget = None) -> QWidget:
    """行内小按钮（表格、密集表单里那种紧致按钮）。

    Fluent 按钮默认高 32px，塞进密集表单会把整行撑高；这里只压高度和字号，
    配色、圆角、悬停动画仍然由 qfluentwidgets 负责。
    """
    b = button(text, primary=primary, parent=parent)
    b.setFixedHeight(spx(h))
    b.setMinimumWidth(spx(52))
    setFontPx(b, px)
    return b


def tool_button(text: str, parent: QWidget = None) -> QWidget:
    btn = ToolButton(parent) if FLUENT else _QtButton(parent)
    if text:
        btn.setText(text)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def combo(parent: QWidget = None) -> QWidget:
    c = ComboBox(parent) if FLUENT else _QtCombo(parent)
    return c


def line_edit(parent: QWidget = None, placeholder: str = '') -> QWidget:
    e = LineEdit('', parent)
    if placeholder:
        e.setPlaceholderText(placeholder)
    return e


def check(text: str, parent: QWidget = None) -> QWidget:
    return CheckBox(text, parent) if FLUENT else _QtCheck(text, parent)


def spin(parent: QWidget = None) -> QWidget:
    return SpinBox(parent) if FLUENT else _QtSpin(parent)


def dspin(parent: QWidget = None) -> QWidget:
    return DoubleSpinBox(parent) if FLUENT else _QtDSpin(parent)


def table(rows: int, cols: int, parent: QWidget = None) -> QWidget:
    t = TableWidget(parent) if FLUENT else _QtTable(parent)
    if FLUENT:
        try:
            t.setBorderVisible(True)
            t.setBorderRadius(8)
            t.setWordWrap(False)
        except Exception:
            pass
    t.setRowCount(rows)
    t.setColumnCount(cols)
    return t


def segmented(parent: QWidget = None) -> QWidget:
    """分段选择器（Fluent 的「图形 / 终端」切换）。"""
    s = SegmentedWidget(parent) if FLUENT else QWidget(parent)
    return s


if FLUENT:
    _FSW = SwitchButton
else:
    class _FSW(_QtCheck):  # noqa: F811
        """原生降级：给 QCheckBox 补一个同名的 checkedChanged 信号。"""

        checkedChanged = Signal(bool)

        def __init__(self, parent: QWidget = None):
            super().__init__(parent)
            self.toggled.connect(self.checkedChanged.emit)

        def setOnText(self, text: str) -> None:
            self._onText = text

        def setOffText(self, text: str) -> None:
            self._offText = text


def switch(text: str = '接收', on_text: str = '', off_text: str = '',
           parent: QWidget = None) -> QWidget:
    """开关（代替「开始 / 停止」两个按钮）。

    开启时文字用 `on_text`、关闭时用 `off_text`，一眼能看出当前状态；
    信号名统一为 `checkedChanged(bool)`，降级实现也补齐了这个名字。
    """
    sw = _FSW(parent) if not FLUENT else _FSW(text, parent)
    try:
        sw.setOffText(off_text or text)
        sw.setOnText(on_text or (text + '中'))
        sw.setText(off_text or text)
    except Exception:
        pass
    if not FLUENT:
        sw.setText(off_text or text)
    sw.setCursor(Qt.PointingHandCursor)
    return sw


# ---------------------------------------------------------------------------
# 5. 文本
# ---------------------------------------------------------------------------
def label(text: str = '', size: float = 12, color: str = '', bold: bool = False,
          parent: QWidget = None) -> QLabel:
    """带主题色与字号的小标签（统一走 QLabel，避免两种控件混排对不齐）。"""
    lb = QLabel(text, parent) if parent is not None else QLabel(text)
    setLabelStyle(lb, size=size, color=color, bold=bold)
    return lb


def setLabelStyle(lb: QLabel, size: float = None, color: str = '',
                  bold: bool = None) -> None:
    """只改字号/颜色/字重，不动背景（背景由父容器决定）。"""
    css = 'background: transparent;'
    if size is not None:
        css += f' font-size: {fontPx(size)}px;'
    if color:
        css += f' color: {color};'
    if bold is not None:
        css += f' font-weight: {"bold" if bold else "normal"};'
    lb.setStyleSheet(css)


# ---------------------------------------------------------------------------
# 6. 卡片（替代原 CardBox）
# ---------------------------------------------------------------------------
class CardBox(SimpleCardWidget if FLUENT else QFrame):
    """带标题的卡片容器。

    用 Fluent 的 `SimpleCardWidget` 作底（自带圆角、卡片底色、深浅色适配），
    标题用加粗小字，右侧可挂一个小控件（如频谱的「图形 / 终端」分段选择器）。

    title 传空字符串则不生成标题行：内容本身已带标识（比如页签写着
    「当前解码 / 历史记录」）时，再来一行大字标题纯属重复，还占高度。
    """

    def __init__(self, title: str = '', content: QWidget = None,
                 right: QWidget = None, margins=(8, 6, 8, 6)):
        super().__init__()
        self.content = content
        self.setObjectName('cardBox')

        v = QVBoxLayout(self)
        v.setContentsMargins(spx(margins[0]), spx(margins[1]),
                             spx(margins[2]), spx(margins[3]))
        v.setSpacing(spx(4))

        self.titleLabel = None
        if title:
            head = QHBoxLayout()
            head.setContentsMargins(spx(2), 0, spx(2), 0)
            head.setSpacing(spx(6))
            self.titleLabel = QLabel(title)
            self.titleLabel.setStyleSheet(
                f'background: transparent; color: {accentColor()};'
                f' font-size: {fontPx(12)}px; font-weight: bold;')
            head.addWidget(self.titleLabel, 0)
            head.addStretch(1)
            if right is not None:
                head.addWidget(right, 0, Qt.AlignVCenter)
            v.addLayout(head)
        elif right is not None:
            # 没标题但仍有右侧控件：单独一行放控件，避免它和内容抢高度
            head = QHBoxLayout()
            head.setContentsMargins(spx(2), 0, spx(2), 0)
            head.addWidget(right, 0, Qt.AlignVCenter)
            head.addStretch(1)
            v.addLayout(head)
        v.addWidget(content, 1)

    def setTitle(self, text: str) -> None:
        if self.titleLabel is not None:
            self.titleLabel.setText(text)

    # F-luent 的 CardWidget 只画一层「白色 + 13/170 透明度」的底，
    # 靠父控件透上来定深浅；父层是 Fusion 默认的浅色时整张卡就发白。
    # 这里自己先用主题色铺一层实的，再把 Fluent 的描边叠上去。
    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QPen, QBrush
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(TH.c('border', '#2b3138')), 1))
            p.setBrush(QBrush(QColor(TH.c('panel', '#191c21'))))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
            p.end()
        except Exception:
            pass
        try:
            super().paintEvent(e)
        except Exception:
            pass
