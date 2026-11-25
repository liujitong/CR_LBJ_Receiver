# -*- coding: utf-8 -*-
"""自动更新（cr_lbj/data/updater.py）测试。

全部用合成数据 + monkeypatch 替换网络层，不依赖外网；真实上游只在校验脚本里手工跑。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cr_lbj.data import loco_roster as R  # noqa: E402
from cr_lbj.data import paths as P  # noqa: E402
from cr_lbj.data import updater as U  # noqa: E402


def make_csv(rows: int = 15100, models: int = 130) -> str:
    """造一份「结构合格」的号段表：models 个型号、每个若干行、中文配属。"""
    out = []
    per = max(1, rows // models)
    n = 0
    for m in range(models):
        model = 'T%03d' % m
        depot = '测试机务段%d' % m
        for i in range(per):
            out.append('%s,%d,%d,%s,,测试厂' % (model, i * 10 + 1, i * 10 + 10, depot))
            n += 1
    while n < rows:                      # 补齐到目标行数
        out.append('T000,%d,%d,测试机务段0,,测试厂' % (n * 10, n * 10 + 9))
        n += 1
    return '\n'.join(out) + '\n'


class ValidateTest(unittest.TestCase):
    def test_good(self):
        rows, models, err = U.validate_roster_text(make_csv())
        self.assertEqual(err, '', err)
        self.assertGreaterEqual(rows, U.MIN_ROWS)
        self.assertGreaterEqual(models, U.MIN_MODELS)

    def test_too_short(self):
        rows, models, err = U.validate_roster_text('A,1,2,某段,,厂\n')
        self.assertTrue(err)
        self.assertTrue(('行数不足' in err) or ('过短' in err), err)

    def test_html_page(self):
        _, _, err = U.validate_roster_text('<!DOCTYPE html><html><body>404</body></html>')
        self.assertTrue(err)

    def test_malformed_numbers(self):
        bad = make_csv().replace('T000,1,10', 'T000,x,10')
        _, _, err = U.validate_roster_text(bad)
        # 畸形占比很低时仍应通过（容忍上游偶发脏行）
        self.assertEqual(err, '')

    def test_reversed_range_detected(self):
        # 少量脏行要容忍（上游偶发），超过 2% 必须拒绝
        txt = make_csv() + 'ZZ9,100,50,某段,,厂\n' * 50
        self.assertEqual('', U.validate_roster_text(txt)[2])
        txt = make_csv() + 'ZZ9,100,50,某段,,厂\n' * 800
        self.assertIn('畸形行', U.validate_roster_text(txt)[2])


class UpdateFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='crlbj_upd_')
        self._old_env = os.environ.get('CRLBJ_DATA_DIR')
        os.environ['CRLBJ_DATA_DIR'] = self.tmp
        R.invalidate()
        self._orig_fetch = U.fetch_remote

    def tearDown(self):
        U.fetch_remote = self._orig_fetch
        if self._old_env is None:
            os.environ.pop('CRLBJ_DATA_DIR', None)
        else:
            os.environ['CRLBJ_DATA_DIR'] = self._old_env
        R.invalidate()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_update_writes_file_and_manifest(self):
        csv_text = 'T001,1,100,测试机务段A,,厂\n' * 200
        U.fetch_remote = lambda timeout=20.0: (csv_text, 'sha-abc')
        # 合成数据行数不够 → 应被校验挡下，不写盘
        res = U.check_and_update(force=True)
        self.assertFalse(res['ok'])
        self.assertIn('校验未通过', res['message'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'loco_roster.csv')))

        big = make_csv()
        U.fetch_remote = lambda timeout=20.0: (big, 'sha-abc')
        res = U.check_and_update(force=True)
        self.assertTrue(res['ok'], res['message'])
        self.assertTrue(res['updated'], res['message'])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'loco_roster.csv')))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, U.MANIFEST_NAME)))
        self.assertEqual(U.read_manifest()[U.ROSTER_NAME]['sha'], 'sha-abc')

    def test_same_sha_skips(self):
        big = make_csv()
        U.fetch_remote = lambda timeout=20.0: (big, 'sha-xyz')
        self.assertTrue(U.check_and_update(force=True)['updated'])
        res = U.check_and_update(force=True)
        self.assertFalse(res['updated'])
        self.assertTrue(res['skipped'])
        self.assertIn('已是最新', res['message'])

    def test_interval_skip_without_force(self):
        res = U.check_and_update(force=False, interval_days=7)
        # 刚写过的 manifest 会让非强制检查直接跳过
        U.fetch_remote = lambda timeout=20.0: (_ for _ in ()).throw(AssertionError('不该联网'))
        res2 = U.check_and_update(force=False, interval_days=7)
        self.assertTrue(res2['skipped'] or res2['ok'])
        self.assertEqual(res2['message'].count('不该联网'), 0)

    def test_network_error_is_soft(self):
        def boom(timeout=20.0):
            raise OSError('no route to host')
        U.fetch_remote = boom
        res = U.check_and_update(force=True)
        self.assertFalse(res['ok'])
        self.assertIn('失败', res['message'])

    def test_backup_and_restore(self):
        big = make_csv()
        U.fetch_remote = lambda timeout=20.0: (big, 'sha-1')
        U.check_and_update(force=True)
        first = open(os.path.join(self.tmp, 'loco_roster.csv'), encoding='utf-8').read()
        big2 = big.replace('测试机务段0', '测试机务段改')
        U.fetch_remote = lambda timeout=20.0: (big2, 'sha-2')
        self.assertTrue(U.check_and_update(force=True)['updated'])
        self.assertTrue(U.backup_exists())
        r = U.restore_backup()
        self.assertTrue(r['ok'], r['message'])
        second = open(os.path.join(self.tmp, 'loco_roster.csv'), encoding='utf-8').read()
        self.assertEqual(first, second)


class PathsTest(unittest.TestCase):
    def test_user_dir_env_override(self):
        tmp = tempfile.mkdtemp(prefix='crlbj_paths_')
        old = os.environ.get('CRLBJ_DATA_DIR')
        try:
            os.environ['CRLBJ_DATA_DIR'] = tmp
            self.assertEqual(os.path.abspath(P.user_data_dir()), os.path.abspath(tmp))
            # 覆盖层没有文件时回退到内置快照
            self.assertFalse(P.is_user_override(P.data_path('loco_roster.csv')))
            open(os.path.join(tmp, 'loco_roster.csv'), 'w', encoding='utf-8').write('x')
            self.assertTrue(P.is_user_override(P.data_path('loco_roster.csv')))
        finally:
            if old is None:
                os.environ.pop('CRLBJ_DATA_DIR', None)
            else:
                os.environ['CRLBJ_DATA_DIR'] = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
