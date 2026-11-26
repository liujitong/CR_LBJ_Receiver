#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志总线与日志窗口。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class LogBus(QObject):
    """日志中枢 (v2.1)：集中保存自启动以来的全部日志。

    界面底部只显示最新一条；「帮助 → 实时日志」里看完整输出。
    保留 appendLog() 方法签名，旧的调用点无需改动。
    """

    lineAdded = Signal(str, str)   # (带时间戳的整行, 级别)
    cleared = Signal()

    def __init__(self, maxLines: int = 20000, parent=None):
        super().__init__(parent)
        self.maxLines = int(maxLines)
        self._lines: List[tuple] = []      # (时间, 消息, 级别)

    @staticmethod
    def levelOf(msg: str) -> str:
        if '[错误]' in msg or '[断连]' in msg or '[问题]' in msg or '[失败]' in msg:
            return 'err'
        if '[告警]' in msg or '[警告]' in msg or '[干扰]' in msg:
            return 'warn'
        if ('[连接]' in msg or '[启动]' in msg or '[诊断]' in msg
                or '[配置]' in msg or '[链路]' in msg):
            return 'ok'
        return 'info'

    def appendLog(self, msg: str):
        ts = datetime.now().strftime('%H:%M:%S')
        lvl = self.levelOf(msg)
        self._lines.append((ts, msg, lvl))
        if len(self._lines) > self.maxLines:
            del self._lines[:len(self._lines) - self.maxLines]
        self.lineAdded.emit(f'[{ts}] {msg}', lvl)

    # 兼容旧接口
    def append(self, msg: str):  # pragma: no cover
        self.appendLog(msg)

    def lines(self) -> List[tuple]:
        return list(self._lines)

    def latest(self):
        return self._lines[-1] if self._lines else None

    def count(self) -> int:
        return len(self._lines)

    def formatted(self, limit: int = 0) -> str:
        items = self._lines[-limit:] if limit else self._lines
        return '\n'.join(f'[{ts}] {msg}' for ts, msg, _ in items)

    def clear(self):
        self._lines.clear()
        self.cleared.emit()


# 兼容旧名字
LogPanel = LogBus


class LogWindow(QDialog):
    """实时日志窗口：显示自程序启动以来的全部日志。"""

    LEVEL_COLOR = {'err': f'{CLR("err")}', 'warn': f'{CLR("warn")}',
                   'ok': f'{CLR("ok")}', 'info': f'{CLR("text")}'}

    def __init__(self, bus: LogBus, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.setWindowTitle('实时日志 — 自启动以来的全部输出')
        self.resize(spx(900), spx(560))
        self.setSizeGripEnabled(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        bar = QHBoxLayout()
        self.countLabel = QLabel('0 行')
        self.countLabel.setStyleSheet(f'color: {CLR("dim")}; font-size: 12px;')
        self.autoScroll = QCheckBox('自动滚动到最新')
        self.autoScroll.setChecked(True)
        pauseBtn = QPushButton('暂停刷新')
        pauseBtn.setCheckable(True)
        pauseBtn.toggled.connect(self._onPause)
        clearBtn = QPushButton('清空记录')
        clearBtn.clicked.connect(self._onClear)
        saveBtn = QPushButton('另存为...')
        saveBtn.clicked.connect(self._onSave)
        closeBtn = QPushButton('关闭')
        closeBtn.clicked.connect(self.close)
        bar.addWidget(self.countLabel)
        bar.addStretch()
        bar.addWidget(self.autoScroll)
        bar.addWidget(pauseBtn)
        bar.addWidget(clearBtn)
        bar.addWidget(saveBtn)
        bar.addWidget(closeBtn)
        outer.addLayout(bar)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.NoWrap)
        outer.addWidget(self.text, 1)

        self._paused = False
        bus.lineAdded.connect(self._onLine)
        bus.cleared.connect(self._onCleared)
        self._reload()

    # ---- 内部 ----
    def _append(self, line: str, level: str):
        color = self.LEVEL_COLOR.get(level, f'{CLR("text")}')
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(
            '<span style="color:%s; white-space:pre">%s</span><br>'
            % (color, line.replace('&', '&amp;').replace('<', '&lt;')
                            .replace('>', '&gt;')))
        self.text.setTextCursor(cursor)
        if self.autoScroll.isChecked():
            self.text.ensureCursorVisible()

    def _reload(self):
        self.text.clear()
        for ts, msg, lvl in self.bus.lines()[-3000:]:
            self._append(f'[{ts}] {msg}', lvl)
        self.countLabel.setText(f'{self.bus.count()} 行')

    def _onLine(self, line: str, level: str):
        if self._paused:
            return
        self._append(line, level)
        self.countLabel.setText(f'{self.bus.count()} 行')

    def _onCleared(self):
        self.text.clear()
        self.countLabel.setText('0 行')

    def _onPause(self, on: bool):
        self._paused = on
        if not on:
            self._reload()

    def _onClear(self):
        if QMessageBox.question(self, '确认', '清空日志记录？此操作不可恢复。') \
                == QMessageBox.Yes:
            self.bus.clear()

    def _onSave(self):
        path, _ = QFileDialog.getSaveFileName(
            self, '保存日志',
            f'lbj_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt',
            'Text Files (*.txt)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.bus.formatted())
            QMessageBox.information(self, '成功', f'已保存到\n{path}')
        except Exception as e:
            QMessageBox.warning(self, '错误', f'保存失败: {e}')


# ===========================================================================
# 使用手册对话框
# ===========================================================================
