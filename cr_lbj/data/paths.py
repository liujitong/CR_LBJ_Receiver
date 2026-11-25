# -*- coding: utf-8 -*-
"""paths.py — 共享数据的目录解析与「用户可写覆盖层」。

两端（桌面/安卓）的数据都来自 `shared/data/`，但**可更新的数据**不能写进安装目录：
exe 可能在 Program Files 下、_MEIPASS 是临时目录、绿解包目录也可能只读。
所以引入一个用户可写覆盖层，读取顺序（先命中先用）：

    1. 环境变量 CRLBJ_DATA_DIR（测试 / 便携部署：指定目录）
    2. 用户数据目录 %LOCALAPPDATA%/CR-LBJ-Receiver/data（更新器写这里）
    3. 可执行文件同级 shared/data（绿色版：exe 与 shared 并排）
    4. _MEIPASS/shared/data（PyInstaller 打包进来的内置快照）
    5. 仓库根 shared/data（源码运行）

这样「自动更新」只是往第 2 层写文件，内层快照永远保留可回退。
"""

from __future__ import annotations

import os
import sys
from typing import List

APP_DIR_NAME = 'CR-LBJ-Receiver'


def user_data_dir(create: bool = False) -> str:
    """用户可写数据目录（不存在时按需创建）。"""
    env = os.environ.get('CRLBJ_DATA_DIR', '').strip()
    if env:
        d = env
    elif os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(
            os.path.expanduser('~'), 'AppData', 'Local')
        d = os.path.join(base, APP_DIR_NAME, 'data')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(
            os.path.expanduser('~'), '.local', 'share')
        d = os.path.join(base, APP_DIR_NAME, 'data')
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    return d


def bundled_data_dir() -> str:
    """内置快照目录（只读）。"""
    cands: List[str] = []
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.append(os.path.join(exe_dir, 'shared', 'data'))
    except Exception:
        pass
    mei = getattr(sys, '_MEIPASS', None)
    if mei:
        cands.append(os.path.join(str(mei), 'shared', 'data'))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.abspath(os.path.join(here, '..', '..', 'shared', 'data')))
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


def shared_data_dir() -> str:
    """兼容旧接口：内置快照目录（不再用于写入）。"""
    return bundled_data_dir()


def candidates(name: str) -> List[str]:
    """某个数据文件的所有候选路径（覆盖层在前）。"""
    return [os.path.join(user_data_dir(), name),
            os.path.join(bundled_data_dir(), name)]


def data_path(name: str) -> str:
    """实际生效的数据文件路径；都不存在时返回内置目录下的路径（供报错用）。"""
    for p in candidates(name):
        if os.path.isfile(p):
            return p
    return os.path.join(bundled_data_dir(), name)


def is_user_override(path: str) -> bool:
    try:
        return os.path.abspath(path).startswith(os.path.abspath(user_data_dir()))
    except Exception:
        return False
