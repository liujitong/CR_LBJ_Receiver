# -*- coding: utf-8 -*-
"""train_info.py — 车次查询（桌面端与安卓端同一套字段语义）。

两条数据源，各有长处，界面上合并展示：

    RailGo  https://data.railgo.zenglingkun.cn/api/train/query?train=G7
            · 零鉴权、CORS *、返回列车等级 / 担当局 / 客运段 / 配属段 / 车型
              / 时刻表 / 开行日 / 交路——「车次查询」要的字段它基本都有；
            · 个人托管服务，可能随时不可用，所以只做**首选**，失败自动退回 12306。
    12306   search.12306.cn 查 train_no → kyfw.12306.cn 查时刻表
            · 官方、稳定，但没有担当/配属信息。

设计约定：
    * 全部走标准库 urllib（桌面端打包不引入新依赖，安卓端照抄字段即可）。
    * 任一来源失败都不抛异常，返回 {'ok': False, 'error': ...}，界面据此提示。
    * 结果字段名与安卓端 Kotlin 数据类一一对应（见 docs/车次与配属查询.md）。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as _date, datetime, timedelta
from typing import Any, Dict, List, Optional

RAILGO_URL = 'https://data.railgo.zenglingkun.cn/api/train/query'
SEARCH_12306_URL = 'https://search.12306.cn/search/v1/train/search'
DETAIL_12306_URL = 'https://kyfw.12306.cn/otn/queryTrainInfo/query'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

_TRAIN_RE = re.compile(r'^[A-Za-z]{0,2}\d{1,5}$')


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def normalize_train(text: Any) -> str:
    """车次号规整：去空格、去全角、字母大写。`g 7` → `G7`。"""
    s = str(text or '').strip().replace(' ', '').replace('　', '')
    return s.upper()


def is_train_code(text: Any) -> bool:
    return bool(_TRAIN_RE.match(normalize_train(text)))


def _http_get_json(url: str, timeout: float = 10.0,
                   headers: Optional[Dict[str, str]] = None) -> Any:
    hdrs = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    return json.loads(raw)


def _err(source: str, msg: str) -> Dict[str, Any]:
    return {'ok': False, 'source': source, 'error': msg}


def _friendly(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return '服务返回 HTTP %d' % exc.code
    if isinstance(exc, urllib.error.URLError):
        return '网络不可达（%s）' % (getattr(exc, 'reason', '') or '')
    if isinstance(exc, TimeoutError) or 'timed out' in str(exc):
        return '请求超时'
    if isinstance(exc, ValueError):
        return '返回内容不是合法 JSON'
    return '请求失败：%s' % (exc,)


def _blank() -> Dict[str, Any]:
    return {
        'ok': False, 'source': '', 'error': '',
        'train': '', 'numberFull': [], 'category': '',
        'bureau': '', 'runner': '', 'carOwner': '', 'car': '',
        'rundays': [], 'rundaysCount': 0, 'diagramType': '',
        'diagram': [], 'stops': [],
        'start': '', 'end': '', 'startTime': '', 'endTime': '',
        'distance': None, 'queryDate': '',
    }


# --------------------------------------------------------------------------
# RailGo
# --------------------------------------------------------------------------
def query_railgo(train: str, timeout: float = 10.0) -> Dict[str, Any]:
    t = normalize_train(train)
    if not is_train_code(t):
        return _err('railgo', '车次号格式不对：%s' % (train or '空'))
    url = '%s?train=%s' % (RAILGO_URL, urllib.parse.quote(t))
    try:
        d = _http_get_json(url, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - 任何失败都要变成可展示的文案
        return _err('railgo', _friendly(e))
    if not isinstance(d, dict) or not d.get('number'):
        return _err('railgo', '未查询到车次 %s' % t)

    out = _blank()
    out.update({
        'ok': True, 'source': 'railgo',
        'train': str(d.get('number') or t),
        'numberFull': [str(x) for x in (d.get('numberFull') or [])],
        'category': str(d.get('type') or ''),
        'bureau': str(d.get('bureauName') or ''),
        'runner': str(d.get('runner') or ''),
        'carOwner': str(d.get('carOwner') or ''),
        'car': str(d.get('car') or ''),
        'rundays': [str(x) for x in (d.get('rundays') or [])],
        'diagramType': str(d.get('diagramType') or ''),
    })
    out['rundaysCount'] = len(out['rundays'])

    stops: List[Dict[str, Any]] = []
    for i, s in enumerate(d.get('timetable') or []):
        if not isinstance(s, dict):
            continue
        stops.append({
            'no': i + 1,
            'station': str(s.get('station') or ''),
            'telecode': str(s.get('stationTelecode') or ''),
            'arrive': str(s.get('arrive') or ''),
            'depart': str(s.get('depart') or ''),
            'stop': int(s.get('stopTime') or 0),
            'day': int(s.get('day') or 0),
            'distance': s.get('distance'),
            'speed': s.get('speed') or 0,
        })
    out['stops'] = stops
    if stops:
        out['start'] = stops[0]['station']
        out['startTime'] = stops[0]['depart'] or stops[0]['arrive']
        out['end'] = stops[-1]['station']
        out['endTime'] = stops[-1]['arrive'] or stops[-1]['depart']
        try:
            out['distance'] = float(stops[-1].get('distance'))
        except (TypeError, ValueError):
            out['distance'] = None

    diagram: List[Dict[str, Any]] = []
    for seg in d.get('diagram') or []:
        if not isinstance(seg, dict):
            continue
        frm = seg.get('from') or []
        to = seg.get('to') or []
        diagram.append({
            'number': str(seg.get('number') or ''),
            'fromStation': str(frm[0]) if len(frm) > 0 else '',
            'fromTime': str(frm[1]) if len(frm) > 1 else '',
            'toStation': str(to[0]) if len(to) > 0 else '',
            'toTime': str(to[1]) if len(to) > 1 else '',
        })
    out['diagram'] = diagram
    return out


# --------------------------------------------------------------------------
# 12306
# --------------------------------------------------------------------------
def _today() -> str:
    return _date.today().strftime('%Y%m%d')


def query_12306(train: str, dateStr: Optional[str] = None,
                timeout: float = 10.0) -> Dict[str, Any]:
    """走 12306 两张表：先搜 train_no，再查时刻表。没有担当/配属字段。"""
    t = normalize_train(train)
    if not is_train_code(t):
        return _err('12306', '车次号格式不对：%s' % (train or '空'))
    ds = (dateStr or _today()).replace('-', '')
    try:
        search = _http_get_json(
            '%s?keyword=%s&date=%s' % (SEARCH_12306_URL, urllib.parse.quote(t), ds),
            timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return _err('12306', _friendly(e))
    rows = (search or {}).get('data') or []
    if not search.get('status') or not rows:
        return _err('12306', '12306 未查询到车次 %s（%s）' % (t, ds))
    first = rows[0]
    trainNo = str(first.get('train_no') or '')
    trainCode = str(first.get('station_train_code') or t)
    detailDate = '%s-%s-%s' % (ds[:4], ds[4:6], ds[6:8])
    try:
        detail = _http_get_json(
            '%s?leftTicketDTO.train_no=%s&leftTicketDTO.train_date=%s&rand_code='
            % (DETAIL_12306_URL, urllib.parse.quote(trainNo), detailDate),
            timeout=timeout,
            headers={'Referer': 'https://kyfw.12306.cn/otn/leftTicket/init'})
    except Exception as e:  # noqa: BLE001
        return _err('12306', _friendly(e))
    data = ((detail or {}).get('data') or {}).get('data') or []
    if not detail.get('status') or not data:
        return _err('12306', '12306 时刻表为空（%s）' % trainCode)

    out = _blank()
    out.update({'ok': True, 'source': '12306', 'train': trainCode,
                'queryDate': ds, 'numberFull': [trainCode]})
    stops = []
    for s in data:
        stops.append({
            'no': int(s.get('station_no') or 0),
            'station': str(s.get('station_name') or ''),
            'telecode': '',
            'arrive': str(s.get('arrive_time') or '----'),
            'depart': str(s.get('start_time') or '----'),
            'stop': _stop_minutes(s.get('arrive_time'), s.get('start_time')),
            'day': int(s.get('arrive_day_diff') or 0),
            'distance': None,
            'speed': 0,
        })
    out['stops'] = stops
    if stops:
        out['start'] = stops[0]['station']
        out['startTime'] = stops[0]['depart']
        out['end'] = stops[-1]['station']
        out['endTime'] = stops[-1]['arrive']
        out['category'] = str((data[0] or {}).get('train_class_name') or '')
    return out


def _stop_minutes(arrive: Any, depart: Any) -> int:
    """停站分钟数（12306 只给时刻，自己减）。"""
    def parse(x):
        m = re.match(r'^(\d{1,2}):(\d{2})$', str(x or ''))
        return int(m.group(1)) * 60 + int(m.group(2)) if m else None
    a, b = parse(arrive), parse(depart)
    if a is None or b is None:
        return 0
    d = b - a
    return d if 0 <= d < 24 * 60 else 0


# --------------------------------------------------------------------------
# 合并入口
# --------------------------------------------------------------------------
def query(train: str, prefer: str = 'auto', timeout: float = 10.0,
          dateStr: Optional[str] = None) -> Dict[str, Any]:
    """车次查询总入口。

    prefer:
        'auto'   先 RailGo（字段全），失败退回 12306
        'railgo' 只问 RailGo
        '12306'  只问 12306（官方口径/离线环境）
    """
    t = normalize_train(train)
    order = {'auto': ['railgo', '12306'], 'railgo': ['railgo'],
             '12306': ['12306']}.get(prefer, ['railgo', '12306'])
    firstErr = None
    for src in order:
        res = (query_railgo(t, timeout=timeout) if src == 'railgo'
               else query_12306(t, dateStr=dateStr, timeout=timeout))
        if res.get('ok'):
            if firstErr:
                res['fallbackFrom'] = firstErr
            return res
        firstErr = firstErr or res.get('error', '')
    out = _blank()
    out['error'] = firstErr or '未查询到车次'
    out['train'] = t
    return out


def nearby_dates(count: int = 3) -> List[str]:
    """缺省查询用的近几天（YYYYMMDD），12306 时刻表按日期取。"""
    base = _date.today()
    return [(base + timedelta(days=i)).strftime('%Y%m%d') for i in range(count)]


def summary_line(res: Dict[str, Any]) -> str:
    """一行摘要（状态栏/日志用）。"""
    if not res.get('ok'):
        return '车次 %s 查询失败：%s' % (res.get('train', ''), res.get('error', ''))
    bits = [res.get('train', '')]
    if res.get('category'):
        bits.append(res['category'])
    if res.get('start') and res.get('end'):
        bits.append('%s→%s' % (res['start'], res['end']))
    if res.get('carOwner'):
        bits.append('配属 %s' % res['carOwner'])
    elif res.get('bureau'):
        bits.append('担当 %s' % res['bureau'])
    return ' · '.join(x for x in bits if x)


def now_text() -> str:
    return datetime.now().strftime('%H:%M:%S')
