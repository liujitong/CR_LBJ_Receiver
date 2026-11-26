# -*- coding: utf-8 -*-
"""info_lookup.py — 车次/机车信息的后台查询与缓存（地图页与信息面板共用）。

## 为什么单独一层

地图标记与「车次信息」面板都要显示：**车次等级、担当路局、担当段/客运段、
配属段/车辆段、车型、机车配属单位、制造厂**。

* 车次信息来自 `cr_lbj.data.train_info.query()`（RailGo / 12306，需要联网）；
* 机车信息来自本地号段表 `cr_lbj.data.loco_roster.lookup_loco()`（瞬时，无需线程）。

网络查询不能阻塞 UI，所以这里用 QThread 异步取，并按车次号缓存结果
（同一车次只查一次）。查询失败静默——地图/面板只是少几行信息，不影响解码。

字段契约（与 shared/web/railmap.html 的 `LBJ.setTrainInfo` 一致）：

    grade      车次等级（如「快速旅客列车」「动车组」）
    bureau     担当路局（如「南昌局」）
    section    担当段 / 客运段
    owner      配属段 / 车辆段
    model      车底 / 车型
    from/to    始发 / 终到站
    locoDepot  机车配属单位（局/段）
    locoMaker  机车制造厂
    locoModel  机车型号
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal

from cr_lbj.ui.ui_threads import keep_thread as _keepWorker

#: train_info.query 结果字段 → 页面 info 字段
_TRAIN_FIELD_MAP = (
    ('category', 'grade'),
    ('bureau', 'bureau'),
    ('runner', 'section'),
    ('carOwner', 'owner'),
    ('car', 'model'),
)


def _clean(value: Any) -> str:
    return str(value or '').strip()


class TrainInfoWorker(QThread):
    """后台查询一趟车的等级/担当/配属（联网，失败静默）。"""

    ready = Signal(str, dict)      # train, info

    def __init__(self, train: str, prefer: str = 'auto'):
        super().__init__()
        self.train = train
        self.prefer = prefer or 'auto'

    def run(self):
        try:
            from cr_lbj.data import train_info
        except Exception:
            return
        try:
            res = train_info.query(self.train, prefer=self.prefer)
        except Exception:
            return
        if not isinstance(res, dict) or not res.get('ok'):
            return
        info: Dict[str, str] = {}
        for src, dst in _TRAIN_FIELD_MAP:
            v = _clean(res.get(src))
            if v:
                info[dst] = v
        for src, dst in (('start', 'from'), ('end', 'to')):
            v = _clean(res.get(src))
            if v:
                info[dst] = v
        if info:
            self.ready.emit(self.train, info)


class TrainInfoService(QObject):
    """车次/机车信息查询服务：异步取车次信息 + 本地取机车配属，均带缓存。"""

    infoReady = Signal(str, dict)   # train, info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: Dict[str, Dict[str, str]] = {}
        self._pending = set()
        self._workers = []

    # ---- 车次（联网，异步） ----
    def lookup(self, train: str, prefer: str = 'auto') -> Dict[str, str]:
        """请求查询某车次；已有缓存立即返回，否则后台查（结果经 infoReady 发出）。"""
        key = _clean(train)
        if not key or key == '----':
            return {}
        cached = self._cache.get(key)
        if cached is not None:
            return dict(cached)
        if key in self._pending:
            return {}
        self._pending.add(key)
        w = TrainInfoWorker(key, prefer)
        w.ready.connect(self._on_worker_ready)
        _keepWorker(w)
        self._workers.append(w)
        if len(self._workers) > 24:          # 只保留最近 24 个已结束的线程对象
            self._workers = [x for x in self._workers if x.isRunning()][-24:]
        w.start()
        return {}

    def cached(self, train: str) -> Dict[str, str]:
        return dict(self._cache.get(_clean(train)) or {})

    def _on_worker_ready(self, train: str, info: dict):
        self._pending.discard(_clean(train))
        if info:
            self._cache[_clean(train)] = dict(info)
            self.infoReady.emit(_clean(train), dict(info))

    # ---- 机车（本地号段表，同步） ----
    @staticmethod
    def loco_info(loco: Any, loco_code: Any = None) -> Dict[str, str]:
        """型号 + 机车号 → 配属单位 / 制造厂 / 型号（本地 CSV，毫秒级）。"""
        text = _clean(loco)
        code = _clean(loco_code)
        if not text and not code:
            return {}
        try:
            from cr_lbj.data import loco_roster
            r = loco_roster.lookup_loco(text, code) or {}
        except Exception:
            return {}
        if not r.get('ok') and not (r.get('model') or r.get('name')):
            return {}
        out: Dict[str, str] = {}
        depot = _clean(r.get('depot'))
        if depot:
            out['locoDepot'] = depot
        maker = _clean(r.get('maker'))
        if maker:
            out['locoMaker'] = maker
        model = _clean(r.get('name')) or _clean(r.get('model'))
        if model:
            out['locoModel'] = model
        return out


def merge_info(*parts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把多份 info 合并成一份（后面的非空值覆盖前面的）。"""
    out: Dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for k, v in part.items():
            if v:
                out[k] = v
    return out