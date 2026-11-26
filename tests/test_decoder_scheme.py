# -*- coding: utf-8 -*-
"""任务11：车次分类纯自动、纯日期驱动（2027-01-01 切换）测试。

覆盖桌面 cr_lbj/core/decoder.py 的 classifyTrainCategory（拨钟注入 now）与
配置加载器对旧 trainScheme 键的容错。安卓 TrainClassifier 的 1:1 由同源向量
（android/tools/duipai/gen_classifier_vectors.py 生成）保证：
  - Kotlin 侧：android/app/src/test/.../engine/TrainClassifierTest.kt（lead 集成时跑）
  - Python 侧：本文件 VectorConsistencyTest 消费同一组 classifier_vectors.json
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(ROOT, 'desktop')   # 桌面端包 cr_lbj 在 desktop/ 下
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

from cr_lbj.core import decoder as D  # noqa: E402

# 拨钟档位（本地时间语义，与桌面 datetime.now() 一致）
BEFORE = datetime(2026, 11, 26, 12, 0, 0)   # 过渡期
MID = datetime(2026, 12, 26, 12, 0, 0)      # 旧切换日(2026-12-25)之后、新切换日之前
AFTER = datetime(2027, 1, 2, 12, 0, 0)      # 新切换日之后
TZ8 = timezone(timedelta(hours=8))


def cat(train, speed=None, now=BEFORE, detailed=False):
    return D.classifyTrainCategory(train, detailed, speed=speed, now=now)


class TransitionTest(unittest.TestCase):
    """now < 2027-01-01：过渡期行为与原 auto 逐条一致。"""

    def test_stable_prefixes_always_new(self):
        cases = {
            'G1234': '高速动车组 (350km/h)',
            'D123': '动力集中动车组 (≤200km/h)',
            'C12': '城际动车组 (≤200km/h)',
            'S1': '市郊(域)列车 (≤160km/h)',
            'Z123': '快速旅客列车 (160km/h)',
            'N123': '快速旅客列车 (140km/h)',
        }
        for train, expected in cases.items():
            self.assertEqual(cat(train), expected, train)
            self.assertEqual(cat(train, speed='80'), expected, train)  # 低速不影响

    def test_v_y_b_dh_dj_segments(self):
        cases = {
            'V6001': '普通旅客快车 (120km/h)',
            'V7001': '普通旅客慢车 (120km/h)',
            'V3000': '快速旅客列车 (120km/h)',
            'Y500': '普速旅游专线列车',
            'Y1500': '普速旅游专列',
            'B100': '特快城际班列 (160km/h)',
            'B2001': '快速中欧班列 (120km/h)',
            'B9001': '普快中亚班列 (90km/h)',
            'B5000': '普快多式联运班列 (90km/h)',
            'DH500': '动车组快运 (250km/h+)',
            'DH1500': '动车组快运 (≤250km/h)',
            'DJ1': '动车组检测/确认列车',
        }
        for train, expected in cases.items():
            self.assertEqual(cat(train), expected, train)

    def test_tkx_low_speed_legacy(self):
        self.assertEqual(cat('T398', speed='140'), '特快旅客列车')
        self.assertEqual(cat('K19533', speed='80'), '快速旅客列车')
        self.assertEqual(cat('X101', speed='160'), '行包货物列车')
        self.assertEqual(cat('T398', speed='199'), '特快旅客列车')   # 边界下侧
        self.assertEqual(cat('T398', speed='0'), '特快旅客列车')     # 0 是有效速度

    def test_tkx_high_speed_new(self):
        self.assertEqual(cat('T398', speed='200'), '特快动车组 (300km/h)')  # 边界上侧
        self.assertEqual(cat('K19533', speed='250'), '快速动车组 (200~250km/h)')
        self.assertEqual(cat('X101', speed='350'), '新时速动车组 (350km/h+)')
        self.assertEqual(cat('T398', speed='500'), '特快动车组 (300km/h)')

    def test_tkx_speed_missing_or_invalid_legacy(self):
        for spd in (None, '---', '', 'abc', '501', '-5'):
            self.assertEqual(cat('T398', speed=spd), '特快旅客列车', repr(spd))
            self.assertEqual(cat('K19533', speed=spd), '快速旅客列车', repr(spd))
            self.assertEqual(cat('X101', speed=spd), '行包货物列车', repr(spd))
        self.assertEqual(cat('T398', speed='80km/h'), '特快旅客列车')  # 后缀可解析

    def test_numeric_new_table_in_transition(self):
        # 纯数字过渡期也走新版区段表（原 auto 行为）：71001~77998 统一重载
        self.assertEqual(cat('50001'), '客车单机')
        self.assertEqual(cat('71001'), '重载货物列车')
        self.assertEqual(cat('73001'), '重载货物列车')
        self.assertEqual(cat('75001'), '重载货物列车')
        self.assertEqual(cat('00123'), '动车组无火跨局回送')
        self.assertEqual(cat('00050'), '动车组有火回送')
        self.assertEqual(cat('00500'), '未知类别')
        self.assertEqual(cat('1234'), '等待详细报文确认...')
        self.assertEqual(cat('1234', detailed=True), '普通旅客列车')
        self.assertEqual(cat('Q123'), '等待详细报文确认...')  # 未知前缀数字兜底

    def test_normalization_and_placeholders(self):
        self.assertEqual(cat('g7'), '高速动车组 (350km/h)')
        self.assertEqual(cat(' T 398 '), '特快旅客列车')
        for train in ('', '----', '等待信号...'):
            self.assertEqual(cat(train), '等待信号...')


class AfterSwitchTest(unittest.TestCase):
    """now >= 2027-01-01：高铁+普速一律新版，不看速度。"""

    def test_tkx_any_speed_new(self):
        for spd in (None, '---', '0', '80', '140', '199', '350', 'abc'):
            self.assertEqual(cat('T398', speed=spd, now=AFTER),
                             '特快动车组 (300km/h)', repr(spd))
            self.assertEqual(cat('K19533', speed=spd, now=AFTER),
                             '快速动车组 (200~250km/h)', repr(spd))
            self.assertEqual(cat('X101', speed=spd, now=AFTER),
                             '新时速动车组 (350km/h+)', repr(spd))

    def test_stable_prefixes_unchanged(self):
        self.assertEqual(cat('G1234', now=AFTER), '高速动车组 (350km/h)')
        self.assertEqual(cat('D123', speed='30', now=AFTER), '动力集中动车组 (≤200km/h)')
        self.assertEqual(cat('V6001', now=AFTER), '普通旅客快车 (120km/h)')
        self.assertEqual(cat('B2001', now=AFTER), '快速中欧班列 (120km/h)')
        self.assertEqual(cat('DJ1', now=AFTER), '动车组检测/确认列车')

    def test_numeric_new_table(self):
        self.assertEqual(cat('71001', now=AFTER), '重载货物列车')
        self.assertEqual(cat('73001', now=AFTER), '重载货物列车')
        self.assertEqual(cat('75001', now=AFTER), '重载货物列车')
        self.assertEqual(cat('00123', now=AFTER), '动车组无火跨局回送')
        self.assertEqual(cat('1234', now=AFTER), '等待详细报文确认...')
        self.assertEqual(cat('1234', now=AFTER, detailed=True), '普通旅客列车')


class BoundaryTest(unittest.TestCase):
    """切换边界与「速度缺失回退日期统一 2027-01-01」。"""

    def test_constant(self):
        self.assertEqual(D.TRAIN_NEW_SCHEME_DATE, datetime(2027, 1, 1))

    def test_boundary_inclusive(self):
        # 2027-01-01 00:00:00 整（>=）即全量新版
        self.assertEqual(cat('T398', now=datetime(2027, 1, 1, 0, 0, 0)),
                         '特快动车组 (300km/h)')
        self.assertEqual(cat('K19533', speed='80', now=datetime(2027, 1, 1)),
                         '快速动车组 (200~250km/h)')
        # 前一秒仍是过渡期
        self.assertEqual(cat('T398', now=datetime(2026, 12, 31, 23, 59, 59)),
                         '特快旅客列车')

    def test_missing_speed_fallback_date_unified(self):
        # 2026-12-26 已过旧切换日(2026-12-25)：旧实现会判新版，
        # 新实现回退日期统一为 2027-01-01 → 仍按旧版兜底
        self.assertEqual(cat('T398', now=MID), '特快旅客列车')
        self.assertEqual(cat('K19533', now=MID), '快速旅客列车')
        self.assertEqual(cat('X101', now=MID), '行包货物列车')
        # 有速度时 MID 档仍按速度判定（过渡期行为不变）
        self.assertEqual(cat('T398', speed='300', now=MID), '特快动车组 (300km/h)')

    def test_default_now_uses_system_clock(self):
        class FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2027, 3, 1, 12, 0, 0)
        with mock.patch.object(D, 'datetime', FakeDateTime):
            self.assertEqual(D.classifyTrainCategory('T398', False),
                             '特快动车组 (300km/h)')


class ApiAndConfigTest(unittest.TestCase):
    """手动方案删除干净 + 旧配置容错（破坏性更新，无迁移层）。"""

    def test_no_scheme_parameter(self):
        params = inspect.signature(D.classifyTrainCategory).parameters
        self.assertNotIn('scheme', params)
        self.assertIn('now', params)
        self.assertIsNone(params['now'].default)
        self.assertNotIn('trainScheme', inspect.signature(D.LbjDecoder).parameters)
        self.assertNotIn('trainScheme', inspect.signature(D.LbjCore).parameters)
        self.assertNotIn('newScheme', inspect.signature(D._categoryNumeric).parameters)

    def test_core_config_no_train_scheme(self):
        c = D.CoreConfig()
        self.assertFalse(hasattr(c, 'trainScheme'))
        self.assertNotIn('trainScheme', c.toDict())

    def test_from_dict_ignores_legacy_key(self):
        c = D.CoreConfig.fromDict({'trainScheme': 'legacy', 'host': '1.2.3.4'})
        self.assertFalse(hasattr(c, 'trainScheme'))
        self.assertEqual(c.host, '1.2.3.4')

    def test_load_old_config_file_no_crash(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'old.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'trainScheme': '2026', 'dedupeWindow': 3.0}, f)
            c = D.CoreConfig.load(p)
            self.assertFalse(hasattr(c, 'trainScheme'))
            self.assertEqual(c.dedupeWindow, 3.0)

    def test_shipped_configs_have_no_key(self):
        for name in ('lbj_config.json', 'lbj_config.local.json'):
            p = os.path.join(DESKTOP, name)
            if not os.path.exists(p):
                continue
            with open(p, encoding='utf-8') as f:
                self.assertNotIn('trainScheme', json.load(f), name)

    def test_decoder_constructs_without_scheme(self):
        dec = D.LbjDecoder(fs=48000)
        self.assertFalse(hasattr(dec, 'trainScheme'))


class VectorConsistencyTest(unittest.TestCase):
    """与 Kotlin 测试同源的覆盖性向量（≥60 条）在 Python 侧逐条复核。"""

    def test_vectors(self):
        p = os.path.join(ROOT, 'android', 'tools', 'duipai', 'classifier_vectors.json')
        if not os.path.exists(p):
            self.skipTest('classifier_vectors.json 缺失（先跑 gen_classifier_vectors.py）')
        with open(p, encoding='utf-8') as f:
            rows = json.load(f)
        self.assertGreaterEqual(len(rows), 60)
        for r in rows:
            now = datetime.fromtimestamp(r['nowMs'] / 1000, TZ8).replace(tzinfo=None)
            got = D.classifyTrainCategory(r['train'], r['detailed'],
                                          speed=r['speed'], now=now)
            self.assertEqual(got, r['expected'],
                             f"{r['train']} speed={r['speed']} nowMs={r['nowMs']}")


if __name__ == '__main__':
    unittest.main()
