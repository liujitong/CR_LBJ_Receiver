# -*- coding: utf-8 -*-
"""ui_threads.py — 界面层后台线程的「保活 + 退出收尾」登记处。

## 解决什么问题

界面里有两类 QThread：长时间常驻的（DSP 桥接，由主窗口自己 stop/wait），
和「点一下就跑」的短任务（12306 车次查询、上游数据更新检查，最长约 20 秒）。
后者有两个真实的崩溃场景：

1. **对象被回收**：`dlg.exec()` 里的局部窗口一关就被回收，如果它的
   `self._worker` 还在跑，QThread 对象被析构 → Qt `qFatal`
   `QThread: Destroyed while thread is still running` → 整个程序退出码异常。
   所以线程**不能挂 parent**，还要登记到本模块保活到 `finished`。
2. **退出时还有线程在跑**：用户查完车次立刻按 Ctrl+Q，解释器开始销毁对象，
   线程仍在 `urllib` 里等超时 → 同样 qFatal。`wait_all()` 在主窗口
   `closeEvent` 里调用：先等，等不到就 `terminate()`（只在退出路径上用，
   这些线程只做 HTTP + 发信号，不会留下半写文件）。

## 用法

    from cr_lbj.ui.ui_threads import keep_thread, wait_all

    th = MyWorker()          # 不要传 parent
    keep_thread(th)          # 登记保活（finished 自动摘除）
    th.start()

    # 主窗口 closeEvent：
    wait_all(1500)
"""

from __future__ import annotations

import time
from typing import Any, Set

_LIVE: Set[Any] = set()


def keep_thread(worker) -> None:
    """登记一个线程：保活到它 finished（线程对象不要挂 parent）。"""
    if worker is None:
        return
    _LIVE.add(worker)
    try:
        worker.finished.connect(lambda w=worker: _LIVE.discard(w))
    except Exception:
        pass


def running_count() -> int:
    """当前还在跑的短任务线程数（测试/仪表板用）。"""
    return len([w for w in list(_LIVE) if _is_running(w)])


def _is_running(worker) -> bool:
    try:
        return bool(worker.isRunning())
    except Exception:
        return False


def wait_all(timeout_ms: int = 1500, terminate: bool = True) -> int:
    """等所有登记线程结束；超时则（可选）terminate。返回仍在运行的个数。

    只在退出路径调用：等待时间要短，不能让用户以为程序卡住。
    """
    deadline = time.time() + max(0, int(timeout_ms)) / 1000.0
    left = [w for w in list(_LIVE) if _is_running(w)]
    for w in left:
        remain = max(0, int((deadline - time.time()) * 1000))
        try:
            w.wait(remain)
        except Exception:
            pass
    left = [w for w in list(_LIVE) if _is_running(w)]
    if left and terminate:
        for w in left:
            try:
                w.terminate()
                w.wait(300)
            except Exception:
                pass
        left = [w for w in list(_LIVE) if _is_running(w)]
    return len(left)
