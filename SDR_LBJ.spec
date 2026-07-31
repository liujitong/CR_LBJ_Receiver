# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — CR-LBJ-Receiver 单体 EXE 打包配置。

构建: pyinstaller SDR_LBJ.spec --clean
输出: dist/CR-LBJ-Receiver.exe (单文件)

运行时行为:
  - 图标从 _MEIPASS 加载 (只读)
  - lbj_config.json 作为初始模板打包到 _MEIPASS
    首次运行时复制到 EXE 同级目录 (用户可修改)
  - history.db 在 EXE 同级目录创建 (SQLite 数据库)
"""

import os

block_cipher = None

a = Analysis(
    ['SDR_ALL_LBJ_GUI.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 只读资源打包到 _MEIPASS
        ('国铁.ico', '.'),
        ('lbj_config.json', '.'),   # 初始配置模板
        ('loco_info.py', '.'),      # 机车信息映射表
    ],
    hiddenimports=[
        # PySide6 插件
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        # pyqtgraph
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        # scipy 信号处理 + 数组 API 兼容层
        'scipy.signal',
        'scipy.signal._firfilters',
        'scipy.signal._signaltools',
        'scipy._lib._array_api',
        'scipy._external.array_api_compat',
        'scipy._external.array_api_compat.numpy',
        'scipy._external.array_api_compat.numpy.fft',
        'scipy._external.array_api_compat.numpy.linalg',
        'scipy._external.array_api_compat.numpy.typing',
        # numpy
        'numpy',
        'numpy.core._multiarray_umath',
        'numpy.fft',
        'numpy.linalg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大模块
        'matplotlib',
        'tkinter',
        'pytest',
        'IPython',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CR-LBJ-Receiver',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'python3.dll',
        'python314.dll',
        'PySide6.QtCore.dll',
        'PySide6.QtGui.dll',
        'PySide6.QtWidgets.dll',
        'PySide6.QtNetwork.dll',
    ],
    runtime_tmpdir=None,
    console=False,          # GUI 程序，不显示控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='国铁.ico',
)
