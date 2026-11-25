# -*- coding: utf-8 -*-
"""updater.py — 第三方数据（机车配属号段表）的自动更新。

为什么需要它：
    `shared/data/loco_roster.csv` 来自开源项目 LBJ_Console 的 `resources` 分支，
    上游会零星补录/修正号段。把这些数据钉死在安装包里，用户只能等下一个版本，
    所以做成「内置快照 + 用户可写覆盖层 + 自动检查更新」。

更新链路（只依赖标准库）：
    1. 查上游文件 sha：
       https://api.gitcode.com/api/v5/repos/CCCccc233/LBJ_Console/contents/loco_info.csv?ref=resources
       （GitCode 是 GitHub 的国内镜像，实测可达；GitHub raw 常被墙，仅作备选）
    2. 与本地 manifest 记录的 sha 比对——相同就不下载。
    3. 下载 → **严格校验**（行数/列数/号段数字/型号数量/中文配属占比）→
       校验不过直接丢弃，绝不覆盖能用的旧文件。
    4. 原子写入用户目录（`%LOCALAPPDATA%/CR-LBJ-Receiver/data/`），旧文件留 `.bak`，
       并写 `data_manifest.json`（sha / 行数 / 时间 / 来源）。

安全约定：
    * 任何失败都不抛异常，返回 `{ok: False, message: ...}`，界面只记日志。
    * 自动检查有最小间隔（默认 7 天），避免每次启动都打上游。
    * 支持 `CRLBJ_DATA_SOURCE_URL` 环境变量换成自建镜像（返回同样的 JSON 结构）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from . import loco_roster
from . import paths

# GitCode API：contents 接口一次返回 base64 内容 + 文件 sha，足够判断「是否变化」
DEFAULT_SOURCE = ('https://api.gitcode.com/api/v5/repos/CCCccc233/LBJ_Console/'
                  'contents/loco_info.csv?ref=resources')
SOURCE_LABEL = 'gitcode:CCCccc233/LBJ_Console@resources'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 CR-LBJ-Receiver/3.0')

MANIFEST_NAME = 'data_manifest.json'
ROSTER_NAME = 'loco_roster.csv'

# 校验基线（当前内置快照 16622 行 / 131 型号；留足余量，只挡「明显坏掉的文件」）
MIN_ROWS = 15000
MIN_MODELS = 120
MIN_CHINESE_DEPOT = 50

_HEADER = (
    '# 机车配属号段表 · 数据来源: LBJ_Console 项目 resources 分支 loco_info.csv\n'
    '#   https://github.com/undef-i/LBJ_Console  (GPL-3.0)  迁移说明见 shared/NOTICE.md\n'
    '# 格式: 机车型号,起号,止号,配属单位(路局/机务段),备注,制造厂\n'
    '# 匹配规则: 机车型号精确匹配 + 机车号落在 [起号,止号] 闭区间\n'
)


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def manifest_path() -> str:
    return os.path.join(paths.user_data_dir(), MANIFEST_NAME)


def read_manifest() -> Dict[str, Any]:
    try:
        with open(manifest_path(), 'r', encoding='utf-8') as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_manifest(data: Dict[str, Any]) -> None:
    paths.user_data_dir(create=True)
    tmp = manifest_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.replace(tmp, manifest_path())


def local_sha() -> str:
    """当前生效的 loco_roster.csv 的 sha256（用于判断是否已被更新过）。"""
    p = paths.data_path(ROSTER_NAME)
    if not os.path.isfile(p):
        return ''
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def _norm_sha(text: str) -> str:
    """按行归一化（去行尾空白、去末尾空行）后取 sha。

    直接比原始字节太脆：上游有没有末尾换行、行尾有没有 \\r 都会让「内容完全一样」
    的两个文件算出不同的 sha，白白多写一次盘。
    """
    norm = '\n'.join(line.rstrip() for line in text.replace('\r\n', '\n').split('\n'))
    return hashlib.sha256(norm.rstrip('\n').encode('utf-8')).hexdigest()


def local_norm_sha() -> str:
    p = paths.data_path(ROSTER_NAME)
    if not os.path.isfile(p):
        return ''
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return _norm_sha(f.read())
    except OSError:
        return ''


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
def validate_roster_text(text: str) -> Tuple[int, int, str]:
    """校验号段表文本。返回 (rows, models, error)；error 为空表示通过。"""
    if not text or len(text) < 1000:
        return 0, 0, '内容过短（可能拿到的不是 CSV）'
    rows = 0
    models = set()
    chinese_depot = 0
    bad_rows = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',')
        if len(parts) < 4:
            bad_rows += 1
            continue
        model, start, end, depot = (parts[0].strip(), parts[1].strip(),
                                    parts[2].strip(), parts[3].strip())
        a = start.lstrip('-').isdigit()
        b = end.lstrip('-').isdigit()
        if not model or not a or not b:
            bad_rows += 1
            continue
        if int(end) < int(start):
            bad_rows += 1
            continue
        rows += 1
        models.add(model.upper())
        if any('\u4e00' <= ch <= '\u9fa5' for ch in depot):
            chinese_depot += 1
    if rows < MIN_ROWS:
        return rows, len(models), '行数不足（%d < %d）' % (rows, MIN_ROWS)
    if len(models) < MIN_MODELS:
        return rows, len(models), '型号太少（%d < %d）' % (len(models), MIN_MODELS)
    if chinese_depot < MIN_CHINESE_DEPOT:
        return rows, len(models), '配属单位几乎没有中文（%d），疑似字段错位' % chinese_depot
    if bad_rows > rows * 0.02:
        return rows, len(models), '畸形行过多（%d / %d）' % (bad_rows, rows)
    return rows, len(models), ''


# --------------------------------------------------------------------------
# 远端
# --------------------------------------------------------------------------
def source_url() -> str:
    return os.environ.get('CRLBJ_DATA_SOURCE_URL', '').strip() or DEFAULT_SOURCE


def _get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', errors='replace'))


def fetch_remote(timeout: float = 20.0) -> Tuple[str, str]:
    """返回 (csv 文本, 远端 sha)。失败抛异常，由 check_and_update 兜住。"""
    d = _get_json(source_url(), timeout)
    if not isinstance(d, dict) or 'content' not in d:
        # 兼容「直接返回裸 CSV」的自建镜像
        if isinstance(d, str):
            return d, ''
        raise ValueError('上游返回结构不对（缺 content 字段）')
    content = d.get('content') or ''
    sha = str(d.get('sha') or '')
    raw = base64.b64decode(content.replace('\n', '').replace('\r', ''))
    text = raw.decode('utf-8', errors='replace')
    if not text.strip():
        # 大文件时接口可能只给下载地址
        dl = d.get('download_url') or d.get('raw_url') or ''
        if dl:
            req = urllib.request.Request(dl, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode('utf-8', errors='replace')
    return text, sha


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def _write_atomic(text: str) -> str:
    paths.user_data_dir(create=True)
    dst = os.path.join(paths.user_data_dir(), ROSTER_NAME)
    tmp = dst + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    if os.path.isfile(dst):
        try:
            os.replace(dst, dst + '.bak')
        except OSError:
            pass
    os.replace(tmp, dst)
    return dst


def _age_days(iso: str) -> Optional[float]:
    if not iso:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            then = datetime.strptime(iso[:19], fmt)
            return (datetime.now() - then).total_seconds() / 86400.0
        except ValueError:
            continue
    return None


def check_and_update(force: bool = False, interval_days: int = 7,
                     timeout: float = 20.0) -> Dict[str, Any]:
    """检查并按需更新号段表。

    返回：{ok, updated, rows, models, sha, fetchedAt, source, message, skipped}
    """
    man = read_manifest()
    entry = (man.get(ROSTER_NAME) or {}) if isinstance(man, dict) else {}
    last_check = str(man.get('lastCheck') or '')
    age = _age_days(last_check)
    out: Dict[str, Any] = {
        'ok': True, 'updated': False, 'skipped': False,
        'rows': int(entry.get('rows') or 0),
        'models': int(entry.get('models') or 0),
        'sha': str(entry.get('sha') or ''),
        'fetchedAt': str(entry.get('fetchedAt') or ''),
        'source': str(entry.get('source') or SOURCE_LABEL),
        'message': '',
    }
    if not force and age is not None and age < max(1, interval_days):
        out['skipped'] = True
        out['message'] = '上次检查于 %s（%.0f 天前），本次跳过' % (last_check[:16].replace('T', ' '), age)
        return out

    try:
        text, remote_sha = fetch_remote(timeout=timeout)
    except Exception as e:  # noqa: BLE001
        out['ok'] = False
        out['message'] = '检查更新失败：%s' % _friendly(e)
        return out

    rows, models, err = validate_roster_text(text)
    if err:
        out['ok'] = False
        out['message'] = '上游数据校验未通过（%s），已保留现有数据' % err
        return out

    local = local_sha()
    remote_text_sha = hashlib.sha256((_HEADER + text).encode('utf-8')).hexdigest()
    # 内容与当前生效文件一致（首次运行时常见：内置快照就是最新）→ 只记 sha，不写盘
    if _norm_sha(_HEADER + text) == local_norm_sha():
        out['skipped'] = True
        out['message'] = '已是最新（内容一致，%d 行 / %d 型号）' % (rows, models)
        man[ROSTER_NAME] = {
            'sha': remote_sha or remote_text_sha,
            'fetchedAt': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            'rows': rows, 'models': models, 'source': SOURCE_LABEL,
            'path': paths.data_path(ROSTER_NAME),
        }
        man['lastCheck'] = man[ROSTER_NAME]['fetchedAt']
        try:
            _write_manifest(man)
        except OSError:
            pass
        out['sha'] = man[ROSTER_NAME]['sha']
        out['fetchedAt'] = man[ROSTER_NAME]['fetchedAt']
        return out
    if remote_sha and entry.get('sha') == remote_sha:
        out['skipped'] = True
        out['message'] = '已是最新（上游 sha 未变，%d 行 / %d 型号）' % (rows, models)
        _touch_last_check(man)
        return out
    if not remote_sha and remote_text_sha == local:
        out['skipped'] = True
        out['message'] = '已是最新（无 sha 且内容一致，%d 行 / %d 型号）' % (rows, models)
        _touch_last_check(man)
        return out
    try:
        path = _write_atomic(_HEADER + text.replace('\r\n', '\n'))
    except OSError as e:
        out['ok'] = False
        out['message'] = '写入失败（%s）：%s' % (paths.user_data_dir(), e)
        return out

    fetched = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    man[ROSTER_NAME] = {
        'sha': remote_sha or remote_text_sha,
        'fetchedAt': fetched,
        'rows': rows,
        'models': models,
        'source': SOURCE_LABEL,
        'path': path,
    }
    man['lastCheck'] = fetched
    try:
        _write_manifest(man)
    except OSError:
        pass
    loco_roster.invalidate()
    out.update({'updated': True, 'rows': rows, 'models': models,
                'sha': man[ROSTER_NAME]['sha'], 'fetchedAt': fetched})
    out['message'] = '已更新配属号段表：%d 行 / %d 型号（%s）' % (rows, models, fetched[:16].replace('T', ' '))
    return out


def _touch_last_check(man: Dict[str, Any]) -> None:
    """只更新「上次检查时间」，不动数据条目。"""
    man['lastCheck'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    try:
        _write_manifest(man)
    except OSError:
        pass


def _friendly(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return 'HTTP %d' % e.code
    if isinstance(e, urllib.error.URLError):
        return '网络不可达（%s）' % (getattr(e, 'reason', '') or '')
    if isinstance(e, TimeoutError):
        return '请求超时'
    if isinstance(e, ValueError):
        return '返回内容不是合法 JSON（%s）' % e
    return str(e) or e.__class__.__name__


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------
def status() -> Dict[str, Any]:
    """给界面用的一句话状态 + 结构化数据。"""
    man = read_manifest()
    entry = (man.get(ROSTER_NAME) or {}) if isinstance(man, dict) else {}
    st = loco_roster.stats()
    info = loco_roster.source_info()
    roster_info = info.get(ROSTER_NAME) or {}
    used = roster_info.get('userOverride', False)
    fetched = str(entry.get('fetchedAt') or '')
    return {
        'available': loco_roster.available(),
        'rows': st.get('rows', 0),
        'models': st.get('models', 0),
        'emptyDepot': st.get('emptyDepot', 0),
        'sha': str(entry.get('sha') or local_sha())[:12],
        'fetchedAt': fetched,
        'lastCheck': str(man.get('lastCheck') or ''),
        'source': str(entry.get('source') or '内置快照 shared/data/loco_roster.csv'),
        'isBundled': not used,
        'path': roster_info.get('path') or paths.data_path(ROSTER_NAME),
        'userDir': paths.user_data_dir(),
        'remoteUrl': source_url(),
    }


def last_check_text() -> str:
    s = status()
    where = '内置快照' if s['isBundled'] else '已更新'
    when = s['fetchedAt'][:16].replace('T', ' ') or '—'
    return '配属表 %d 行 / %d 型号 · %s · %s' % (s['rows'], s['models'], where, when)


def next_check_due(interval_days: int = 7) -> bool:
    age = _age_days(str(read_manifest().get('lastCheck') or ''))
    return age is None or age >= max(1, interval_days)


def backup_exists() -> bool:
    return os.path.isfile(os.path.join(paths.user_data_dir(), ROSTER_NAME + '.bak'))


def restore_backup() -> Dict[str, Any]:
    """回退到更新前的版本（`.bak`）。"""
    bak = os.path.join(paths.user_data_dir(), ROSTER_NAME + '.bak')
    dst = os.path.join(paths.user_data_dir(), ROSTER_NAME)
    if not os.path.isfile(bak):
        return {'ok': False, 'message': '没有可回退的备份'}
    try:
        os.replace(bak, dst)
        loco_roster.invalidate()
        return {'ok': True, 'message': '已回退到上一版号段表'}
    except OSError as e:
        return {'ok': False, 'message': '回退失败：%s' % e}


def _now() -> float:
    return time.time()
