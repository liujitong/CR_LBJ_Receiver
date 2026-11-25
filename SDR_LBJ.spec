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

# 随包附带 RTL-SDR 官方命令行工具（项目内 tools/rtl），实现“插上即用”
_ROOT = os.path.dirname(os.path.abspath(
    globals().get('SPEC') or globals().get('SPECPATH') or '.'))
_LOCAL_TOOLS = os.path.join(_ROOT, 'tools', 'rtl')
_LEGACY_TOOLS = os.path.normpath(os.path.join(_ROOT, '..', '..', 'RTL_TCP_Server'))
_TOOLS = _LOCAL_TOOLS if os.path.isdir(_LOCAL_TOOLS) else _LEGACY_TOOLS
_RTL_NAMES = ['rtl_tcp.exe', 'rtl_test.exe', 'rtlsdr.dll', 'msvcr100.dll',
              'pthreadVC2.dll', 'README.txt']
_RTL_DATAS = [(os.path.join(_TOOLS, n), 'rtl')
              for n in _RTL_NAMES if os.path.exists(os.path.join(_TOOLS, n))]
print('[spec] RTL 工具目录: %s (%d 个文件)' % (_TOOLS, len(_RTL_DATAS)))

# 未使用的重型依赖：本机环境装了大量科学计算/ML 包，若不排除会被连带收进
# 单文件 EXE（实测可达 575 MB）。这些包与 LBJ 解码、地图显示均无关。
_PY_EXCLUDES = [
    'torch', 'torchvision', 'torchaudio', 'tensorboard', 'accelerate',
    'transformers', 'sentencepiece', 'onnx', 'onnxruntime',
    'pandas', 'pyarrow', 'h5py', 'pyspark', 'jpype', 'py4j',
    'sklearn', 'numba', 'llvmlite', 'sympy', 'networkx',
    'shapely', 'pyproj', 'pyogrio', 'geopandas', 'fiona', 'rasterio',
    'matplotlib', 'tkinter', 'IPython', 'notebook', 'jupyter', 'nbconvert',
    'pytest', 'sphinx', 'setuptools._distutils',
]

# 未使用的 Qt 模块（WebEngine 依赖 QtQuick/Qml，但不需要 3D/图表/多媒体等）
_QT_DROP_PREFIX = (
    'qt63d', 'qt6charts', 'qt6datavisualization', 'qt6graphs',
    'qt6quick3d', 'qt6multimedia', 'qt6pdf', 'qt6sensors', 'qt6serialport',
    'qt6test', 'qt6texttospeech', 'qt6virtualkeyboard', 'qt6remoteobjects',
    'qt6scxml', 'qt6statemachine', 'qt6spatialaudio', 'qt6webview',
    'qt6quicktest', 'qt6quickvectorimage', 'qt6shadertools',
    'qt6labsstylekit', 'qt6quicktimeline',
)
_QT_DROP_KEYWORDS = (
    'quick3d', 'charts', 'datavisualization', 'graphsplugin', 'multimedia',
    'pdf', 'sensor', 'vkb', 'virtualkeyboard', 'texttospeech', 'remoteobjects',
    'scxml', 'statemachine', 'spatialaudio', 'webview', 'testplugin',
    'quicktest', 'vectorimage', '3d', 'shadertools', 'stylekit', 'timeline',
)


def _keep_qt(name: str) -> bool:
    low = name.lower().replace('/', '\\')
    base = low.rsplit('\\', 1)[-1]
    if base.startswith(_QT_DROP_PREFIX):
        return False
    if base.startswith('qt6') or base.endswith('plugin.dll'):
        return not any(k in base for k in _QT_DROP_KEYWORDS)
    return True


a = Analysis(
    ['main.py'],                    # v2.5 分层后统一入口
    pathex=[],
    binaries=[],
    datas=[
        # 只读资源打包到 _MEIPASS
        ('国铁.ico', '.'),
        ('lbj_config.json', '.'),   # 初始配置模板
        ('cr_lbj/data/loco_info.py', '.'),  # 机车信息映射表（便于查阅/核对）
        ('README.md', '.'),
        ('docs', 'docs'),           # 用户手册 / 技术参考 / 架构说明 / 安卓文档
        # v3.0：桌面与安卓共用的地图页与数据（配属号段表 / 车型参数 / 预设中心）
        ('shared', 'shared'),
    ] + _RTL_DATAS,
    hiddenimports=[
        # PySide6 插件
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick',
        # 外观层（v2.4）：qfluentwidgets 缺了不会崩，但会静默降级成原生外观，
        # 所以必须显式列出来；qframelesswindow / darkdetect 是它的硬依赖。
        'qfluentwidgets',
        'qfluentwidgets.common',
        'qfluentwidgets.components',
        'qfluentwidgets.window',
        'qframelesswindow',
        'darkdetect',
        # 分层包（v2.5）：入口会静态导入，这里显式列出全部实现模块更保险，
        # 尤其是 gui.py 用 importlib.import_module 取模块对象的那些
        'cr_lbj',
        'cr_lbj.runtime',
        'cr_lbj.gui',
        'cr_lbj.app',
        'cr_lbj.core.decoder',
        'cr_lbj.core.usb_direct',
        'cr_lbj.core.source_stats',
        'cr_lbj.core.rtl_paths',
        'cr_lbj.core.bridge',
        'cr_lbj.data.loco_info',
        'cr_lbj.data.history',
        'cr_lbj.ui.theme',
        'cr_lbj.ui.widgets',
        'cr_lbj.ui.map_panel',
        'cr_lbj.ui.components.spectrum',
        'cr_lbj.ui.components.basics',
        'cr_lbj.ui.components.info_panels',
        'cr_lbj.ui.components.history_panel',
        'cr_lbj.ui.components.train_query',
        'cr_lbj.ui.dialogs.detail_dialogs',
        'cr_lbj.ui.dialogs.config_ui',
        'cr_lbj.ui.dialogs.log_ui',
        'cr_lbj.ui.dialogs.help_dialogs',
        'cr_lbj.ui.windows.main_window',
        'cr_lbj.utils.helpers',
        # v3.0 新增：地图宿主 / 配置扩展 / 数据更新 / 查询对话框 / 数据层
        'cr_lbj.ui.map_host',
        'cr_lbj.ui.config_ext',
        'cr_lbj.ui.data_update',
        'cr_lbj.ui.ui_threads',
        'cr_lbj.ui.dialogs.query_ui',
        'cr_lbj.data.loco_roster',
        'cr_lbj.data.train_info',
        'cr_lbj.data.updater',
        'cr_lbj.data.paths',
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
    ] + _PY_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 剔除未用到的 Qt 模块二进制，减小单文件体积
_dropped = [x for x in a.binaries if not _keep_qt(x[0])]
if _dropped:
    print('[spec] 剔除 Qt 模块 %d 个' % len(_dropped))
a.binaries = TOC([x for x in a.binaries if _keep_qt(x[0])])

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

# ---------------------------------------------------------------------------
# 打包后处理：把文档复制到 EXE 同级目录
# 内嵌在 _MEIPASS 里的文档解压后是临时目录，用户看不到；这里再放一份可直接打开。
# spec 是顺序执行的脚本，下列代码在 EXE() 构建完成后运行。
# ---------------------------------------------------------------------------
import shutil

_OUT = os.path.join(_ROOT, 'dist')
if os.path.isdir(_OUT):
    _src_docs = os.path.join(_ROOT, 'docs')
    if os.path.isdir(_src_docs):
        shutil.copytree(_src_docs, os.path.join(_OUT, 'docs'), dirs_exist_ok=True)
    _readme = os.path.join(_ROOT, 'README.md')
    if os.path.isfile(_readme):
        shutil.copy2(_readme, os.path.join(_OUT, 'README.md'))
    print('[spec] 文档已复制到 dist/')

