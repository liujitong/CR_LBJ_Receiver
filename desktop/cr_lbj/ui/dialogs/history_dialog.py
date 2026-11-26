#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录对话框（v3.1.1：从主界面页签移到「工具 → 历史记录…」）。

主界面只保留「当前解码」，历史记录改为按需打开的独立对话框：

* **查看列表**：时间 / 车次 / 方向 / 速度 / 公里标 / 线路 / 机车 / 类别 / 坐标；
* **查看详情**：双击行或点「查看详情」，复用 `RecordDetailDialog`（含原始数据、
  BCD、解码过程、纠错码字，以及 RailGo 车次信息）；
* **删除**：删除选中 / 删除全部，均二次确认，删完立即刷新列表与数据库计数；
* **导出 CSV**：沿用 `HistoryDb.exportToCsv()`。

数据层完全复用 `cr_lbj.data.history.HistoryDb`，不另建连接参数。
"""

from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

from cr_lbj.data.history import HistoryDb
from cr_lbj.ui.dialogs.detail_dialogs import RecordDetailDialog

#: 历史记录列表的列（v3.1.1）
HISTORY_COLUMNS = ['时间', '车次', '方向', '速度', '公里标', '线路',
                   '机车', '类别', '坐标']

#: 线路列吃剩余宽度
_HISTORY_STRETCH_COL = HISTORY_COLUMNS.index('线路')


class HistoryDialog(QDialog):
    """历史记录对话框：列表 + 详情 + 删除 + 导出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('历史记录')
        self.setMinimumSize(spx(760), spx(460))
        self.resize(spx(1040), spx(700))
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        K.paintBackground(self)

        self.db = HistoryDb(DB_PATH)
        self._rowIds: List[int] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(spx(10), spx(10), spx(10), spx(8))
        outer.setSpacing(spx(6))

        bar = QHBoxLayout()
        bar.setSpacing(spx(6))
        self.refreshBtn = K.small_button('刷新', h=28, px=12)
        self.detailBtn = K.small_button('查看详情', h=28, px=12)
        self.delBtn = K.small_button('删除选中', h=28, px=12)
        self.clearBtn = K.small_button('删除全部', h=28, px=12)
        self.exportBtn = K.small_button('导出 CSV...', h=28, px=12)
        self.countLabel = QLabel('0 条')
        self.countLabel.setStyleSheet(
            f'background: transparent; color: {CLR("faint")};')
        bar.addWidget(self.refreshBtn)
        bar.addWidget(self.detailBtn)
        bar.addWidget(self.delBtn)
        bar.addWidget(self.clearBtn)
        bar.addWidget(self.exportBtn)
        bar.addStretch()
        bar.addWidget(self.countLabel)
        outer.addLayout(bar)

        self.table = QTableWidget(0, len(HISTORY_COLUMNS))
        self.table.setHorizontalHeaderLabels(HISTORY_COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_HISTORY_STRETCH_COL, QHeaderView.Stretch)
        outer.addWidget(self.table, 1)

        btnRow = QHBoxLayout()
        btnRow.addStretch()
        closeBtn = K.button('关闭', primary=True)
        closeBtn.clicked.connect(self.accept)
        btnRow.addWidget(closeBtn)
        outer.addLayout(btnRow)

        self.refreshBtn.clicked.connect(self.loadFromDb)
        self.detailBtn.clicked.connect(self.viewDetail)
        self.delBtn.clicked.connect(self.deleteSelected)
        self.clearBtn.clicked.connect(self.deleteAll)
        self.exportBtn.clicked.connect(self.exportCsv)
        self.table.doubleClicked.connect(self._onDoubleClicked)
        self.table.itemSelectionChanged.connect(self._updateButtons)

        self.loadFromDb()

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------
    def loadFromDb(self):
        """从 SQLite 重新加载历史记录（删除/刷新后调用）。"""
        self.table.setRowCount(0)
        self._rowIds = []
        try:
            rows = self.db.queryRecent(MAX_HISTORY_ROWS_UI)
            for r in rows:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._rowIds.append(int(r.get('id') or 0))
                has_coord = (isinstance(r.get('latitude'), (int, float))
                             and isinstance(r.get('longitude'), (int, float)))
                values = [
                    str(r.get('timeStr') or '--:--:--'),
                    str(r.get('train') or '----'),
                    str(r.get('direction') or '未知'),
                    str(r.get('speed') or '---'),
                    str(r.get('position') or '---.-'),
                    str(r.get('route') or '----'),
                    str(r.get('loco') or '----'),
                    str(r.get('category') or '未知'),
                    '有' if has_coord else '—',
                ]
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    if col == 1:
                        f = item.font()
                        f.setBold(True)
                        item.setFont(f)
                    elif col == 2:
                        if text == '下行':
                            item.setForeground(QColor(CLR('ok')))
                        elif text == '上行':
                            item.setForeground(QColor(CLR('accent2')))
                    elif col == 8 and has_coord:
                        item.setForeground(QColor(CLR('ok')))
                    self.table.setItem(row, col, item)
            total = self.db.count()
            self.countLabel.setText(
                '%d 条 / 共 %d 条（最多显示 %d 条）'
                % (self.table.rowCount(), total, MAX_HISTORY_ROWS_UI))
        except Exception as e:
            QMessageBox.warning(self, '错误', f'读取数据库失败: {e}')
        self._updateButtons()

    def _updateButtons(self):
        has_sel = bool(self.table.selectionModel().selectedRows())
        self.detailBtn.setEnabled(has_sel)
        self.delBtn.setEnabled(has_sel)
        self.clearBtn.setEnabled(self.table.rowCount() > 0)

    def _selectedIds(self) -> List[int]:
        """表格选中行 → 数据库 id（倒序表与 _rowIds 一一对应）。"""
        ids = []
        try:
            for index in self.table.selectionModel().selectedRows():
                row = index.row()
                if 0 <= row < len(self._rowIds):
                    ids.append(self._rowIds[row])
        except Exception:
            pass
        return ids

    def _currentRecord(self) -> Optional[dict]:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rowIds):
            return None
        return self.db.queryById(self._rowIds[row])

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def _onDoubleClicked(self, _index):
        self.viewDetail()

    def viewDetail(self):
        record = self._currentRecord()
        if record is None and self._selectedIds():
            record = self.db.queryById(self._selectedIds()[0])
        if record is None:
            QMessageBox.information(self, '提示', '请先选择一条历史记录。')
            return
        dlg = RecordDetailDialog(record, self)
        dlg.exec()

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------
    def deleteSelected(self):
        ids = self._selectedIds()
        if not ids:
            QMessageBox.information(self, '提示', '请先选择要删除的记录。')
            return
        ret = QMessageBox.question(
            self, '确认删除',
            '确定删除选中的 %d 条历史记录吗？\n\n此操作不可恢复。' % len(ids),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        n = self.db.deleteByIds(ids)
        self.loadFromDb()
        if n <= 0:
            QMessageBox.warning(self, '删除失败', '数据库没有删除任何记录，请重试。')

    def deleteAll(self):
        total = self.db.count()
        if total <= 0:
            QMessageBox.information(self, '提示', '历史数据库已经是空的。')
            return
        ret = QMessageBox.question(
            self, '确认删除全部',
            '确定删除全部 %d 条历史记录吗？\n\n此操作不可恢复，建议先「导出 CSV」。'
            % total,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        if self.db.clear():
            self.loadFromDb()
        else:
            QMessageBox.warning(self, '删除失败', '清空数据库失败，请检查文件占用。')

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def exportCsv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, '导出 CSV', 'lbj_history.csv', 'CSV Files (*.csv)')
        if not path:
            return
        if self.db.exportToCsv(path):
            QMessageBox.information(self, '成功', f'已导出到 {path}')
        else:
            QMessageBox.warning(self, '错误', '导出失败')