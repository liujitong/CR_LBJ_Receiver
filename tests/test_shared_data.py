# -*- coding: utf-8 -*-
"""共享数据（shared/data）的一致性与查询正确性测试。

运行：
    python -m pytest tests -q            # 或
    python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cr_lbj.data import loco_roster as R  # noqa: E402


class SharedFilesTest(unittest.TestCase):
    def test_shared_dir_exists(self):
        d = R.shared_dir()
        self.assertTrue(os.path.isdir(d), '找不到 shared/data: %s' % d)
        for name in ('loco_roster.csv', 'loco_types.csv', 'loco_specs.json', 'places.csv'):
            self.assertTrue(os.path.exists(os.path.join(d, name)), '缺少 %s' % name)

    def test_available(self):
        self.assertTrue(R.available(), 'shared 数据不可用（可能缺 loco_roster.csv）')

    def test_stats(self):
        s = R.stats()
        # 号段表是外部数据，只锁下限量级，避免上游增删导致测试噪音
        self.assertGreaterEqual(s['rows'], 15000, s)
        self.assertGreaterEqual(s['models'], 120, s)
        self.assertLessEqual(s['emptyDepot'], 20, '配属缺失行突然变多，检查数据来源是否换版')


class LocoTypesTest(unittest.TestCase):
    def test_known_codes(self):
        self.assertEqual(R.type_name('240'), 'HXD1D')
        self.assertEqual(R.short_code(code='240'), 'HXD1D')
        self.assertEqual(R.short_code(code='207'), 'SS4')
        self.assertEqual(R.short_code(code='104'), 'DF4B')

    def test_unknown_code(self):
        self.assertEqual(R.type_name('99999'), '')
        # 未知代号退化成「原样大写」，不能抛异常
        self.assertEqual(R.short_code(code='99999', name='xyz1'), 'XYZ1')

    def test_name_to_short(self):
        self.assertEqual(R.short_code(name='韶山4'), 'SS4')
        self.assertEqual(R.short_code(name='HXD1D'), 'HXD1D')
        self.assertEqual(R.short_code(name=''), '')


class LocoLookupTest(unittest.TestCase):
    def test_exact_hit(self):
        res = R.lookup_loco('HXD1D-0123', '240')
        self.assertTrue(res['ok'])
        self.assertTrue(res['exact'])
        self.assertEqual(res['model'], 'HXD1D')
        self.assertEqual(res['number'], 123)
        self.assertTrue(res['depot'])
        self.assertIn('-', res['range'])

    def test_depot_only_not_fabricated(self):
        """号段表里没有的编号 → exact=False，且不能编造配属。"""
        res = R.lookup_loco('HXD1D-99999', '240')
        self.assertTrue(res['ok'])
        self.assertFalse(res['exact'])
        self.assertEqual(res['depot'], '')
        self.assertTrue(res['reason'])

    def test_unknown_model_suggests(self):
        res = R.lookup('DF4B', 3001)
        # DF4B 有别名 → DF4，应命中
        self.assertTrue(res['ok'])
        self.assertTrue(res['exact'])
        self.assertEqual(res.get('aliasFrom'), 'DF4B')

    def test_wrong_model(self):
        res = R.lookup('NOTAMODEL', 1)
        self.assertFalse(res['ok'])
        self.assertTrue(res['reason'])

    def test_lookup_never_raises(self):
        for model, num in [(None, None), ('', 0), ('HXD1D', 'abc'), ('HXD1D', -5),
                           ('韶山4', '0123'), ('  HXD1D  ', ' 106 ')]:
            res = R.lookup(model, num)
            self.assertIsInstance(res, dict)
            self.assertIn('ok', res)

    def test_format_depot(self):
        res = R.lookup_loco('HXD1D-0123', '240')
        line = R.format_depot(res)
        self.assertIn('HXD1D', line)
        self.assertIn('→', line)

    def test_ranges_sorted(self):
        for model in R.models()[:20]:
            nums = R.model_numbers(model)
            starts = [x['start'] for x in nums]
            self.assertEqual(starts, sorted(starts), '%s 号段未按起号排序' % model)

    def test_depots_nonempty(self):
        d = R.depots()
        self.assertGreater(len(d), 100, '配属单位数量异常：%d' % len(d))


class SpecsTest(unittest.TestCase):
    def test_specs_hit(self):
        sp = R.specs_for('HXD1D')
        self.assertTrue(sp, 'HXD1D 应有参数')
        self.assertIn('power', sp)
        self.assertIn('speed', sp)

    def test_specs_prefix_fallback(self):
        # 号段表里有 HXD3CA，参数表只有 HXD3C → 前缀兜底
        sp = R.specs_for('HXD3CA')
        self.assertTrue(sp)

    def test_specs_unknown(self):
        self.assertEqual(R.specs_for('NOSUCHLOCO'), {})

    def test_meta(self):
        m = R.specs_meta()
        self.assertTrue(m['revision'])
        self.assertTrue(m['sources'])


class PlacesTest(unittest.TestCase):
    def test_places_parse(self):
        import csv
        path = os.path.join(R.shared_dir(), 'places.csv')
        rows = []
        with open(path, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                if not row or row[0].startswith('#') or row[0] == 'name':
                    continue
                rows.append(row)
        self.assertGreaterEqual(len(rows), 30, '预设中心太少')
        for name, lat, lng in ((r[0], float(r[1]), float(r[2])) for r in rows):
            self.assertTrue(3.8 <= lat <= 53.6, '%s 纬度越界 %s' % (name, lat))
            self.assertTrue(73.6 <= lng <= 135.1, '%s 经度越界 %s' % (name, lng))


if __name__ == '__main__':
    unittest.main()
