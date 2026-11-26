#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史数据库（SQLite）访问层。

本模块由 GUI 组装层 cr_lbj/gui.py 导入；共享运行时（Qt 类别名、主题色、
缩放、控件工厂）统一来自 cr_lbj/runtime.py。
"""
from __future__ import annotations

from cr_lbj.runtime import *  # noqa: F401,F403

class HistoryDb:
    """SQLite 历史记录数据库管理。

    保存完整的解码结果（含原始码字 rawCodewords），支持从原始数据重新解码。
    """

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        timeStr TEXT,
        train TEXT,
        baseTrain TEXT,
        prefix TEXT,
        direction TEXT,
        speed TEXT,
        position TEXT,
        loco TEXT,
        locoCode TEXT,
        route TEXT,
        category TEXT,
        latitude REAL,
        longitude REAL,
        isDetailed INTEGER,
        routeValid INTEGER,
        msgTypeError INTEGER,
        rawAddr INTEGER,
        rawFunc INTEGER,
        rawBcd TEXT,
        rawCodewords TEXT,
        rawIsShort INTEGER,
        rawIsMerged INTEGER,
        rawIsStandalone INTEGER,
        rssi REAL,
        afcHz REAL,
        afcErrHz REAL,
        afcScore REAL,
        etaSeconds REAL,
        etaTime TEXT,
        etaDistanceKm REAL,
        etaStatus TEXT,
        uid TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_time ON records(timestamp);
    CREATE INDEX IF NOT EXISTS idx_train ON records(train);
    """

    # 历史库结构版本：1 = v2.1（uid 去重）
    _SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lastMigrated = 0
        #: v3.2.9：本次启动清理掉的「解析不出车次」历史记录条数
        self.lastCleaned = 0
        self._initDb()

    def _initDb(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self._CREATE_SQL)
            # 老版本数据库迁移: 补充经纬度列
            cols = {r[1] for r in conn.execute('PRAGMA table_info(records)')}
            if 'latitude' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN latitude REAL')
            if 'longitude' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN longitude REAL')
            if 'uid' not in cols:
                conn.execute('ALTER TABLE records ADD COLUMN uid TEXT')
            conn.commit()
            ver = conn.execute('PRAGMA user_version').fetchone()[0]
            if ver < self._SCHEMA_VERSION:
                self._migrateV21(conn)
                conn.execute(f'PRAGMA user_version = {self._SCHEMA_VERSION}')
                conn.commit()
            # v3.2.9：清理历史遗留的「解析不出车次」记录（train 为空/----）。
            # 这类帧现在按上行/下行干扰统计、只记日志、不再入库，旧库里已有的也一并清掉。
            try:
                cur = conn.execute(
                    "DELETE FROM records WHERE TRIM(COALESCE(train,'')) IN ('', '----', '未知')")
                cleaned = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                if cleaned:
                    self.lastCleaned = cleaned
                conn.commit()
            except Exception:
                pass

    def _migrateV21(self, conn):
        """v2.1 迁移：为旧记录补 uid，并清理同一车次同一秒的重复行。

        旧版本会因 POCSAG 重复解码而在库里留下 2~4 条同秒记录，
        这里按“详细报文 > 有坐标 > 无 BCH 错 > RSSI 高”保留最优一条。
        """
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uid ON records(uid)")
            conn.execute(
                "UPDATE records SET uid = COALESCE(NULLIF(train,''),'NA') || '-' ||"
                " substr(COALESCE(timeStr,''),1,19) || '-' || id "
                "WHERE uid IS NULL OR uid = ''")
            before = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            conn.execute("""
                DELETE FROM records WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY COALESCE(NULLIF(train,''),'NA'),
                                         substr(COALESCE(timeStr,''),1,19)
                            ORDER BY isDetailed DESC,
                                     (latitude IS NOT NULL) DESC,
                                     msgTypeError ASC,
                                     rssi DESC,
                                     id ASC
                        ) AS rn FROM records
                    ) WHERE rn = 1
                )
            """)
            after = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            self.lastMigrated = max(0, before - after)
        except Exception:
            # 迁移失败不影响正常使用（例如老 SQLite 不支持窗口函数）
            self.lastMigrated = 0

    @staticmethod
    def _values(d: dict) -> list:
        """把解码结果字典摊平成与 SQL 列顺序一致的列表。"""
        return [
            d.get('timestamp', 0.0), d.get('timeStr', ''), d.get('train', ''),
            d.get('baseTrain', ''), d.get('prefix', ''), d.get('direction', ''),
            d.get('speed', ''), d.get('position', ''), d.get('loco', ''),
            d.get('locoCode', ''), d.get('route', ''), d.get('category', ''),
            int(d.get('isDetailed', False)), int(d.get('routeValid', False)),
            int(d.get('msgTypeError', False)), d.get('rawAddr', 0),
            d.get('rawFunc', 0), d.get('rawBcd', ''),
            json.dumps(d.get('rawCodewords', [])),
            int(d.get('rawIsShort', False)), int(d.get('rawIsMerged', False)),
            int(d.get('rawIsStandalone', False)), d.get('rssi', -140.0),
            d.get('afcHz', 0.0), d.get('afcErrHz', 0.0), d.get('afcScore', 0.0),
            d.get('etaSeconds', None), d.get('etaTime', '--:--:--'),
            d.get('etaDistanceKm', None), d.get('etaStatus', '等待信号'),
            d.get('latitude'), d.get('longitude'), d.get('uid', ''),
        ]

    _INSERT_COLS = """timestamp, timeStr, train, baseTrain, prefix, direction, speed, position,
            loco, locoCode, route, category, isDetailed, routeValid, msgTypeError,
            rawAddr, rawFunc, rawBcd, rawCodewords, rawIsShort, rawIsMerged, rawIsStandalone,
            rssi, afcHz, afcErrHz, afcScore, etaSeconds, etaTime, etaDistanceKm, etaStatus,
            latitude, longitude, uid"""

    def insert(self, d: dict) -> str:
        """写入一条解码记录。

        带 uid 且库中已存在时执行 UPDATE（同一车次窗口内被更优记录替换），
        返回 'inserted' / 'updated' / 'failed'。
        """
        uid = str(d.get('uid') or '')
        cols = [c.strip() for c in self._INSERT_COLS.replace('\n', ' ').split(',')]
        vals = self._values(d)
        try:
            with sqlite3.connect(self.db_path) as conn:
                if uid:
                    row = conn.execute('SELECT id FROM records WHERE uid = ?',
                                       (uid,)).fetchone()
                    if row:
                        sets = ', '.join(f'{c} = ?' for c in cols)
                        conn.execute(f'UPDATE records SET {sets} WHERE id = ?',
                                     vals + [row[0]])
                        return 'updated'
                marks = ','.join(['?'] * len(cols))
                conn.execute(f'INSERT INTO records ({self._INSERT_COLS}) '
                             f'VALUES ({marks})', vals)
            return 'inserted'
        except Exception:
            return 'failed'

    def queryRecent(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """查询最近的记录（含 id 供详情查询）。

        v3.2.1：多带 latitude / longitude，历史记录对话框要显示「有坐标」标记。
        """
        sql = """
        SELECT id, timeStr, train, direction, speed, position, route, loco, category,
               isDetailed, rawBcd, rawAddr, rawFunc, etaTime, etaDistanceKm,
               latitude, longitude
        FROM records ORDER BY id DESC LIMIT ?
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except Exception:
            return []

    def queryAll(self) -> List[Dict[str, Any]]:
        """查询所有记录（含原始数据）。"""
        sql = "SELECT * FROM records ORDER BY id DESC"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql)
                rows = []
                for row in cur.fetchall():
                    d = dict(row)
                    d['rawCodewords'] = json.loads(d.get('rawCodewords', '[]'))
                    d['isDetailed'] = bool(d.get('isDetailed', 0))
                    d['routeValid'] = bool(d.get('routeValid', 0))
                    d['msgTypeError'] = bool(d.get('msgTypeError', 0))
                    d['rawIsShort'] = bool(d.get('rawIsShort', 0))
                    d['rawIsMerged'] = bool(d.get('rawIsMerged', 0))
                    d['rawIsStandalone'] = bool(d.get('rawIsStandalone', 0))
                    rows.append(d)
                return rows
        except Exception:
            return []

    def count(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                return conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        except Exception:
            return 0

    def queryById(self, record_id: int) -> Optional[Dict[str, Any]]:
        """按 id 查询单条完整记录（含原始数据）。"""
        sql = "SELECT * FROM records WHERE id = ?"
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, (record_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                d = dict(row)
                d['rawCodewords'] = json.loads(d.get('rawCodewords', '[]'))
                d['isDetailed'] = bool(d.get('isDetailed', 0))
                d['routeValid'] = bool(d.get('routeValid', 0))
                d['msgTypeError'] = bool(d.get('msgTypeError', 0))
                d['rawIsShort'] = bool(d.get('rawIsShort', 0))
                d['rawIsMerged'] = bool(d.get('rawIsMerged', 0))
                d['rawIsStandalone'] = bool(d.get('rawIsStandalone', 0))
                return d
        except Exception:
            return None

    def deleteByIds(self, ids: List[int]) -> int:
        """按 id 批量删除记录，返回实际删除条数（v3.2.1 历史记录对话框用）。"""
        clean = [int(i) for i in (ids or []) if str(i).strip().isdigit()]
        if not clean:
            return 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                marks = ','.join(['?'] * len(clean))
                cur = conn.execute('DELETE FROM records WHERE id IN (%s)' % marks, clean)
                return int(cur.rowcount or 0)
        except Exception:
            return 0

    def clear(self) -> bool:
        """清空全部历史记录。

        注意 VACUUM 不能放在 DELETE 开启的事务里（Python sqlite3 默认 deferred
        隔离级别，DELETE 会隐式开事务），否则 3.14 下直接抛
        `cannot VACUUM from within a transaction`；这里先提交再单独 VACUUM，
        VACUUM 失败也不影响“已删空”这个结果。
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM records")
                conn.commit()
                try:
                    conn.execute("VACUUM")
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def exportToCsv(self, path: str) -> bool:
        """导出为 CSV（兼容旧格式）。"""
        headers = ['时间', '车次', '方向', '速度', '公里标', '机车', '线路', '类别',
                   '报文类型', '地址', '功能码', 'BCD', '信号强度', 'AFC', 'FERR', '置信度',
                   '经度', '纬度']
        try:
            rows = self.queryAll()
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([
                        r.get('timeStr', ''), r.get('train', ''), r.get('direction', ''),
                        r.get('speed', ''), r.get('position', ''), r.get('loco', ''),
                        r.get('route', ''), r.get('category', ''),
                        '详细' if r.get('isDetailed') else '短报文',
                        r.get('rawAddr', ''), r.get('rawFunc', ''), r.get('rawBcd', ''),
                        r.get('rssi', ''), r.get('afcHz', ''), r.get('afcErrHz', ''),
                        r.get('afcScore', ''),
                        r.get('longitude', ''), r.get('latitude', ''),
                    ])
            return True
        except Exception:
            return False


# ===========================================================================
# 机车详情对话框 (技术参数 + 资料来源；v2.5 起不再展示机车图片)
# ===========================================================================
