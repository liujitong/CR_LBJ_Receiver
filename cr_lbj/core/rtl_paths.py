#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RTL-SDR 运行时文件定位（rtl_tcp.exe / rtl_test.exe / rtlsdr.dll）。

源码运行、打包成 exe 运行、以及把工具包放在 RTL_TCP_Server 子目录这三种
情况都要能找到文件，因此按「可执行文件目录 → PyInstaller 临时目录 → 本模块
所在目录 → 当前工作目录」的顺序逐个向上回溯若干级，把每级下的
``tools/rtl``、``rtl``、``RTL_TCP_Server`` 子目录也纳入搜索。

本模块只依赖标准库，不引用项目内其他模块，可被 core 层任意模块导入。
"""
from __future__ import annotations

import os
import sys
import shutil
from typing import List, Optional


def runtime_dirs() -> List[str]:
    """返回可能存放 RTL-SDR 工具与 DLL 的目录（按优先级，已去重）。"""
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            roots.append(os.path.join(meipass, 'rtl'))
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    roots.append(os.getcwd())
    dirs = []
    for root in roots:
        p = os.path.abspath(root)
        for _ in range(6):  # 逐级向上，兼容 tools/rtl、RTL_TCP_Server 与程序目录
            dirs += [p, os.path.join(p, 'tools', 'rtl'),
                     os.path.join(p, 'rtl'),
                     os.path.join(p, 'RTL_TCP_Server')]
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
    out = []
    for d in dirs:
        d = os.path.abspath(d)
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def findRtlFile(name: str) -> Optional[str]:
    """在运行时目录里查找任意 RTL-SDR 相关文件（exe 或 dll），找不到返回 None。"""
    for d in runtime_dirs():
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def find_rtl_tool(name: str) -> Optional[str]:
    """查找 rtl_tcp.exe / rtl_test.exe 等工具，找不到返回 None。"""
    exe = name if name.lower().endswith('.exe') else name + '.exe'
    p = findRtlFile(exe)
    if p:
        return p
    return shutil.which(exe) or shutil.which(name)


def findRtlsdrDll() -> Optional[str]:
    """查找 librtlsdr 动态库（Windows 为 rtlsdr.dll，Linux/macOS 为 so/dylib）。"""
    if os.name == 'nt':
        names = ['rtlsdr.dll']
    elif sys.platform == 'darwin':
        names = ['librtlsdr.dylib', 'librtlsdr.0.dylib']
    else:
        names = ['librtlsdr.so.0', 'librtlsdr.so']
    for name in names:
        p = findRtlFile(name)
        if p:
            return p
    # 系统里装过 librtlsdr 的情况
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    return None
