#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录 / 配置面板共用的常量（v3.2.4 起由 `cr_lbj.runtime` 统一提供）。

v3.1.1：历史记录不再常驻主界面，改由「工具 → 历史记录…」的对话框提供
（见 `cr_lbj/ui/dialogs/history_dialog.py`）。

v3.2.4：`CONFIG_PAGES` / `SOURCE_TYPE_LABELS` / `SOURCE_TYPE_TAGS` /
`default_sources()` 已移到 `cr_lbj/runtime.py`。原因：`config_ui.py` 与
`main_window.py` 是 `from cr_lbj.runtime import *`，并不导入本模块，留在
这里会让它们 `NameError`（打开配置对话框直接崩）。本模块保留为兼容壳，
`gui.py` 的 `from ...history_panel import *` 仍可照常工作。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403