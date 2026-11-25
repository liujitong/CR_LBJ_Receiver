# -*- coding: utf-8 -*-
"""config_ext.py — v3.0 新增配置字段的兜底、共享资源路径与图层清单。

## 为什么要有这个模块

v3.0 把地图从「高德 JS API + 自建 HTML」换成「Leaflet + OpenRailwayMap
（`shared/web/railmap.html`，桌面与安卓共用同一页）」，随之多了几个配置字段：

    mapBase          底图 id（'osm' / 'carto_dark' / 'tdt_vec' …）
    mapRail          铁路图层 id（'orm_standard' …，'off' 表示不显示）
    mapRailOpacity   铁路图层不透明度 0.2 ~ 1.0
    tdtKey           天地图「浏览器端」tk（只在该底图被选中时才需要）
    trainQuerySource 车次查询数据源：auto / railgo / 12306
    dataAutoUpdate   第三方数据（机车配属号段表）自动检查更新开关
    dataUpdateIntervalDays  自动检查间隔（天）

这些字段的「正式定义」在 `cr_lbj/core/decoder.py` 的 `CoreConfig` 里（核心层由
另一位维护）。为了让界面层不被核心层的进度绑住，这里做两件事：

1. `install()`：若 `CoreConfig` 还没声明某个字段，就把默认值挂成类属性——
   这样 `CoreConfig.fromDict()` 的 `hasattr()` 判断能认出老配置里存过的值，
   界面读 `getattr(cfg, 'mapBase', ...)` 也永远有值。**幂等**：核心层已经声明了
   就一个字都不动。
2. `ensure(cfg)`：给某个配置实例补齐实例属性，`toDict()` 才会把这些字段写进
   JSON（`toDict` 遍历的是实例 `__dict__`，类属性不会被序列化）。

## 另外两件事

* `shared_root()/web_dir()/data_dir()`：定位仓库根 `shared/`，覆盖源码运行、
  PyInstaller onefile、绿色版（exe 与 shared 并排）三种情形。
* `BASE_LAYERS/RAIL_LAYERS`：底图与铁路图层的**静态清单**，与
  `shared/web/railmap.html` 里的 `BASE_SOURCES/RAIL_SOURCES` 逐字对应。
  配置对话框在地图页面还没加载时也要能列出选项，所以不能只依赖 `LBJ.layers()`。
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. v3.0 新增配置字段（默认值）
# ---------------------------------------------------------------------------
#: 字段名 → 默认值。顺序即配置页上的展示顺序。
NEW_CONFIG_FIELDS: Dict[str, object] = {
    'mapBase': 'osm',
    'mapRail': 'orm_standard',
    'mapRailOpacity': 0.85,
    'tdtKey': '',
    'trainQuerySource': 'auto',
    'dataAutoUpdate': True,
    'dataUpdateIntervalDays': 7,
}


def install() -> List[str]:
    """把缺失的 v3.0 字段补成 `CoreConfig` 的类属性（幂等）。返回补了哪些。"""
    added: List[str] = []
    try:
        from cr_lbj.core.decoder import CoreConfig
    except Exception:            # 核心层不可用：界面也起不来，交给上层报错
        return added
    for key, val in NEW_CONFIG_FIELDS.items():
        if hasattr(CoreConfig, key):
            continue
        try:
            setattr(CoreConfig, key, val)
            added.append(key)
        except Exception:
            pass
    return added


def ensure(config) -> object:
    """给配置实例补齐字段（让 `toDict()` 能把它们写进 JSON）。原样返回。

    注意判断的是**实例字典**而不是 `hasattr`：`install()` 补的是类属性，
    `hasattr` 会命中类属性 → 实例 `__dict__` 里仍然没有这个键，而
    `CoreConfig.toDict()` 遍历的正是实例 `__dict__`，于是字段永远存不进 JSON。
    """
    if config is None:
        return config
    for key, val in NEW_CONFIG_FIELDS.items():
        if key in getattr(config, '__dict__', {}):
            continue
        try:
            setattr(config, key, val)
        except Exception:
            pass
    return config


def get(config, key: str, default=None):
    """读一个新字段（配置对象为空/字段缺失时给默认值）。"""
    if default is None:
        default = NEW_CONFIG_FIELDS.get(key)
    try:
        return getattr(config, key, default)
    except Exception:
        return default


install()


# ---------------------------------------------------------------------------
# 2. 共享资源路径
# ---------------------------------------------------------------------------
def _exe_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        return ''


def _meipass() -> str:
    return str(getattr(sys, '_MEIPASS', '') or '')


def _repo_root() -> str:
    """源码运行时的仓库根（cr_lbj/ui/ 上两级）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, '..', '..'))


def _shared_candidates() -> List[str]:
    out: List[str] = []
    env = os.environ.get('CRLBJ_SHARED_ROOT', '').strip()
    if env:
        out.append(env)
    envd = os.environ.get('CRLBJ_SHARED_DIR', '').strip()
    if envd:                       # 该变量语义是 shared/data，父目录即 shared
        out.append(os.path.dirname(envd.rstrip('\\/')))
    exe = _exe_dir()
    if exe:
        out.append(os.path.join(exe, 'shared'))
    mei = _meipass()
    if mei:
        out.append(os.path.join(mei, 'shared'))
    out.append(os.path.join(_repo_root(), 'shared'))
    return out


def shared_root() -> str:
    """仓库根 `shared/` 目录（优先返回真实存在的那个）。"""
    cands = _shared_candidates()
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


def web_dir() -> str:
    """`shared/web/`（地图页与 Leaflet 依赖所在目录）。"""
    env = os.environ.get('CRLBJ_WEB_DIR', '').strip()
    cands = ([env] if env else []) + [os.path.join(c, 'web') for c in _shared_candidates()]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[-1]


def data_dir() -> str:
    """`shared/data/`（配属号段表、车型参数、预设城市）。

    优先复用数据层自己的定位逻辑：它还会认出用户可写覆盖层
    （`%LOCALAPPDATA%/CR-LBJ-Receiver/data`，自动更新写这里）。
    """
    try:
        from cr_lbj.data import loco_roster
        d = loco_roster.shared_dir()
        if d:
            return d
    except Exception:
        pass
    return os.path.join(shared_root(), 'data')


def data_file(name: str) -> str:
    """某个数据文件**当前生效**的路径（覆盖层优先，其次内置快照）。"""
    try:
        from cr_lbj.data import loco_roster
        return loco_roster.data_path(name)
    except Exception:
        return os.path.join(data_dir(), name)


RAILMAP_FILE = 'railmap.html'


def railmap_path() -> str:
    return os.path.join(web_dir(), RAILMAP_FILE)


def railmap_exists() -> bool:
    return os.path.isfile(railmap_path())


# ---------------------------------------------------------------------------
# 3. 底图 / 铁路图层清单（与 railmap.html 的登记表逐字一致）
# ---------------------------------------------------------------------------
#: (id, 中文名)。名字必须与页面里 `BASE_SOURCES[*].name` 相同，否则工具栏下拉
#: 会和页面内的下拉对不上（两处都由用户改，会互相打架）。
BASE_LAYERS: List[Tuple[str, str]] = [
    ('osm', 'OSM 标准'),
    ('carto_light', 'Carto 浅色'),
    ('carto_dark', 'Carto 深色'),
    ('carto_voyager', 'Carto 路由'),
    ('esri_img', 'Esri 卫星'),
    ('esri_street', 'Esri 街道'),
    ('opentopo', 'OpenTopoMap 地形'),
    ('tdt_vec', '天地图 矢量（CGCS2000）'),
    ('tdt_img', '天地图 影像（CGCS2000）'),
    ('amap', '高德 街道（GCJ-02）'),
    ('amap_img', '高德 卫星（GCJ-02）'),
]

#: 铁路图层：(id, 中文名)。'off' 排第一，配置页与工具栏都用它表示「不显示」。
RAIL_LAYERS: List[Tuple[str, str]] = [
    ('off', '不显示'),
    ('orm_standard', 'ORM 标准（线路+信号）'),
    ('orm_maxspeed', 'ORM 限速'),
    ('orm_signals', 'ORM 信号'),
    ('orm_electrified', 'ORM 电气化'),
    ('orm_gauge', 'ORM 轨距'),
]

#: 需要天地图 tk 的底图 id
TDT_LAYERS = ('tdt_vec', 'tdt_img')

#: GCJ-02 底图：选中后页面会自动关掉 WGS-84 的铁路图层（不混叠）
GCJ_LAYERS = ('amap', 'amap_img')


def base_name(layer_id: str) -> str:
    """底图 id → 中文名（未知 id 原样返回）。"""
    for lid, name in BASE_LAYERS:
        if lid == layer_id:
            return name
    return str(layer_id or '')


def rail_name(layer_id: str) -> str:
    for lid, name in RAIL_LAYERS:
        if lid == layer_id:
            return name
    return str(layer_id or '')


def layer_names() -> Dict[str, str]:
    """id → 中文名（底图 + 铁路合表，供工具栏/配置页查名字）。"""
    out: Dict[str, str] = {}
    for lid, name in BASE_LAYERS:
        out[lid] = name
    for lid, name in RAIL_LAYERS:
        out[lid] = name
    return out


def normalize_base(layer_id, fallback: str = 'osm') -> str:
    """把配置里的底图 id 规整成清单内的值（旧配置/手改配置都不会导致白屏）。"""
    s = str(layer_id or '').strip()
    for lid, _n in BASE_LAYERS:
        if lid == s:
            return s
    return fallback


def normalize_rail(layer_id, fallback: str = 'orm_standard') -> str:
    s = str(layer_id or '').strip()
    for lid, _n in RAIL_LAYERS:
        if lid == s:
            return s
    return fallback


# ---------------------------------------------------------------------------
# 4. 预设城市（shared/data/places.csv）
# ---------------------------------------------------------------------------
def load_places() -> List[Dict[str, object]]:
    """读预设中心点：`[{'name': '南昌', 'lat': 28.68, 'lng': 115.86}, ...]`。

    文件格式见 `shared/data/places.csv`（`#` 开头为注释，首行是表头）。
    读不到就返回空列表，调用方（配置页下拉）自己决定要不要隐藏这一行。
    """
    import csv

    path = data_file('places.csv')
    out: List[Dict[str, object]] = []
    try:
        with open(path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                if not row or row[0].startswith('#'):
                    continue
                if len(row) < 3:
                    continue
                name = row[0].strip()
                if not name or name.lower() == 'name':
                    continue
                try:
                    lat = float(row[1])
                    lng = float(row[2])
                except (TypeError, ValueError):
                    continue
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    continue
                out.append({'name': name, 'lat': lat, 'lng': lng})
    except OSError:
        pass
    return out


def nearest_place(lat: float, lng: float,
                  places: Optional[List[Dict[str, object]]] = None) -> Optional[str]:
    """坐标 → 最近的预设城市名（配置页「选城市填坐标」的双向同步用）。"""
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    if abs(float(lat)) < 1e-6 and abs(float(lng)) < 1e-6:
        return None
    best, best_d = None, 1e18
    for p in (places if places is not None else load_places()):
        d = (float(p['lat']) - float(lat)) ** 2 + (float(p['lng']) - float(lng)) ** 2
        if d < best_d:
            best, best_d = p, d
    # 1.5° 以内才认（约 150 km），太远说明是用户自己填的坐标，不该硬套城市名
    return str(best['name']) if best is not None and best_d <= 2.25 else None
