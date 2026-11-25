# -*- coding: utf-8 -*-
"""map_host.py — 共享地图页（shared/web/railmap.html）的宿主与 JS 桥。

桌面端与安卓端共用**同一份**页面：Leaflet + OpenRailwayMap，零构建、离线可用。
本模块只负责「把页面装进 QtWebEngine 并和它说话」，不参与任何业务逻辑；
工具栏、跟随/夜间按钮、数据推送都在 `map_panel.py` 里。

## 为什么必须走 setHtml + 目录 baseUrl

页面里对 Leaflet 的引用是**相对路径**（`vendor/leaflet/leaflet.css|js`）。
`setHtml(html)` 不带 baseUrl 时基准是 `about:blank`，相对路径一律 404，页面
一片空白。正确做法：

    html = 读 railmap.html → 把配置注入点替换成 `INJECTED = {...};`
    view.setHtml(html, QUrl.fromLocalFile(<shared/web 目录>/))

baseUrl **必须是目录且以 `/` 结尾**，否则最后一段会被当成文件名吃掉。

## 配置注入的两个兜底

1. 页面里有一行 `/*__LBJ_CONFIG_START__*//*__LBJ_CONFIG_END__*/`，替换成
   `INJECTED = {...};` 后页面启动即带上用户的底图/铁路/夜间设置；
2. 即便注入点将来被改掉（页面升级），`loadFinished` 之后还会再调一次
   `LBJ.applyConfig(cfg)` —— 页面缺省配置（OSM）照样能开，只是晚一拍生效。

## 对外接口（MapPanel 只用这些）

    available / ready / view / web_dir / reload() / apply_config(cfg)
    js(code, cb) / update(payload) / focus(id) / clear() / set_follow(b)
    set_night(b) / center_to(addr) / resize() / set_base(id) / set_rail(id)
    set_rail_opacity(v) / status(cb) / center(cb) / layers(cb)
    console_log() / set_fallback(text)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import config_ext
from . import theme as TH

try:                                    # QtWebEngine 由 PySide6-Addons 提供
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage
    HAS_WEBENGINE = True
except Exception:                       # pragma: no cover - 取决于运行环境
    QWebEngineView = None               # type: ignore
    QWebEnginePage = object             # type: ignore
    HAS_WEBENGINE = False


#: 页面里的配置注入点（与 railmap.html 中的注释标记逐字对应）
_CONFIG_MARK = re.compile(
    r'/\*__LBJ_CONFIG_START__\*/.*?/\*__LBJ_CONFIG_END__\*/', re.S)


if HAS_WEBENGINE:

    class _MapPage(QWebEnginePage):
        """带控制台回传的页面对象：JS 报错能落到 Python 日志里，便于定位。"""

        console = Signal(str, int, str)     # message / line / source

        def javaScriptConsoleMessage(self, level, message,  # noqa: N802
                                     lineNumber, sourceID):
            try:
                self.console.emit(str(message), int(lineNumber), str(sourceID))
            except Exception:
                pass
            try:
                super().javaScriptConsoleMessage(level, message,
                                                 lineNumber, sourceID)
            except Exception:
                pass

else:                                   # 无 QtWebEngine：占位，保证导入不炸

    class _MapPage:                     # type: ignore[no-redef]
        pass


class MapHost(QWidget):
    """地图页宿主：一个 QWebEngineView + 降级提示 + JS 调用封装。"""

    readyChanged = Signal(bool)
    consoleMessage = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._view: Optional[Any] = None
        self._page: Optional[Any] = None
        self._ready = False
        self._loaded_dir = ''
        self._console: List[str] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._fallback = QLabel()
        self._fallback.setWordWrap(True)
        self._fallback.setAlignment(Qt.AlignCenter)
        self._fallback.setStyleSheet(
            f'color: {TH.c("dim")}; background-color: {TH.c("panel2")};'
            f' border: 1px solid {TH.c("border")};'
            f' border-radius: 4px; font-size: 11px; padding: 10px;')
        self._fallback.hide()
        lay.addWidget(self._fallback)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """能内嵌地图吗？（缺 QtWebEngine 或缺页面文件都算不能）"""
        return bool(HAS_WEBENGINE and config_ext.railmap_exists())

    @property
    def ready(self) -> bool:
        return bool(self._ready and self._view is not None)

    @property
    def view(self):
        return self._view

    @property
    def web_dir(self) -> str:
        return config_ext.web_dir()

    def console_log(self) -> List[str]:
        return list(self._console)

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def load(self, force: bool = False) -> bool:
        """把页面装进视图。页面目录没变且已就绪时不重复加载。"""
        if not HAS_WEBENGINE:
            self.set_fallback(
                '未安装 <b>PySide6-Addons</b>，无法内嵌地图。<br>'
                '执行 <code>pip install PySide6-Addons</code> 后重启程序即可；'
                '「网页」按钮仍可在系统浏览器里看位置。')
            return False
        if not config_ext.railmap_exists():
            self.set_fallback(
                '缺少地图页面文件：<br><code>%s</code><br>'
                '请确认 <code>shared/web/</code> 与程序一起发布（源码运行时'
                '位于仓库根）。' % config_ext.railmap_path())
            return False

        wdir = config_ext.web_dir()
        if self._view is not None and self._ready and not force and wdir == self._loaded_dir:
            self.apply_config(self.config)
            return True

        if self._view is None:
            self._view = QWebEngineView(self)
            self._view.setContextMenuPolicy(Qt.NoContextMenu)
            self._page = _MapPage(self._view)
            try:
                self._page.console.connect(self._on_console)
                self._view.setPage(self._page)
            except Exception:
                pass
            self._view.loadFinished.connect(self._on_load_finished)
            self.layout().addWidget(self._view)

        self._fallback.hide()
        self._view.show()
        self._ready = False
        self._loaded_dir = wdir
        try:
            html = self._read_html(wdir)
        except OSError as e:
            self.set_fallback('地图页面读取失败：<br>%s' % e)
            return False
        # baseUrl 必须是**目录**且带结尾斜杠，相对路径才能解析到 vendor/
        base = QUrl.fromLocalFile(wdir if wdir.endswith(os.sep) else wdir + os.sep)
        self._view.setHtml(html, base)
        return True

    def reload(self) -> bool:
        return self.load(force=True)

    def _read_html(self, wdir: str) -> str:
        path = os.path.join(wdir, config_ext.RAILMAP_FILE)
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        injected = ('INJECTED = %s;'
                    % json.dumps(self._config_json(), ensure_ascii=False))
        new_html, n = _CONFIG_MARK.subn(lambda _m: injected, html, count=1)
        if n == 0:
            # 注入点被页面改掉了：不阻断加载，等 loadFinished 再 applyConfig
            return html
        return new_html

    def _on_load_finished(self, ok: bool):
        if not ok:
            self._ready = False
            self.set_fallback(
                '地图页面加载失败。<br>若刚换过 <code>shared/web/</code>，请检查'
                '<code>railmap.html</code> 与 <code>vendor/leaflet/</code> 是否完整。')
            self.readyChanged.emit(False)
            return
        self._ready = True
        self.apply_config(self.config)
        self.js('window.LBJ && window.LBJ.resize();')
        self.readyChanged.emit(True)

    def _on_console(self, message: str, line: int, source: str):
        tag = '[地图JS] %s%s' % (message, (' @%d' % line) if line else '')
        self._console.append(tag)
        del self._console[:-120]
        self.consoleMessage.emit(tag)

    def set_fallback(self, text: str):
        """显示降级提示（地图不可用时）。"""
        if self._view is not None:
            self._view.hide()
        self._fallback.setText(text)
        self._fallback.show()

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def _config_json(self) -> Dict[str, Any]:
        cfg = self.config
        base = config_ext.normalize_base(config_ext.get(cfg, 'mapBase', 'osm'))
        rail = config_ext.normalize_rail(config_ext.get(cfg, 'mapRail', 'orm_standard'))
        try:
            op = float(config_ext.get(cfg, 'mapRailOpacity', 0.85) or 0.85)
        except (TypeError, ValueError):
            op = 0.85
        out: Dict[str, Any] = {
            'base': base,
            'rail': rail,
            'railOpacity': max(0.2, min(1.0, op)),
            'night': bool(getattr(cfg, 'mapNight', True)),
            'follow': bool(getattr(cfg, 'mapFollow', True)),
            'showTrail': bool(getattr(cfg, 'mapShowTrail', True)),
            'tdtKey': str(config_ext.get(cfg, 'tdtKey', '') or ''),
            'colors': _page_colors(),
        }
        try:
            out['zoom'] = max(3, min(18, int(getattr(cfg, 'mapZoom', 12) or 12)))
        except (TypeError, ValueError):
            out['zoom'] = 12
        lat = _safe_float(getattr(cfg, 'mapCenterLat', 0))
        lng = _safe_float(getattr(cfg, 'mapCenterLng', 0))
        # 0,0 视为「还没解析出中心」：整块省略，让页面用它自己的缺省中心
        if abs(lat) > 1e-6 and abs(lng) > 1e-6:
            out['center'] = {'lat': lat, 'lng': lng}
        return out

    def apply_config(self, config=None) -> None:
        """把配置推给页面（不重建页面，标记点不丢）。"""
        if config is not None:
            self.config = config
        payload = self._config_json()
        payload.pop('zoom', None)          # 缩放交给页面保持当前视图
        self.js('window.LBJ && window.LBJ.applyConfig(%s);'
                % json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------------
    # JS 调用
    # ------------------------------------------------------------------
    def js(self, code: str, cb: Optional[Callable] = None) -> None:
        """执行一段 JS。页面未就绪时静默丢弃（数据会在就绪后补推）。"""
        if not self.ready or self._view is None:
            return
        try:
            page = self._view.page()
            if cb is None:
                page.runJavaScript(code)
            else:
                page.runJavaScript(code, cb)
        except Exception:
            pass

    def _call(self, name: str, arg: Optional[str] = None,
              cb: Optional[Callable] = None) -> None:
        """调用 `window.LBJ.<name>(arg)`（arg 已序列化成 JS 字面量）。"""
        body = '%s(%s)' % (name, arg if arg is not None else '')
        self.js('window.LBJ && window.LBJ.%s;' % body, cb)

    # ---- 业务入口 ----
    def update(self, payload: Dict[str, Any]) -> None:
        self.js('window.LBJ && window.LBJ.update(%s);'
                % json.dumps(payload, ensure_ascii=False))

    def focus(self, train_id) -> None:
        self._call('focus', json.dumps(str(train_id), ensure_ascii=False))

    def clear(self) -> None:
        self._call('clear')

    def set_follow(self, on: bool) -> None:
        self._call('setFollow', 'true' if on else 'false')

    def set_night(self, on: bool) -> None:
        self._call('setNight', 'true' if on else 'false')

    def center_to(self, addr: str = '') -> None:
        self._call('centerTo', json.dumps(str(addr or ''), ensure_ascii=False))

    def resize(self) -> None:
        self._call('resize')

    def set_base(self, layer_id: str) -> None:
        self._call('setBase', json.dumps(str(layer_id or ''), ensure_ascii=False))

    def set_rail(self, layer_id: str) -> None:
        self._call('setRailStyle', json.dumps(str(layer_id or ''), ensure_ascii=False))

    def set_rail_opacity(self, value: float) -> None:
        self._call('railOpacity', repr(max(0.2, min(1.0, float(value)))))

    # ---- 查询类（异步回调）----
    #
    # 坑：QtWebEngine 的 runJavaScript **不能把 JS 对象转成 Python 对象**（返回空串，
    # 标量/数组可以）。所以查状态一律在 JS 侧 JSON.stringify，Python 侧再 json.loads，
    # 否则 _onStatusPoll 永远拿不到 dict —— 工具栏不同步、跟随锁检测失效、
    # 瓦片失败提示不出现，全都不报错只是"看起来没反应"。
    def _json_call(self, expr: str, cb: Callable) -> None:
        def _wrap(raw):
            data = None
            if isinstance(raw, str) and raw:
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = None
            elif raw is not None and not isinstance(raw, str):
                data = raw
            try:
                cb(data)
            except Exception:
                pass

        self.js('JSON.stringify(%s);' % expr, _wrap)

    def status(self, cb: Callable) -> None:
        self._json_call('window.LBJ ? window.LBJ.status() : null', cb)

    def center(self, cb: Callable) -> None:
        self._json_call('window.LBJ ? window.LBJ.center() : null', cb)

    def layers(self, cb: Callable) -> None:
        self._json_call('window.LBJ ? window.LBJ.layers() : null', cb)

    def is_night(self, cb: Callable) -> None:
        self._json_call('window.LBJ ? window.LBJ.isNight() : null', cb)

    def marker_count(self, cb: Callable) -> None:
        """当前页面上的列车标记数（自检/测试用）。"""
        self.js('document.querySelectorAll(".lbj-marker").length;', cb)


def _safe_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _page_colors() -> Dict[str, str]:
    """列车标记配色（跟随界面主题的 CR 蓝 / CR 红）。"""
    try:
        c = TH.mapColors()
        return {'up': c.get('up', '#4C8DFF'), 'down': c.get('down', '#F0604F'),
                'unknown': c.get('unknown', '#E0A400')}
    except Exception:
        return {'up': '#4C8DFF', 'down': '#F0604F', 'unknown': '#E0A400'}
