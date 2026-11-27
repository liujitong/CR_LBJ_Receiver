# -*- coding: utf-8 -*-
"""CR-LBJ-Receiver 应用包。

分层：
    core/        解码内核与 DSP 线程桥接（不依赖 UI）
    data/        静态映射数据与 SQLite 历史库
    ui/          主题、控件封装、地图面板、可复用组件、对话框、主窗口
    utils/       与 Qt 无关的纯函数
    runtime.py   共享运行时（路径 / 常量 / 缩放 / 控件别名）
    gui.py       组装层：把各实现模块汇到同一命名空间
    app.py       启动层：参数解析、配置、QApplication、主题与缩放
"""
__version__ = '3.2.10'
