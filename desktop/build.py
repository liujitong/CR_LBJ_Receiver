#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build.py — CR-LBJ-Receiver 一键构建（v2.6）

用法（在仓库根执行）:
    python desktop/build.py                # 清理 -> 打包 -> 清理过程文件 -> 校验
    python desktop/build.py --keep-data    # 保留 dist 下已有的 history.db（配置本来就会保留）
    python desktop/build.py --reset-config # 连 dist/lbj_config.json 一起清掉（回到首次运行状态）
    python desktop/build.py --no-clean     # 跳过打包前的清理（增量构建，快）

约定：打包**不再动 dist/lbj_config.json**——高德 Key、数据源、主题这些都在里面，
每次重打包都清掉等于让用户重填一遍。只有明确加 --reset-config 才删除。

源码结构（桌面端收敛在 desktop/，shared/docs/tests/tools 留在仓库根）：
    desktop/main.py        程序入口
    desktop/cr_lbj/        应用包（core / data / ui / utils + runtime / gui / app）
    desktop/SDR_LBJ.spec   打包配置；desktop/build.py 本脚本
    文档   docs/           用户手册 / 技术参考 / 架构说明 / 地图与图源 / …（全量清单见 REQUIRED_DOCS）
    产物   dist/           CR-LBJ-Receiver.exe + README.md + docs/（仍在仓库根）
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

DESKTOP = os.path.dirname(os.path.abspath(__file__))   # 桌面工程目录 desktop/
ROOT = os.path.dirname(DESKTOP)                        # 仓库根（shared/docs/tools/dist 所在）
DIST = os.path.join(ROOT, 'dist')
BUILD = os.path.join(ROOT, 'build')
EXE_NAME = 'CR-LBJ-Receiver.exe'

# 构建产物中必须存在的文档（相对 dist/docs）。与仓库 docs/ 目录一一对应，
# 新增/改名文档时同步登记（docs 整目录由 spec 的 copytree 复制进 dist/docs）。
REQUIRED_DOCS = ['用户手册.md', '技术参考.md', '架构说明.md', '地图与图源.md',
                 '车次与配属查询.md', 'USB直连与设备自适应.md', '安卓版说明.md',
                 '安卓构建与环境.md', 'CHANGELOG.md', '验收记录-v3.0.md',
                 '安卓移植日志.md', '安卓模块划分方案.md', 'NOTICE.md']


def log(msg: str) -> None:
    print('[build] ' + msg, flush=True)


def rm(path: str) -> None:
    """删除文件或目录（不存在则忽略）。"""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log(f'删除目录 {os.path.relpath(path, ROOT)}')
        elif os.path.exists(path):
            os.remove(path)
            log(f'删除文件 {os.path.relpath(path, ROOT)}')
    except Exception as e:  # 只提示，不中断
        log(f'警告: 无法删除 {path}: {e}')


def cleanProcessFiles(deep: bool = True) -> None:
    """清理过程性文件。"""
    rm(BUILD)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # 不动 dist / .git / docs / tools / android（安卓工程有自己的构建体系）
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', 'dist', 'docs', 'tools', 'android')]
        if '__pycache__' in dirnames:
            rm(os.path.join(dirpath, '__pycache__'))
            dirnames.remove('__pycache__')
    if deep:
        for name in os.listdir(ROOT):
            if name.endswith('.pyc'):
                rm(os.path.join(ROOT, name))


def cleanDistRunData(keepConfig: bool = True) -> None:
    """清掉 dist 下的运行时产物。

    默认**保留 lbj_config.json**（用户的 Key、数据源、主题都在里面），
    只清历史库与日志类临时文件；keepConfig=False 时才连配置一起删。
    """
    names = ['history.db', 'history.db-journal', 'history.db-wal']
    if not keepConfig:
        names.insert(0, 'lbj_config.json')
    for name in names:
        rm(os.path.join(DIST, name))


def preCleanDistExe() -> bool:
    """打包前先移除旧 EXE，被占用时立刻报错。

    旧 EXE 还在时 PyInstaller 要自己删它：删除被占用文件会失败，而失败发生在
    收集完 4000 多个文件**之后**（约 6 分钟），白等一趟。这里提前用
    os.remove 直接删（绕开回收站），删得掉就说明没锁；删不掉就明确告诉用户
    先关程序，2 秒内返回。
    """
    exe = os.path.join(DIST, EXE_NAME)
    if not os.path.isfile(exe):
        return True
    try:
        os.remove(exe)
        log('已移除旧 EXE（如有正在运行的旧版，关掉后重开即是新版）')
        return True
    except OSError as e:
        log(f'错误: 旧 EXE 无法删除（{e}）')
        log('      CR-LBJ-Receiver 正在运行？请先退出程序再打包。')
        return False


def checkDeps() -> None:
    """打包前确认外观层依赖在不在。

    `ui_kit` 对 qfluentwidgets 做了降级：库不在也能跑，但**外观会退回原生 Qt**
    而且没有任何提示。打包时静默降级最坑——所以在这里显式报出来。
    """
    for mod, pip in (('qfluentwidgets', 'PySide6-Fluent-Widgets'),
                     ('qframelesswindow', 'PySide6-Frameless-Window')):
        try:
            __import__(mod)
            log(f'依赖 {mod}  OK')
        except Exception as e:
            log(f'警告: 缺少 {mod}（{e}）→ 打包出的 exe 会退回原生外观')
            log(f'      安装: pip install {pip}')


def runPyInstaller() -> int:
    # cwd 保持仓库根：PyInstaller 默认 distpath/workpath 相对 cwd，
    # 产物仍落在仓库根 dist/ 与 build/（spec 内路径全部按仓库根解析）。
    cmd = [sys.executable, '-m', 'PyInstaller',
           os.path.join(DESKTOP, 'SDR_LBJ.spec'), '--clean', '--noconfirm']
    log('执行: ' + ' '.join(cmd))
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT)
    log(f'PyInstaller 退出码 {proc.returncode}，耗时 {time.time() - t0:.0f}s')
    return proc.returncode


def verify() -> bool:
    """校验 dist 结构是否符合交付要求。"""
    ok = True
    exe = os.path.join(DIST, EXE_NAME)
    if not os.path.isfile(exe):
        log(f'缺少可执行文件: {exe}')
        return False
    size_mb = os.path.getsize(exe) / 1024 / 1024
    log(f'可执行文件 {EXE_NAME}  {size_mb:.1f} MB')
    if not os.path.isfile(os.path.join(DIST, 'README.md')):
        log('缺少 dist/README.md'); ok = False
    for name in REQUIRED_DOCS:
        p = os.path.join(DIST, 'docs', name)
        if os.path.isfile(p):
            log(f'文档 {name}  OK')
        else:
            log(f'缺少文档: docs/{name}'); ok = False
    # 运行时产物不应出现在交付目录（配置除外——用户的 Key 要留下）
    if os.path.exists(os.path.join(DIST, 'history.db')):
        log('交付目录仍有 history.db（用 --keep-data 可保留）')
    cfg = os.path.join(DIST, 'lbj_config.json')
    if os.path.exists(cfg):
        log('已保留 dist/lbj_config.json（如需重置：python desktop/build.py --reset-config）')
    # v3.0：两端共用的地图页与数据必须真的进了包（漏了地图会降级成"缺少页面文件"）
    if not _check_shared_in_exe(exe):
        ok = False
    return ok


def _check_shared_in_exe(exe: str) -> bool:
    """检查 onefile 包的 CArchive 里有没有 shared/ 资源（不打解包直接读目录表）。"""
    need = ['shared' + os.sep + 'web' + os.sep + 'railmap.html',
            'shared' + os.sep + 'data' + os.sep + 'loco_roster.csv',
            'shared' + os.sep + 'data' + os.sep + 'loco_types.csv',
            'shared' + os.sep + 'data' + os.sep + 'loco_specs.json',
            'shared' + os.sep + 'data' + os.sep + 'places.csv',
            'shared' + os.sep + 'web' + os.sep + 'vendor' + os.sep + 'leaflet' + os.sep + 'leaflet.js',
            ]
    try:
        from PyInstaller.archive.readers import CArchiveReader
        names = set(CArchiveReader(exe).toc.keys())
    except Exception as e:                                # pragma: no cover
        log(f'读取包内目录失败（跳过 shared 校验）：{e}')
        return True
    missing = [n for n in need if n not in names]
    if missing:
        log('包内缺少共享资源（地图/配属数据会降级）：' + ', '.join(missing))
        return False
    n_shared = sum(1 for n in names if n.startswith('shared' + os.sep))
    log(f'共享资源 shared/ 已入包（{n_shared} 个文件）')
    return True


def summary() -> None:
    log('-' * 46)
    src = [('desktop', n) for n in ('main.py', 'cr_lbj', 'SDR_LBJ.spec',
                                    'lbj_config.json', '国铁.ico', 'build.py')]
    src += [('', n) for n in ('LICENSE', 'README.md')]
    log('源码: ' + ', '.join(os.path.join(d, n) if d else n
                             for d, n in src
                             if os.path.exists(os.path.join(ROOT, d, n))))
    _py_n = sum(1 for _, _, fs in os.walk(os.path.join(DESKTOP, 'cr_lbj'))
                for f in fs if f.endswith('.py'))
    log('应用包 desktop/cr_lbj/: %d 个 Python 模块' % _py_n)
    log('工具: tools/rtl (%d 个文件)' %
        len(os.listdir(os.path.join(ROOT, 'tools', 'rtl'))))
    log('文档: docs/ (' + ', '.join(REQUIRED_DOCS) + ')')
    if os.path.isdir(DIST):
        log('产物: dist/ -> ' + ', '.join(sorted(os.listdir(DIST))))


def main() -> int:
    ap = argparse.ArgumentParser(description='CR-LBJ-Receiver 一键构建')
    ap.add_argument('--keep-data', action='store_true',
                    help='连历史库也保留（默认只保留配置，历史库会清掉）')
    ap.add_argument('--reset-config', action='store_true',
                    help='连 dist/lbj_config.json 一起清掉（回到首次运行状态）')
    ap.add_argument('--no-clean', action='store_true',
                    help='跳过打包前的清理（增量构建）')
    args = ap.parse_args()

    os.chdir(ROOT)
    if not args.no_clean:
        log('清理过程文件...')
        cleanProcessFiles()

    checkDeps()
    if not preCleanDistExe():
        return 2
    rc = runPyInstaller()
    if rc != 0:
        log('打包失败，保留 build/ 以便排查')
        return rc

    if not args.keep_data:
        cleanDistRunData(keepConfig=not args.reset_config)

    # 打包后再清一次过程文件：交付目录只留源码/文档/dist
    cleanProcessFiles()
    ok = verify()
    summary()
    log('构建完成' if ok else '构建完成，但校验有问题（见上）')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
