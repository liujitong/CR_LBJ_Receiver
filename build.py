#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build.py — CR-LBJ-Receiver 一键构建（v2.5）

用法:
    python build.py                # 清理 -> 打包 -> 清理过程文件 -> 校验
    python build.py --keep-data    # 保留 dist 下已有的 history.db（配置本来就会保留）
    python build.py --reset-config # 连 dist/lbj_config.json 一起清掉（回到首次运行状态）
    python build.py --no-clean     # 跳过打包前的清理（增量构建，快）

约定：打包**不再动 dist/lbj_config.json**——高德 Key、数据源、主题这些都在里面，
每次重打包都清掉等于让用户重填一遍。只有明确加 --reset-config 才删除。

源码结构（v2.5 起按职责分层）：
    main.py            程序入口
    cr_lbj/            应用包（core / data / ui / utils + runtime / gui / app）
    SDR_LBJ.spec       打包配置；build.py 本脚本
    文档   docs/       用户手册 / 高德地图配置手册 / 技术参考 / 架构说明
    产物   dist/       CR-LBJ-Receiver.exe + README.md + docs/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist')
BUILD = os.path.join(ROOT, 'build')
EXE_NAME = 'CR-LBJ-Receiver.exe'

# 构建产物中必须存在的文档（相对 dist/docs）
REQUIRED_DOCS = ['用户手册.md', '高德地图配置手册.md', '技术参考.md', '架构说明.md']


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
        # 不动 dist / .git / docs / tools
        dirnames[:] = [d for d in dirnames
                       if d not in ('.git', 'dist', 'docs', 'tools')]
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
    cmd = [sys.executable, '-m', 'PyInstaller', 'SDR_LBJ.spec',
           '--clean', '--noconfirm']
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
        log('已保留 dist/lbj_config.json（如需重置：python build.py --reset-config）')
    return ok


def summary() -> None:
    log('-' * 46)
    src = ['main.py', 'cr_lbj', 'SDR_LBJ.spec', 'lbj_config.json',
           '国铁.ico', 'LICENSE', 'README.md', 'build.py']
    log('源码: ' + ', '.join(n for n in src if os.path.exists(os.path.join(ROOT, n))))
    _py_n = sum(1 for _, _, fs in os.walk(os.path.join(ROOT, 'cr_lbj'))
                for f in fs if f.endswith('.py'))
    log('应用包 cr_lbj/: %d 个 Python 模块' % _py_n)
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
