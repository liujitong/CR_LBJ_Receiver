# -*- coding: utf-8 -*-
"""通用纯函数：不依赖 Qt、不持有运行时状态，任意层都可复用。"""
from __future__ import annotations


def safeFloat(v, default=None):
    """把带单位的数值文本安全转成 float，失败返回 default。"""
    try:
        return float(str(v).replace('KM', '').replace('km', '').strip())
    except Exception:
        return default
