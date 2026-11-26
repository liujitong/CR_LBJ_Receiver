#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置分页名与数据源预设常量。

v3.2.1：历史记录不再常驻主界面，改由「工具 → 历史记录…」的对话框提供
（见 `cr_lbj/ui/dialogs/history_dialog.py`）；本模块只保留配置面板共用的
分页名、数据源类型标签与首次运行预设。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403


# ===========================================================================
# 配置面板
# ===========================================================================
def default_sources(cfg: CoreConfig) -> List[Dict[str, Any]]:
    """首次运行时给出的数据源预设。"""
    base = {'sampleRate': cfg.sampleRate, 'gainDb': cfg.gainDb,
            'ppm': cfg.ppm}
    return [
        dict(base, name='本机 RTL-SDR (USB 直连)', type='rtl_usb',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='本机 RTL-SDR (rtl_tcp 中转)', type='rtl_usb_tcp',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='本地 rtl_tcp', type='rtl_tcp',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='OWRX 服务器', type='owrx',
             host='127.0.0.1', port=8073, dcOffsetHz=0.0),
    ]


SOURCE_TYPE_LABELS = [
    ('本机 USB (直连，推荐)', 'rtl_usb'),
    ('本机 USB (经 rtl_tcp 中转)', 'rtl_usb_tcp'),
    ('局域网 / 本地 RTL-TCP', 'rtl_tcp'),
    ('OWRX (OpenWebRX)', 'owrx'),
]

#: 数据源类型在列表里的短标签
SOURCE_TYPE_TAGS = {'rtl_usb': 'USB', 'rtl_usb_tcp': 'USB*',
                    'rtl_tcp': 'TCP', 'owrx': 'OWRX'}

#: 配置分页名（与 ConfigPanel 里的 page(...) 名字一一对应）。
#: 「配置」菜单直接列这几项，点哪项就单独开哪一页，不再用页签切换。
#: v3.2.1：「数据源配置」「射频设置」合并为「数据源与射频」一页。
CONFIG_PAGES = ['数据源与射频', '到达估算', '地图与车次',
                '解码与界面', '外观主题', '数据更新']


