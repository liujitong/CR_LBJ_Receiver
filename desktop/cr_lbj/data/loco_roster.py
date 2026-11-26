# -*- coding: utf-8 -*-
"""loco_roster.py — 机车配属查询（车次/机车配属查询功能的桌面端数据层）。

数据全部来自仓库里的 `shared/data/`（与安卓端逐字同一份文件）：

    loco_types.csv    机车代号 → 短型号 / 中文名
    loco_roster.csv   机车型号 + 号段 → 配属单位（路局/机务段）、制造厂
    loco_specs.json   机车型号 → 技术参数（功率/轴式/构造速度…）

三条查询路径对应界面上的三件小事：
    lookup_code(code)          报文里的「机车代号」(如 240) → 车型名/短型号
    lookup(model, number)      短型号 + 机车号 → 配属局段（号段表命中）
    lookup_loco(text, code)    解码结果里的 "HXD1D-0123" + 代号 → 一次拿到全部

设计约定（两端一致）：
    * 型号一律用**短型号**（DF4 / SS4 / HXD1D），与 loco_roster.csv 第一列对齐；
      中文名只用于显示。
    * 号段是**闭区间**，一行一个区间；同一型号内区间不保证不重叠，命中即返回
      第一条，并在结果里带上所有候选（`alternatives`），供界面提示歧义。
    * 找不到号段不等于型号不存在：返回值分 `exact`（号段命中）/`modelOnly`
      （只认出了型号）两种状态，界面据此显示「配属未知」而不是「无此机车」。
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import paths as _paths

_CACHE: Dict[str, Any] = {'key': None, 'types': None, 'roster': None, 'specs': None,
                          'stats': None}

_ROSTER_FILE = 'loco_roster.csv'
_TYPES_FILE = 'loco_types.csv'
_SPECS_FILE = 'loco_specs.json'

# 报文里的「未知型号」占位符，查询时要当作没给
_PLACEHOLDERS = {'', '----', '---', '未知型号', 'None', 'none'}


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------
def shared_dir() -> str:
    """内置快照目录（只读）。实际读取走 `data_path()`，见 cr_lbj/data/paths.py。"""
    return _paths.bundled_data_dir()


def data_path(name: str) -> str:
    """某数据文件当前生效的路径（用户更新过的覆盖层优先）。"""
    return _paths.data_path(name)


def _ensure() -> None:
    key = (_paths.user_data_dir(), _paths.bundled_data_dir())
    if _CACHE['key'] == key:
        return
    _CACHE.update({'key': key, 'types': None, 'roster': None, 'specs': None,
                   'stats': None})


def invalidate() -> None:
    """数据文件被更新后调用，强制下次读盘。"""
    _CACHE.update({'key': None, 'types': None, 'roster': None, 'specs': None,
                   'stats': None})


def available() -> bool:
    """共享数据是否可用（缺文件时界面降级为「未内置配属表」）。"""
    _ensure()
    return os.path.isfile(data_path(_ROSTER_FILE))


def source_info() -> Dict[str, Any]:
    """数据来源信息（界面展示「内置快照 / 已更新」用）。"""
    _ensure()
    out: Dict[str, Any] = {}
    for name in (_ROSTER_FILE, _TYPES_FILE, _SPECS_FILE):
        p = data_path(name)
        out[name] = {
            'path': p,
            'exists': os.path.isfile(p),
            'userOverride': _paths.is_user_override(p),
            'mtime': (os.path.getmtime(p) if os.path.isfile(p) else 0),
        }
    return out


# --------------------------------------------------------------------------
# 机车代号 → 短型号 / 中文名
# --------------------------------------------------------------------------
def _load_types() -> Dict[str, Dict[str, str]]:
    _ensure()
    if _CACHE['types'] is not None:
        return _CACHE['types']
    by_code: Dict[str, Dict[str, str]] = {}
    by_short: Dict[str, Dict[str, str]] = {}
    by_name: Dict[str, Dict[str, str]] = {}
    path = data_path(_TYPES_FILE)
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                if not row or row[0].startswith('#') or row[0] == 'code':
                    continue
                if len(row) < 3:
                    continue
                code, short, name = row[0].strip(), row[1].strip(), row[2].strip()
                item = {'code': code, 'short': short, 'name': name}
                by_code[code] = item
                by_short.setdefault(short.upper(), item)
                by_name.setdefault(name, item)
    except OSError:
        pass
    _CACHE['types'] = {'by_code': by_code, 'by_short': by_short, 'by_name': by_name}
    return _CACHE['types']


def type_name(code: Any) -> str:
    """机车代号 → 中文显示名（查不到返回空串）。"""
    key = str(code if code is not None else '').strip()
    item = _load_types()['by_code'].get(key)
    return item['name'] if item else ''


def short_code(code: Any = None, name: Any = None) -> str:
    """把「代号」或「中文名/短型号」统一成短型号（DF4/SS4/HXD1D）。"""
    t = _load_types()
    if code is not None:
        item = t['by_code'].get(str(code).strip())
        if item and item['short']:
            return item['short'].upper()
    s = str(name or '').strip()
    if not s or s in _PLACEHOLDERS:
        return ''
    item = t['by_short'].get(s.upper())
    if item:
        return item['short'].upper()
    item = t['by_name'].get(s)
    if item:
        return item['short'].upper()
    return s.upper()


# --------------------------------------------------------------------------
# 号段表
# --------------------------------------------------------------------------
def _parse_number(raw: Any) -> Optional[int]:
    s = re.sub(r'[^0-9]', '', str(raw if raw is not None else ''))
    return int(s) if s else None


def _load_roster() -> Dict[str, List[Dict[str, Any]]]:
    _ensure()
    if _CACHE['roster'] is not None:
        return _CACHE['roster']
    idx: Dict[str, List[Dict[str, Any]]] = {}
    rows = 0
    empty_depot = 0
    path = data_path(_ROSTER_FILE)
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                if not row or row[0].startswith('#'):
                    continue
                if len(row) < 4:
                    continue
                model = row[0].strip().upper()
                a, b = _parse_number(row[1]), _parse_number(row[2])
                if not model or a is None or b is None:
                    continue
                depot = row[3].strip() if len(row) > 3 else ''
                remark = row[4].strip() if len(row) > 4 else ''
                maker = row[5].strip() if len(row) > 5 else ''
                if not depot:
                    empty_depot += 1
                idx.setdefault(model, []).append(
                    {'start': min(a, b), 'end': max(a, b), 'depot': depot,
                     'remark': remark, 'maker': maker})
                rows += 1
    except OSError:
        pass
    for v in idx.values():
        v.sort(key=lambda x: x['start'])
    _CACHE['roster'] = idx
    _CACHE['stats'] = {'rows': rows, 'models': len(idx), 'emptyDepot': empty_depot}
    return idx


def stats() -> Dict[str, int]:
    _load_roster()
    return dict(_CACHE['stats'] or {'rows': 0, 'models': 0, 'emptyDepot': 0})


def models() -> List[str]:
    return sorted(_load_roster().keys())


def suggest_models(model: Any, limit: int = 4) -> List[str]:
    """表里没收录该型号时，给出**开头相同**的候选（只作提示，不自动采用）。"""
    key = str(model or '').strip().upper()
    if not key:
        return []
    keys = list(_load_roster().keys())
    pref = [k for k in keys if k != key and (k.startswith(key) or key.startswith(k))]
    pref.sort(key=lambda k: (abs(len(k) - len(key)), k))
    return pref[:limit]


def model_numbers(model: Any) -> List[Dict[str, Any]]:
    """某型号的全部号段（按起号排序）。"""
    return list(_load_roster().get(str(model or '').strip().upper(), []))


def depots() -> List[str]:
    seen = set()
    for v in _load_roster().values():
        for r in v:
            if r['depot']:
                seen.add(r['depot'])
    return sorted(seen)


# --------------------------------------------------------------------------
# 主查询
# --------------------------------------------------------------------------
def lookup(model: Any, number: Any) -> Dict[str, Any]:
    """按短型号 + 机车号查配属。

    返回：
        {
          'ok': bool,            是否至少认出了型号
          'exact': bool,         号段命中（否则只认出型号）
          'model': 短型号, 'number': int|None, 'numberText': 原始号,
          'depot': 配属单位, 'maker': 制造厂, 'remark': 备注,
          'range': 'a-b', 'alternatives': [...], 'reason': 未命中原因
        }
    """
    m = short_code(name=model)
    n = _parse_number(number)
    out: Dict[str, Any] = {
        'ok': False, 'exact': False, 'model': m,
        'number': n, 'numberText': str(number if number is not None else ''),
        'depot': '', 'maker': '', 'remark': '', 'range': '',
        'alternatives': [], 'reason': '',
    }
    if not m:
        out['reason'] = '缺少机车型号'
        return out
    asked = m
    if m not in _load_roster() and m in _MODEL_ALIASES:
        m = _MODEL_ALIASES[m]
        out['aliasFrom'] = asked
    ranges = _load_roster().get(m)
    if not ranges:
        out['reason'] = '配属号段表未收录该型号'
        out['suggest'] = suggest_models(asked)
        return out
    out['model'] = m
    out['ok'] = True
    if n is None:
        out['reason'] = '缺少机车编号（只有车型信息）'
        return out
    hits = [r for r in ranges if r['start'] <= n <= r['end']]
    if not hits:
        out['reason'] = '号段表内无该编号（可能新造/未收录）'
        return out
    first = hits[0]
    out.update({
        'exact': True, 'depot': first['depot'], 'maker': first['maker'],
        'remark': first['remark'],
        'range': '%d-%d' % (first['start'], first['end']),
        'alternatives': [
            {'depot': h['depot'], 'maker': h['maker'],
             'range': '%d-%d' % (h['start'], h['end'])} for h in hits[1:]
        ],
    })
    return out


_LOCO_RE = re.compile(r'^(?P<model>[A-Za-z][A-Za-z0-9\-]*?)\s*[-_ ]?\s*(?P<num>\d{1,6})$')

# 号段表把「东风4B」并入 DF4 统计（DF4 有 2000+ 行，DF4B/DF4R 都在其号段内）。
# 只放**确定合并**的别名，不做泛化的前缀回退——HXD1D 绝不能退成 HXD1。
_MODEL_ALIASES = {'DF4B': 'DF4', 'DF4R': 'DF4'}


def parse_loco_text(text: Any) -> Tuple[str, Optional[str]]:
    """把 "HXD1D-0123" / "HXD1D0123" / "韶山4-0123" 拆成 (型号, 号)。

    型号可能是中文名（韶山4），交给 short_code() 再归一。
    """
    s = str(text or '').strip().replace(' ', '')
    if not s or s in _PLACEHOLDERS:
        return '', None
    m = _LOCO_RE.match(s)
    if not m:
        # "韶山4-0123" 这种中文名开头：用「最后一个非数字块 + 尾号」兜底
        mm = re.match(r'^(?P<model>.*?)[-_]?(?P<num>\d{1,6})$', s)
        if not mm:
            return s, None
        return mm.group('model'), mm.group('num')
    return m.group('model'), m.group('num')


def lookup_loco(loco_text: Any = None, loco_code: Any = None) -> Dict[str, Any]:
    """解码结果 → 配属。`loco_code` 是报文里的机车代号（如 '240'），最可靠。

    优先级：代号 → 型号短码；文本里的型号名兜底。
    """
    model_from_text, num = parse_loco_text(loco_text)
    model = short_code(code=loco_code) if str(loco_code or '').strip() not in _PLACEHOLDERS else ''
    if not model:
        model = short_code(name=model_from_text)
    res = lookup(model, num)
    res['locoText'] = str(loco_text or '')
    res['locoCode'] = str(loco_code or '')
    res['name'] = type_name(loco_code) or res.get('model', '')
    return res


# --------------------------------------------------------------------------
# 机车技术参数（loco_specs.json，桌面端与安卓端共用）
# --------------------------------------------------------------------------
def _load_specs() -> Dict[str, Any]:
    _ensure()
    if _CACHE['specs'] is not None:
        return _CACHE['specs']
    path = data_path(_SPECS_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {'models': {}}
    _CACHE['specs'] = data
    return data


def specs_for(model: Any) -> Dict[str, Any]:
    """短型号 → 技术参数（找不到返回空 dict）。"""
    models_dict = _load_specs().get('models') or {}
    key = short_code(name=model)
    if key in models_dict:
        return dict(models_dict[key])
    # 号段表里常见 "HXD3CA" / "DF4DD" 这种加长写法，退一步做前缀匹配
    for k in sorted(models_dict, key=len, reverse=True):
        if key.startswith(k):
            return dict(models_dict[k])
    return {}


def specs_meta() -> Dict[str, Any]:
    d = _load_specs()
    return {'revision': d.get('revision', ''), 'source': d.get('source', ''),
            'sources': d.get('sources') or []}


def format_depot(res: Dict[str, Any]) -> str:
    """把查询结果压成一行字（界面/日志用）。"""
    if not res.get('ok'):
        return res.get('reason') or '未知'
    head = '%s %s' % (res.get('model', ''), res.get('numberText') or '')
    head = head.strip()
    if res.get('exact'):
        s = '%s → %s' % (head, res.get('depot') or '（原表未标注配属）')
        if res.get('range'):
            s += '（号段 %s）' % res['range']
        return s
    return '%s → 配属未知（%s）' % (head, res.get('reason') or '未命中号段')
