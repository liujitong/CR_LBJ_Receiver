#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CR-LBJ-Receiver 程序入口。

源码运行:  python desktop/main.py [选项]   # 仓库根执行；desktop/ 内执行 python main.py 亦可
打包运行:  PyInstaller 以本文件为入口（见 desktop/SDR_LBJ.spec）
"""
import sys

from cr_lbj.app import main

if __name__ == '__main__':
    sys.exit(main())
