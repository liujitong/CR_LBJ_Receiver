#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录面板。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class HistoryPanel(QWidget):
    """历史记录面板：从 SQLite 数据库读取并显示。"""

    def __init__(self):
        super().__init__()
        self.db = HistoryDb(DB_PATH)
        self._rowIds = []  # 每行对应的数据库 id
        self._reloadPending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        self.refreshBtn = K.small_button('刷新', h=28, px=12)
        self.clearBtn = K.small_button('清空', h=28, px=12)
        self.exportBtn = K.small_button('导出 CSV...', h=28, px=12)
        self.countLabel = QLabel('0 条')
        self.countLabel.setStyleSheet(f'background: transparent; color: {CLR("faint")};')
        toolbar.addWidget(self.refreshBtn)
        toolbar.addWidget(self.clearBtn)
        toolbar.addWidget(self.exportBtn)
        toolbar.addStretch()
        toolbar.addWidget(self.countLabel)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(DECODE_COLUMNS))
        initDecodeTable(self.table)
        layout.addWidget(self.table)

        self.refreshBtn.clicked.connect(self.loadFromDb)
        self.clearBtn.clicked.connect(self.clearDb)
        self.exportBtn.clicked.connect(self.exportCsv)
        self.table.doubleClicked.connect(self._onDoubleClicked)

    def addRecord(self, d: dict):
        """写入一条记录；若为窗口内择优替换，1.2 秒后刷新表格。"""
        res = self.db.insert(d)
        if res == 'updated' and self.isVisible() and not self._reloadPending:
            self._reloadPending = True
            QTimer.singleShot(1200, self._reloadIfNeeded)

    def _reloadIfNeeded(self):
        self._reloadPending = False
        if self.isVisible():
            self.loadFromDb()

    def loadFromDb(self):
        """从 SQLite 加载历史记录到表格。"""
        self.table.setRowCount(0)
        self._rowIds = []
        try:
            rows = self.db.queryRecent(MAX_HISTORY_ROWS_UI)
            for r in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._rowIds.append(r.get('id', 0))
                for col, val in enumerate(decodeRowValues(r)):
                    item = QTableWidgetItem(str(val))
                    styleDecodeItem(item, col, val)
                    self.table.setItem(row, col, item)
            self.countLabel.setText(f'{self.table.rowCount()} 条 / 共 {self.db.count()} 条')
        except Exception as e:
            QMessageBox.warning(self, '错误', f'读取数据库失败: {e}')

    def _onDoubleClicked(self, index):
        """双击历史记录行，弹出详情对话框。"""
        row = index.row()
        if row < 0 or row >= len(self._rowIds):
            return
        record_id = self._rowIds[row]
        record = self.db.queryById(record_id)
        if record is None:
            QMessageBox.warning(self, '错误', '无法读取该记录')
            return
        dlg = RecordDetailDialog(record, self)
        dlg.exec()

    def clearDb(self):
        ret = QMessageBox.question(self, '确认', '确定要清空历史数据库吗？')
        if ret != QMessageBox.Yes:
            return
        if self.db.clear():
            self.loadFromDb()
            QMessageBox.information(self, '成功', '已清空历史数据库')
        else:
            QMessageBox.warning(self, '错误', '清空失败')

    def exportCsv(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出 CSV', 'lbj_history.csv',
                                              'CSV Files (*.csv)')
        if not path:
            return
        if self.db.exportToCsv(path):
            QMessageBox.information(self, '成功', f'已导出到 {path}')
        else:
            QMessageBox.warning(self, '错误', '导出失败')


# ===========================================================================
# 配置面板
# ===========================================================================
def default_sources(cfg: CoreConfig) -> List[Dict[str, Any]]:
    """首次运行时给出的数据源预设。"""
    base = {'sampleRate': cfg.sampleRate, 'gainDb': cfg.gainDb,
            'ppm': cfg.ppm}
    return [
        dict(base, name='本机 RTL-SDR (USB 自动)', type='rtl_usb',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='本地 rtl_tcp', type='rtl_tcp',
             host='127.0.0.1', port=1234, dcOffsetHz=50000.0),
        dict(base, name='OWRX 服务器', type='owrx',
             host='127.0.0.1', port=8073, dcOffsetHz=0.0),
    ]


SOURCE_TYPE_LABELS = [
    ('本机 USB (自动启动 rtl_tcp)', 'rtl_usb'),
    ('局域网 / 本地 RTL-TCP', 'rtl_tcp'),
    ('OWRX (OpenWebRX)', 'owrx'),
]

#: 配置分页名（与 ConfigPanel 里的 page(...) 名字一一对应）。
#: 「配置」菜单直接列这几项，点哪项就单独开哪一页，不再用页签切换。
CONFIG_PAGES = ['数据源配置', '射频设置', '到达估算', '地图与车次', '解码与界面', '外观主题']


