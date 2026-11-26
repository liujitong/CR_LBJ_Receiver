# -*- coding: utf-8 -*-
"""data_update.py — 第三方数据（机车配属号段表）更新的界面侧封装。

数据层 `cr_lbj/data/updater.py` 负责「怎么查、怎么校验、怎么写盘」；本模块只做
界面需要的那一层：

* **线程**：`check_and_update()` 会真的发 HTTP（最长 ~20 秒），绝不能在 UI 线程跑；
* **防御**：数据层模块缺失/接口变动时返回可读的中文说明，界面不崩；
* **文案**：把结构化结果压成一句给日志/状态栏看的话，并区分「内置快照 / 已更新」。

约定：任何失败都不抛异常，只返回 `{'ok': False, 'message': ...}`。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QThread, Signal

#: 数据层缺失时的兜底状态（界面照样能渲染）
_BLANK: Dict[str, Any] = {
    'available': False, 'rows': 0, 'models': 0, 'emptyDepot': 0,
    'sha': '', 'fetchedAt': '', 'lastCheck': '', 'source': '',
    'isBundled': True, 'path': '', 'userDir': '', 'remoteUrl': '',
}


def _updater():
    """取数据层 updater 模块（缺失返回 None，不抛）。"""
    try:
        from cr_lbj.data import updater
        return updater
    except Exception:
        return None


def available() -> bool:
    """自动更新能力是否可用（数据层模块在就可用）。"""
    mod = _updater()
    return bool(mod is not None and hasattr(mod, 'check_and_update'))


def status() -> Dict[str, Any]:
    """当前数据状态：行数 / 型号数 / 是否内置快照 / 上次更新与检查时间。"""
    out = dict(_BLANK)
    mod = _updater()
    if mod is not None and hasattr(mod, 'status'):
        try:
            d = mod.status()
            if isinstance(d, dict):
                out.update(d)
                return out
        except Exception:
            pass
    # 数据层不可用：至少把「表有没有、多少行」报出来（离线也能看）
    try:
        from cr_lbj.data import loco_roster
        st = loco_roster.stats()
        out.update({'available': loco_roster.available(),
                    'rows': int(st.get('rows') or 0),
                    'models': int(st.get('models') or 0),
                    'emptyDepot': int(st.get('emptyDepot') or 0),
                    'source': '内置快照 shared/data/loco_roster.csv'})
    except Exception:
        pass
    return out


def last_check_text() -> str:
    """一句话状态（状态栏/日志/配置页共用）。"""
    mod = _updater()
    if mod is not None and hasattr(mod, 'last_check_text'):
        try:
            return str(mod.last_check_text())
        except Exception:
            pass
    s = status()
    where = '内置快照' if s.get('isBundled', True) else '已更新'
    return '配属表 %d 行 / %d 型号 · %s' % (s.get('rows', 0), s.get('models', 0), where)


def status_text_multiline() -> str:
    """配置页用的多行描述。"""
    s = status()
    where = '内置快照（安装包自带）' if s.get('isBundled', True) else '已更新（用户目录）'
    when = str(s.get('fetchedAt') or '')[:16].replace('T', ' ') or '—'
    last = str(s.get('lastCheck') or '')[:16].replace('T', ' ') or '—'
    lines = [
        '当前：%s' % where,
        '规模：%d 行 / %d 个型号' % (int(s.get('rows') or 0), int(s.get('models') or 0)),
        '更新于：%s' % when,
        '上次检查：%s' % last,
        '来源：%s' % (s.get('source') or '—'),
    ]
    if s.get('userDir'):
        lines.append('用户数据目录：%s' % s['userDir'])
    return '\n'.join(lines)


def auto_enabled(config) -> bool:
    """配置里的自动检查开关（缺字段时按开处理）。"""
    try:
        return bool(getattr(config, 'dataAutoUpdate', True))
    except Exception:
        return True


def interval_days(config) -> int:
    """配置里的自动检查间隔（天），夹在 1~90。"""
    try:
        v = int(getattr(config, 'dataUpdateIntervalDays', 7) or 7)
    except (TypeError, ValueError):
        v = 7
    return max(1, min(90, v))


#: 线程对象**不要**挂 parent（挂上就会随对话框/面板一起被 C++ 析构，运行中的
#: QThread 被销毁会直接崩程序）；由 ui_threads 登记保活到 finished。
_LIVE_THREADS: set = set()


class DataUpdateThread(QThread):
    """后台检查/下载号段表。结果通过 `done(dict)` 回主线程。"""

    done = Signal(dict)

    def __init__(self, force: bool = False, interval_days: int = 7,
                 timeout: float = 20.0, parent=None):
        super().__init__(parent)
        self.force = bool(force)
        self.interval = max(1, int(interval_days or 7))
        self.timeout = float(timeout or 20.0)
        # 自注册：调用方（主窗口/配置页）关掉也不影响线程跑完
        _LIVE_THREADS.add(self)
        try:
            from cr_lbj.ui.ui_threads import keep_thread
            keep_thread(self)
        except Exception:
            pass

    def run(self):
        res: Dict[str, Any] = {'ok': False, 'updated': False, 'skipped': False,
                               'rows': 0, 'models': 0, 'message': '', 'sha': '',
                               'fetchedAt': '', 'source': ''}
        mod = _updater()
        if mod is None or not hasattr(mod, 'check_and_update'):
            res['message'] = ('数据更新模块不可用（缺少 cr_lbj/data/updater.py），'
                              '本次跳过；内置快照仍可正常查询。')
            self.done.emit(res)
            return
        try:
            out = mod.check_and_update(force=self.force,
                                       interval_days=self.interval,
                                       timeout=self.timeout)
            if isinstance(out, dict):
                res.update(out)
            else:
                res['message'] = '数据层返回结构异常，已忽略'
        except Exception as e:                       # noqa: BLE001 - 界面不允许崩
            res['ok'] = False
            res['message'] = '检查更新异常：%s' % (e or e.__class__.__name__)
        # 更新成功时让 loco_roster 丢缓存（updater 内部也会做，这里兜一次）
        if res.get('updated'):
            try:
                from cr_lbj.data import loco_roster
                loco_roster.invalidate()
            except Exception:
                pass
        self.done.emit(res)


def result_text(res: Optional[Dict[str, Any]]) -> str:
    """把一次检查结果压成一句中文（日志/提示框共用）。"""
    if not isinstance(res, dict):
        return '检查更新失败：无结果'
    msg = str(res.get('message') or '').strip()
    if msg:
        return msg
    if res.get('updated'):
        return '已更新配属号段表：%d 行 / %d 型号' % (
            int(res.get('rows') or 0), int(res.get('models') or 0))
    if res.get('ok'):
        return '已是最新（%d 行 / %d 型号）' % (
            int(res.get('rows') or 0), int(res.get('models') or 0))
    return '检查更新失败'
