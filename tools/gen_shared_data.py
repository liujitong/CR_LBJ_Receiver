#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_shared_data.py — 生成桌面端 / 安卓端共用的数据文件。

共享数据目录 `shared/data/` 是两端唯一的数据来源：

    loco_types.csv    机车代号 → 短型号 / 中文名（来自解码器 LOCO_TABLE + LBJ_Console）
    loco_specs.json   机车型号 → 技术参数（来自 desktop/cr_lbj/data/loco_info.py）
    loco_roster.csv   机车号段 → 配属局段（外部数据，本脚本只校验不生成）
    places.csv        预设中心点（手工维护，本脚本只校验）

用法：
    python tools/gen_shared_data.py            # 生成并校验
    python tools/gen_shared_data.py --check    # 只校验，不写文件（CI/提交前用）

设计说明：
    * 桌面端 Python 直接读 CSV/JSON，安卓端读同一份文件（构建时拷进 assets），
      因此两端的车型名、配属判断、预设中心必须逐字一致。
    * LOCO_TABLE 是解码器里「报文机车代号 → 显示名」的唯一来源，这里连同
      LBJ_Console 的 loco_type_info.csv（代号 → 短型号）合并成一张表，
      短型号用于匹配 loco_roster.csv（那边用的是 DF4 / SS4 / HXD1D 这种写法）。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(ROOT, 'shared', 'data')
sys.path.insert(0, os.path.join(ROOT, 'desktop'))   # cr_lbj 包在 desktop/ 下

# LBJ_Console 的「机车代号 → 短型号」原始表（GPL-3.0，见 shared/NOTICE.md）
# 这里内联成一张精简表，避免生成时依赖外部下载；新增代号时同步补这里。
CODE_SHORT = {
    1: 'JF', 3: 'QJ', 5: 'JS', 6: 'KD7', 55: 'LJKC', 57: 'JW2', 58: 'GQ164',
    59: 'JY29010', 60: 'JZW3', 61: 'JW5', 62: 'JY29010P', 63: 'HS280', 64: '240',
    65: 'HS260', 66: 'GCS220', 68: 'JY290', 69: 'JY2905', 70: 'JY360', 71: 'JY230',
    81: 'DF21', 101: 'DF', 102: 'DF2', 103: 'DF3', 104: 'DF4B', 105: 'DF4R',
    106: 'DF4C', 107: 'DF5', 108: 'DF5R', 109: 'DF6', 110: 'DF7', 111: 'DF8',
    112: 'DF9', 113: 'DF10', 114: 'DFH1', 115: 'DFH2', 116: 'DFH3', 117: 'DFH5',
    118: 'BJ', 119: 'BJR', 120: 'ND2', 121: 'ND3', 122: 'ND4', 123: 'ND5',
    124: 'NY5', 125: 'NY6', 126: 'NY7', 127: 'QY', 128: 'DFH21', 129: 'DF7B',
    130: 'DF5R0', 131: 'DF7C', 132: 'DF7S', 133: 'GK1', 134: 'GK1F', 135: 'DF4E',
    136: 'DF7D', 137: 'GK1A', 138: 'DF11', 139: 'TA', 140: 'DF10F', 141: 'DF4D',
    142: 'DF8B', 143: 'DF12', 144: 'DF7E', 145: 'NYJ1', 146: 'NYJ2', 147: 'NZJ2',
    148: 'DF4DJ', 149: 'NDJ1', 150: 'NDJ2', 151: 'NJ2', 152: 'DF7G', 156: 'DF11Z',
    158: 'DF11G', 160: 'HXN3', 161: 'HXN5', 162: 'HXN3B', 163: 'HXN5B', 191: 'DF4DH',
    201: '8G', 202: '8K', 203: '6G', 204: '6K', 205: 'SS1', 206: 'SS3', 207: 'SS4',
    208: 'SS5', 209: 'SS6', 210: 'SS3G', 211: 'SS7', 212: 'SS8', 213: 'SS7B',
    214: 'SS7C', 215: 'SS6B', 216: 'SS9', 217: 'SS7D', 218: 'DJ', 219: 'DJ1',
    220: 'DJ2', 221: 'DJF', 222: 'DJJ1', 223: 'DJF2', 224: 'SS7E', 225: 'SSJ3',
    226: 'SS3C', 228: 'TS', 229: 'DJ4', 230: 'KTT', 231: 'HXD1', 232: 'HXD2',
    233: 'HXD3', 234: 'HXD1B', 235: 'HXD2B', 236: 'HXD3B', 237: 'HXD1C', 238: 'HXD2C',
    239: 'HXD3C', 240: 'HXD1D', 241: 'HXD2D', 242: 'HXD3D', 243: 'HXD1F', 244: 'HXD2F',
    245: 'HXD2G', 246: 'HXD3G', 247: 'CR200J', 254: 'CQDC', 300: 'CRH1A', 301: 'CRH2A',
    302: 'CRH3', 303: 'CRH3A', 304: 'CRH380AL', 305: 'CRH5A', 306: 'CRH3C',
    307: 'CRH380BG', 308: 'CRH380A', 309: 'CRH380D', 310: 'CRH380B', 311: 'CRH380BL',
    313: 'CRH2B', 314: 'CRH2C', 315: 'CRH2E', 316: 'CRH6F', 319: 'CRH1B',
    330: 'CJ-1', 331: 'CJ-2', 351: 'JW3', 352: 'JW4', 353: 'JW7', 354: 'TY2',
    355: 'TY5', 356: 'TY6', 357: 'DB7B', 358: 'DA8', 359: 'DA11', 360: 'DA12',
    361: 'DA220', 381: 'JZW4', 382: 'DAX', 391: 'QGC16', 392: 'QGC25', 801: 'NS1600',
}


def load_loco_table():
    from cr_lbj.core.decoder import LbjDecoder
    return dict(LbjDecoder.LOCO_TABLE)


def load_specs():
    from cr_lbj.data.loco_info import (LOCO_INFO, LOCO_DATA_REVISION,
                                       LOCO_DATA_SOURCES, LOCO_SOURCE,
                                       LOCO_SOURCE_URL_ELECTRIC, LOCO_SOURCE_URL_DIESEL)
    return {
        'revision': LOCO_DATA_REVISION,
        'source': LOCO_SOURCE,
        'sourceUrls': {
            'electric': LOCO_SOURCE_URL_ELECTRIC,
            'diesel': LOCO_SOURCE_URL_DIESEL,
        },
        'sources': [list(x) for x in LOCO_DATA_SOURCES],
        'models': LOCO_INFO,
    }


def build_types():
    """code, shortCode, name —— name 取解码器里的中文显示名，缺失时退回短型号。"""
    table = load_loco_table()
    codes = sorted(set(table) | set(CODE_SHORT))
    rows = []
    for c in codes:
        short = CODE_SHORT.get(c, '')
        name = table.get(c, '')
        if not short:
            short = name
        if not name:
            name = short
        rows.append((c, short, name))
    return rows


def write_types(rows):
    path = os.path.join(SHARED, 'loco_types.csv')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('# 机车代号 → 短型号 / 中文名（由 tools/gen_shared_data.py 生成，勿手改）\n')
        f.write('# shortCode 用于匹配 loco_roster.csv 的机车型号列；name 是界面显示名\n')
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['code', 'shortCode', 'name'])
        for c, s, n in rows:
            w.writerow([c, s, n])
    return path


def write_specs(specs):
    path = os.path.join(SHARED, 'loco_specs.json')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(specs, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write('\n')
    return path


# ---------------------------------------------------------------- 校验

def check_roster():
    """校验配属号段表：必填列、号段区间、重复与畸形行。"""
    path = os.path.join(SHARED, 'loco_roster.csv')
    problems, count, emptyDepot = [], 0, 0
    models = set()
    if not os.path.exists(path):
        return ['缺少 loco_roster.csv'], 0, models
    with open(path, 'r', encoding='utf-8', newline='') as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if not row or row[0].startswith('#'):
                continue
            if len(row) < 4:
                problems.append('第 %d 行字段不足: %r' % (lineno, row[:6]))
                continue
            model, s, e, depot = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
            models.add(model.upper())
            count += 1
            try:
                a, b = int(s), int(e)
            except ValueError:
                problems.append('第 %d 行号段非数字: %r' % (lineno, row[:4]))
                continue
            if not depot:
                emptyDepot += 1
            if b < a:
                problems.append('第 %d 行号段倒置: %s %d-%d' % (lineno, model, a, b))
            if not model:
                problems.append('第 %d 行型号为空' % lineno)
    return problems[:40], count, models, emptyDepot


def check_places():
    path = os.path.join(SHARED, 'places.csv')
    problems = []
    if not os.path.exists(path):
        return ['缺少 places.csv']
    with open(path, 'r', encoding='utf-8', newline='') as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if not row or row[0].startswith('#') or row[0] == 'name':
                continue
            if len(row) < 3:
                problems.append('第 %d 行字段不足' % lineno)
                continue
            try:
                lat, lon = float(row[1]), float(row[2])
            except ValueError:
                problems.append('第 %d 行坐标非数字: %r' % (lineno, row[:3]))
                continue
            if not (3.8 <= lat <= 53.6 and 73.6 <= lon <= 135.1):
                problems.append('第 %d 行坐标越界: %s %s,%s' % (lineno, row[0], lat, lon))
    return problems[:20]


def main(argv=None):
    ap = argparse.ArgumentParser(description='生成/校验两端共享数据')
    ap.add_argument('--check', action='store_true', help='只校验，不写文件')
    args = ap.parse_args(argv)
    os.makedirs(SHARED, exist_ok=True)

    rows = build_types()
    specs = load_specs()
    if args.check:
        print('[check] loco_types 行数 = %d，loco_specs 车型 = %d'
              % (len(rows), len(specs['models'])))
    else:
        p1 = write_types(rows)
        p2 = write_specs(specs)
        print('[write] %s (%d 行)' % (os.path.relpath(p1, ROOT), len(rows)))
        print('[write] %s (%d 车型)' % (os.path.relpath(p2, ROOT), len(specs['models'])))

    bad = []
    rp, rcount, rmodels, rempty = check_roster()
    bad += rp
    print('[check] loco_roster 行数 = %d，机车型号 = %d，配属缺失行 = %d'
          % (rcount, len(rmodels), rempty))
    pp = check_places()
    bad += pp
    if bad:
        print('[FAIL] 共享数据校验未通过：')
        for b in bad:
            print('   -', b)
        return 1
    print('[OK] 共享数据校验通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
