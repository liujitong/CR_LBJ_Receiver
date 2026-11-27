# -*- coding: utf-8 -*-
"""桌面端 v3.2.1 改动回归测试（新增文件，由 desktop-fix 提交）。

覆盖两类无需启动 Qt 的检查：

1. `cr_lbj.data.depot_names` 的配属/制造厂全称化（含用户要求的
   「南局南段 → 南昌局南昌机务段」与查不到时原样返回、不编造）；
2. 桌面端源码里的 v3.2.1 结构约定（版本号、配置分页合并、历史记录进工具菜单、
   列车信息面板瘦身、车次卡改用整份查询结果）。

Qt 界面本身由离屏冒烟与人工验收覆盖，这里不导入 Qt，保证测试快速稳定。
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(ROOT, 'desktop')
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

from cr_lbj.data import depot_names as D  # noqa: E402


# ---------------------------------------------------------------------------
# 一、全称化
# ---------------------------------------------------------------------------
def test_depot_full_name_for_user_examples():
    # 用户点名的例子：南昌局南昌机务段
    assert D.full_depot('南局南段') == '南昌局南昌机务段'
    # 号段表最常见的几条
    assert D.full_depot('上局沪段') == '上海局上海机务段'
    assert D.full_depot('京局京段') == '北京局北京机务段'
    assert D.full_depot('广铁株段') == '广州局株洲机务段'
    assert D.full_depot('西局新段') == '西安局新丰镇机务段'


def test_depot_bracket_remark_preserved():
    assert D.full_depot('京局丰段（京铁运输）') == '北京局丰台机务段（京铁运输）'
    assert D.full_depot('沈局锦州车辆段') == '沈阳局锦州车辆段'


def test_depot_unknown_kept_verbatim():
    # 号段表里还有大量地方铁路/企业自备配属：没人工核对过就原样显示，绝不猜
    for raw in ('上局皖铁发', '西局国铁运维', '哈局运管', '暂无数据', '配属未知'):
        assert D.full_depot(raw) == raw
    assert D.full_depot('南局南段') != '南局南段'


def test_maker_full_names():
    assert D.full_maker('中车株洲机车') == '中车株洲电力机车有限公司'
    assert D.full_maker('中车大连机车') == '中车大连机车车辆有限公司'
    assert D.full_maker('中车株洲') == '中车株洲电力机车有限公司'
    assert D.full_maker('四方/唐山') == (
        '中车青岛四方机车车辆股份有限公司 / 中车唐山机车车辆有限公司')
    assert D.full_maker('AST') == 'AST'
    assert D.full_maker('') == ''


def test_duty_full_name_concat():
    # 车次卡：RailGo 的 bureau 常是简称（京局 / 南局），必须展开成全称再拼担当段
    assert D.full_bureau('京局') == '北京局'
    assert D.full_bureau('南局') == '南昌局'
    assert D.full_bureau('南昌局') == '南昌局'          # 已全称不动
    assert D.format_duty('南昌局', '南昌客运段') == '南昌局南昌客运段'
    assert D.format_duty('京局', '天津客运段') == '北京局天津客运段'
    assert D.format_duty('北京局集团公司', '北京客运段') == '北京局集团公司北京客运段'
    # 段名已自带局名时不重复
    assert D.format_duty('南局', '南昌局南昌客运段') == '南昌局南昌客运段'
    assert D.format_duty('', '南昌客运段') == '南昌客运段'
    assert D.format_duty('南昌局', '') == '南昌局'


def test_train_range_text():
    assert D.format_train_range('北京西', '上海虹桥') == '北京西 → 上海虹桥'
    assert D.format_train_range('北京西', '') == '北京西'


# ---------------------------------------------------------------------------
# 二、源码结构约定（只读文本，不导入 Qt）
# ---------------------------------------------------------------------------
def _read(*parts: str) -> str:
    path = os.path.join(DESKTOP, *parts)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def test_version_is_v321():
    # 版本断言随当前发布版滚动更新（v3.2.5）；旧版本标题/标签不应残留
    # （代码注释里的历史小版本说明允许保留，不算残留）
    init = _read('cr_lbj', '__init__.py')
    assert "__version__ = '3.2.10'" in init
    main = _read('cr_lbj', 'ui', 'windows', 'main_window.py')
    assert "v3.2.10'" in main
    assert "kv('版本', 'v3.2.10')" in main
    assert "v3.2.4'" not in main
    assert "v3.2.0'" not in main


def test_history_tab_removed_and_tool_action_added():
    main = _read('cr_lbj', 'ui', 'windows', 'main_window.py')
    assert 'self.historyPanel' not in main
    assert '历史记录...' in main
    assert 'openHistoryDialog' in main
    # 主界面不再有两个页签
    assert "addTab(self.currentPanel" not in main
    assert 'self.tabs = QTabWidget()' not in main


def test_train_info_panel_slimmed():
    panel = _read('cr_lbj', 'ui', 'components', 'info_panels.py')
    assert "'trainInfo'" not in panel
    assert "'locoDepot'" not in panel
    assert 'def setInfo' not in panel


def test_config_pages_merged():
    # v3.2.4：常量从 history_panel.py 移到 runtime 共享层（config_ui/main_window 只
    # star-import runtime，留在旧模块会 NameError，打开配置对话框直接崩）
    const = _read('cr_lbj', 'runtime.py')
    assert "CONFIG_PAGES = ['数据源与射频'" in const
    pages_line = next(line for line in const.splitlines()
                      if line.startswith('CONFIG_PAGES = '))
    assert '射频设置' not in pages_line
    assert '数据源配置' not in pages_line
    ui = _read('cr_lbj', 'ui', 'dialogs', 'config_ui.py')
    assert "page('数据源与射频')" in ui
    assert "page('射频设置')" not in ui


def test_train_card_uses_full_query_worker():
    src = _read('cr_lbj', 'ui', 'components', 'train_query.py')
    # 车次卡优先 RailGo、保留 12306 兜底（复用 train_info.query 的 prefer）
    assert 'TrainFullQueryWorker' in src
    assert 'train_display' in src
    # 旧的手写 12306 worker 已删除
    assert 'class TrainQueryWorker' not in src
    # 机车卡使用全称化
    assert 'full_depot' in src and 'full_maker' in src


def test_detail_dialog_has_railgo_section():
    src = _read('cr_lbj', 'ui', 'dialogs', 'detail_dialogs.py')
    assert 'TrainFullQueryWorker' in src
    assert '_railgoLabel' in src
    assert '未查询到' in src


def test_history_dialog_and_db_delete():
    src = _read('cr_lbj', 'ui', 'dialogs', 'history_dialog.py')
    assert 'class HistoryDialog' in src
    assert 'deleteByIds' in src
    assert 'deleteAll' in src
    db = _read('cr_lbj', 'data', 'history.py')
    assert 'def deleteByIds' in db
    assert 'def queryRecent' in db
    assert 'latitude' in db


@pytest.mark.parametrize('name,expect', [
    ('上局徐段', '上海局徐州机务段'),
    ('兰局迎段', '兰州局迎水桥机务段'),
    ('太局候段', '太原局侯马北机务段'),
    ('青藏宁段', '青藏集团公司西宁机务段'),
])
def test_more_depot_names(name, expect):
    assert D.full_depot(name) == expect