#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用启动层：参数解析、配置加载、QApplication 初始化、主题与缩放。"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403
from cr_lbj.gui import *      # noqa: F401,F403 —— 组装层带入全部窗口/面板/对话框类

def main():
    parser = argparse.ArgumentParser(description='SDR-LBJ GUI (PySide6)')
    parser.add_argument('--host', type=str, default=None)
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--sr', type=int, default=None, help='采样率 (Hz)')
    parser.add_argument('-f', '--freq', type=float, default=None, help='频率 (MHz)')
    parser.add_argument('--gain', type=float, default=None)
    parser.add_argument('--no-autostart', action='store_true')
    args = parser.parse_args()

    # 加载配置
    first_run = FIRST_RUN
    config = CoreConfig.load(CONFIG_PATH)
    normalize_sources(config, first_run)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.sr:
        config.sampleRate = args.sr
    if args.freq:
        config.freqMhz = args.freq
    if args.gain:
        config.gainDb = args.gain

    # 高 DPI：允许非整数缩放（125%/150% 更平滑）。必须在 QApplication 之前设置。
    # Qt6 在 Windows 上默认按显示器分别处理 DPI（per-monitor v2），
    # 本机两块屏 dpr 可能一个 1.0 一个 2.0 —— 窗口几何/最小尺寸必须跟着
    # 窗口所在屏走，见 MainWindow._onScreenChanged()。
    try:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # 外观主题：dark / light / auto（auto 读系统配色），必须在建窗口之前定好
    resolved_theme = TH.applyMode(str(getattr(config, 'theme', 'dark') or 'dark'))
    applyPgTheme()

    # 界面缩放：0（或老的 100%）= 按屏幕自动；其余用配置倍率
    # 大屏给小屏同一条布局，但字号/控件尺寸按档位放大（v2.4：大屏别再看小字）
    global UI_SCALE
    UI_SCALE = resolveUiScale(config)
    K.setScale(UI_SCALE)
    app.setStyleSheet(scale_qss(TH.styleSheet()) + scale_qss(TOUCH_STYLE))

    # Fluent 外观层：强调色、字体、深浅色（qfluentwidgets 缺失时自动降级）
    K.setupApp(app)
    K.applyTheme(resolved_theme)
    # Fluent 控件的字号是构造时 setFont 定的，不吃应用级 QSS —— 用事件过滤器补上缩放
    K.installFontScaler(app)

    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = MainWindow(config)
    if args.no_autostart:
        window.statusBar().showMessage('点击 文件 → 启动 DSP 开始')
    window.show()
    try:
        _scr = window._currentScreen()
        _dpr = round(float(_scr.devicePixelRatio()), 2) if _scr is not None else 0
        _scrTxt = f'，屏幕 {_scr.name()} dpr={_dpr}' if _scr is not None else ''
    except Exception:
        _scrTxt = ''
    window.logBus.appendLog(
        f'[启动] 主题 {resolved_theme}（{getattr(config, "theme", "dark")}），'
        f'界面缩放 {UI_SCALE:.2f}x{_scrTxt}，去重窗口 {config.dedupeWindow:.1f}s')

    sys.exit(app.exec())


if __name__ == '__main__':  # 允许 python -m cr_lbj.app 直接启动
    main()
