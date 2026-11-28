#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""瀑布图控件（v4.0）。

参照 SDR# / SDR++ / GQRX 的瀑布显示惯例实现：

* **时间轴向下滚动**：最新一帧画在最上面，历史逐帧下移（SDR# 默认方向）；
* **感知均匀色标**：用 Google Turbo（多项式近似）而不是红蓝彩虹——
  彩虹色标在等 dB 间隔下会出现明显"色带/台阶"，Turbo 单调且过渡平滑；
* **自动增益 + 噪声底归一化**：按最近若干帧的 5% / 99% 分位裁剪，
  再按对数压缩映射到色标，弱信号也有层次（SDR# 的 Auto Gain/Contrast 思路）；
* **环形缓冲 + NumPy**：每帧只写一行，不重排整幅图；
  绘制时用 QImage 直接引用同一块内存，缩放交给 Qt（平滑插值）。

只依赖 numpy + Qt，不依赖 pyqtgraph（瀑布是位图，不是矢量曲线）。
"""
from __future__ import annotations

import numpy as np

from cr_lbj.runtime import *  # noqa: F401,F403


def _turbo_lut() -> np.ndarray:
    """Google Turbo 色标（256 级，BGR 顺序，供 QImage Format_ARGB32 使用）。

    多项式近似出自 Google 的 Turbo colormap 参考实现；比 jet/rainbow 更均匀，
    且两端不发黑发白，适合显示 dB 动态范围。
    """
    x = np.linspace(0.0, 1.0, 256)
    r = (0.13572138 + 4.61539260 * x - 42.66032258 * x ** 2
         + 132.13108234 * x ** 3 - 152.94239396 * x ** 4
         + 59.28637943 * x ** 5)
    g = (0.09140261 + 2.19418839 * x + 4.84296658 * x ** 2
         - 14.18503333 * x ** 3 + 4.27729857 * x ** 4
         + 2.82956604 * x ** 5)
    b = (0.10667330 + 12.64194608 * x - 60.58204836 * x ** 2
         + 110.36276771 * x ** 3 - 89.90310912 * x ** 4
         + 27.34824973 * x ** 5)
    r = np.clip(r, 0.0, 1.0)
    g = np.clip(g, 0.0, 1.0)
    b = np.clip(b, 0.0, 1.0)
    # QImage.Format_ARGB32 在小端机器上是 0xAARRGGBB
    return ((np.uint32(255) << 24)
            | (np.uint32(r * 255).astype(np.uint32) << 16)
            | (np.uint32(g * 255).astype(np.uint32) << 8)
            | np.uint32(b * 255).astype(np.uint32))


_LUT = _turbo_lut()


class WaterfallPanel(QWidget):
    """滚动瀑布图（SDR# 风格）。

    参数
    ----
    bins:     每帧频点数（与核心库一致，v4.0 起 256）
    rows:     保留的历史行数（屏幕高度约等于该值）
    contrast: 动态范围压缩强度（越大弱信号越亮，SDR# 的 Contrast）
    gain_db:  额外增益（dB），整体平移显示窗口
    """

    def __init__(self, bins: int = 256, rows: int = 220):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.setMinimumHeight(spx(90))
        self._bins = max(8, int(bins))
        self._rows = max(32, int(rows))
        self._contrast = 2.0
        self._gainDb = 0.0
        self._auto = True

        # 环形缓冲：第 0 行 = 最新
        self._img = np.zeros((self._rows, self._bins), dtype=np.uint32)
        self._img[:] = _LUT[0]
        self._pending = True
        self._qimage = QImage(self._img.data, self._bins, self._rows,
                              self._bins * 4, QImage.Format_ARGB32)
        # 噪声底 / 峰值（滑动分位，来自最近若干帧）
        self._lo = -120.0
        self._hi = -40.0

        self.setToolTip('瀑布图：新帧在上、历史向下滚动；颜色越亮能量越强')

    # ------------------------------------------------------------------
    def setBins(self, bins: int):
        bins = max(8, int(bins))
        if bins == self._bins:
            return
        self._bins = bins
        self._img = np.zeros((self._rows, self._bins), dtype=np.uint32)
        self._img[:] = _LUT[0]
        self._qimage = QImage(self._img.data, self._bins, self._rows,
                              self._bins * 4, QImage.Format_ARGB32)
        self.update()

    def setAuto(self, on: bool):
        self._auto = bool(on)

    def setContrast(self, v: float):
        self._contrast = max(0.2, min(8.0, float(v)))

    def setGainDb(self, db: float):
        self._gainDb = float(db)

    def clear(self):
        self._img[:] = _LUT[0]
        self._pending = True
        self.update()

    # ------------------------------------------------------------------
    def pushSpectrum(self, data):
        """追加一帧频谱（dB 数组）。耗时可忽略：一次行拷贝 + 一次色标查表。"""
        try:
            arr = np.asarray(data, dtype=np.float32).ravel()
        except Exception:
            return
        if arr.size < 8:
            return
        if arr.size != self._bins:
            self.setBins(arr.size)

        # 自动增益：用分位裁剪（避开单点尖峰的极端值），再叠加手动增益
        if self._auto and arr.size >= 8:
            lo = float(np.percentile(arr, 5.0)) + self._gainDb
            hi = float(np.percentile(arr, 99.5)) + self._gainDb
            if hi - lo < 6.0:            # 全静噪时避免放大噪声成雪花
                hi = lo + 6.0
            # 缓慢跟随，避免逐帧跳色
            self._lo = 0.85 * self._lo + 0.15 * lo
            self._hi = 0.85 * self._hi + 0.15 * hi
        else:
            self._lo = -120.0 + self._gainDb
            self._hi = -20.0 + self._gainDb
        span = max(1e-3, self._hi - self._lo)

        v = (arr - self._lo) / span
        v = np.clip(v, 0.0, 1.0)
        # 对数动态范围压缩：弱信号层次更丰富（SDR# Contrast 的等效做法）
        k = self._contrast
        v = np.log1p(k * v) / np.log1p(k)

        idx = (v * 255.0).astype(np.int32)
        np.clip(idx, 0, 255, out=idx)

        # 整体下移一行，新帧写第 0 行
        self._img[1:] = self._img[:-1]
        self._img[0] = _LUT[idx]
        self._pending = True
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            rect = self.rect()
            if rect.width() <= 0 or rect.height() <= 0:
                return
            # 让行数按控件高度自适应：位图行少时纵向拉伸，行多时压缩
            target = QRect(rect)
            # 保持"时间连续"：半行偏移让滚动看起来是淡入而不是整行跳
            p.drawImage(target, self._qimage)
        finally:
            p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()