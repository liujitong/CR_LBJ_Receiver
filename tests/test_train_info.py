# -*- coding: utf-8 -*-
"""车次查询（cr_lbj/data/train_info.py）测试。

联网用例在本机网络不可达时自动 skip（RailGo / 12306 都是外部服务）。
"""

from __future__ import annotations

import os
import socket
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cr_lbj.data import train_info as T  # noqa: E402


def _online(host: str, port: int = 443, timeout: float = 4.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


HAS_RAILGO = _online('data.railgo.zenglingkun.cn')
HAS_12306 = _online('search.12306.cn')


class OfflineLogicTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(T.normalize_train(' g7 '), 'G7')
        self.assertEqual(T.normalize_train('　k１２３'), 'K１２３')
        self.assertEqual(T.normalize_train(None), '')

    def test_is_train_code(self):
        for good in ('G7', 'K1234', 'Z1', 'D1', 'C2001', '1461', 'T1', 'y701'):
            self.assertTrue(T.is_train_code(good), good)
        for bad in ('', 'G', '/', 'G1234567', '车站'):
            self.assertFalse(T.is_train_code(bad), bad)

    def test_stop_minutes(self):
        self.assertEqual(T._stop_minutes('10:00', '10:05'), 5)
        self.assertEqual(T._stop_minutes('10:05', '10:00'), 0)   # 跨零点/异常 → 0
        self.assertEqual(T._stop_minutes('----', '----'), 0)
        self.assertEqual(T._stop_minutes('23:50', '00:10'), 0)   # 不臆测跨日

    def test_blank_shape(self):
        b = T._blank()
        for key in ('ok', 'source', 'error', 'train', 'stops', 'diagram',
                    'stops', 'start', 'end', 'rundaysCount'):
            self.assertIn(key, b)
        self.assertFalse(b['ok'])

    def test_bad_input_returns_error(self):
        res = T.query('不是车次')
        self.assertFalse(res['ok'])
        self.assertTrue(res['error'])

    def test_summary_line(self):
        ok = {'ok': True, 'train': 'G7', 'category': '高速',
              'start': '北京南', 'end': '上海虹桥', 'carOwner': '北京动车段'}
        self.assertIn('G7', T.summary_line(ok))
        self.assertIn('北京动车段', T.summary_line(ok))
        bad = {'ok': False, 'train': 'X1', 'error': '超时'}
        self.assertIn('失败', T.summary_line(bad))


@unittest.skipUnless(HAS_RAILGO, 'RailGo 不可达')
class RailGoLiveTest(unittest.TestCase):
    def test_query_g7(self):
        res = T.query_railgo('G7')
        self.assertTrue(res['ok'], res.get('error'))
        self.assertEqual(res['source'], 'railgo')
        self.assertTrue(res['stops'], '时刻表不应为空')
        self.assertEqual(res['start'], '北京南')
        self.assertTrue(res['carOwner'] or res['bureau'], '应至少给出配属段或担当局')
        self.assertEqual(res['stops'][0]['no'], 1)

    def test_query_case_and_fallback(self):
        res = T.query('g7')
        self.assertTrue(res['ok'], res.get('error'))
        self.assertEqual(res['train'], 'G7')

    def test_unknown_train(self):
        res = T.query_railgo('G99999')
        self.assertFalse(res['ok'])
        self.assertTrue(res['error'])


@unittest.skipUnless(HAS_12306, '12306 不可达')
class Official12306LiveTest(unittest.TestCase):
    def test_query_g1(self):
        res = T.query_12306('G1')
        self.assertTrue(res['ok'], res.get('error'))
        self.assertEqual(res['source'], '12306')
        self.assertTrue(res['stops'])
        self.assertEqual(res['start'], '北京南')


if __name__ == '__main__':
    unittest.main()
