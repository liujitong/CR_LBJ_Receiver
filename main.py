#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CR-LBJ-Receiver 程序入口。

源码运行:  python main.py [选项]
打包运行:  PyInstaller 以本文件为入口（见 SDR_LBJ.spec）
"""
import sys

from cr_lbj.app import main

if __name__ == '__main__':
    sys.exit(main())
