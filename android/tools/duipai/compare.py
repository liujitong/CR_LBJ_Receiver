#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare.py — 对拍比对器

逐条逐字段比对 C++ lbj_cli 与 Python offline_decode.py 的 JSONL 输出。
比对字段为 C++ 侧输出的解码层字段（时间戳/车次分类/ETA 属业务层，不在
native 对拍范围）。浮点按各自序列化精度留容差。差异必须为 0。

用法:
    python compare.py cli.jsonl py.jsonl
退出码: 0 = 无差异；1 = 有差异。
"""
import json
import math
import sys

# 字段 → 数值容差（%.1f / %.3f / %.6f 序列化精度）
FLOAT_TOL = {
    'rssi': 0.06,
    'afcHz': 0.06,
    'afcErrHz': 0.06,
    'afcScore': 6e-4,
    'latitude': 6e-6,
    'longitude': 6e-6,
}
COMPARABLE = ['train', 'baseTrain', 'prefix', 'direction', 'speed', 'position',
              'loco', 'locoCode', 'route', 'isDetailed', 'routeValid',
              'latitude', 'longitude', 'msgTypeError', 'hasInterference',
              'rawBcd', 'rawAddr', 'rawFunc', 'rawCodewords',
              'rawIsShort', 'rawIsMerged', 'rawIsStandalone',
              'rssi', 'afcHz', 'afcErrHz', 'afcScore']


def norm(v):
    if isinstance(v, bool):
        return int(v)
    return v


def load(path):
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def main():
    cli = load(sys.argv[1])
    py = load(sys.argv[2])
    print(f'C++ 条数 {len(cli)}，Python 条数 {len(py)}')

    diffs = 0
    n = max(len(cli), len(py))
    for i in range(n):
        if i >= len(cli) or i >= len(py):
            print(f'[{i}] 条数不匹配（一侧缺失）')
            diffs += 1
            continue
        c, p = cli[i], py[i]
        for k in COMPARABLE:
            cv, pv = norm(c.get(k)), norm(p.get(k))
            if k in FLOAT_TOL:
                a = cv if isinstance(cv, (int, float)) else None
                b = pv if isinstance(pv, (int, float)) else None
                if (a is None) != (b is None):
                    diffs += 1
                    print(f'[{i}].{k}: C++={cv!r} Python={pv!r}')
                elif a is not None and abs(a - b) > FLOAT_TOL[k]:
                    diffs += 1
                    print(f'[{i}].{k}: C++={cv!r} Python={pv!r}')
            elif cv != pv:
                diffs += 1
                print(f'[{i}].{k}: C++={cv!r} Python={pv!r}')

    if diffs == 0:
        print('✅ 对拍通过：0 差异')
        return 0
    print(f'❌ 对拍失败：{diffs} 处差异')
    return 1


if __name__ == '__main__':
    sys.exit(main())
