#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI 组装层。

窗口 / 面板 / 对话框按职责分布在 core / data / ui 下，本模块把它们汇到同一
命名空间，并把聚合结果**回填**到各实现模块——这样方法体里跨模块的裸类名
（例如 MainWindow 里引用某个 Dialog）在运行时也能解析。

依赖方向：runtime -> 各实现模块 -> gui(组装) -> app(启动) -> main(入口)，
单向、无环。
"""
from __future__ import annotations

import importlib

from cr_lbj.runtime import *  # noqa: F401,F403

from cr_lbj.core.bridge import *  # noqa: F401,F403
from cr_lbj.ui.components.spectrum import *  # noqa: F401,F403
from cr_lbj.ui.components.basics import *  # noqa: F401,F403
from cr_lbj.ui.components.info_panels import *  # noqa: F401,F403
from cr_lbj.data.history import *  # noqa: F401,F403
from cr_lbj.ui.dialogs.detail_dialogs import *  # noqa: F401,F403
from cr_lbj.ui.components.history_panel import *  # noqa: F401,F403
from cr_lbj.ui.dialogs.history_dialog import *  # noqa: F401,F403  （v3.2.1 历史记录对话框）
from cr_lbj.ui.dialogs.config_ui import *  # noqa: F401,F403
from cr_lbj.ui.dialogs.log_ui import *  # noqa: F401,F403
from cr_lbj.ui.dialogs.help_dialogs import *  # noqa: F401,F403
from cr_lbj.ui.dialogs.query_ui import *  # noqa: F401,F403  （v3.0 车次/配属查询）
from cr_lbj.ui.components.train_query import *  # noqa: F401,F403
from cr_lbj.ui.windows.main_window import *  # noqa: F401,F403

# 命名空间缝合：让每个实现模块都能看到聚合后的全部名字。
# 只在缺失时补齐，不覆盖模块自身的定义。
_PART_MODULES = [
    'cr_lbj.core.bridge',
    'cr_lbj.ui.components.spectrum',
    'cr_lbj.ui.components.basics',
    'cr_lbj.ui.components.info_panels',
    'cr_lbj.data.history',
    'cr_lbj.ui.dialogs.detail_dialogs',
    'cr_lbj.ui.components.history_panel',
    'cr_lbj.ui.dialogs.history_dialog',
    'cr_lbj.ui.dialogs.config_ui',
    'cr_lbj.ui.dialogs.log_ui',
    'cr_lbj.ui.dialogs.help_dialogs',
    'cr_lbj.ui.dialogs.query_ui',
    'cr_lbj.ui.components.train_query',
    'cr_lbj.ui.windows.main_window',
]
_ALL = {k: v for k, v in globals().items() if not k.startswith('_')}
for _name in _PART_MODULES:
    _m = importlib.import_module(_name)
    for _k, _v in _ALL.items():
        if _k not in _m.__dict__:
            setattr(_m, _k, _v)
