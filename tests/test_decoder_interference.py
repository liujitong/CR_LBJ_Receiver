# -*- coding: utf-8 -*-
"""v3.2.9：解析不出车次的帧 → 计为上行/下行干扰（只统计 + 日志，不入库）。

双端一致性要求（用户明确）：
  * 车次解析不出来（BCD 前 6 位不是字母数字 / 最终 train 为 ----）时，
    按功能码判「上行 / 下行」并累加干扰计数；
  * 限速输出日志提示；
  * **绝不产出 DecodeResult**（因此不会写进历史数据库）。

桌面端这里做真实功能验证；安卓端（C++/Kotlin）做源码契约断言
（完整 bit 级对拍由 android/tools/duipai 的 IQ 回放套件保证）。
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(ROOT, 'desktop')
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

from cr_lbj.core import decoder as D  # noqa: E402

CPP_CORE = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'cpp', 'core')
ANDROID_JAVA = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'java',
                           'xyz', 'mlxkj', 'crlbj')


def read(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class PcInterferenceTest(unittest.TestCase):
    """桌面：解析不出车次的帧必须计干扰且不产出结果。"""

    def _decoder(self):
        d = D.LbjDecoder(fs=48000, baudRate=1200)
        d.currentCodewords = [0x80000000]
        return d

    def test_invalid_train_counts_downlink(self):
        d = self._decoder()
        out = []
        warns = []
        d.onDecode = out.append
        d.onInterference = lambda direction, text: warns.append((direction, text))
        d.currentAddr = 1233999      # 短报文地址
        d.currentFunc = 1            # 下行
        d.decodeLbj('------' + '0' * 20)
        self.assertEqual(out, [], '车次解析失败不得产出 DecodeResult（否则会入库）')
        self.assertEqual(d.interferenceDown, 1)
        self.assertEqual(d.interferenceUp, 0)
        self.assertEqual(len(warns), 1, '应给出一条干扰日志提示')
        self.assertIn('下行', warns[0][1])

    def test_invalid_train_counts_uplink(self):
        d = self._decoder()
        d.onDecode = lambda r: self.fail('不应产出结果')
        d.currentAddr = 1233999
        d.currentFunc = 3            # 上行
        d.decodeLbj('------' + '0' * 20)
        self.assertEqual(d.interferenceUp, 1)
        self.assertEqual(d.interferenceDown, 0)

    def test_warn_rate_limited(self):
        """限速：1 秒内多条干扰只提示一次（避免刷屏）。"""
        d = self._decoder()
        warns = []
        d.onInterference = lambda direction, text: warns.append(text)
        d.currentAddr = 1233999
        d.currentFunc = 1
        for _ in range(5):
            d.decodeLbj('------' + '0' * 20)
        self.assertEqual(d.interferenceDown, 5, '计数不受限速影响')
        self.assertEqual(len(warns), 1, '日志 1 秒内只一条')

    def test_dash_train_never_emits(self):
        """短报文车次为 ---- 时连会话都不应建立（旧实现会建 '----' 会话）。"""
        d = self._decoder()
        d.currentAddr = 1233999
        d.currentFunc = 1
        d.decodeLbj('------' + '0' * 20)
        self.assertNotIn('----', d.sessions,
                         "不得再为 '----' 建会话（否则会产出入库记录）")


class AndroidInterferenceContractTest(unittest.TestCase):
    """安卓：与桌面同口径（早退 + 计数 + 告警排空 + 状态帧上报）。"""

    def test_cpp_early_return_and_counter(self):
        h = read(os.path.join(CPP_CORE, 'decoder.h'))
        self.assertIn('noteInterference', h, 'C++ 需有干扰计数函数')
        self.assertIn('interferenceUp', h)
        self.assertIn('interferenceDown', h)
        # 短报文车次无效 → 计干扰并早退
        seg = h.split('if (baseTrain == "----")', 1)
        self.assertEqual(len(seg), 2, '短报文需判 baseTrain == "----"')
        self.assertIn('noteInterference(func);', seg[1].split('}', 1)[0])
        self.assertIn('return;', seg[1].split('}', 1)[0], '必须早退，不建会话')
        # 汇总阶段再兜一次
        self.assertIn('if (aid.empty() || aid == "----")', h)

    def test_engine_drains_warnings(self):
        cpp = read(os.path.join(CPP_CORE, 'engine.cpp'))
        self.assertIn('pendingWarnings', cpp,
                      'engine 必须消费 pendingWarnings（原来只 push 从不读）')
        self.assertIn('[告警]', cpp)

    def test_engine_publishes_counters(self):
        cpp = read(os.path.join(CPP_CORE, 'engine.cpp'))
        self.assertIn('status_.setInt(19', cpp, '干扰计数应写入状态帧保留字 word[19]')

    def test_kotlin_parses_and_shows(self):
        sf = read(os.path.join(ANDROID_JAVA, 'engine', 'StatusFrame.kt'))
        self.assertIn('interferenceRaw', sf)
        self.assertIn('interferenceUp', sf)
        self.assertIn('interferenceDown', sf)
        self.assertIn('bb.getInt(76)', sf, 'word[19] 偏移 = 19*4')
        page = read(os.path.join(ANDROID_JAVA, 'ui', 'pages', 'StatusPage.kt'))
        self.assertIn('干扰 上行', page)
        self.assertIn('干扰 下行', page)

    def test_android_gate_default_matches_pc(self):
        """安卓 RSSI 迟滞默认值必须与桌面 DEFAULT_RSSI_HYST_DB 一致。"""
        pc = read(os.path.join(DESKTOP, 'cr_lbj', 'core', 'decoder.py'))
        self.assertIn('DEFAULT_RSSI_HYST_DB = 4.0', pc)
        kt = read(os.path.join(ANDROID_JAVA, 'core', 'ReceiverSettings.kt'))
        self.assertIn('val rssiHystDb: Double = 4.0', kt,
                      '安卓迟滞默认值应已对齐 PC 的 4.0')


if __name__ == '__main__':
    unittest.main()