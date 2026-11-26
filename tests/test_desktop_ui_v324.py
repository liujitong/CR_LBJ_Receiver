# -*- coding: utf-8 -*-
"""桌面端 v3.2.4 回归测试（纯源码约定检查，不导入 Qt）。

覆盖：
1. `fit_dialog_to_screen` 公共函数存在且按屏收尺寸；
2. 六个二级窗口都改用它（不再写死尺寸 / setFixedSize）；
3. 表格列宽策略：只保留 1~2 个关键列 ResizeToContents，其余可压缩；
4. 状态仪表板网格列数按宽度自适应（宽 4 / 中 3 / 窄 2）；
5. ORM 透明度链路：配置 → payload.railOpacity → 页面，且死方法已清理；
6. v3.2.4 回归防护：`CONFIG_PAGES` 等常量必须在 runtime 共享层（否则
   config_ui / main_window 会 NameError，打开配置直接崩）。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, 'desktop', 'cr_lbj', 'ui')


def read(rel: str) -> str:
    with open(os.path.join(UI, rel), 'r', encoding='utf-8') as f:
        return f.read()


class DialogFitTest(unittest.TestCase):

    def test_helper_exists(self):
        w = read('widgets.py')
        self.assertIn('def fit_dialog_to_screen(', w)
        body = w.split('def fit_dialog_to_screen(', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('availableGeometry()', body, '必须按屏可用区收紧')
        self.assertIn('screenAt(QCursor.pos())', body, '未 show 时用鼠标所在屏兜底')
        self.assertIn('setMinimumSize(', body, '下限也要收进屏幕')
        self.assertIn('dlg.resize(', body)
        self.assertIn('.move(', body, '要居中')
        # runtime 转发，保证所有 `from cr_lbj.runtime import *` 的模块都能用
        self.assertIn('fit_dialog_to_screen', read('../runtime.py'))

    def test_dialogs_use_helper(self):
        cases = [
            ('dialogs/history_dialog.py', 'fit_dialog_to_screen(self, 1040, 700, 760, 460)'),
            ('dialogs/query_ui.py', 'fit_dialog_to_screen(self, 860, 720, 620, 480)'),
            ('dialogs/help_dialogs.py', 'fit_dialog_to_screen(self, 700, 640, 460, 400)'),
            ('dialogs/help_dialogs.py', 'fit_dialog_to_screen(self, 540, 480, 420, 360)'),
            ('windows/main_window.py', 'fit_dialog_to_screen(self, 720, 660, 520, 440)'),
            ('dialogs/config_ui.py', 'fit_dialog_to_screen(self, 820, 660, 720, 560)'),
        ]
        for rel, needle in cases:
            self.assertIn(needle, read(rel), '%s 未改为 fit_dialog_to_screen' % rel)

    def test_no_hardcoded_dialog_sizes(self):
        # AboutDialog 原 setFixedSize 必须去掉（用户要求可缩放）
        self.assertNotIn('setFixedSize(spx(540), spx(480))',
                         read('dialogs/help_dialogs.py'))
        # 配置对话框原来用裸像素 720/560，不是 spx，用户点名要改
        cfg = read('dialogs/config_ui.py')
        self.assertNotIn('setMinimumSize(720, 560)', cfg)
        self.assertNotIn('self.resize(820, 660)', cfg)


class TableColumnTest(unittest.TestCase):

    def test_history_columns_compressible(self):
        src = read('dialogs/history_dialog.py')
        self.assertIn('_HISTORY_TIME_COL', src)
        # 显式 Interactive 兜底 + 仅时间列 ResizeToContents + 线路列 Stretch
        self.assertIn('setSectionResizeMode(QHeaderView.Interactive)', src)
        self.assertIn('setSectionResizeMode(_HISTORY_TIME_COL, QHeaderView.ResizeToContents)',
                      src)
        self.assertIn('setSectionResizeMode(_HISTORY_STRETCH_COL, QHeaderView.Stretch)',
                      src)
        self.assertIn('setMinimumWidth(0)', src, '表格最小宽度必须放开')
        self.assertNotIn('header.setSectionResizeMode(QHeaderView.ResizeToContents)\n'
                         '        header.setSectionResizeMode(_HISTORY_STRETCH_COL',
                         src, '不应再对所有列 ResizeToContents')

    def test_query_table_columns_compressible(self):
        src = read('dialogs/query_ui.py')
        self.assertIn('table.setMinimumWidth(0)', src)
        self.assertIn('setStretchLastSection(False)', src)
        # 只让到点/发点按内容自适应
        self.assertIn('for c in (1, 2):', src)
        self.assertIn('header.setSectionResizeMode(c, QHeaderView.ResizeToContents)', src)


class DashboardAdaptiveTest(unittest.TestCase):

    def test_grid_columns_adaptive(self):
        src = read('windows/main_window.py')
        self.assertIn('def _grid_cols(', src)
        body = src.split('def _grid_cols(', 1)[1].split('\ndef ', 1)[0]
        self.assertIn('return 2', body)
        self.assertIn('return 3', body)
        self.assertIn('return 4', body)
        self.assertIn('def resizeEvent(', src, '窗口变宽/变窄时要重排列数')
        self.assertIn('cols = self._grid_cols()', src, '建卡时按当前宽度选列数')
        self.assertIn('self._builtCols', src)


class OrmOpacityTest(unittest.TestCase):

    def test_payload_carries_rail_opacity(self):
        host = read('map_host.py')
        self.assertIn("'railOpacity'", host)
        self.assertIn('mapRailOpacity', host)
        # 配置保存后走 setConfig → apply_config
        panel = read('map_panel.py')
        self.assertIn('def setConfig(', panel)
        self.assertIn('self.host.apply_config(self.config)', panel)
        # 页面侧消费（共享页）
        page = os.path.join(ROOT, 'shared', 'web', 'railmap.html')
        with open(page, 'r', encoding='utf-8') as f:
            html = f.read()
        self.assertIn('typeof cfg.railOpacity', html,
                      '页面 applyConfig 必须消费 railOpacity')

    def test_dead_method_removed(self):
        self.assertNotIn('def setRailOpacity(', read('map_panel.py'),
                         'setRailOpacity 无调用方，已清理（透明度走 apply_config）')


class SharedConstantsRegressionTest(unittest.TestCase):
    """v3.2.4 回归防护：v3.1.1 删 HistoryPanel 时把常量留在了旧模块。"""

    def test_config_pages_in_runtime(self):
        rt = read('../runtime.py')
        for name in ('CONFIG_PAGES', 'SOURCE_TYPE_LABELS', 'SOURCE_TYPE_TAGS',
                     'def default_sources('):
            self.assertIn(name, rt, '%s 必须在 runtime 共享层（否则配置对话框 NameError）' % name)

    def test_history_panel_is_thin_compat_shell(self):
        hp = read('components/history_panel.py')
        self.assertIn('from cr_lbj.runtime import *', hp)
        # 兼容壳里不应再重复定义（否则两处定义容易再次分叉）
        self.assertNotIn('CONFIG_PAGES = [', hp)

    def test_no_stale_module_references(self):
        # 配置/主窗口不应再依赖未导入的模块名
        for rel in ('dialogs/config_ui.py', 'windows/main_window.py'):
            src = read(rel)
            self.assertIn('from cr_lbj.runtime import *', src)
            self.assertNotIn('from cr_lbj.ui.components.history_panel import', src)


if __name__ == '__main__':
    unittest.main()